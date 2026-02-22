# AtomS3 Lite E2E Tester for UnitV (K210)

Минимальная прошивка для `M5Stack AtomS3 / AtomS3 Lite`, которая:

- общается с камерой `UnitV` по Grove UART (`115200`, JSONL),
- принимает команды по USB Serial от ПК,
- отправляет `PING / INFO / SCAN / WHO / OBJECTS`,
- печатает сырой JSON-ответ обратно в монитор порта,
- ведёт простую статистику `tx/rx/timeouts/detect_hits`.

Это удобно для e2e-проверки цепочки:

`PC -> AtomS3 USB -> AtomS3 Grove UART -> UnitV vision runtime -> AtomS3 -> PC`

## Wiring

- Соедините `AtomS3 Lite` и `UnitV` обычным `HY2.0-4P / Grove` кабелем.
- Подключите **оба** устройства к ПК по USB.
- На `UnitV` должна быть загружена ваша MaixPy-прошивка с JSONL runtime (`main.py` из этого репо).

## Build / Upload (PlatformIO)

Из каталога `atoms3-e2e-tester/`:

```bash
pio run
pio run -t upload
pio device monitor -b 115200
```

Если в системе несколько портов, укажите порт явно:

```bash
pio run -t upload --upload-port /dev/ttyACM0
pio device monitor -b 115200 --port /dev/ttyACM0
```

## Quick Start (USB monitor commands)

После старта в мониторе доступны команды:

- `ping` — проверка UART-связи с камерой
- `info` — инфо/модели/статус runtime
- `scan 3 reliable` — полный скан (лица + объекты)
- `who 3 reliable` — только лица
- `objects 3 reliable` — только объекты
- `auto on 1000 3 reliable` — автоскан каждую секунду
- `auto off`
- `stats`
- `raw {"cmd":"PING","req_id":"123"}`

Если `ping` даёт timeout при живом `UnitV` runtime, попробуйте:

- `pins` (посмотреть текущую конфигурацию)
- `pinswap` (поменять RX/TX местами)

Для текущей рабочей связки в этом репо дефолт уже настроен как `RX=G1`, `TX=G2`.

## Что считать успешным e2e

1. `ping` возвращает `{"ok":true,...}` — UART и протокол живы.
2. `scan ...` возвращает `{"ok":true,"result":...}` — камера/runtime реально работают.
3. `detect_hits` растёт или в JSON есть:
   - `"person":"OWNER_1" / "OWNER_2" / "UNKNOWN"` (не `NONE`)
   - или непустой массив `"objects":[...]`

Если `ping` проходит, а `scan` даёт ошибки/таймауты — проблема уже в vision runtime/модели/камере, а не в линии связи.
