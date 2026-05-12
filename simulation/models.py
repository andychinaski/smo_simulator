from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict


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


@dataclass
class ServerState:
    id: int
    name: str          # например "Специалист #1"
    op_type: str       # например "Специалист"
    mu: float          # заявок/час
    busy: bool = False
    busy_since: Optional[float] = None
    busy_time: float = 0.0  # занятость, накопленная НА ИНТЕРВАЛЕ [0, time_end]


@dataclass
class SimulationResult:
    requests: List[RequestRecord]
    server_utilization: Dict[int, float]  # server_id -> utilization [0..1]
    stats: Dict[str, float]