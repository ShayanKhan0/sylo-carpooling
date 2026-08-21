# 🚗 SmartCarpoolingApp

**Final Year Project by:**  
- M. Mobeen Shoukat Ch  
- M. Shayan Khan  

**Bachelor of Computer Science (7th Semester)**  
Bahria University, Islamabad

---

## 📄 Description
This repository hosts the **Smart Carpooling App for Educational Institutions and Office Organizations**, a modular, scalable, and production-grade carpooling solution.  
It implements all functionalities described in the file **SmartCarpoolingApp_Final_Functionalities_Modular.pdf**, including AI-based clustering, anomaly detection, ride scheduling, SOS safety features, online payments, and verified profiles.

## 🧰 Tech Stack
- **Frontend:** Flutter  
- **Backend:** FastAPI (Python)  
- **Database:** PostgreSQL  
- **Maps & Geolocation:** Google Maps API  
- **Notifications:** Firebase Cloud Messaging (for push notifications only)

## 🧩 Architecture
Modular mono-repo with distinct modules for authentication, ride management, payment integration, safety, AI clustering, and notifications.

## 🧑‍💻 Project Principles
- Fully modular and scalable architecture  
- Production-ready structure following industry standards  
- Clean code with detailed comments for each logic block  
- Microservice-ready structure  
- All secrets handled through environment variables

## ⚙️ Environment Variables
Refer to `ENV_EXAMPLE.md` for a complete list of required environment variables.

## 🛠️ Development Setup

### Windows Stable Local Run (recommended)

To prevent recurring "Cannot reach the backend" errors during local testing, use the PowerShell launchers in `scripts`:

```powershell
# 1) Ensure backend is up on :8001 once
powershell -ExecutionPolicy Bypass -File .\scripts\ensure-backend-8001.ps1 -SingleRun

# 2) Start Edge frontend on any port (default 3002)
powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend-edge.ps1 -Port 3002

# Optional: keep backend auto-restarting in a watchdog window
powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend-edge.ps1 -Port 3002 -WatchBackend
```

Notes:
- `ensure-backend-8001.ps1` starts backend automatically if health check fails.
- `start-frontend-edge.ps1` always verifies backend before launching Flutter on Edge.

### 🧹 Code Quality
This project uses **pre-commit hooks** for linting and formatting.

**Setup:**
```bash
pip install pre-commit
pre-commit install
```

Hooks will automatically run Black, Ruff, isort, and dart format before every commit.

## 🧠 Target
The system should handle high concurrent user loads (100k+ active users) without crashes or bottlenecks.  
Target performance benchmark: comparable to Uber, Careem, Yango, and inDrive.

---

**License:** MIT  
**Version:** 1.0.0  
