"""Remove old security.py file"""
import os

security_file = r"D:\Projects\Projects Inprogress\FYP\SmartCarpoolingApp\backend\app\core\security.py"

if os.path.exists(security_file):
    os.remove(security_file)
    print(f"✅ Removed {security_file}")
else:
    print(f"File already removed or doesn't exist: {security_file}")
