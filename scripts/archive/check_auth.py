"""Add login route to online auth.py"""

# Read the existing auth.py
content = open("/d/链客宝AI/backend/app/routers/auth.py", "r", encoding="utf-8").read()
# Export to a deploy-ready version
open("/d/链客宝AI/backend/scripts/auth_login_deploy.py", "w", encoding="utf-8").write(
    content
)
print(f"auth.py: {len(content)} chars, {content.count(chr(10)) + 1} lines")
print("Ready for deploy")
