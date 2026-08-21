"""
Install missing dependencies and test server startup
"""
import subprocess
import sys

def install_package(package):
    """Install a package using pip"""
    print(f"Installing {package}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✅ {package} installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {package}: {e}")
        return False

def test_server_import():
    """Test if the server can be imported"""
    print("\n" + "=" * 70)
    print("Testing server import...")
    print("=" * 70)
    try:
        from app.main import app
        print("✅ Server can initialize successfully!")
        
        # Count endpoints
        endpoints = [
            f"{list(r.methods)[0]} {r.path}" 
            for r in app.routes 
            if hasattr(r, 'path') and hasattr(r, 'methods') and r.methods
        ]
        print(f"✅ Total endpoints: {len(endpoints)}")
        return True
    except Exception as e:
        print(f"❌ Server import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("SmartCarpoolingApp Backend - Dependency Check & Test")
    print("=" * 70)
    
    # List of required packages
    required_packages = [
        "python-multipart",
        "email-validator",
    ]
    
    # Install missing packages
    for package in required_packages:
        install_package(package)
    
    # Test server
    if test_server_import():
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED - Backend is ready!")
        print("=" * 70)
        sys.exit(0)
    else:
        print("\n" + "=" * 70)
        print("❌ TESTS FAILED - Please check errors above")
        print("=" * 70)
        sys.exit(1)
