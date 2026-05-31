"""Fix Settings class - add extra='allow' to accept env vars"""
import os

path = "/opt/chainke/backend/app/config.py"
with open(path, "r") as f:
    content = f.read()

# Fix: replace the bad model_config line with the right one
content = content.replace(
    'model_config = {"extra": "allow"}\n    class Config:',
    '    class Config:\n        extra = "allow"'
)

with open(path, "w") as f:
    f.write(content)

import ast
ast.parse(content)
print("Syntax OK")
print(f"Fixed {len(content)} bytes")
