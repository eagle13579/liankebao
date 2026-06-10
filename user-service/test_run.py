import sys
sys.path.insert(0, '/var/www/liankebao/backend')
try:
    from app.routers.auth import router
    print(f"✅ auth router imported: {len(router.routes)} routes")
except Exception as e:
    print(f"❌ import failed: {e}")
