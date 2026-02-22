# ESP <-> UnitV (K210) Протокол по Grove UART (JSONL)

## Назначение

Протокол для обмена между ESP (например, `AtomS3 Lite`) и камерой `UnitV-M12` по Grove UART.

- Транспорт: UART
- Формат сообщений: `JSON` по одной строке (`JSONL`)
- Модель взаимодействия: `one request -> one response`

## Физика и UART

### UnitV (runtime)

- Используется `UART_ID = 0` (на текущей сборке MaixPy это рабочий UART для Grove)
- Скорость: `115200`
- Линии UnitV (по runtime-конфигу):
  - `TX = G34`
  - `RX = G35`

### AtomS3 Lite (проверенная связка)

Для нашей текущей проводки рабочая конфигурация тестера:

- `RX = 1`
- `TX = 2`

В тестере:

```text
uartpins 1 2
timeout 7000
```

### M5StickC-Plus (по маркировке на корпусе)

По фото на корпусе у Grove-порта отмечено:

- `G` — GND
- `V` — VCC (5V)
- `G32`
- `G33`

То есть для UART на `M5StickC-Plus` можно использовать:

- `GPIO32`
- `GPIO33`

Важно:

- порядок `RX/TX` зависит от того, как именно это заведено в прошивке ESP
- если после подключения нет ответов, нужно поменять местами `RX/TX` (аналогично `pinswap`)

Практический старт для тестовой прошивки (если пины настраиваются командой):

```text
uartpins 32 33
```

Если нет ответа:

```text
uartpins 33 32
```

## Формат сообщений

### Запрос (ESP -> UnitV)

Одна строка JSON, завершается `\\n`.

Обязательные поля:

- `req_id` — идентификатор запроса (любой JSON-скаляр, обычно строка/число)
- `cmd` — имя команды (строка)

Опционально:

- `args` — объект аргументов (`{}`)

Пример:

```json
{"cmd":"PING","req_id":"1","args":{}}
```

### Ответ (UnitV -> ESP)

Всегда один JSON-ответ на запрос.

Успех:

```json
{"req_id":"1","ok":true,"result":{...}}
```

Ошибка:

```json
{"req_id":"1","ok":false,"error":{"code":"TIMEOUT","message":"timeout"}}
```

## Общая схема команд

Команды (регистр не важен, runtime приводит к `UPPERCASE`):

- `PING`
- `INFO`
- `SCAN`
- `WHO`
- `OBJECTS`
- `LEARN`
- `RESET_FACES`
- `DEBUG`

Неизвестная команда:

- `BAD_REQUEST / unknown_cmd`

## Команды и ответы

### `PING`

Проверка доступности runtime.

Запрос:

```json
{"cmd":"PING","req_id":"1","args":{}}
```

Ответ:

```json
{"req_id":"1","ok":true,"result":{"status":"ok","tool":"vision_k210"}}
```

### `INFO`

Информация о runtime и возможностях.

Запрос:

```json
{"cmd":"INFO","req_id":"2","args":{}}
```

Ответ (пример):

```json
{
  "req_id":"2",
  "ok":true,
  "result":{
    "tool":"vision_k210",
    "fw_version":"1.0.0",
    "protocol_version":"1",
    "capabilities":{
      "faces":true,
      "objects":true,
      "learn":true,
      "sd":true
    }
  }
}
```

### `WHO`

Распознавание лица (без object detection).

Аргументы:

- `mode`: `"FAST"` | `"RELIABLE"` (по умолчанию `RELIABLE`)
- `frames`: число кадров (ограничивается runtime)

Запрос:

```json
{"cmd":"WHO","req_id":"3","args":{"mode":"RELIABLE","frames":1}}
```

Ответ (пример):

```json
{"req_id":"3","ok":true,"result":{"person":"NONE","frames":1}}
```

Возможные `person`:

- `NONE` — лицо не найдено
- `UNKNOWN` — лицо найдено, но шаблон не совпал
- `owner_1` / `owner_2` — совпадение с шаблоном из `/sd/faces_data`

### `OBJECTS`

Детекция объектов (YOLO2/KPU).

Аргументы:

- `mode`: `"FAST"` | `"RELIABLE"`
- `frames`: число кадров
- `allow_partial`: `true/false` (опционально)

Запрос:

```json
{"cmd":"OBJECTS","req_id":"4","args":{"mode":"RELIABLE","frames":1}}
```

Ответ (пример):

```json
{"req_id":"4","ok":true,"result":{"frames":1,"truncated":false,"objects":[]}}
```

Поля:

- `objects` — список распознанных объектов (после фильтрации/агрегации)
- `truncated` — список был обрезан до `MAX_OBJECTS`
- `frames` — фактически использованное число кадров

### `SCAN`

Комбинированный запрос: лицо + объекты.

Аргументы:

- `mode`: `"FAST"` | `"RELIABLE"`
- `frames`: число кадров
- `allow_partial`: `true/false` (опционально)

Запрос:

```json
{"cmd":"SCAN","req_id":"5","args":{"mode":"RELIABLE","frames":1}}
```

Ответ (пример):

```json
{
  "req_id":"5",
  "ok":true,
  "result":{
    "person":"NONE",
    "faces_detected":0,
    "objects":["cup","table"],
    "frames":1,
    "truncated":false
  }
}
```

Опционально может быть:

- `confidence`: `{"person": <float>}` — если определён `UNKNOWN`/`owner_*`

### `LEARN`

Сохранение face template для владельца.

Аргументы:

- `person`: обычно `owner_1` или `owner_2`
- `frames`: число кадров для выбора лучшего шаблона (runtime ограничит)

Запрос (пример):

```json
{"cmd":"LEARN","req_id":"6","args":{"person":"owner_1","frames":7}}
```

Результат зависит от реализации `faces.py`, но при успехе runtime возвращает `ok:true` и обновляет шаблон в:

- `/sd/faces_data/owner_1.jpg`
- `/sd/faces_data/owner_2.jpg`

### `RESET_FACES`

Сброс шаблонов лиц (`owner_1.jpg`, `owner_2.jpg`).

Запрос:

```json
{"cmd":"RESET_FACES","req_id":"7","args":{}}
```

### `DEBUG`

Переключение runtime debug-режима (внутренний флаг runtime).

Запрос:

```json
{"cmd":"DEBUG","req_id":"8","args":{"enabled":true}}
```

## Ошибки протокола

Основные коды ошибок:

- `BAD_REQUEST`
- `BUSY`
- `TIMEOUT`
- `VISION_FAILED`

Примеры:

```json
{"req_id":"x","ok":false,"error":{"code":"BAD_REQUEST","message":"bad_json"}}
```

```json
{"req_id":"x","ok":false,"error":{"code":"BUSY","message":"busy"}}
```

```json
{"req_id":"x","ok":false,"error":{"code":"TIMEOUT","message":"timeout"}}
```

```json
{"req_id":"x","ok":false,"error":{"code":"VISION_FAILED","message":"objects_detect"}}
```

### Когда приходит `BUSY`

Если новый запрос пришёл, пока предыдущий ещё обрабатывается, runtime отвечает:

- `BUSY`

Это нормальное поведение. На стороне ESP нужно:

- дождаться ответа/таймаута прошлого запроса
- затем ретраить

## Важные свойства runtime

### Дедупликация по `req_id`

Runtime кэширует последний ответ по `req_id` (TTL).

Если повторить тот же `req_id`, может вернуться тот же raw-ответ (`dedup`), а не повторное выполнение команды.

Рекомендация:

- использовать новый `req_id` на каждый новый запрос

### Ограничение размера JSON

Runtime ограничивает размер UART-JSON ответа.

Если ответ слишком длинный:

- вернётся `BAD_REQUEST / too_long`

### Таймауты

Есть два уровня таймаута:

1. Внутренний timeout runtime (`COMMAND_TIMEOUT_MS` в `config.py`)
2. Таймаут ожидания ответа на стороне ESP/тестера

Рекомендовано для тестера:

- `timeout 7000` (для `OBJECTS/SCAN`)

## USB vs Grove (важно)

- JSONL-протокол (`PING/INFO/WHO/OBJECTS/SCAN/...`) идёт по **Grove UART**
- USB (`/dev/ttyUSB0`) используется для:
  - REPL
  - boot-лога
  - debug-логов (`[vision]`, `[vision.rt]`, `[vision.obj]`)

Не отправляйте JSONL-команды в USB REPL в расчёте получить runtime-ответ.

## Минимальный smoke-test (ESP/Atom)

```text
uartpins 1 2
timeout 7000
ping
info
objects 1 reliable
scan 1 reliable
```

Ожидаемо:

- все ответы `ok:true`
- `objects` может быть пустым списком (`[]`) в зависимости от сцены
- `person` может быть `NONE` или `UNKNOWN`, если `faces_data` пустой
