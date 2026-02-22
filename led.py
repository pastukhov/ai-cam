"""WS2812 status LED for UnitV (1 LED on pin 8)."""

import config

_ws = None


def init():
  """Register pin and create WS2812 driver. No-op off-device."""
  global _ws
  try:
    from modules import ws2812
    # MaixPy's ws2812 driver configures the FPIOA pin internally.
    # Calling fm.register() without a function prints noisy debug text
    # ("Please enter Pin and function") during boot.
    _ws = ws2812(config.LED_PIN, 1)
    off()
  except Exception:
    _ws = None


def _set(r, g, b):
  if _ws is None:
    return
  try:
    _ws.set_led(0, (r, g, b))
    _ws.display()
  except Exception:
    pass


def off():
  _set(0, 0, 0)


def boot():
  _set(0, 0, 30)


def idle():
  _set(0, 6, 0)


def busy():
  _set(15, 15, 15)


def ok():
  _set(0, 40, 0)


def owner():
  _set(0, 80, 0)


def unknown():
  _set(50, 30, 0)


def error():
  _set(60, 0, 0)


def learning():
  _set(40, 0, 40)
