from __future__ import annotations

from typing import Any, Literal, Tuple

EventKind = Literal["ARRIVAL", "SERVICE_END"]
PoolMode = Literal["round_robin", "fastest"]

# (t, priority, seq, kind, payload)
Event = Tuple[float, int, int, EventKind, Any]