"""Fix login route - online User model has no username field"""

path = "/opt/chainke/backend/app/routers/auth.py"
with open(path, "r") as f:
    content = f.read()

# Old login route
old_login = '''@router.post("/auth/login", response_model=WxLoginResponse)
def login(data: dict, db: Session = Depends(get_db)):
    """用户名密码登录（开发/测试用）"""
    username = data.get("username", "")
    password = data.get("password", "")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if _PASSWORD_MAP.get(username) != password:
        raise HTTPException(status_code=401, detail="密码错误")

    token = create_access_token(data={"sub": str(user.id), "user_id": user.id})
    return WxLoginResponse(token=token, is_new_user=False, user_id=user.id)'''

new_login = '''@router.post("/auth/login", response_model=WxLoginResponse)
def login(data: dict, db: Session = Depends(get_db)):
    """用户名密码登录（开发/测试用）"""
    username = data.get("username", "")
    password = data.get("password", "")
    expected_pwd = _PASSWORD_MAP.get(username, "")
    if not expected_pwd:
        raise HTTPException(status_code=404, detail="用户不存在")

    # Map username to wx_openid for the online model (no username field)
    wx_map = {"admin": "test_admin", "test_contacts": "test_contacts_fixed"}
    openid = wx_map.get(username, username)

    user = db.query(User).filter(User.wx_openid == openid).first()
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
    return WxLoginResponse(token=token, is_new_user=False, user_id=user.id)'''

content = content.replace(old_login, new_login)

with open(path, "w") as f:
    f.write(content)

import ast

ast.parse(content)
print("Syntax OK")
