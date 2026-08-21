"""
Script to run Alembic migrations directly without terminal issues
"""
import subprocess
import sys
from pathlib import Path

# Get the backend directory
backend_dir = Path(__file__).parent
venv_python = backend_dir / ".venv" / "Scripts" / "python.exe"

# Run alembic upgrade heads
print("Running alembic upgrade heads...", flush=True)
result = subprocess.run(
    [str(venv_python), "-m", "alembic", "upgrade", "heads"],
    cwd=str(backend_dir),
    capture_output=False,
    text=True
)

sys.exit(result.returncode)
