from __future__ import annotations

import heapq
from typing import Any, Dict, List, Tuple

from .formatting import to_float, to_int


def expand_server_names_from_config(config: Dict[str, Any]) -> List[str]:
    ops = config.get("operators") or []
    if not isinstance(ops, list):
        return []

    names: List[str] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        op_type = str(op.get("type", "Канал"))
        count = to_int(op.get("count", 1), 1)
        for k in range(max(0, count)):
            names.append(f"{op_type} #{k + 1}")
    return names


def assign_queue_slots(
    requests: List[Dict[str, Any]],
    queue_size: int,
    t_fallback_end: float,
) -> List[Tuple[int, int, float, float]]:
    if queue_size <= 0:
        return []

    events: List[Tuple[float, int, int]] = []
    # (time, priority, req_id) where priority: LEAVE=0, ENTER=1
    for r in requests:
        rid = to_int(r.get("id", 0), 0)
        t_enter = to_float(r.get("t_queue_enter"))
        t_leave = to_float(r.get("t_service_start")) if t_enter is not None else None
        if t_enter is not None:
            events.append((t_enter, 1, rid))
        if t_leave is not None:
            events.append((t_leave, 0, rid))

    events.sort(key=lambda x: (x[0], x[1]))

    free_slots = list(range(1, queue_size + 1))
    heapq.heapify(free_slots)

    req_to_slot: Dict[int, int] = {}
    req_to_start: Dict[int, float] = {}
    segments: List[Tuple[int, int, float, float]] = []

    id_to_req = {to_int(r.get("id", 0), 0): r for r in requests}

    for t, pr, rid in events:
        req = id_to_req.get(rid, {})
        t_enter = to_float(req.get("t_queue_enter"))

        if pr == 0:
            if rid in req_to_slot:
                slot = req_to_slot.pop(rid)
                t0 = req_to_start.pop(rid)
                segments.append((slot, rid, t0, t))
                heapq.heappush(free_slots, slot)
        else:
            if t_enter is None:
                continue
            if rid in req_to_slot:
                continue
            if free_slots:
                slot = heapq.heappop(free_slots)
                req_to_slot[rid] = slot
                req_to_start[rid] = t_enter

    for rid, slot in req_to_slot.items():
        t0 = req_to_start.get(rid)
        if t0 is None:
            continue
        segments.append((slot, rid, t0, t_fallback_end))

    segments.sort(key=lambda x: (x[0], x[2], x[3]))
    return segments