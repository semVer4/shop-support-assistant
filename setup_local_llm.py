"""Download and verify the portable Vulkan runtime and Qwen GGUF model."""
from pathlib import Path
import argparse
from urllib.request import Request, urlopen
from zipfile import ZipFile
import hashlib
import json
import time

ROOT = Path(__file__).resolve().parent / ".runtime"
ASSETS = (
    ("llama-vulkan.zip", "https://github.com/ggml-org/llama.cpp/releases/download/b12069/llama-b12069-bin-win-vulkan-x64.zip", "e1b1c4e5481fe88e3f49f97908b53bb7699ad8aa3f6332a58f944e7a8f068b33", 37554286),
    ("Qwen3.5-2B-Q4_K_M.gguf", "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf", "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223", 1280835840),
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, default=ROOT)
    ROOT = parser.parse_args().runtime_dir.resolve()
    ROOT.mkdir(parents=True, exist_ok=True)
    archive = download(*ASSETS[0])
    runtime = ROOT / "llama-vulkan"
    runtime.mkdir(exist_ok=True)
    with ZipFile(archive) as files:
        for member in files.infolist():
            target = (runtime / member.filename).resolve()
            if not target.is_relative_to(runtime.resolve()):
                raise ValueError("Unexpected archive path")
        files.extractall(runtime)
    download(*ASSETS[1])
    (ROOT / "verified-generation.json").write_text(json.dumps({"runtime": "llama.cpp b12069 Vulkan x64", "model": "Qwen3.5-2B Q4_K_M (Unsloth GGUF)", "verified_files": [{"name": name, "source": url, "sha256": sha, "size": size} for name, url, sha, size in ASSETS]}, indent=2), encoding="utf-8")
    print("Local runtime ready. Start: python start_local_llm.py", flush=True)
