"""Run the portable local model and the assistant; no keys or system install."""
from pathlib import Path
from urllib.request import urlopen
import argparse
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-port", type=int, default=8089)
    parser.add_argument("--port", type=int, default=8087)
    parser.add_argument("--model-only", action="store_true")
    parser.add_argument("--runtime-dir", type=Path, default=ROOT / ".runtime")
    parser.add_argument("--device", default="Vulkan0")
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    runtime = args.runtime_dir
    binaries = list((runtime / "llama-vulkan").rglob("llama-server.exe"))
    model = runtime / "Qwen3.5-2B-Q4_K_M.gguf"
    if len(binaries) != 1 or not model.is_file():
        raise SystemExit("Prepare the runtime first: python setup_local_llm.py")
    base = f"http://127.0.0.1:{args.model_port}"
    try:
        urlopen(base + "/health", timeout=1).close()
    except OSError:
        pass
    else:
        raise SystemExit(f"Port {args.model_port} already has a server; choose --model-port")
    log = (runtime / "generation-server.log").open("w", encoding="utf-8")
    command = [str(binaries[0]), "-m", str(model), "--alias", "qwen3.5-2b", "--host", "127.0.0.1", "--port", str(args.model_port), "-c", "4096", "--parallel", "1", "--threads", "4", "-ngl", "auto", "--jinja"]
    if args.cpu:
        command[command.index("-ngl") + 1] = "0"
    else:
        command.extend(["--device", args.device])
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    app = None
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Model server stopped. See .runtime/generation-server.log")
            try:
                with urlopen(base + "/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.5)
        else:
            raise TimeoutError("Model did not become ready. See .runtime/generation-server.log")
        print(f"Real local LLM ready: {base}", flush=True)
        if args.model_only:
            process.wait()
        else:
            env = {**os.environ, "LLM_PROVIDER": "local", "LOCAL_LLM_URL": base}
            app = subprocess.Popen([sys.executable, "-X", "utf8", "server.py", "--port", str(args.port)], cwd=ROOT, env=env)
            app.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if app and app.poll() is None:
            app.terminate()
            app.wait(timeout=5)
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        log.close()
