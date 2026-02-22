# UnitV Deployment Policy: `maixctl` Only

## Назначение

`UnitV` (K210, MaixPy / MicroPython) должен обслуживаться через `maixctl` (MaixPy IDE protocol client) для всех file/runtime операций на устройстве.

Все операции деплоя/синхронизации файлов и удалённого выполнения для `UnitV`:

- `MUST` использовать `maixctl` или `tools/k210_loader.py` (backend `maixctl`)
- `MUST NOT` использовать самодельные протоколы передачи по UART
- `MUST NOT` использовать REPL paste/raw serial для ручной загрузки файлов

## Среда

Пользователь установил инструменты в проектный `venv` и зафиксировал policy на `maixctl`.

Проверка:

```bash
python3 -m maixctl --help
```

## Порт устройства

Определение порта:

```bash
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

Для текущего окружения обычно:

```bash
PORT=/dev/ttyUSB0
```

## Файловая структура на устройстве

- `/flash` — boot-критичные скрипты
- `/sd` — модели, конфиги, лица, runtime-данные

Правила:

- `/flash` держать минимальным (launcher/boot)
- всё изменяемое и объёмное хранить на `/sd`

## Обязательный workflow (для сабагентов и Codex)

1. Правка файлов локально.
2. Загрузка изменённых файлов через `python3 -m maixctl upload ...` или `tools/k210_loader.py`.
3. Перезапуск/сброс устройства.
4. Верификация поведения через Atom UART e2e tool.

## Команды `maixctl`

### Загрузка файла

```bash
python3 -m maixctl upload --port $PORT ./main.py /flash/main.py
python3 -m maixctl upload --port $PORT ./config.py /sd/config.py
```

### Загрузка модели/данных

```bash
python3 -m maixctl upload --port $PORT ./models/objects.kmodel /sd/models/objects.kmodel
```

### Скачивание файла (если нужно)

```bash
python3 -m maixctl download --port $PORT /flash/main.py ./main.py.device
```

### Список файлов

```bash
python3 -m maixctl fs-ls --port $PORT /flash
python3 -m maixctl fs-ls --port $PORT /sd
```

### Удалённый Python (диагностика)

```bash
python3 -m maixctl run --port $PORT --code "import os; print(os.listdir('/sd'))" --follow
```

### Запуск локального скрипта (диагностика)

```bash
python3 -m maixctl run --port $PORT --script ./test_script.py --follow
```

## Запреты (обязательно)

- Не передавать файлы через REPL paste mode
- Не стримить base64/blob через UART для записи файлов
- Не реализовывать альтернативный custom transfer layer
- Не использовать ручной raw serial upload вместо `maixctl upload`

## Верификация после деплоя

```bash
python3 -m maixctl fs-ls --port $PORT /flash
python3 -m maixctl fs-ls --port $PORT /sd
```

Для runtime также рекомендуется:

```bash
python3 -m maixctl run --port $PORT --code "import sys; sys.path.insert(0, '/sd'); import main; print('main import ok')" --follow
```

## Примечание для `UnitV Deployer Agent`

`UnitV Deployer Agent` обязан использовать этот документ как policy-first источник для всех file operations на `UnitV`.
Если используется `tools/k210_loader.py`, должен использоваться backend `maixctl` (не `raw`, если пользователь не запросил явно).
