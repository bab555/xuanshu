"""
工作流相关模型
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class WorkflowRun(Base):
    """工作流运行记录"""
    __tablename__ = "workflow_runs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    triggered_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    current_node = Column(String(50), nullable=True)  # 当前执行到的节点
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    # 状态快照
    doc_variables = Column(JSON, default=dict)  # 工作流开始时的变量
    final_md = Column(Text, nullable=True)  # 最终文档（如果成功）
    error = Column(JSON, nullable=True)  # 错误信息（如果失败）
    
    # 关系
    document = relationship("Document", back_populates="workflow_runs")
    triggered_by = relationship("User")
    node_runs = relationship("WorkflowNodeRun", back_populates="workflow_run", order_by="WorkflowNodeRun.started_at")
    
    def __repr__(self):
        return f"<WorkflowRun {self.id[:8]} status={self.status}>"


class WorkflowNodeRun(Base):
    """工作流节点运行记录（中间栏展示的核心数据）"""
    __tablename__ = "workflow_node_runs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_run_id = Column(String(36), ForeignKey("workflow_runs.id"), nullable=False, index=True)
    node_type = Column(String(50), nullable=False)  # controller, writer, diagram, image, assembler, attachment, export
    status = Column(String(20), default="pending")  # pending, running, success, fail
    
    # 输入（node_prompt_spec）
    prompt_spec = Column(JSON, default=dict)
    
    # 输出
    result = Column(JSON, nullable=True)
    artifacts = Column(JSON, default=list)  # 产物路径列表
    
    # 错误
    error = Column(JSON, nullable=True)
    
    # 时间
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    # 重试计数
    retry_count = Column(Integer, default=0)
    
    # 关系
    workflow_run = relationship("WorkflowRun", back_populates="node_runs")
    
    def __repr__(self):
        return f"<WorkflowNodeRun {self.node_type} status={self.status}>"

