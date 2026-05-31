"""Add missing schemas to online server"""
path = "/opt/chainke/backend/app/schemas.py"
with open(path, "r") as f:
    content = f.read()

if "class ApiResponse" not in content:
    api_response = '''

# ===== 通用响应 =====
class ApiResponse(BaseModel):
    """统一API响应格式"""
    code: int = 200
    message: str = "success"
    data: object = None
'''
    content = content.replace("# ===== 联系人", api_response + "\n# ===== 联系人")
    
    with open(path, "w") as f:
        f.write(content)
    print("Added ApiResponse")
else:
    print("ApiResponse already exists")

import ast
ast.parse(content)
print("Syntax OK")
