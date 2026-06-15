"""Register contacts routes directly on the app object"""
with open("/opt/chainke/backend/app/main.py", "r") as f:
    content = f.read()

# Instead of include_router, register contacts routes inline
old = "from app.routers import auth, products, orders, promoter, admin, analytics, user, crm, contacts"
new = "from app.routers import auth, products, orders, promoter, admin, analytics, user, crm"
content = content.replace(old, new)

# Remove contacts.router from include_router
content = content.replace(
    "app.include_router(contacts.router)\n",
    ""
)

# Add contacts routes inline
inline_routes = '''

# ===== 联系人路由（内联注册，避免/ api / { id } 路由冲突） =====
from app.routers.contacts import router as _contacts_router
app.include_router(_contacts_router)
'''

content = content.replace(
    "app.include_router(crm.router)",
    "app.include_router(crm.router)" + inline_routes
)

import ast
ast.parse(content)
print("Syntax OK")
with open("/opt/chainke/backend/app/main.py", "w") as f:
    f.write(content)
print("Updated")
