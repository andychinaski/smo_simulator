from __future__ import annotations

from dataclasses import replace
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple
import heapq

from .models import ServerState
from .types import PoolMode


class FreeServerPool:
    """
    mode:
      - "round_robin": очередь свободных серверов (deque)
      - "fastest": выбирать самый быстрый (max mu) среди свободных (heap)

    Важно: пул НЕ полагается на то, что server.id == индекс в списке servers.
    """
    def __init__(self, servers: List[ServerState], mode: PoolMode = "round_robin"):
        self.mode: PoolMode = mode
        self._mu_by_id: Dict[int, float] = {s.id: float(s.mu) for s in servers}

        if mode == "round_robin":
            self._dq: Deque[int] = deque(s.id for s in servers)
            self._heap: Optional[List[Tuple[float, int, int]]] = None
            self._seq = 0
        elif mode == "fastest":
            self._dq = None  # type: ignore[assignment]
            self._heap = []
            self._seq = 0
            for s in servers:
                heapq.heappush(self._heap, (-float(s.mu), self._seq, s.id))
                self._seq += 1
        else:
            raise ValueError(f"Unknown pool mode: {mode}")

    def has_free(self) -> bool:
        return bool(self._dq) if self.mode == "round_robin" else bool(self._heap)

    def pop(self) -> int:
        if self.mode == "round_robin":
            assert self._dq is not None
            return self._dq.popleft()

        assert self._heap is not None
        _, _, sid = heapq.heappop(self._heap)
        return sid

    def add(self, server_id: int) -> None:
        """Добавляем в пул, когда сервер освобождается и очереди ожидания нет."""
        if self.mode == "round_robin":
            assert self._dq is not None
            self._dq.append(server_id)
            return

        assert self._heap is not None
        mu = self._mu_by_id.get(server_id)
        if mu is None:
            return
        heapq.heappush(self._heap, (-mu, self._seq, server_id))
        self._seq += 1


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


def prepare_servers(servers: List[ServerState]) -> Tuple[List[ServerState], Dict[int, ServerState]]:
    """
    Если в config передали "servers" (готовые ServerState),
    нельзя мутировать их между запусками симуляции.
    Поэтому делаем копии и сбрасываем runtime-поля.
    """
    clean: List[ServerState] = [replace(s, busy=False, busy_since=None, busy_time=0.0) for s in servers]
    by_id: Dict[int, ServerState] = {s.id: s for s in clean}

    if len(by_id) != len(clean):
        raise ValueError("server.id должны быть уникальны")

    return clean, by_id