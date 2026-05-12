from __future__ import annotations

# Совместимость: оставляем прежний модуль simulation.simulator
# и прежние имена моделей.

from .engine import simulate
from .models import RequestRecord, ServerState, SimulationResult

__all__ = ["simulate", "RequestRecord", "ServerState", "SimulationResult"]