from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_MODEL_REPO = "unsloth/Nemotron-3-Nano-30B-A3B-GGUF"
DEFAULT_MODEL_FILE = "Nemotron-3-Nano-30B-A3B-UD-Q8_K_XL.gguf"
DEFAULT_MODEL_NAME = "nemotron"
DEFAULT_PORT = 30000
DEFAULT_READY_TIMEOUT_SECONDS = 900


class NemotronRuntimeError(RuntimeError):
    pass


def ensure_local_nemotron(setup_only: bool = False) -> subprocess.Popen[bytes] | None:
    """Ensure a local OpenAI-compatible Nemotron endpoint is ready.

    This follows NVIDIA's DGX Spark llama.cpp path. It is intentionally opt-in
    because first-time setup downloads a large model and builds llama.cpp.
    """

    config = _runtime_config()
    os.environ["NIM_BASE_URL"] = config["base_url"]
    os.environ["NIM_MODEL"] = config["model_name"]

    if _endpoint_ready(config["base_url"], config["model_name"], timeout=2.0):
        print(f"Nemotron endpoint already running at {config['base_url']}")
        return None

    if platform.system().lower() != "linux":
        raise NemotronRuntimeError("--with-nemotron setup is supported on Linux DGX Spark only.")

    _ensure_llama_cpp(config)
    _ensure_model(config)

    if setup_only:
        print("Nemotron setup complete. Start the app with `python3 app.py --with-nemotron`.")
        return None

    return _start_llama_server(config)


def stop_managed_nemotron(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    print("Stopping managed Nemotron server...")
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _runtime_config() -> dict[str, Any]:
    home = Path(
        os.getenv("CONTRACT_RADAR_NEMOTRON_HOME", Path.home() / ".contract-radar" / "nemotron")
    ).expanduser()
    model_repo = os.getenv("CONTRACT_RADAR_NEMOTRON_MODEL_REPO", DEFAULT_MODEL_REPO)
    model_file = os.getenv("CONTRACT_RADAR_NEMOTRON_MODEL_FILE", DEFAULT_MODEL_FILE)
    model_name = os.getenv("CONTRACT_RADAR_NEMOTRON_MODEL_NAME", DEFAULT_MODEL_NAME)
    port = int(os.getenv("CONTRACT_RADAR_NEMOTRON_PORT", str(DEFAULT_PORT)))
    base_url = os.getenv("CONTRACT_RADAR_NEMOTRON_BASE_URL", f"http://127.0.0.1:{port}/v1").rstrip("/")
    return {
        "home": home,
        "venv_dir": home / "nemotron-venv",
        "llama_dir": home / "llama.cpp",
        "build_dir": home / "llama.cpp" / "build",
        "server_bin": home / "llama.cpp" / "build" / "bin" / "llama-server",
        "model_dir": home / "models" / "nemotron3-gguf",
        "model_path": home / "models" / "nemotron3-gguf" / model_file,
        "model_repo": model_repo,
        "model_file": model_file,
        "model_name": model_name,
        "port": port,
        "base_url": base_url,
        "log_path": home / "llama-server.log",
        "gpu_layers": os.getenv("CONTRACT_RADAR_NEMOTRON_GPU_LAYERS", "99"),
        "ctx_size": os.getenv("CONTRACT_RADAR_NEMOTRON_CTX_SIZE", "8192"),
        "threads": os.getenv("CONTRACT_RADAR_NEMOTRON_THREADS", "8"),
        "ready_timeout": int(
            os.getenv("CONTRACT_RADAR_NEMOTRON_READY_TIMEOUT_SECONDS", str(DEFAULT_READY_TIMEOUT_SECONDS))
        ),
    }


def _ensure_llama_cpp(config: dict[str, Any]) -> None:
    server_bin: Path = config["server_bin"]
    if server_bin.exists():
        return

    _require_commands(["git", "cmake", "make", "nvcc"])
    home: Path = config["home"]
    llama_dir: Path = config["llama_dir"]
    build_dir: Path = config["build_dir"]
    home.mkdir(parents=True, exist_ok=True)

    if not llama_dir.exists():
        _run(["git", "clone", "https://github.com/ggml-org/llama.cpp", str(llama_dir)])

    build_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "cmake",
            "..",
            "-DGGML_CUDA=ON",
            "-DCMAKE_CUDA_ARCHITECTURES=121",
            "-DLLAMA_CURL=OFF",
        ],
        cwd=build_dir,
    )
    _run(["make", "-j8"], cwd=build_dir)

    if not server_bin.exists():
        raise NemotronRuntimeError(f"llama-server was not built at {server_bin}")


def _ensure_model(config: dict[str, Any]) -> None:
    model_path: Path = config["model_path"]
    if model_path.exists():
        return

    venv_dir: Path = config["venv_dir"]
    model_dir: Path = config["model_dir"]
    model_dir.mkdir(parents=True, exist_ok=True)
    _ensure_hf_cli(venv_dir)
    hf = _hf_command(venv_dir)
    _run(
        [
            str(hf),
            "download",
            config["model_repo"],
            config["model_file"],
            "--local-dir",
            str(model_dir),
        ]
    )

    if not model_path.exists():
        raise NemotronRuntimeError(f"Nemotron model was not downloaded to {model_path}")


def _ensure_hf_cli(venv_dir: Path) -> None:
    python_bin = _venv_python(venv_dir)
    if not python_bin.exists():
        _run([sys.executable, "-m", "venv", str(venv_dir)])
    if not _hf_command(venv_dir, required=False):
        _run([str(python_bin), "-m", "pip", "install", "-U", "huggingface_hub[cli]"])


def _start_llama_server(config: dict[str, Any]) -> subprocess.Popen[bytes]:
    log_path: Path = config["log_path"]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    cmd = [
        str(config["server_bin"]),
        "--model",
        str(config["model_path"]),
        "--host",
        "0.0.0.0",
        "--port",
        str(config["port"]),
        "--n-gpu-layers",
        config["gpu_layers"],
        "--ctx-size",
        config["ctx_size"],
        "--threads",
        config["threads"],
    ]
    print("Starting Nemotron model server...")
    print(f"Nemotron logs: {log_path}")
    process = subprocess.Popen(cmd, cwd=config["build_dir"], stdout=log_file, stderr=subprocess.STDOUT)
    log_file.close()
    _wait_for_endpoint(config, process)
    print(f"Nemotron endpoint ready at {config['base_url']}")
    return process


def _wait_for_endpoint(config: dict[str, Any], process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + int(config["ready_timeout"])
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise NemotronRuntimeError(
                f"Nemotron server exited early with code {process.returncode}. Check {config['log_path']}."
            )
        if _endpoint_ready(config["base_url"], config["model_name"], timeout=5.0):
            return
        time.sleep(5)
    stop_managed_nemotron(process)
    raise NemotronRuntimeError(f"Nemotron did not become ready before timeout. Check {config['log_path']}.")


def _endpoint_ready(base_url: str, model_name: str, timeout: float) -> bool:
    models_url = f"{base_url}/models"
    try:
        with request.urlopen(models_url, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True
    except (error.URLError, TimeoutError, OSError):
        pass

    payload = json.dumps(
        {
            "model": model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
    ).encode("utf-8")
    req = request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (error.URLError, TimeoutError, OSError):
        return False


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / "bin" / "python"


def _hf_command(venv_dir: Path, required: bool = True) -> Path | None:
    for name in ("hf", "huggingface-cli"):
        candidate = venv_dir / "bin" / name
        if candidate.exists():
            return candidate
    if required:
        raise NemotronRuntimeError(f"Hugging Face CLI was not installed under {venv_dir}")
    return None


def _require_commands(commands: list[str]) -> None:
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise NemotronRuntimeError(
            "Missing required command(s): "
            + ", ".join(missing)
            + ". Install the DGX Spark prerequisites from NVIDIA's Nemotron llama.cpp guide."
        )


def _run(command: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(command)
    print(f"$ {printable}")
    subprocess.run(command, cwd=cwd, check=True)
