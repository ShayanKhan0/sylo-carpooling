import subprocess
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
venv_python = backend_dir / ".venv" / "Scripts" / "python.exe"

print("Installing email-validator...", flush=True)
result = subprocess.run(
    [str(venv_python), "-m", "pip", "install", "email-validator"],
    cwd=str(backend_dir),
    capture_output=False,
    text=True
)
sys.exit(result.returncode)
