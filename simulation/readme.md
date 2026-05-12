# Simulation package

## Структура

simulation/
├─ __init__.py
├─ simulator.py
├─ engine.py
├─ config.py
├─ models.py
├─ servers.py
├─ types.py
└─ constants.py

## Описание файлов

### __init__.py
Публичный экспорт основного API пакета (simulate и модели). Удобно для импорта `from simulation import simulate`.

### simulator.py
Совместимость. Сохраняет старую точку входа `simulation.simulator`.
Реэкспортирует `simulate` и dataclass-модели

### engine.py
Основное ядро дискретно-событийной симуляции: очередь событий, обработчики arrival/service_end, сбор статистики.

### config.py
Нормализация входного конфига (поддержка UI-формата и engine-формата), валидация, приведение типов.
Возвращает `NormalizedConfig`.

### models.py
Чистые dataclass-модели результата симуляции:
- RequestRecord
- ServerState
- SimulationResult

### servers.py
Всё, что относится к обслуживающим каналам:
- build_servers() из operators
- FreeServerPool (round_robin/fastest)
- prepare_servers() (копирование и сброс runtime-полей, чтобы не мутировать входные ServerState)

### types.py
Типы для повышения читаемости:
- PoolMode
- EventKind
- Event

### constants.py
Константы приоритетов событий (ARRIVAL vs SERVICE_END)