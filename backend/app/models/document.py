"""
文档相关模型
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Document(Base):
    """文档表"""
    __tablename__ = "documents"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), default="未命名文档")
    status = Column(String(20), default="draft")  # draft, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 软删除：仅对 owner 隐藏，不影响已抄送者访问
    owner_deleted_at = Column(DateTime, nullable=True)
    
    # 关系
    owner = relationship("User", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document", order_by="DocumentVersion.created_at.desc()")
    shares = relationship("DocumentShare", back_populates="document")
    workflow_runs = relationship("WorkflowRun", back_populates="document", order_by="WorkflowRun.started_at.desc()")
    attachments = relationship("Attachment", back_populates="document")
    
    def __repr__(self):
        return f"<Document {self.title}>"


class DocumentVersion(Base):
    """文档版本表"""
    __tablename__ = "document_versions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    content_md = Column(Text, default="")  # 文档内容（Markdown，含 Mermaid/HTML 标记）
    doc_variables = Column(JSON, default=dict)  # 文档变量
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    document = relationship("Document", back_populates="versions")
    
    def __repr__(self):
        return f"<DocumentVersion {self.id[:8]}>"


class DocumentShare(Base):
    """文档抄送表"""
    __tablename__ = "document_shares"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    from_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    to_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # 软删除：仅对接收者隐藏，不影响抄送方与其他接收者
    deleted_at = Column(DateTime, nullable=True)
    
    # 关系
    document = relationship("Document", back_populates="shares")
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
    
    def __repr__(self):
        return f"<DocumentShare {self.document_id[:8]} -> {self.to_user_id[:8]}>"

