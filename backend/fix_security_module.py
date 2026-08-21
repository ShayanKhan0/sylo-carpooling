"""
Fix the security module naming conflict
"""
import os
import shutil

# Define paths
security_file = r"D:\Projects\Projects Inprogress\FYP\SmartCarpoolingApp\backend\app\core\security.py"
auth_utils_file = r"D:\Projects\Projects Inprogress\FYP\SmartCarpoolingApp\backend\app\core\auth_utils.py"

# Check if security.py exists
if os.path.exists(security_file):
    print(f"Moving {security_file} to {auth_utils_file}")
    shutil.move(security_file, auth_utils_file)
    print("✅ File moved successfully")
else:
    print(f"❌ {security_file} not found")

# Create __init__.py in security directory if it doesn't exist
security_init = r"D:\Projects\Projects Inprogress\FYP\SmartCarpoolingApp\backend\app\core\security\__init__.py"
if not os.path.exists(security_init):
    with open(security_init, 'w') as f:
        f.write('"""Security package"""\n')
    print("✅ Created __init__.py in security directory")
else:
    print("✅ security/__init__.py already exists")
