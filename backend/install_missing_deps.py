import subprocess
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
venv_python = backend_dir / ".venv" / "Scripts" / "python.exe"

packages = ["python-multipart", "email-validator"]

for package in packages:
    print(f"Installing {package}...", flush=True)
    result = subprocess.run(
        [str(venv_python), "-m", "pip", "install", package],
        cwd=str(backend_dir),
        capture_output=False,
        text=True
    )
    if result.returncode != 0:
        print(f"Failed to install {package}", flush=True)
        sys.exit(1)

print("\nAll packages installed successfully!", flush=True)
sys.exit(0)
