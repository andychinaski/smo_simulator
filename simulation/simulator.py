from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from collections import deque
import heapq
import random
import math


# ---------------- ЛОГ ЗАЯВКИ ----------------

@dataclass
class RequestRecord:
    id: int
    t_arrival: float
    t_queue_enter: Optional[float] = None
    t_service_start: Optional[float] = None
    server_id: Optional[int] = None
    t_service_end: Optional[float] = None
    t_refuse: Optional[float] = None


# ---------------- КАНАЛ ----------------

@dataclass
class ServerState:
    id: int
    mu: float  # заявок/час
    busy: bool = False
    busy_since: Optional[float] = None
    busy_time: float = 0.0


# ---------------- РЕЗУЛЬТАТ ----------------

@dataclass
class SimulationResult:
    requests: List[RequestRecord]
    server_utilization: Dict[int, float]
    stats: Dict[str, float]


# ---------------- ПУЛ СВОБОДНЫХ СЕРВЕРОВ ----------------

class FreeServerPool:
    """
    mode:
      - "round_robin": очередь свободных серверов (deque)
      - "fastest": всегда выбирать самый быстрый mu среди свободных (heap)
    """
    def __init__(self, servers: List[ServerState], mode: str = "round_robin"):
        self.mode = mode
        self.servers = servers

        if mode == "round_robin":
            self._dq = deque(s.id for s in servers)   # все свободны в начале
        elif mode == "fastest":
            self._heap = []
            self._seq = 0
            for s in servers:
                # (-mu) чтобы max mu был сверху
                heapq.heappush(self._heap, (-s.mu, self._seq, s.id))
                self._seq += 1
        else:
            raise ValueError(f"Unknown pool mode: {mode}")

    def has_free(self) -> bool:
        if self.mode == "round_robin":
            return bool(self._dq)
        return bool(self._heap)

    def pop(self) -> int:
        if self.mode == "round_robin":
            return self._dq.popleft()
        _, _, sid = heapq.heappop(self._heap)
        return sid

    def add(self, server_id: int) -> None:
        # Добавляем в пул, когда сервер освобождается И очереди ожидания нет
        if self.mode == "round_robin":
            self._dq.append(server_id)
        else:
            s = self.servers[server_id]
            heapq.heappush(self._heap, (-s.mu, self._seq, server_id))
            self._seq += 1


# ---------------- СИМУЛЯТОР ----------------

SERVICE_END_PRIORITY = 0
ARRIVAL_PRIORITY = 1

def simulate(config: Dict[str, Any]) -> SimulationResult:
    """
    config:
      arrival_rate: float (lambda, заявок/час)
      service_rates: list[float] (mu_i, заявок/час)
      queue_capacity: int
      time_end: float (часов)
      seed: int|None (опционально)
      drain: bool (опционально, по умолчанию True)
      start_at_zero: bool (опционально, по умолчанию True)
      free_server_policy: "round_robin" | "fastest" (опционально)
      max_arrivals: int|None (опционально)
    """
    lam = float(config["arrival_rate"])
    mus = [float(x) for x in config["service_rates"]]
    queue_capacity = int(config["queue_capacity"])
    time_end = float(config["time_end"])

    seed = config.get("seed", None)
    drain = bool(config.get("drain", True))
    start_at_zero = bool(config.get("start_at_zero", True))
    policy = str(config.get("free_server_policy", "round_robin"))
    max_arrivals = config.get("max_arrivals", None)
    if max_arrivals is not None:
        max_arrivals = int(max_arrivals)

    if lam <= 0:
        raise ValueError("arrival_rate (lambda) должен быть > 0")
    if any(mu <= 0 for mu in mus):
        raise ValueError("Все service_rates (mu) должны быть > 0")
    if queue_capacity < 0:
        raise ValueError("queue_capacity должен быть >= 0")

    rng = random.Random(seed)

    def exp_time(rate: float) -> float:
        # -ln(U)/rate, U in (0,1]
        u = 1.0 - rng.random()
        return -math.log(u) / rate

    # Состояние
    servers: List[ServerState] = [ServerState(id=i, mu=mus[i]) for i in range(len(mus))]
    free_pool = FreeServerPool(servers, mode=policy)

    q = deque()  # очередь ожидания: request_id
    requests: List[RequestRecord] = []

    # События: (t, priority, seq, kind, payload)
    event_heap: List[Tuple[float, int, int, str, Any]] = []
    seq = 0

    def push_event(t: float, kind: str, payload: Any) -> None:
        nonlocal seq
        pr = SERVICE_END_PRIORITY if kind == "SERVICE_END" else ARRIVAL_PRIORITY
        heapq.heappush(event_heap, (t, pr, seq, kind, payload))
        seq += 1

    def start_service(t: float, server_id: int, req_id: int) -> None:
        s = servers[server_id]
        r = requests[req_id]

        s.busy = True
        s.busy_since = t

        r.t_service_start = t
        r.server_id = server_id

        dt = exp_time(s.mu)
        push_event(t + dt, "SERVICE_END", (server_id, req_id))

    arrivals_count = 0

    def handle_arrival(t: float) -> None:
        nonlocal arrivals_count

        if max_arrivals is not None and arrivals_count >= max_arrivals:
            return

        req_id = len(requests)
        requests.append(RequestRecord(id=req_id, t_arrival=t))
        arrivals_count += 1

        # если есть свободный сервер — сразу в работу
        if free_pool.has_free():
            sid = free_pool.pop()
            start_service(t, sid, req_id)
        else:
            # иначе очередь/отказ
            if len(q) < queue_capacity:
                requests[req_id].t_queue_enter = t
                q.append(req_id)
            else:
                requests[req_id].t_refuse = t

        # планируем следующий arrival (только до time_end)
        t_next = t + exp_time(lam)
        if t_next <= time_end:
            push_event(t_next, "ARRIVAL", None)

    def handle_service_end(t: float, server_id: int, req_id: int) -> None:
        s = servers[server_id]
        r = requests[req_id]

        r.t_service_end = t

        # обновляем занятость
        if s.busy_since is not None:
            s.busy_time += t - s.busy_since

        s.busy = False
        s.busy_since = None

        # если есть очередь — сервер сразу берёт следующую
        if q:
            next_id = q.popleft()
            start_service(t, server_id, next_id)
        else:
            # сервер становится свободным и попадает в пул (конец очереди или в heap)
            free_pool.add(server_id)

    # старт
    if start_at_zero:
        push_event(0.0, "ARRIVAL", None)
    else:
        push_event(exp_time(lam), "ARRIVAL", None)

    current_time = 0.0

    while event_heap:
        t, _, _, kind, payload = heapq.heappop(event_heap)

        if (not drain) and (t > time_end):
            break

        current_time = t

        if kind == "ARRIVAL":
            if t <= time_end:
                handle_arrival(t)
        else:  # SERVICE_END
            sid, rid = payload
            handle_service_end(t, sid, rid)

    # утилизация каналов (по горизонту генерации заявок)
    horizon = time_end if time_end > 0 else 1.0
    server_util = {s.id: min(1.0, s.busy_time / horizon) for s in servers}

    total = len(requests)
    refused = sum(1 for r in requests if r.t_refuse is not None)
    served = sum(1 for r in requests if r.t_service_end is not None)

    waits = []
    sys_times = []
    for r in requests:
        if r.t_service_start is not None:
            if r.t_queue_enter is None:
                waits.append(0.0)
            else:
                waits.append(r.t_service_start - r.t_queue_enter)
        if r.t_service_end is not None:
            sys_times.append(r.t_service_end - r.t_arrival)

    stats = {
        "total_arrivals": float(total),
        "served": float(served),
        "refused": float(refused),
        "refuse_rate": (refused / total) if total else 0.0,
        "avg_wait": (sum(waits) / len(waits)) if waits else 0.0,
        "avg_system_time": (sum(sys_times) / len(sys_times)) if sys_times else 0.0,
        "time_end": float(time_end),
        "last_event_time": float(current_time),
    }

    return SimulationResult(
        requests=requests,
        server_utilization=server_util,
        stats=stats
    )


# ---- пример ----
if __name__ == "__main__":
    cfg = {
        "arrival_rate": 20.0,
        "service_rates": [4.0, 5.0],
        "queue_capacity": 5,
        "time_end": 8.0,
        "free_server_policy": "round_robin",  # или "fastest"
        "seed": 1,
        "drain": True,
    }
    res = simulate(cfg)
    print(res.stats)
    print(res.server_utilization)
    print(res.requests[:3])