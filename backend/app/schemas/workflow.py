"""
工作流相关 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


class ChatMessage(BaseModel):
    """对话消息"""
    role: Literal["system", "user", "assistant"]
    content: str


class Attachment(BaseModel):
    """附件信息"""
    attachment_id: str
    filename: str
    file_type: Optional[str] = None
    url: str
    summary: Optional[str] = None


class NodePromptSpec(BaseModel):
    """节点提示词规格（中间栏展示核心）"""
    node_type: str
    goal: str
    constraints: List[str] = []
    materials: List[str] = []
    output_format: str = ""
    variables_snapshot: Dict[str, Any] = {}
    attachments_snapshot: List[Attachment] = []


class ErrorInfo(BaseModel):
    """错误信息"""
    error_type: Literal[
        "mermaid_render_failed",
        "html_capture_failed", 
        "pandoc_failed",
        "asset_missing",
        "model_error",
        "validation_failed"
    ]
    error_message: str
    block_id: Optional[str] = None
    block_source: Optional[str] = None
    retry_guidance: str = ""


class NodeResult(BaseModel):
    """节点输出"""
    draft_md: Optional[str] = None
    mermaid_blocks: List[dict] = []
    html_blocks: List[dict] = []
    final_md: Optional[str] = None
    attachment_summary: Optional[str] = None
    doc_variables_patch: Dict[str, Any] = {}
    validation_report: Optional[dict] = None
    image_urls: List[str] = []


class NodeRunInfo(BaseModel):
    """节点运行信息"""
    node_type: str
    status: str
    prompt_spec: Optional[NodePromptSpec] = None
    result: Optional[NodeResult] = None
    error: Optional[ErrorInfo] = None
    timestamp: datetime


class WorkflowRunRequest(BaseModel):
    """启动工作流请求"""
    user_message: Optional[str] = None
    from_node: Optional[str] = None  # 从某节点开始（用于重跑）
    attachments: List[str] = []  # attachment_id 列表


class WorkflowRunResponse(BaseModel):
    """工作流运行响应"""
    run_id: str
    status: str


class WorkflowRunDetail(BaseModel):
    """工作流运行详情"""
    run_id: str
    status: str
    current_node: Optional[str] = None
    node_runs: List[NodeRunInfo] = []
    doc_variables: Dict[str, Any] = {}
    final_md: Optional[str] = None
    error: Optional[ErrorInfo] = None


# ===== LangGraph State =====

class DocVariables(BaseModel):
    """文档变量（中控澄清产出）"""
    doc_type: Optional[str] = None
    audience: Optional[str] = None
    outline: List[str] = []
    key_points: List[str] = []
    materials: List[str] = []
    constraints: Dict[str, Any] = {}
    
    class Config:
        extra = "allow"  # 允许额外字段


class WorkflowState(BaseModel):
    """LangGraph 工作流状态"""
    doc_id: str
    run_id: str
    user_id: str
    
    # 核心数据
    doc_variables: Dict[str, Any] = {}
    attachments: List[Attachment] = []
    chat_history: List[dict] = []
    
    # 各节点产物
    draft_md: Optional[str] = None
    mermaid_blocks: List[dict] = []
    html_blocks: List[dict] = []
    mermaid_placeholders: List[dict] = []
    html_placeholders: List[dict] = []
    image_urls: List[str] = []
    final_md: Optional[str] = None
    export_url: Optional[str] = None
    
    # 当前节点与状态
    current_node: str = "controller"
    node_status: str = "pending"
    
    # 错误与回流
    error: Optional[ErrorInfo] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # 节点运行记录
    node_runs: List[dict] = []
    
    class Config:
        extra = "allow"

