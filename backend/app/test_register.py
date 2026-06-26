
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Override port
os.environ['PORT'] = '8002'

from app.main import app
import uvicorn

# Print registered routes
for route in app.routes:
    if hasattr(route, 'path') and 'auth' in (route.path or ''):
        print(f"  {route.methods} {route.path}")

print("\nServing on :8002...")
uvicorn.run(app, host="0.0.0.0", port=8002)
