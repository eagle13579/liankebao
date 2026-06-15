"""Fix main.py - remove config import that causes validation error"""
import os

path = "/opt/chainke/backend/app/main.py"

with open(path, "r") as f:
    content = f.read()

# Remove the from app.config import settings line
content = content.replace(
    'from app.config import settings\n',
    ''
)

# Remove references to settings.CORS_ORIGINS
content = content.replace(
    'if settings.CORS_ORIGINS and settings.CORS_ORIGINS != "*":',
    'if False:'
)

with open(path, "w") as f:
    f.write(content)

import ast
ast.parse(content)
print("Syntax OK")
print(f"Written {len(content)} bytes")
