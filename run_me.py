from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "enterprise_runtime"
VENV_DIR = BASE_DIR / "venv"
CONFIG_FILE = BASE_DIR / "config" / "tenants.json"
REQUIREMENTS_DIR = BASE_DIR / "requirements"
REQUIREMENTS_FILE = REQUIREMENTS_DIR / "base.txt"
RUNTIME_REQUIREMENTS_FILE = REQUIREMENTS_DIR / "runtime.txt"
LORA_REQUIREMENTS_FILE = REQUIREMENTS_DIR / "lora.txt"
FULL_REQUIREMENTS_FILE = REQUIREMENTS_DIR / "full.txt"
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
DEFAULT_LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama").strip().lower() or "ollama"
DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
DEFAULT_VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8001")
DEFAULT_API_HOST = os.getenv("API_HOST", "127.0.0.1")
DEFAULT_API_PORT = int(os.getenv("API_PORT", "8000"))
DEFAULT_STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))

REQUIRED_PACKAGE_FILES = [
    SOURCE_DIR / "__init__.py",
    SOURCE_DIR / "api.py",
    SOURCE_DIR / "config.py",
    SOURCE_DIR / "models.py",
    SOURCE_DIR / "tools_core.py",
    SOURCE_DIR / "tools_supporting.py",
    SOURCE_DIR / "utils.py",
    SOURCE_DIR / "workflow.py",
]


def run_command(
    cmd: List[str],
    extra_env: Dict[str, str] | None = None,
    allow_fail: bool = False,
    cwd: Path | None = None,
) -> bool:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        subprocess.check_call(cmd, cwd=str(cwd or BASE_DIR), env=env)
    except subprocess.CalledProcessError as exc:
        if allow_fail:
            return False
        print(f"EXECUTION ERROR: {exc}")
        raise
    return True


def spawn_process(
    cmd: Sequence[str],
    name: str,
    extra_env: Dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.Popen:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    print(f"--- Starting {name}: {' '.join(cmd)} ---")
    return subprocess.Popen(list(cmd), cwd=str(cwd or BASE_DIR), env=env)


def get_python_paths() -> Tuple[Path, Path]:
    if os.getenv("RUN_ME_USE_SYSTEM_PYTHON", "false").lower() == "true":
        python_exe = Path(sys.executable)
        return python_exe, python_exe
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe", VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "python", VENV_DIR / "bin" / "pip"


def base_python_env() -> Dict[str, str]:
    pythonpath = os.environ.get("PYTHONPATH", "")
    parts = [str(BASE_DIR)]
    if pythonpath:
        parts.append(pythonpath)
    return {"PYTHONPATH": os.pathsep.join(parts)}


def check_package_layout() -> None:
    missing = [path for path in REQUIRED_PACKAGE_FILES if not path.exists()]
    if not missing:
        print("--- Detected a complete enterprise_runtime package layout ---")
        return

    print("--- The package layout is missing required files ---")
    for path in missing:
        print(f"    - {path.relative_to(BASE_DIR)}")
    raise FileNotFoundError("Required package files are missing; startup cannot continue safely.")


def ensure_basic_dirs() -> None:
    for rel in [
        "data",
        "storage",
        "memory",
        "config",
        "data/shared/files",
        "data/tenants",
        "systems_evaluation/generated_reports",
        "systems_evaluation/artifacts",
    ]:
        (BASE_DIR / rel).mkdir(parents=True, exist_ok=True)


def ensure_venv() -> bool:
    if os.getenv("RUN_ME_USE_SYSTEM_PYTHON", "false").lower() == "true":
        print("--- [1/4] Using the container system Python; skipping virtualenv creation. ---")
        return False
    if not VENV_DIR.exists():
        print(f"--- [1/4] Creating a virtual environment (venv) for {os.name}... ---")
        run_command([sys.executable, "-m", "venv", str(VENV_DIR)])
        return True
    print("--- [1/4] Virtual environment already exists; skipping creation. ---")
    return False


def _install_requirements(python_exe: Path, requirement_file: Path, pip_env: Dict[str, str], label: str) -> None:
    if not requirement_file.exists():
        print(f"(!) Skipping {label}: {requirement_file.name} was not found")
        return
    print(f"--- Installing {label}: {requirement_file.name} ---")
    run_command(
        [
            str(python_exe),
            "-m",
            "pip",
            "install",
            "-r",
            str(requirement_file),
            "--retries",
            "10",
            "--timeout",
            "100",
        ],
        extra_env=pip_env,
    )


def ensure_requirements(setup_mode: str, upgrade_pip: bool = False) -> None:
    if setup_mode == "none":
        print("--- [2/4] Skipping requirements installation (fast mode). ---")
        return

    python_exe, _ = get_python_paths()
    pip_env = {
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_DEFAULT_TIMEOUT": "100",
    }
    print("--- [2/4] Checking and updating required dependencies... ---")
    if upgrade_pip:
        run_command(
            [str(python_exe), "-m", "pip", "install", "--upgrade", "pip", "--retries", "10"],
            extra_env=pip_env,
            allow_fail=True,
        )

    _install_requirements(python_exe, RUNTIME_REQUIREMENTS_FILE, pip_env, "runtime dependencies")
    if setup_mode == "full":
        _install_requirements(python_exe, LORA_REQUIREMENTS_FILE, pip_env, "LoRA/checklist-3 dependencies")


def _normalize_backend(value: str | None = None) -> str:
    raw = (value or DEFAULT_LLM_BACKEND or "ollama").strip().lower()
    if raw in {"vllm", "openai", "openai-compatible", "openai_compatible"}:
        return "vllm"
    return "ollama"


def _check_http_alive(url: str, timeout: float = 2.0) -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False


def check_ollama_alive() -> bool:
    return _check_http_alive(f"{DEFAULT_OLLAMA_BASE_URL.rstrip('/')}/api/tags")


def check_llm_backend_alive(backend: str | None = None) -> bool:
    backend = _normalize_backend(backend)
    if backend == "vllm":
        return _check_http_alive(f"{DEFAULT_VLLM_BASE_URL.rstrip('/')}/v1/models")
    return check_ollama_alive()


def load_models_from_config() -> List[str]:
    models = {DEFAULT_MODEL}
    if CONFIG_FILE.exists():
        try:
            configs = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for conf in configs.values():
                model_name = conf.get("model_name")
                if model_name:
                    models.add(model_name)
        except Exception:
            pass
    return sorted(models)


def ensure_ollama_models(pull_models: bool) -> None:
    if not pull_models:
        print("--- [3/4] Skipping Ollama model checks/pulls (fast mode). ---")
        return
    if _normalize_backend() != "ollama":
        print("--- [3/4] Skipping Ollama pulls because LLM_BACKEND is not ollama. ---")
        print("    The vLLM benchmark expects externally served models via VLLM_BASE_URL.")
        return
    print("--- [3/4] Checking Ollama and the configured models... ---")
    if not check_ollama_alive():
        print(f"(!) Could not connect to the Ollama server at {DEFAULT_OLLAMA_BASE_URL}.")
        print("    You can still run `api` or `ui`, but chat and benchmark flows will fail if they require an LLM.")
        return

    for model in load_models_from_config():
        print(f"    + Checking/pulling model: {model}")
        run_command(["ollama", "pull", model], allow_fail=True)


def ensure_environment(setup_mode: str, pull_models: bool, upgrade_pip: bool = False) -> Path:
    ensure_basic_dirs()
    venv_created = ensure_venv()
    effective_setup_mode = setup_mode
    if setup_mode == "auto":
        effective_setup_mode = "runtime" if venv_created else "none"
    ensure_requirements(effective_setup_mode, upgrade_pip=upgrade_pip)
    ensure_ollama_models(pull_models)
    check_package_layout()
    python_exe, _ = get_python_paths()
    return python_exe


def _wait_forever(processes: Sequence[Tuple[str, subprocess.Popen]]) -> None:
    print("--- The system is running. Press Ctrl+C to stop. ---")
    try:
        while True:
            time.sleep(1)
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    raise RuntimeError(f"Process `{name}` exited with code {code}.")
    finally:
        for name, proc in processes:
            if proc.poll() is None:
                print(f"--- Stopping {name} ---")
                proc.terminate()
        deadline = time.time() + 5
        for _, proc in processes:
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.2)
        for name, proc in processes:
            if proc.poll() is None:
                print(f"--- Force-stopping {name} ---")
                proc.kill()


def run_api(python_exe: Path, host: str, port: int) -> None:
    env = base_python_env()
    cmd = [
        str(python_exe),
        "-m",
        "uvicorn",
        "enterprise_runtime.api:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    run_command(cmd, extra_env=env, cwd=BASE_DIR)


def run_ui(python_exe: Path, port: int) -> None:
    env = base_python_env()
    cmd = [
        str(python_exe),
        "-m",
        "streamlit",
        "run",
        str(BASE_DIR / "streamlit_app.py"),
        "--server.port",
        str(port),
        "--server.headless",
        "true",
    ]
    run_command(cmd, extra_env=env, cwd=BASE_DIR)


def run_all(python_exe: Path, host: str, api_port: int, ui_port: int) -> None:
    env = base_python_env()
    api_cmd = [
        str(python_exe),
        "-m",
        "uvicorn",
        "enterprise_runtime.api:app",
        "--host",
        host,
        "--port",
        str(api_port),
    ]
    ui_cmd = [
        str(python_exe),
        "-m",
        "streamlit",
        "run",
        str(BASE_DIR / "streamlit_app.py"),
        "--server.port",
        str(ui_port),
        "--server.headless",
        "true",
    ]
    api_proc = spawn_process(api_cmd, "backend API", extra_env=env, cwd=BASE_DIR)
    time.sleep(2)
    ui_proc = spawn_process(ui_cmd, "Streamlit UI", extra_env=env, cwd=BASE_DIR)
    _wait_forever([("backend API", api_proc), ("Streamlit UI", ui_proc)])


def run_benchmark(python_exe: Path, dataset: str) -> None:
    env = base_python_env()
    retrieval_cmd = [
        str(python_exe),
        str(BASE_DIR / "systems_evaluation" / "evaluate_retrieval.py"),
        "--dataset",
        dataset,
        "--variants",
        "dense_raw",
        "dense_prioritized",
        "--json-out",
        "systems_evaluation/artifacts/retrieval_metrics_v2.json",
        "--report-out",
        "systems_evaluation/retrieval_results.md",
        "--error-out",
        "systems_evaluation/error_analysis.md",
    ]
    run_command(retrieval_cmd, extra_env=env, cwd=BASE_DIR)

    backend = _normalize_backend()
    if check_llm_backend_alive(backend):
        real_cmd = [
            str(python_exe),
            str(BASE_DIR / "systems_evaluation" / "run_real_benchmark.py"),
            "--dataset",
            dataset,
            "--label",
            "baseline_real",
            "--output-dir",
            "systems_evaluation/generated_reports",
            "--llm-backend",
            backend,
        ]
        run_command(real_cmd, extra_env=env, cwd=BASE_DIR, allow_fail=True)
    else:
        base_url = DEFAULT_VLLM_BASE_URL if backend == "vllm" else DEFAULT_OLLAMA_BASE_URL
        print(f"(!) Skipping answer-level benchmarking because the {backend} backend is not ready at {base_url}.")


def choose_mode_interactive() -> str:
    print("\nChoose a startup mode:")
    print("  1. backend API")
    print("  2. streamlit UI")
    print("  3. backend + UI")
    print("  4. benchmark/evaluation")
    print("  5. quit")
    raw = input("Enter your choice [default: 3]: ").strip()
    mapping = {
        "1": "api",
        "2": "ui",
        "3": "all",
        "4": "benchmark",
        "5": "quit",
        "": "all",
    }
    return mapping.get(raw, "all")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified launcher for the multi-tenant enterprise LLM project.")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["api", "ui", "all", "benchmark", "interactive"],
        default="interactive",
        help="System startup mode.",
    )
    parser.add_argument("--host", default=DEFAULT_API_HOST, help="Host for the backend API.")
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT, help="Port for the backend API.")
    parser.add_argument("--ui-port", type=int, default=DEFAULT_STREAMLIT_PORT, help="Port for the Streamlit UI.")
    parser.add_argument("--dataset", default="systems_evaluation/test_queries_multidomain.json", help="Dataset used for benchmark runs.")
    parser.add_argument(
        "--setup",
        choices=["auto", "none", "runtime", "full"],
        default="auto",
        help="Environment setup policy: auto installs runtime deps only for a new venv; full also installs LoRA dependencies.",
    )
    parser.add_argument(
        "--pull-models",
        action="store_true",
        help="Check and pull the Ollama models declared in the config.",
    )
    parser.add_argument(
        "--upgrade-pip",
        action="store_true",
        help="Upgrade pip before installing dependencies. Usually only needed on a fresh machine.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    python_exe = ensure_environment(
        setup_mode=args.setup,
        pull_models=args.pull_models,
        upgrade_pip=args.upgrade_pip,
    )
    print("--- [4/4] Environment ready. ---")

    mode = args.mode
    if mode == "interactive":
        mode = choose_mode_interactive()

    if mode == "quit":
        print("Exited on request.")
        return

    if mode == "api":
        run_api(python_exe, args.host, args.api_port)
        return

    if mode == "ui":
        run_ui(python_exe, args.ui_port)
        return

    if mode == "all":
        run_all(python_exe, args.host, args.api_port, args.ui_port)
        return

    if mode == "benchmark":
        run_benchmark(python_exe, args.dataset)
        return

    raise ValueError(f"Invalid mode: {mode}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped on request.")
    except Exception as exc:
        print(f"\n[FATAL ERROR]: {exc}")
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
