"""
认证相关 Schema
"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)


class AuthResponse(BaseModel):
    """认证响应"""
    user_id: str
    username: str
    token: str


class UserInfo(BaseModel):
    """用户信息"""
    user_id: str
    username: str
    
    class Config:
        from_attributes = True

