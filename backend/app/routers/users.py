"""
用户相关路由（用于抄送下拉列表等）
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.dependencies import get_current_user

router = APIRouter()


@router.get("", response_model=dict)
async def list_users(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出可选择的用户（用于抄送下拉）"""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return {
        "users": [
            {"user_id": u.id, "username": u.username}
            for u in users
            if u.id != user.id
        ]
    }


