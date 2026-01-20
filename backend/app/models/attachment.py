"""
附件模型
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Attachment(Base):
    """附件表"""
    __tablename__ = "attachments"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=True)  # MIME type
    filepath = Column(String(500), nullable=False)  # 服务器存储路径
    
    # 分析状态
    status = Column(String(20), default="pending")  # pending, analyzing, completed, failed
    summary = Column(Text, nullable=True)  # LONG 模型分析的摘要
    analysis_result = Column(JSON, nullable=True)  # 完整分析结果
    error = Column(Text, nullable=True)  # 分析失败的错误信息
    
    # 时间
    created_at = Column(DateTime, default=datetime.utcnow)
    analyzed_at = Column(DateTime, nullable=True)
    
    # 关系
    document = relationship("Document", back_populates="attachments")
    
    def __repr__(self):
        return f"<Attachment {self.filename}>"

