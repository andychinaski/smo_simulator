from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .models import ServerState
from .servers import build_servers
from .types import PoolMode


@dataclass(frozen=True)
class NormalizedConfig:
    lam: float
    queue_capacity: int
    time_end: float
    servers: List[ServerState]
    seed: Any
    drain: bool
    start_at_zero: bool
    policy: PoolMode
    max_arrivals: Optional[int]


def _as_bool(x: Any, default: bool) -> bool:
    if x is None:
        return default
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true", "yes", "y", "1", "да"):
            return True
        if s in ("false", "no", "n", "0", "нет"):
            return False
    return default


def normalize_config(config: Dict[str, Any]) -> NormalizedConfig:
    """
    Поддерживает 2 формата:
    1) UI-конфиг:
       {
         "call_flow": 30,
         "queue_size": 5,
         "duration": 1,
         "operators": [{"type": "...", "mu": 6, "count": 1}, ...]
       }

    2) Engine-конфиг:
       {
         "arrival_rate": 30,
         "queue_capacity": 5,
         "time_end": 1,
         "operators": [...],  # или "servers": [ServerState,...]
         ...
       }
    """
    if not isinstance(config, dict):
        raise ValueError("config должен быть dict")

    # lambda
    if "arrival_rate" in config:
        lam = float(config["arrival_rate"])
    elif "call_flow" in config:
        lam = float(config["call_flow"])
    else:
        raise ValueError("Нет arrival_rate/call_flow в конфиге")

    # queue capacity
    if "queue_capacity" in config:
        queue_capacity = int(config["queue_capacity"])
    elif "queue_size" in config:
        queue_capacity = int(config["queue_size"])
    else:
        raise ValueError("Нет queue_capacity/queue_size в конфиге")

    # time end
    if "time_end" in config:
        time_end = float(config["time_end"])
    elif "duration" in config:
        time_end = float(config["duration"])
    else:
        raise ValueError("Нет time_end/duration в конфиге")

    # servers
    servers: Optional[List[ServerState]] = None
    if config.get("servers") is not None:
        servers = config["servers"]
        if not isinstance(servers, list) or (servers and not isinstance(servers[0], ServerState)):
            raise ValueError('"servers" должен быть List[ServerState]')
    elif config.get("operators") is not None:
        servers = build_servers(config["operators"])
    elif config.get("service_rates") is not None:
        mus = [float(x) for x in config["service_rates"]]
        servers = [
            ServerState(id=i, name=f"Server #{i+1}", op_type="Server", mu=mus[i])
            for i in range(len(mus))
        ]
    else:
        raise ValueError('Нужно передать "operators" или "servers" (или хотя бы "service_rates").')

    seed = config.get("seed", None)
    drain = _as_bool(config.get("drain", True), default=True)
    start_at_zero = _as_bool(config.get("start_at_zero", True), default=True)

    policy_raw = str(config.get("free_server_policy", "round_robin"))
    if policy_raw not in ("round_robin", "fastest"):
        raise ValueError(f"free_server_policy должен быть 'round_robin' или 'fastest' (получено: {policy_raw!r})")
    policy: PoolMode = policy_raw  # type: ignore[assignment]

    max_arrivals = config.get("max_arrivals", None)
    if max_arrivals is not None:
        max_arrivals = int(max_arrivals)

    # базовые проверки
    if lam <= 0:
        raise ValueError("arrival_rate (lambda) должен быть > 0")
    if queue_capacity < 0:
        raise ValueError("queue_capacity должен быть >= 0")
    if time_end <= 0:
        raise ValueError("time_end/duration должен быть > 0")
    if not servers:
        raise ValueError("Список servers пуст")
    if any(float(s.mu) <= 0 for s in servers):
        raise ValueError("У всех серверов mu должен быть > 0")

    return NormalizedConfig(
        lam=lam,
        queue_capacity=queue_capacity,
        time_end=time_end,
        servers=servers,
        seed=seed,
        drain=drain,
        start_at_zero=start_at_zero,
        policy=policy,
        max_arrivals=max_arrivals,
    )