"""
文档相关 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime


class DocumentCreate(BaseModel):
    """创建文档请求"""
    title: Optional[str] = "未命名文档"


class DocumentUpdate(BaseModel):
    """更新文档请求（创建新版本）"""
    title: Optional[str] = None
    content_md: Optional[str] = None
    doc_variables: Optional[Dict[str, Any]] = None


class DocumentInfo(BaseModel):
    """文档信息"""
    doc_id: str
    title: str
    status: str
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DocumentDetail(BaseModel):
    """文档详情"""
    doc_id: str
    title: str
    status: str
    owner: dict
    latest_version: Optional[dict] = None
    workflow_runs: List[dict] = []
    shares: List[dict] = []
    
    class Config:
        from_attributes = True


class ShareRequest(BaseModel):
    """抄送请求"""
    to_username: str
    note: Optional[str] = None


class ShareInfo(BaseModel):
    """抄送信息"""
    doc_id: str
    title: str
    from_user: str
    shared_at: datetime
    
    class Config:
        from_attributes = True

