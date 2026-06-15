"""Fix route order - contacts must be registered before catch-all routes"""
with open("/opt/chainke/backend/app/main.py", "r") as f:
    content = f.read()

# Move contacts.router from last to just after auth.router
content = content.replace(
    "app.include_router(auth.router)\napp.include_router(products.router)",
    "app.include_router(auth.router)\napp.include_router(contacts.router)\napp.include_router(products.router)"
)
content = content.replace(
    "app.include_router(contacts.router)\n",
    "",
    1  # Only remove the first occurrence (the one at the end)
)

import ast
ast.parse(content)
print("Syntax OK")
with open("/opt/chainke/backend/app/main.py", "w") as f:
    f.write(content)
print("Reordered: contacts.router moved before products.router")
