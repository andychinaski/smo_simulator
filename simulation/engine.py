from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from collections import deque
import heapq
import random
import math

from .config import normalize_config
from .constants import ARRIVAL_PRIORITY, SERVICE_END_PRIORITY
from .models import RequestRecord, SimulationResult
from .servers import FreeServerPool, prepare_servers
from .types import Event, EventKind


def simulate(config: Dict[str, Any]) -> SimulationResult:
    """
    Дискретно-событийная симуляция СМО:
    - экспоненциальные межприходы: -ln(U)/lambda
    - экспоненциальное обслуживание: -ln(U)/mu
    - ограниченная общая очередь ожидания
    - политика свободных серверов: round_robin / fastest

    Важно: server_utilization считается на интервале [0, time_end]
    (даже если drain=True и дообслуживание уходит дальше time_end).
    """
    cfg = normalize_config(config)

    lam = float(cfg.lam)
    queue_capacity = int(cfg.queue_capacity)
    time_end = float(cfg.time_end)

    servers_list, servers_by_id = prepare_servers(cfg.servers)

    rng = random.Random(cfg.seed)

    def exp_time(rate: float) -> float:
        u = 1.0 - rng.random()  # (0, 1]
        return -math.log(u) / rate

    def add_busy_overlap(server_id: int, t_start: float, t_end: float) -> None:
        """
        Добавляет к busy_time пересечение [t_start, t_end] с [0, time_end].
        """
        a = max(0.0, t_start)
        b = min(time_end, t_end)
        if b > a:
            servers_by_id[server_id].busy_time += (b - a)

    free_pool = FreeServerPool(servers_list, mode=cfg.policy)
    q = deque()  # request_id
    requests: List[RequestRecord] = []

    event_heap: List[Event] = []
    seq = 0

    def push_event(t: float, kind: EventKind, payload: Any) -> None:
        nonlocal seq
        pr = SERVICE_END_PRIORITY if kind == "SERVICE_END" else ARRIVAL_PRIORITY
        heapq.heappush(event_heap, (t, pr, seq, kind, payload))
        seq += 1

    def start_service(t: float, server_id: int, req_id: int) -> None:
        s = servers_by_id[server_id]
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

        if cfg.max_arrivals is not None and arrivals_count >= cfg.max_arrivals:
            return

        req_id = len(requests)
        requests.append(RequestRecord(id=req_id, t_arrival=t))
        arrivals_count += 1

        if free_pool.has_free():
            sid = free_pool.pop()
            start_service(t, sid, req_id)
        else:
            if len(q) < queue_capacity:
                requests[req_id].t_queue_enter = t
                q.append(req_id)
            else:
                requests[req_id].t_refuse = t

        # следующий arrival только до time_end
        t_next = t + exp_time(lam)
        if t_next <= time_end:
            push_event(t_next, "ARRIVAL", None)

    def handle_service_end(t: float, server_id: int, req_id: int) -> None:
        s = servers_by_id[server_id]
        r = requests[req_id]

        r.t_service_end = t

        if s.busy_since is not None:
            add_busy_overlap(server_id, s.busy_since, t)

        s.busy = False
        s.busy_since = None

        if q:
            next_id = q.popleft()
            start_service(t, server_id, next_id)
        else:
            free_pool.add(server_id)

    # стартовое событие
    if cfg.start_at_zero:
        push_event(0.0, "ARRIVAL", None)
    else:
        push_event(exp_time(lam), "ARRIVAL", None)

    current_time = 0.0

    while event_heap:
        t, _, _, kind, payload = heapq.heappop(event_heap)

        # drain=False: режем всё после time_end
        if (not cfg.drain) and (t > time_end):
            break

        current_time = t

        if kind == "ARRIVAL":
            if t <= time_end:
                handle_arrival(t)
        else:
            sid, rid = payload
            handle_service_end(t, sid, rid)

    horizon = time_end
    server_util = {s.id: (s.busy_time / horizon) for s in servers_list}

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
        "refused": float(refused)
    }

    return SimulationResult(
        requests=requests,
        server_utilization=server_util,
        stats=stats,
    )