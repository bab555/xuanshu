"""
文件存储工具
"""
import os
import uuid
import aiofiles
from typing import Optional

from app.config import settings


async def save_file(
    content: bytes,
    filename: str,
    subdir: str = "attachments"
) -> str:
    """
    保存文件到存储目录
    
    Args:
        content: 文件内容
        filename: 原始文件名
        subdir: 子目录（attachments/exports）
    
    Returns:
        保存的文件路径
    """
    # 生成唯一文件名
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4()}{ext}"
    
    # 确保目录存在
    dir_path = os.path.join(settings.storage_path, subdir)
    os.makedirs(dir_path, exist_ok=True)
    
    # 保存文件
    filepath = os.path.join(dir_path, unique_name)
    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(content)
    
    return filepath


def get_file_url(filepath: str) -> str:
    """
    获取文件的访问 URL
    
    Args:
        filepath: 文件路径
    
    Returns:
        可访问的 URL
    """
    # 转换为相对于 storage 的路径
    if filepath.startswith(settings.storage_path):
        relative = filepath[len(settings.storage_path):].lstrip(os.sep)
        return f"/storage/{relative.replace(os.sep, '/')}"
    return filepath


def ensure_dir(path: str):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)

