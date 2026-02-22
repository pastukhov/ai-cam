# Обнаружение AI Rover через mDNS / DNS-SD

## Назначение

Ровер регистрирует себя в локальной сети через mDNS (Multicast DNS) и публикует HTTP-сервис через DNS-SD. Это позволяет находить устройство по имени `ai-rover.local` без знания IP-адреса.

## Hostname

```
ai-rover.local
```

Резолвится в текущий IP ровера (DHCP).

## DNS-SD сервис

| Поле | Значение |
|------|----------|
| Instance name | `AI Rover` |
| Service type | `_http._tcp` |
| Port | `80` |

## TXT-записи

Сервис публикует эндпоинты веб-интерфейса в TXT-записях (стандарт DNS-SD):

| Ключ | Значение | Описание |
|------|----------|----------|
| `path` | `/` | Веб-интерфейс (HTML) |
| `api_cmd` | `/cmd` | Управление движением и манипулятором |
| `api_status` | `/status` | Статус ровера (JSON) |
| `api_vision` | `/vision` | Камера UnitV (SCAN/OBJECTS/WHO) |
| `api_chat` | `/chat` | AI-чат (POST — отправка, GET — запрос) |
| `api_chat_result` | `/chat_result` | Результат AI-чата |

## Обнаружение с клиентских устройств

### Linux (Avahi)

```bash
# Найти все HTTP-сервисы
avahi-browse -r _http._tcp

# Проверить доступность
ping ai-rover.local

# Открыть веб-интерфейс
curl http://ai-rover.local/status
```

### macOS

```bash
# Найти сервис
dns-sd -B _http._tcp

# Подробности с TXT-записями
dns-sd -L "AI Rover" _http._tcp

# Проверить
ping ai-rover.local
```

### Python

```python
from zeroconf import Zeroconf, ServiceBrowser

class Listener:
    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name)
        if info and b"ai-rover" in (info.server or b""):
            print(f"Found: {info.server}:{info.port}")
            for key, val in info.properties.items():
                print(f"  {key.decode()}: {val.decode()}")

zc = Zeroconf()
ServiceBrowser(zc, "_http._tcp.local.", Listener())
```

## Жизненный цикл

- **Регистрация** — при подключении к WiFi (первичном и при реконнекте)
- **Освобождение** — перед уходом в deep sleep (`mdns_free()`)
- После пробуждения из deep sleep mDNS регистрируется заново

## Реализация

Исходный код: `src/main_idf.cpp`, функция `start_mdns()`.

Используется компонент `espressif/mdns` (ESP-IDF managed component, `src/idf_component.yml`).
