from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple, Union
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
    server_name: Optional[str] = None
    t_service_end: Optional[float] = None
    t_refuse: Optional[float] = None


# ---------------- КАНАЛ ----------------

@dataclass
class ServerState:
    id: int
    name: str          # например "Специалист #1"
    op_type: str       # например "Специалист"
    mu: float          # заявок/час
    busy: bool = False
    busy_since: Optional[float] = None
    busy_time: float = 0.0  # занятость, накопленная НА ИНТЕРВАЛЕ [0, time_end]


# ---------------- РЕЗУЛЬТАТ ----------------

@dataclass
class SimulationResult:
    requests: List[RequestRecord]
    server_utilization: Dict[int, float]  # server_id -> utilization [0..1]
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
            self._dq = deque(s.id for s in servers)  # все свободны в начале
        elif mode == "fastest":
            self._heap: List[Tuple[float, int, int]] = []
            self._seq = 0
            for s in servers:
                heapq.heappush(self._heap, (-s.mu, self._seq, s.id))  # max mu first
                self._seq += 1
        else:
            raise ValueError(f"Unknown pool mode: {mode}")

    def has_free(self) -> bool:
        return bool(self._dq) if self.mode == "round_robin" else bool(self._heap)

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


# ---------------- КОНСТРУКТОРЫ СЕРВЕРОВ ИЗ КОНФИГА ----------------

def build_servers(operators: List[Dict[str, Any]]) -> List[ServerState]:
    """
    operators: [
      {"type": "...", "mu": 6, "count": 2},
      ...
    ]
    """
    servers: List[ServerState] = []
    sid = 0
    for op in operators:
        op_type = str(op["type"])
        mu = float(op["mu"])
        count = int(op.get("count", 1))
        for k in range(count):
            servers.append(ServerState(
                id=sid,
                name=f"{op_type} #{k + 1}",
                op_type=op_type,
                mu=mu,
            ))
            sid += 1
    return servers


# ---------------- НОРМАЛИЗАЦИЯ КОНФИГА ----------------

def _normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Поддерживает 2 формата:
    1) "UI-конфиг" (как у вас):
       {
         "call_flow": 30,
         "queue_size": 5,
         "duration": 1,
         "operators": [{"type": "...", "mu": 6, "count": 1}, ...]
       }

    2) "Engine-конфиг":
       {
         "arrival_rate": 30,
         "queue_capacity": 5,
         "time_end": 1,
         "operators": [...],  # или "servers": [ServerState,...]
         ...
       }
    """
    # arrival_rate
    if "arrival_rate" in config:
        lam = float(config["arrival_rate"])
    elif "call_flow" in config:
        lam = float(config["call_flow"])
    else:
        raise ValueError("Нет arrival_rate/call_flow в конфиге")

    # queue_capacity
    if "queue_capacity" in config:
        queue_capacity = int(config["queue_capacity"])
    elif "queue_size" in config:
        queue_capacity = int(config["queue_size"])
    else:
        raise ValueError("Нет queue_capacity/queue_size в конфиге")

    # time_end
    if "time_end" in config:
        time_end = float(config["time_end"])
    elif "duration" in config:
        time_end = float(config["duration"])
    else:
        raise ValueError("Нет time_end/duration в конфиге")

    # servers
    servers: Optional[List[ServerState]] = None
    if "servers" in config and config["servers"] is not None:
        servers = config["servers"]
        if not isinstance(servers, list) or (servers and not isinstance(servers[0], ServerState)):
            raise ValueError('"servers" должен быть List[ServerState]')
    elif "operators" in config and config["operators"] is not None:
        servers = build_servers(config["operators"])
    elif "service_rates" in config and config["service_rates"] is not None:
        # запасной вариант: просто mu-список
        mus = [float(x) for x in config["service_rates"]]
        servers = [
            ServerState(id=i, name=f"Server #{i+1}", op_type="Server", mu=mus[i])
            for i in range(len(mus))
        ]
    else:
        raise ValueError('Нужно передать "operators" или "servers" (или хотя бы "service_rates").')

    # прочие параметры
    seed = config.get("seed", None)
    drain = bool(config.get("drain", True))
    start_at_zero = bool(config.get("start_at_zero", True))
    policy = str(config.get("free_server_policy", "round_robin"))
    max_arrivals = config.get("max_arrivals", None)
    if max_arrivals is not None:
        max_arrivals = int(max_arrivals)

    return {
        "lam": lam,
        "queue_capacity": queue_capacity,
        "time_end": time_end,
        "servers": servers,
        "seed": seed,
        "drain": drain,
        "start_at_zero": start_at_zero,
        "policy": policy,
        "max_arrivals": max_arrivals,
    }


# ---------------- СИМУЛЯТОР ----------------

SERVICE_END_PRIORITY = 0
ARRIVAL_PRIORITY = 1

def simulate(config: Dict[str, Any]) -> SimulationResult:
    """
    Дискретно-событийная симуляция СМО с:
    - экспоненциальными межприходами: -ln(U)/lambda
    - экспоненциальным обслуживанием: -ln(U)/mu для каждого сервера
    - ограниченной общей очередью ожидания
    - политикой распределения свободных серверов: round_robin / fastest

    Важно: server_utilization считается на интервале [0, time_end]
    (даже если drain=True и дообслуживание уходит дальше time_end).
    """
    cfg = _normalize_config(config)

    lam: float = float(cfg["lam"])
    queue_capacity: int = int(cfg["queue_capacity"])
    time_end: float = float(cfg["time_end"])
    servers: List[ServerState] = cfg["servers"]

    seed = cfg["seed"]
    drain: bool = bool(cfg["drain"])
    start_at_zero: bool = bool(cfg["start_at_zero"])
    policy: str = str(cfg["policy"])
    max_arrivals: Optional[int] = cfg["max_arrivals"]

    if lam <= 0:
        raise ValueError("arrival_rate (lambda) должен быть > 0")
    if not servers:
        raise ValueError("Список servers пуст")
    if any(s.mu <= 0 for s in servers):
        raise ValueError("У всех серверов mu должен быть > 0")
    if queue_capacity < 0:
        raise ValueError("queue_capacity должен быть >= 0")
    if time_end <= 0:
        raise ValueError("time_end/duration должен быть > 0")

    rng = random.Random(seed)

    def exp_time(rate: float) -> float:
        # -ln(U)/rate, U in (0,1]
        u = 1.0 - rng.random()  # (0, 1]
        return -math.log(u) / rate

    # Пул свободных серверов
    free_pool = FreeServerPool(servers, mode=policy)

    # Очередь ожидания (общая)
    q = deque()  # request_id

    # Логи заявок
    requests: List[RequestRecord] = []

    # События: (t, priority, seq, kind, payload)
    # kind: "ARRIVAL" | "SERVICE_END"
    event_heap: List[Tuple[float, int, int, str, Any]] = []
    seq = 0

    def push_event(t: float, kind: str, payload: Any) -> None:
        nonlocal seq
        pr = SERVICE_END_PRIORITY if kind == "SERVICE_END" else ARRIVAL_PRIORITY
        heapq.heappush(event_heap, (t, pr, seq, kind, payload))
        seq += 1

    def _add_busy_overlap(s: ServerState, t_start: float, t_end: float) -> None:
        """
        Добавляет к s.busy_time только пересечение [t_start, t_end] с [0, time_end].
        Это нужно, чтобы утилизация считалась именно на горизонте генерации заявок.
        """
        a = max(0.0, t_start)
        b = min(time_end, t_end)
        if b > a:
            s.busy_time += (b - a)

    def start_service(t: float, server_id: int, req_id: int) -> None:
        s = servers[server_id]
        r = requests[req_id]

        s.busy = True
        s.busy_since = t

        r.t_service_start = t
        r.server_id = server_id
        r.server_name = s.name

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

        # Если есть свободный сервер — сразу в работу
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

        # Планируем следующий arrival (только до time_end)
        t_next = t + exp_time(lam)
        if t_next <= time_end:
            push_event(t_next, "ARRIVAL", None)

    def handle_service_end(t: float, server_id: int, req_id: int) -> None:
        s = servers[server_id]
        r = requests[req_id]

        r.t_service_end = t

        # учёт занятости (только на [0, time_end])
        if s.busy_since is not None:
            _add_busy_overlap(s, s.busy_since, t)

        s.busy = False
        s.busy_since = None

        # если есть очередь — сервер сразу берёт следующую
        if q:
            next_id = q.popleft()
            start_service(t, server_id, next_id)
        else:
            # сервер становится свободным и попадает в пул
            free_pool.add(server_id)

    # Стартовое событие
    if start_at_zero:
        push_event(0.0, "ARRIVAL", None)
    else:
        push_event(exp_time(lam), "ARRIVAL", None)

    current_time = 0.0

    while event_heap:
        t, _, _, kind, payload = heapq.heappop(event_heap)

        # Если drain=False — жёстко режем всё, что после time_end
        if (not drain) and (t > time_end):
            break

        current_time = t

        if kind == "ARRIVAL":
            if t <= time_end:
                handle_arrival(t)
        else:  # SERVICE_END
            sid, rid = payload
            handle_service_end(t, sid, rid)

    # утилизация каналов (на горизонте [0, time_end])
    horizon = time_end
    server_util = {s.id: (s.busy_time / horizon) for s in servers}

    total = len(requests)
    refused = sum(1 for r in requests if r.t_refuse is not None)
    served = sum(1 for r in requests if r.t_service_end is not None)

    waits: List[float] = []
    sys_times: List[float] = []

    for r in requests:
        if r.t_service_start is not None:
            waits.append(0.0 if r.t_queue_enter is None else (r.t_service_start - r.t_queue_enter))
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
    # Ваш UI-конфиг:
    ui_cfg = {
        "call_flow": 30,
        "queue_size": 5,
        "duration": 1,
        "operators": [
            {"type": "Специалист", "mu": 6, "count": 1},
            {"type": "Ведущий специалист", "mu": 7, "count": 1},
            {"type": "Эксперт", "mu": 8, "count": 1},
        ],
        "free_server_policy": "round_robin",  # или "fastest"
        "seed": 1,
        "drain": True,
        "start_at_zero": True,
    }

    res = simulate(ui_cfg)
    print("stats:", res.stats)
    print("util:", res.server_utilization)
    print("first 3:", res.requests[:3])
