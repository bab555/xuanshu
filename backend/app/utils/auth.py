"""
认证工具函数
"""
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from app.config import settings

# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """哈希密码"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT Access Token
    
    Args:
        data: payload（至少包含 sub）
        expires_delta: 自定义过期时间
    """
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=settings.jwt_expire_hours))
    to_encode = {**data, "exp": expire, "iat": datetime.utcnow()}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """解码 JWT Token，返回 payload（失败返回 None）"""
    try:
        return jwt.decode(
            token, 
            settings.jwt_secret, 
            algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None


# ===== Backward compatible helpers (used by routers/dependencies) =====

def create_token(user_id: str) -> str:
    """创建 JWT Token（兼容旧接口）"""
    return create_access_token(data={"sub": user_id}, expires_delta=timedelta(hours=settings.jwt_expire_hours))


def decode_token(token: str) -> Optional[str]:
    """解码 JWT Token，返回 user_id（兼容旧接口）"""
    payload = decode_access_token(token)
    if not payload:
        return None
    return payload.get("sub")

