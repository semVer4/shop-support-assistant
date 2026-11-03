"""Bot token: environment variable or Windows DPAPI, never committed to Git."""
from pathlib import Path
import os
import re
import subprocess

TOKEN_PATH = Path(__file__).resolve().parent / ".runtime" / "telegram-token.dpapi"
ENCRYPT = "$ErrorActionPreference='Stop'; $value=[Console]::In.ReadToEnd(); $secure=ConvertTo-SecureString -String $value -AsPlainText -Force; ConvertFrom-SecureString -SecureString $secure"
DECRYPT = "$ErrorActionPreference='Stop'; $secure=ConvertTo-SecureString -String ([Console]::In.ReadToEnd()); $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure); try { [Console]::Out.Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }"


def validate_token(token):
    if not isinstance(token, str) or not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{30,60}", token.strip()):
        raise ValueError("Некорректный формат токена Telegram")
    return token.strip()


def transform(value, script):
    if os.name != "nt":
        raise RuntimeError("На этой системе задайте TELEGRAM_BOT_TOKEN через окружение")
    result = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script], input=value, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("Не удалось обработать локальный токен через Windows DPAPI")
    return result.stdout.strip()


def save_token(token):
    protected = transform(validate_token(token), ENCRYPT)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(protected, encoding="ascii")


def load_token():
    value = os.environ.get("TELEGRAM_BOT_TOKEN")
    if value:
        return validate_token(value)
    if TOKEN_PATH.is_file():
        return validate_token(transform(TOKEN_PATH.read_text(encoding="ascii"), DECRYPT))
    raise RuntimeError("Токен не задан. Запустите python configure_telegram.py")
