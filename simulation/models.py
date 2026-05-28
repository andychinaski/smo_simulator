from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class QueueSlotEntry:
    """Запись о пребывании заявки в конкретном слоте очереди"""
    slot: int
    t_enter: float
    t_leave: Optional[float] = None


@dataclass
class RequestRecord:
    id: int
    t_arrival: float
    arrival_rng: Optional[float] = None
    t_queue_enter: Optional[float] = None
    t_service_start: Optional[float] = None
    service_rng: Optional[float] = None
    server_id: Optional[int] = None
    server_name: Optional[str] = None
    t_service_end: Optional[float] = None
    t_refuse: Optional[float] = None
    queue_history: List[QueueSlotEntry] = field(default_factory=list)


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
    stats: Dict[str, float]
