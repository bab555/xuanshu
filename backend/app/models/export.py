"""
导出记录模型
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Export(Base):
    """导出记录表"""
    __tablename__ = "exports"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    version_id = Column(String(36), ForeignKey("document_versions.id"), nullable=True)
    
    # 状态
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    
    # 结果
    download_path = Column(String(500), nullable=True)  # DOCX 文件路径
    artifacts = Column(JSON, default=list)  # 渲染产物（PNG 等）
    error = Column(Text, nullable=True)  # 错误信息
    
    # 时间
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # 关系
    document = relationship("Document")
    user = relationship("User")
    version = relationship("DocumentVersion")
    
    def __repr__(self):
        return f"<Export {self.id[:8]} status={self.status}>"

