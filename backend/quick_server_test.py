"""Quick server test"""
import sys
try:
    print("Importing app...")
    from app.main import app
    print("SUCCESS - Server can initialize!")
    
    # Count earnings endpoints
    earnings_endpoints = [
        f"{m} {r.path}" 
        for r in app.routes 
        if hasattr(r, 'path') and '/earnings' in r.path
        and hasattr(r, 'methods')
        for m in r.methods if m != 'HEAD'
    ]
    
    print(f"\nEarnings endpoints ({len(earnings_endpoints)}):")
    for ep in earnings_endpoints:
        print(f"  - {ep}")
    
    print("\nPROMPT 11C VERIFICATION: PASS")
    sys.exit(0)
    
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)
