"""
LangGraph 工作流定义

整合所有节点，定义状态机流转逻辑
"""
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from app.schemas.workflow import WorkflowState

# 导入节点
from app.nodes import controller, attachment, writer, image, checker


def _to_dict(state: Any) -> Dict[str, Any]:
    """将 state 统一转为 dict（兼容 Pydantic 模型和普通 dict）"""
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if hasattr(state, "dict"):
        return state.dict()
    if isinstance(state, dict):
        return state
    return {}


def create_workflow() -> StateGraph:
    """创建工作流状态图"""
    
    # 定义状态图
    workflow = StateGraph(WorkflowState)
    
    # 添加节点
    workflow.add_node("controller", controller.run)
    workflow.add_node("attachment", attachment.run)
    workflow.add_node("writer", writer.run)
    workflow.add_node("image", image.run)
    workflow.add_node("checker", checker.run)
    
    # 定义边
    workflow.set_entry_point("controller")
    
    # controller -> 条件路由
    workflow.add_conditional_edges(
        "controller",
        _route_from_controller,
        {
            "attachment": "attachment",
            "chat": END,  # 继续对话
            "write": "writer",
            "retry": "controller",  # 重试
        }
    )
    
    # attachment -> controller
    workflow.add_conditional_edges(
        "attachment",
        _route_from_attachment,
        {
            "controller": "controller",
            "retry": "attachment",
        }
    )
    
    # writer -> image
    workflow.add_conditional_edges(
        "writer",
        _route_from_writer,
        {
            "image": "image",
            "retry": "writer",
        }
    )
    
    # image -> checker
    workflow.add_conditional_edges(
        "image",
        _route_from_image,
        {
            "checker": "checker",
            "retry": "image",
        }
    )
    
    # checker -> END
    workflow.add_conditional_edges(
        "checker",
        _route_from_checker,
        {
            "done": END,
            "retry": "checker",
        }
    )
    
    return workflow


def _route_from_controller(state: Any) -> Literal["attachment", "chat", "write", "retry"]:
    """从 controller 路由"""
    s = _to_dict(state)
    
    # 检查错误
    if s.get("node_status") == "fail":
        if s.get("retry_count", 0) < 3:
            return "retry"
        # 超过重试次数，结束对话
        return "chat"
    
    # 检查是否有未分析的附件
    attachments = s.get("attachments", [])
    pending = [a for a in attachments if not a.get("summary")]
    if pending:
        return "attachment"
    
    # 检查是否准备好撰写
    if s.get("ready_to_write"):
        return "write"
    
    # 继续对话
    return "chat"


def _route_from_attachment(state: Any) -> Literal["controller", "retry"]:
    """从 attachment 路由"""
    s = _to_dict(state)
    
    if s.get("node_status") == "fail":
        if s.get("retry_count", 0) < 3:
            return "retry"
    
    return "controller"


def _route_from_writer(state: Any) -> Literal["image", "retry"]:
    """从 writer 路由"""
    s = _to_dict(state)
    
    if s.get("node_status") == "fail":
        if s.get("retry_count", 0) < 3:
            return "retry"
    
    return "image"


def _route_from_image(state: Any) -> Literal["checker", "retry"]:
    """从 image 路由"""
    s = _to_dict(state)
    
    if s.get("node_status") == "fail":
        if s.get("retry_count", 0) < 3:
            return "retry"
    
    return "checker"


def _route_from_checker(state: Any) -> Literal["done", "retry"]:
    """从 checker 路由"""
    s = _to_dict(state)
    
    if s.get("node_status") == "fail":
        if s.get("retry_count", 0) < 3:
            return "retry"
    
    return "done"


# 创建可编译的工作流
def get_compiled_workflow():
    """获取编译后的工作流"""
    workflow = create_workflow()
    return workflow.compile()
