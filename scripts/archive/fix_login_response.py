"""Fix login response format - add access_token and user data"""

path = "/opt/chainke/backend/app/routers/auth.py"
with open(path, "r") as f:
    content = f.read()

# Update login return to match frontend expectations
old = """    user = db.query(User).filter(User.wx_openid == openid).first()
    if not user:
        # Create user if not exists
        user = User(
            wx_openid=openid,
            nickname=username,
            company="链客宝AI",
            share_code=_generate_share_code(),
            roles=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if expected_pwd != password:
        raise HTTPException(status_code=401, detail="密码错误")

    token = create_access_token(data={"sub": str(user.id), "user_id": user.id})
    return WxLoginResponse(token=token, is_new_user=False, user_id=user.id)"""

new = """    user = db.query(User).filter(User.wx_openid == openid).first()
    if not user:
        # Create user if not exists
        user = User(
            wx_openid=openid,
            nickname=username,
            company="链客宝AI",
            share_code=_generate_share_code(),
            roles=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if expected_pwd != password:
        raise HTTPException(status_code=401, detail="密码错误")

    token = create_access_token(data={"sub": str(user.id), "user_id": user.id})
    # Return both token and access_token for frontend compatibility, plus user info
    return {
        "token": token,
        "access_token": token,
        "user_id": user.id,
        "is_new_user": False,
        "user": {
            "id": user.id,
            "nickname": user.nickname or username,
            "avatar": user.avatar or "",
            "avatar_url": user.avatar_url or "",
            "phone": user.phone or "",
            "company": user.company or "",
            "position": user.position or "",
        }
    }"""

content = content.replace(old, new)

# Also change the return type annotation
content = content.replace("response_model=WxLoginResponse", "response_model=None")

with open(path, "w") as f:
    f.write(content)

import ast

ast.parse(content)
print("Syntax OK")
