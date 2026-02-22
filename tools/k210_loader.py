#!/usr/bin/env python3
"""K210 loader: flash firmware/models and upload MicroPython files (maixctl or raw REPL)."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import serial


REPO_ROOT = Path(__file__).resolve().parent.parent
KFLASH_PY = REPO_ROOT / "kflash_gui" / "kflash_py" / "kflash.py"
DEFAULT_FACE_MODEL = REPO_ROOT / "face_model_at_0x300000.kfpkg"
DEFAULT_APP_FILES = [
    "config.py",
    "protocol.py",
    "storage.py",
    "faces.py",
    "objects.py",
    "vision.py",
    "led.py",
    "main.py",
]
APP_REMOTE_DIR = "/sd"
FLASH_LAUNCHER_PATHS = ["/flash/boot.py", "/flash/main.py"]
FLASH_LAUNCHER_CODE = (
    "# Auto-generated launcher. Keep runtime on SD.\n"
    "# Boot-safe mode: create /sd/.safe_mode to skip autostart and stay in REPL.\n"
    "import sys\n"
    "try:\n"
    "    import uos as _os\n"
    "except ImportError:\n"
    "    import os as _os\n"
    "try:\n"
    "    import utime as _time\n"
    "except ImportError:\n"
    "    import time as _time\n"
    "\n"
    "SAFE_FLAG = '/sd/.safe_mode'\n"
    "APP_MAIN = '/sd/main.py'\n"
    "\n"
    "def _exists(path):\n"
    "    try:\n"
    "        _os.stat(path)\n"
    "        return True\n"
    "    except Exception:\n"
    "        return False\n"
    "\n"
    "def _sleep_ms(ms):\n"
    "    try:\n"
    "        _time.sleep_ms(ms)\n"
    "    except Exception:\n"
    "        _time.sleep(ms / 1000.0)\n"
    "\n"
    "def _wait_grace():\n"
    "    # Small grace window to allow Ctrl+C from USB UART before autostart.\n"
    "    _sleep_ms(1200)\n"
    "\n"
    "def _run_app():\n"
    "    sys.path.insert(0, '/sd')\n"
    "    g = {'__name__': '__main__'}\n"
    "    exec(open(APP_MAIN).read(), g)\n"
    "\n"
    "try:\n"
    "    _wait_grace()\n"
    "    if _exists(SAFE_FLAG):\n"
    "        print('BOOT_SAFE_MODE')\n"
    "    elif not _exists(APP_MAIN):\n"
    "        print('BOOT_LAUNCH_ERR', 'main_missing')\n"
    "    else:\n"
    "        _run_app()\n"
    "except KeyboardInterrupt:\n"
    "    print('BOOT_INTERRUPTED')\n"
    "except Exception as _e:\n"
    "    try:\n"
    "        print('BOOT_LAUNCH_ERR', repr(_e))\n"
    "    except Exception:\n"
    "        print('BOOT_LAUNCH_ERR')\n"
)

DEFAULT_SAMPLE_MODEL_DIR = Path(
    "/home/artem/tmp/MaixPy-v1_scripts/machine_vision/fans_share/yolov2_apple,banana,orange"
)
DEFAULT_SAMPLE_MODEL = DEFAULT_SAMPLE_MODEL_DIR / "yolov2.kmodel"
DEFAULT_SAMPLE_CLASSES = DEFAULT_SAMPLE_MODEL_DIR / "classes.txt"


class LoaderError(Exception):
    pass


class RawReplClient:
    def __init__(self, port: str, baudrate: int, timeout: float = 1.0):
        self.ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout, write_timeout=timeout)

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()

    def _read_until(self, marker: bytes, timeout_s: float) -> bytes:
        end = time.time() + timeout_s
        buf = bytearray()
        while time.time() < end:
            chunk = self.ser.read(256)
            if chunk:
                buf.extend(chunk)
                if marker in buf:
                    return bytes(buf)
        raise LoaderError(f"Timeout waiting for marker {marker!r}. Got: {bytes(buf)!r}")

    def _read_exec_triplet(self, timeout_s: float) -> tuple[bytes, bytes]:
        end = time.time() + timeout_s
        buf = bytearray()
        marker = b"\x04\x04>"
        while time.time() < end:
            chunk = self.ser.read(256)
            if chunk:
                buf.extend(chunk)
                idx = bytes(buf).find(marker)
                if idx != -1:
                    payload = bytes(buf[:idx])
                    first = payload.find(b"\x04")
                    if first == -1:
                        if payload == b"":
                            return b"", b""
                        # Some firmware variants may skip empty streams markers on tiny snippets.
                        return payload, b""
                    stdout = payload[:first]
                    stderr = payload[first + 1 :]
                    return stdout, stderr
        raise LoaderError(f"Timeout waiting for raw repl exec result. Got: {bytes(buf)!r}")

    def enter_raw_repl(self) -> None:
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        # Boards may spew boot logs and exceptions before REPL is stable.
        # Try several times to force raw REPL.
        last = b""
        for _ in range(6):
            self.ser.write(b"\r\x03\x03\x02\r")
            time.sleep(0.2)
            _ = self.ser.read(4096)
            self.ser.write(b"\r\x01")
            try:
                out = self._read_until(b">", timeout_s=2.0)
            except LoaderError:
                out = b""
            last = out or last
            if b"raw REPL" in out:
                return
        raise LoaderError(f"Device did not enter raw REPL: {last!r}")

    def exit_raw_repl(self) -> None:
        self.ser.write(b"\x02")  # Ctrl-B

    def exec_raw(self, code: str, timeout_s: float = 5.0) -> bytes:
        payload = code.encode("utf-8")

        # Retry once if ACK is polluted by noise.
        for _ in range(2):
            self.ser.reset_input_buffer()
            self.ser.write(payload + b"\x04")  # Ctrl-D executes script in raw repl

            ok = self.ser.read(2)
            if ok == b"OK":
                break
            # Try to recover raw repl and retry once.
            self.enter_raw_repl()
        else:
            raise LoaderError(f"raw repl did not ACK with OK, got: {ok!r}")

        stdout, stderr = self._read_exec_triplet(timeout_s=timeout_s)

        if stderr:
            raise LoaderError(f"Remote error: {stderr.decode('utf-8', errors='replace')}")
        return stdout

    def ensure_dir(self, path: str) -> None:
        path = path.strip()
        if not path:
            return
        code = (
            "import uos\n"
            f"p={path!r}\n"
            "parts=[x for x in p.split('/') if x]\n"
            "cur=''\n"
            "for part in parts:\n"
            "    cur += '/' + part\n"
            "    try:\n"
            "        uos.stat(cur)\n"
            "    except:\n"
            "        uos.mkdir(cur)\n"
        )
        self.exec_raw(code, timeout_s=8.0)

    def write_file(self, remote_path: str, data: bytes, chunk_size: int = 1024) -> None:
        parent = str(Path(remote_path).parent)
        if parent not in ("", "."):
            self.ensure_dir(parent)

        self.exec_raw(f"f=open({remote_path!r},'wb')\nf.close()", timeout_s=5.0)

        sent = 0
        total = len(data)
        last_report = 0
        while sent < total:
            chunk = data[sent : sent + chunk_size]
            code = (
                f"f=open({remote_path!r},'ab')\n"
                f"f.write({chunk!r})\n"
                "f.close()\n"
            )
            self.exec_raw(code, timeout_s=10.0)
            sent += len(chunk)
            if total >= 65536 and (sent - last_report >= 65536 or sent == total):
                pct = int((sent * 100) / total)
                print(f"  {remote_path}: {sent}/{total} bytes ({pct}%)", flush=True)
                last_report = sent


def run_cmd(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise LoaderError(
            f"Command failed: {' '.join(cmd)}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        )
    if res.stdout.strip():
        print(res.stdout.strip(), flush=True)


def run_cmd_result(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, capture_output=True, text=True)


def flash_with_kflash(port: str, baud: int, image_path: Path) -> None:
    if not image_path.exists():
        raise LoaderError(f"Flash image not found: {image_path}")
    if not KFLASH_PY.exists():
        raise LoaderError(f"kflash.py not found: {KFLASH_PY}")

    run_cmd(
        [
            sys.executable,
            str(KFLASH_PY),
            "-p",
            port,
            "-b",
            str(baud),
            str(image_path),
        ]
    )


def have_maixctl() -> bool:
    try:
        __import__("maixctl")
        return True
    except Exception:
        return False


def maixctl_cmd(args: argparse.Namespace, subcmd: str, *extra: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "maixctl",
        subcmd,
        "--port",
        args.port,
        "--baud",
        str(args.ide_baud),
        "--repl-baud",
        str(args.uart_baud),
        "--enter-ide",
        *extra,
    ]


def maixctl_ensure_dir(args: argparse.Namespace, path: str) -> None:
    path = path.strip("/")
    if not path:
        return
    cur = ""
    for part in path.split("/"):
        cur += "/" + part
        stat_cmd = maixctl_cmd(args, "fs-stat", cur)
        res = run_cmd_result(stat_cmd)
        if res.returncode == 0:
            continue
        mkdir_cmd = maixctl_cmd(args, "fs-mkdir", cur)
        mk = run_cmd_result(mkdir_cmd)
        if mk.returncode != 0:
            raise LoaderError(
                f"Failed to create remote dir {cur}\nstdout:\n{mk.stdout}\nstderr:\n{mk.stderr}"
            )


def maixctl_upload_file(args: argparse.Namespace, local_path: Path, remote_path: str) -> None:
    cmd = maixctl_cmd(args, "upload", "--timeout", "20", str(local_path), remote_path)
    run_cmd(cmd)


def maixctl_reset(args: argparse.Namespace) -> None:
    cmd = maixctl_cmd(
        args,
        "run",
        "--code",
        "import machine; machine.reset()",
        "--timeout",
        "3",
    )
    run_cmd(cmd)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Flash and deploy K210 UnitV vision runtime")
    p.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyUSB0")
    p.add_argument("--flash-baud", type=int, default=1500000, help="Baudrate for kflash")
    p.add_argument("--uart-baud", type=int, default=115200, help="Baudrate for raw REPL upload")
    p.add_argument("--ide-baud", type=int, default=1500000, help="Baudrate for maixctl IDE protocol")
    p.add_argument(
        "--deploy-backend",
        choices=("auto", "maixctl", "raw"),
        default="auto",
        help="File upload backend (default: auto=prefer maixctl, fallback raw)",
    )

    p.add_argument("--firmware", type=Path, help="Firmware image (.bin/.kfpkg) to flash")
    p.add_argument(
        "--flash-face",
        nargs="?",
        const=str(DEFAULT_FACE_MODEL),
        type=Path,
        help="Flash face model .kfpkg (default path from repo)",
    )

    p.add_argument("--no-code", action="store_true", help="Skip uploading app python files")
    p.add_argument("--no-models", action="store_true", help="Skip uploading object model files to /sd/models")

    p.add_argument("--object-model", type=Path, help="Local object model file to upload as /sd/models/objects.kmodel")
    p.add_argument("--object-classes", type=Path, help="Local classes file to upload as /sd/models/classes.txt")
    p.add_argument("--object-label-map", type=Path, help="Local label_map json to upload as /sd/models/label_map.json")
    p.add_argument(
        "--use-sample-model",
        action="store_true",
        help="Use /home/artem/tmp/MaixPy-v1_scripts sample yolov2 model/classes if present",
    )
    p.add_argument("--reset-after", action="store_true", help="Reset device at end of upload")
    return p.parse_args()


def choose_model_inputs(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    model = args.object_model
    classes = args.object_classes

    if args.use_sample_model:
        if model is None and DEFAULT_SAMPLE_MODEL.exists():
            model = DEFAULT_SAMPLE_MODEL
        if classes is None and DEFAULT_SAMPLE_CLASSES.exists():
            classes = DEFAULT_SAMPLE_CLASSES

    return model, classes


def upload_files(port: str, baud: int, upload_code: bool, upload_models: bool, args: argparse.Namespace) -> None:
    client = RawReplClient(port=port, baudrate=baud)
    try:
        client.enter_raw_repl()

        if upload_code:
            client.ensure_dir(APP_REMOTE_DIR)
            for name in DEFAULT_APP_FILES:
                src = REPO_ROOT / name
                if not src.exists():
                    raise LoaderError(f"Missing app file: {src}")
                remote_path = f"{APP_REMOTE_DIR}/{src.name}"
                print(f"Uploading {src.name} -> {remote_path}", flush=True)
                client.write_file(remote_path, src.read_bytes())

            # Keep flash minimal: only a bootstrap that executes /sd/main.py.
            for launcher_path in FLASH_LAUNCHER_PATHS:
                print(f"Uploading launcher -> {launcher_path}", flush=True)
                client.write_file(launcher_path, FLASH_LAUNCHER_CODE.encode("utf-8"))

        if upload_models:
            model, classes = choose_model_inputs(args)
            label_map = args.object_label_map

            if model is not None:
                if not model.exists():
                    raise LoaderError(f"Object model file not found: {model}")
                print(f"Uploading {model} -> /sd/models/objects.kmodel", flush=True)
                client.write_file("/sd/models/objects.kmodel", model.read_bytes())

            if classes is not None:
                if not classes.exists():
                    raise LoaderError(f"Object classes file not found: {classes}")
                print(f"Uploading {classes} -> /sd/models/classes.txt", flush=True)
                client.write_file("/sd/models/classes.txt", classes.read_bytes())

            if label_map is not None:
                if not label_map.exists():
                    raise LoaderError(f"Object label map file not found: {label_map}")
                print(f"Uploading {label_map} -> /sd/models/label_map.json", flush=True)
                client.write_file("/sd/models/label_map.json", label_map.read_bytes())

        if args.reset_after:
            client.exec_raw("import machine\nmachine.reset()", timeout_s=2.0)
    finally:
        try:
            client.exit_raw_repl()
        except Exception:
            pass
        client.close()


def upload_files_via_maixctl(upload_code: bool, upload_models: bool, args: argparse.Namespace) -> None:
    if upload_code:
        maixctl_ensure_dir(args, APP_REMOTE_DIR)
        for name in DEFAULT_APP_FILES:
            src = REPO_ROOT / name
            if not src.exists():
                raise LoaderError(f"Missing app file: {src}")
            remote_path = f"{APP_REMOTE_DIR}/{src.name}"
            print(f"Uploading {src.name} -> {remote_path} (maixctl)", flush=True)
            maixctl_upload_file(args, src, remote_path)

        with tempfile.NamedTemporaryFile("wb", suffix=".py", delete=True) as tmp:
            tmp.write(FLASH_LAUNCHER_CODE.encode("utf-8"))
            tmp.flush()
            for launcher_path in FLASH_LAUNCHER_PATHS:
                print(f"Uploading launcher -> {launcher_path} (maixctl)", flush=True)
                maixctl_upload_file(args, Path(tmp.name), launcher_path)

    if upload_models:
        model, classes = choose_model_inputs(args)
        label_map = args.object_label_map

        if any(x is not None for x in (model, classes, label_map)):
            maixctl_ensure_dir(args, "/sd/models")

        if model is not None:
            if not model.exists():
                raise LoaderError(f"Object model file not found: {model}")
            print(f"Uploading {model} -> /sd/models/objects.kmodel (maixctl)", flush=True)
            maixctl_upload_file(args, model, "/sd/models/objects.kmodel")

        if classes is not None:
            if not classes.exists():
                raise LoaderError(f"Object classes file not found: {classes}")
            print(f"Uploading {classes} -> /sd/models/classes.txt (maixctl)", flush=True)
            maixctl_upload_file(args, classes, "/sd/models/classes.txt")

        if label_map is not None:
            if not label_map.exists():
                raise LoaderError(f"Object label map file not found: {label_map}")
            print(f"Uploading {label_map} -> /sd/models/label_map.json (maixctl)", flush=True)
            maixctl_upload_file(args, label_map, "/sd/models/label_map.json")

    if args.reset_after:
        maixctl_reset(args)


def main() -> int:
    args = parse_args()

    try:
        if args.firmware:
            print(f"Flashing firmware: {args.firmware}", flush=True)
            flash_with_kflash(args.port, args.flash_baud, args.firmware)

        if args.flash_face:
            print(f"Flashing face model: {args.flash_face}", flush=True)
            flash_with_kflash(args.port, args.flash_baud, args.flash_face)

        upload_code = not args.no_code
        upload_models = not args.no_models
        if upload_code or upload_models:
            backend = args.deploy_backend
            if backend == "auto":
                backend = "maixctl" if have_maixctl() else "raw"

            if backend == "maixctl":
                upload_files_via_maixctl(upload_code, upload_models, args)
            else:
                upload_files(args.port, args.uart_baud, upload_code, upload_models, args)

        print("Done.", flush=True)
        return 0
    except LoaderError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
