"""Download a portable CPU runtime and model from their official repositories."""
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile
import hashlib
import json
import time

ROOT = Path(__file__).resolve().parent / ".runtime"
ASSETS = (
    ("llama-cpu.zip", "https://github.com/ggml-org/llama.cpp/releases/download/b12069/llama-b12069-bin-win-cpu-x64.zip", "5658d79020c5b6a32f1e267c548383942d7c6c1784814f23b9da33d1f4eb0ff2", 24609224),
    ("qwen2.5-1.5b-instruct-q4_k_m.gguf", "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf", "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e", 1117320736),
)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def download(name, url, expected_hash, expected_size):
    target = ROOT / name
    if target.is_file() and target.stat().st_size == expected_size and digest(target) == expected_hash:
        print(f"Verified existing {name}", flush=True)
        return target
    temporary = target.with_suffix(target.suffix + ".part")
    request = Request(url, headers={"User-Agent": "shop-support-assistant-setup"})
    downloaded = 0
    last_update = time.monotonic()
    with urlopen(request, timeout=60) as response, temporary.open("wb") as file:
        while chunk := response.read(1024 * 1024):
            file.write(chunk)
            downloaded += len(chunk)
            if time.monotonic() - last_update >= 5:
                print(f"{name}: {downloaded / expected_size:.0%} ({downloaded // 1048576} MiB)", flush=True)
                last_update = time.monotonic()
    if temporary.stat().st_size != expected_size or digest(temporary) != expected_hash:
        raise ValueError(f"Size or SHA-256 mismatch: {name}")
    temporary.replace(target)
    print(f"Downloaded and verified {name}", flush=True)
    return target


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    archive = download(*ASSETS[0])
    runtime = ROOT / "llama"
    runtime.mkdir(exist_ok=True)
    with ZipFile(archive) as files:
        for member in files.infolist():
            target = (runtime / member.filename).resolve()
            if not target.is_relative_to(runtime.resolve()):
                raise ValueError("Unexpected archive path")
        files.extractall(runtime)
    download(*ASSETS[1])
    (ROOT / "verified.json").write_text(json.dumps({"runtime": "llama.cpp b12069 CPU x64", "model": "Qwen2.5-1.5B-Instruct Q4_K_M", "verified_files": [{"name": name, "source": url, "sha256": sha, "size": size} for name, url, sha, size in ASSETS]}, indent=2), encoding="utf-8")
    print("Local runtime ready. Start: python start_local_llm.py", flush=True)
