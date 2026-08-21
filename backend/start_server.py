import subprocess
import sys
import os
import certifi
from pathlib import Path

# Configure secure certificates for Firebase / External Requests
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

backend_dir = Path(__file__).parent
venv_python = backend_dir / ".venv" / "Scripts" / "python.exe"

print("Starting FastAPI backend server...", flush=True)
result = subprocess.run(
    [
        str(venv_python),
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ],
    cwd=str(backend_dir),
    capture_output=False,
    text=True
)
sys.exit(result.returncode)
