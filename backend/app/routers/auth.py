"""认证路由：登录/注册/微信登录/获取当前用户"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import (
    ApiResponse, LoginRequest, RegisterRequest, TokenResponse,
    UserResponse, WechatLoginRequest,
)
from app.auth import (
    verify_password, hash_password, create_access_token,
    get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES,
)

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=ApiResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return ApiResponse(
        code=200,
        message="登录成功",
        data={
            "token": token,
            "user": UserResponse.model_validate(user).model_dump(),
        },
    )


@router.post("/register", response_model=ApiResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # 创建用户
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        name=req.name,
        phone=req.phone,
        company=req.company,
        position=req.position,
        role=req.role,
        avatar=f"https://api.dicebear.com/7.x/avataaars/svg?seed={req.username}",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return ApiResponse(
        code=200,
        message="注册成功",
        data=UserResponse.model_validate(user).model_dump(),
    )


@router.get("/me", response_model=ApiResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return ApiResponse(
        code=200,
        message="success",
        data=UserResponse.model_validate(current_user).model_dump(),
    )


@router.post("/wechat-login", response_model=ApiResponse)
def wechat_login(req: WechatLoginRequest, db: Session = Depends(get_db)):
    """微信登录（模拟）"""
    # 模拟微信登录：根据code查找或创建用户
    # 实际应调用微信API获取openId
    mock_openid = f"wx_{req.code[:8] if len(req.code) >= 8 else req.code}"
    mock_username = f"wechat_{mock_openid[:10]}"

    user = db.query(User).filter(User.username == mock_username).first()
    if not user:
        # 自动创建微信用户
        user = User(
            username=mock_username,
            password_hash=hash_password("wechat_default"),
            name=f"微信用户_{mock_openid[:6]}",
            role="buyer",
            avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=wechat",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(
        data={"sub": user.username, "role": user.role},
    )

    return ApiResponse(
        code=200,
        message="微信登录成功",
        data={
            "token": token,
            "user": UserResponse.model_validate(user).model_dump(),
        },
    )
