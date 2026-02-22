# AtomS3 Lite + UnitV-M12 E2E: Цепочка Сабагентов

## Контекст (снимок состояния)

- Устройства:
  - `AtomS3 Lite` по USB: `/dev/ttyACM0`
  - `UnitV-M12 (K210)` по USB: `/dev/ttyUSB0`
- Соединение: `Atom <-> UnitV` через Grove (уже проверено по цветам/подписям).
- Подтверждённые факты:
  - `Atom` loopback (`G1 <-> G2`) проходит.
  - `UnitV` loopback на `G34/G35` проходит при `machine.UART(0)`.
  - `UnitV` sniffer (`uid=0`, `G34/G35`) видит `PING` от `Atom`.
  - `Atom` прошивка-тестер принимает ответы от `UnitV` после фикса парсера (whitespace-tolerant JSON).
- Найденные причины (уже частично исправлены в коде репо):
  - `UnitV` должен использовать `UART_ID = 0` на этой сборке MaixPy (`UART1=0`).
  - Конфликт имён: `faces.py` (модуль) vs `/sd/faces` (каталог данных) ломает импорт в MicroPython.
  - На SD камеры были частично повреждённые `*.py` после прерванных загрузок.

## Цель

Довести до рабочего e2e:

- `ping` -> `ok:true`
- `info` -> `ok:true`
- `scan` -> корректный ответ (успех или осмысленная ошибка, но не timeout)

## Текущий Статус (2026-02-22)

- `PING`, `INFO`, `WHO`, `OBJECTS`, `SCAN` проходят end-to-end на реальном железе.
- Для текущей связки `AtomS3 Lite <-> UnitV` рабочие пины тестера: `RX=1`, `TX=2` (`uartpins 1 2`).
- `UnitV` runtime размещён на `/sd`; на `/flash` оставлены только launcher'ы (`boot.py`, `main.py`).
- Приёмочный сценарий после cleanup (`PING/INFO/WHO/OBJECTS/SCAN` + повторы `OBJECTS/SCAN`) прошёл без таймаутов.
- Спецификация протокола UART/JSONL: `docs/protocols/esp-unitv-grove-uart-jsonl.md`

## Оркестрация (Controller)

- Роль: основной агент (controller), использует подход `subagent-driven-development`.
- Ограничение: доступ к USB-портам только по одному агенту одновременно.

### Портовые mutex

- `unitv_usb`: `/dev/ttyUSB0`
- `atom_usb`: `/dev/ttyACM0`

## Роли сабагентов

### 1. UnitV Runtime Agent

- Тип: `worker`
- Скилл: `subagent-driven-development`
- Владение:
  - `config.py`
  - `main.py`
  - `vision.py`
  - `faces.py`
  - `objects.py`
  - `storage.py`
  - `protocol.py`
  - `led.py`
- Задача:
  - финализировать runtime под конкретную MaixPy сборку
  - закрепить `UART_ID = 0`
  - убрать конфликт путей данных лиц (`/sd/faces_data` вместо `/sd/faces`)
- Критерий успеха:
  - код в репо консистентный
  - импорты `main/vision/faces` логически не конфликтуют

### 2. UnitV Deployer Agent

- Тип: `worker`
- Скилл: `subagent-driven-development`
- Владение:
  - `mpremote` + `/dev/ttyUSB0`
  - host-side команды файловой синхронизации через `mpremote`
- Задача:
  - восстановить файлы `*.py` на `/sd` камеры
  - переименовать каталог `/sd/faces -> /sd/faces_data`
  - подтвердить загрузку по размерам файлов
- Критерий успеха:
  - `import main` через `mpremote exec` проходит
  - нет `BOOT_LAUNCH_ERR` на boot
 - Ограничение (deployment policy):
  - передача файлов только через `mpremote` (`cp`, `exec`, `run`)
  - не использовать paste mode/raw serial для загрузки файлов

### 3. E2E Acceptance Agent

- Тип: `worker`
- Скилл: `subagent-driven-development`
- Владение:
  - Atom USB CLI (`/dev/ttyACM0`)
  - при необходимости короткий UnitV debug-loop по USB (но без изменения файлов)
- Задача:
  - прогнать приёмочный сценарий e2e
- Критерий успеха:
  - `ping_ok >= 1`
  - `info_ok >= 1`
  - `scan_ok >= 1` (или диагностированная не-timeout ошибка на уровне vision)

## Порядок выполнения (минимальный)

1. `UnitV Runtime Agent`
2. `Spec Reviewer` (runtime)
3. `Code Quality Reviewer` (runtime)
4. `UnitV Deployer Agent`
5. `Spec Reviewer` (deploy procedure / verification)
6. `E2E Acceptance Agent`
7. `Final Reviewer` (общий итог)

## Review Gates (по subagent-driven-development)

После каждого изменяющего агента:

1. `Spec Reviewer`
2. `Code Quality Reviewer`

## Что нельзя делать параллельно

- Два агента на `/dev/ttyUSB0`
- Два агента на `/dev/ttyACM0`
- Прошивка и монитор одного устройства одновременно

## Быстрый чек-лист для Controller

- Перед каждым агентом: проверить, что порт свободен.
- После `UnitV Deployer`: проверить `import main` на `UnitV`.
- Для `UnitV Deployer` использовать только `maixctl` / `tools/k210_loader.py --deploy-backend maixctl` (см. `docs/subagents/unitv-mpremote-deployment.md`).
- Перед `E2E Acceptance`: убедиться, что кабель снова `Atom <-> UnitV` (не loopback).
