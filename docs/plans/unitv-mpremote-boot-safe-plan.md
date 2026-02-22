# План: UnitV Boot-Safe + `maixctl`-Only Deployment

## Цель

Сделать деплой `UnitV` совместимым с policy `maixctl-only` без ручного raw REPL/paste upload как рабочего пути восстановления.

## Статус (2026-02-22)

Частично реализовано в коде:

- `tools/k210_loader.py` уже поддерживает boot-safe launcher (`/flash/main.py`)
- launcher поддерживает флаг `/sd/.safe_mode`
- добавлено окно grace period перед автозапуском
- `tools/k210_loader.py` умеет деплой через backend `maixctl` (`--deploy-backend maixctl`, `auto`)

Осталось:

- подтвердить bootstrap/recovery flow на реальном `UnitV`
- подтвердить дальнейший `maixctl-only` runtime workflow (без `mpremote`)

## Исходные факты

- На `UnitV` обычный REPL доступен через `Ctrl+C` по USB UART.
- `mpremote` на текущей прошивке ненадёжен (`could not enter raw repl`), поэтому выбран `maixctl-only` путь.
- Ранее автозапуск runtime и повреждённые файлы на `/sd` мешали стабильному обслуживанию устройства.

## Подход (правильный путь)

### 1. Boot-safe launcher в `/flash/main.py`

Нужен launcher, который:

- держит runtime на `/sd`
- умеет **не запускать** `/sd/main.py` в “safe mode”
- оставляет устройство в состоянии, пригодном для обслуживания через `maixctl`/диагностику
- пишет короткие диагностические сообщения (`BOOT_LAUNCH_ERR ...`)

### 2. Механизм включения safe mode (без raw REPL)

Базовый способ (подтверждён пользователем):

- отправить `Ctrl+C` по USB UART
- попасть в обычный REPL

Дальше (однократно, короткой командой в обычном REPL):

- создать флаг-файл на SD, например `:/sd/.safe_mode`

После этого при boot launcher:

- видит `/.safe_mode`
- **не** автозапускает runtime
- остаётся в REPL/idle (удобно для последующего `maixctl` обслуживания / диагностики)

Важно:

- это не bulk-transfer через REPL
- это bootstrap-шаг для перехода на `maixctl-only` workflow

### 3. Дальнейший workflow только через `maixctl`

- `maixctl upload` для файлов
- `maixctl run --follow` для проверок/диагностики
- `maixctl fs-ls`/`fs-stat` для верификации
- `tools/k210_loader.py --deploy-backend maixctl` для пакетной заливки runtime

## Что меняем в коде/инструментах

### `tools/k210_loader.py`

- обновить шаблон `FLASH_LAUNCHER_CODE` (сделано)
- добавить (сделано):
  - флаг safe mode (`/sd/.safe_mode`)
  - короткое окно перед автозапуском (grace period)
  - понятный `BOOT_LAUNCH_ERR`
- добавить backend деплоя через `maixctl` для bootstrap/recovery (сделано)

## Критерии успеха

1. Launcher поддерживает safe mode через флаг-файл.
2. Есть документированный bootstrap-шаг через обычный REPL (`Ctrl+C`) без raw REPL.
3. После включения safe mode следующий деплой выполняется через `maixctl`.

## Следующие шаги на железе

1. Поставить/обновить boot-safe launcher на `UnitV` через `python3 tools/k210_loader.py --port ... --deploy-backend maixctl` (bootstrap/recovery).
2. Создать `/.safe_mode` (короткой командой через обычный REPL после `Ctrl+C`, если `maixctl` не может зайти в IDE mode).
3. Проверить, что `maixctl` стабильно обслуживает `/flash`/`/sd` и можно выставить/считать safe flag.
4. Восстановить `/sd` runtime через `maixctl` (`maixctl upload` или `tools/k210_loader.py --deploy-backend maixctl`).
5. Убрать `/.safe_mode` и проверить e2e (`PING`/`INFO`/`SCAN`). `(сделано)`
6. Подтвердить `launcher-only` на `/flash` (оставить только `/flash/boot.py` и `/flash/main.py`; runtime на `/sd`). `(сделано)`

### Статус hardware e2e (2026-02-22)

- `maixctl-only` deploy + boot-safe recovery подтверждены на железе.
- `AtomS3 Lite -> UnitV` e2e по Grove UART проходит для `PING`, `INFO`, `WHO`, `OBJECTS`, `SCAN`.
- `OBJECTS`/`SCAN` стабилизированы для sample-model (`224x224`) через resize fallback в runtime.
- `/flash` очищен до launcher-only:
  - `/flash/boot.py`
  - `/flash/main.py`
- Приёмочный e2e после cleanup пройден:
  - `PING`, `INFO`, `WHO`, `OBJECTS`, `SCAN` -> `ok`
  - серия повторных `OBJECTS/SCAN` без таймаутов

### Остаточный техдолг

- На `/sd` остались битые записи каталога с `NUL`-именами после прерванных upload'ов.
- Это не блокирует runtime/e2e, но требует отдельной санитации (`sd` cleanup / reformat) вне текущего шага.
