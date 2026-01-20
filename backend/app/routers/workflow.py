"""
工作流路由
"""
import os
import asyncio
from typing import List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import json

from app.database import get_db
from app.models.user import User
from app.models.document import Document, DocumentVersion
from app.models.workflow import WorkflowRun, WorkflowNodeRun
from app.schemas.workflow import (
    WorkflowRunRequest, 
    WorkflowRunResponse, 
    WorkflowState,
    ChatMessage
)
from app.dependencies import get_current_user
from app.nodes.graph import get_compiled_workflow

router = APIRouter()

# 活跃的 WebSocket 连接
active_connections: Dict[str, List[WebSocket]] = {}

# 运行中的后台任务（用于 stop/取消）
run_tasks: Dict[str, asyncio.Task] = {}
run_cancel_events: Dict[str, asyncio.Event] = {}

def _is_pytest_env() -> bool:
    # When running under pytest, BackgroundTasks will be awaited by the ASGI test client,
    # which makes workflow execution (LLM calls / multi-engine DB) flaky and slow.
    return "PYTEST_CURRENT_TEST" in os.environ


async def broadcast_to_run(run_id: str, event: str, data: dict):
    """向订阅某个运行的所有客户端广播消息"""
    if run_id in active_connections:
        message = {"event": event, "data": data}
        for ws in active_connections[run_id]:
            try:
                await ws.send_json(message)
            except:
                pass


def to_dict(obj: Any) -> Dict[str, Any]:
    """Helper: ensure object is a dict"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return obj
    return {}


async def execute_workflow_streaming(
    run_id: str,
    initial_state: Dict[str, Any],
    db_url: str
):
    """
    后台执行工作流（带流式输出）
    
    Plan 阶段：仅执行 controller（A），流式推送思考/回复。
    不自动进入撰写流水线（由前端“开始执行”按钮触发）。
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.nodes import controller
    
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # 更新状态为运行中
            stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
            run = (await db.execute(stmt)).scalar_one()
            run.status = "running"
            await db.commit()
            
            await broadcast_to_run(run_id, "run_start", {"run_id": run_id})
            
            cancel_event = run_cancel_events.get(run_id)

            # 定义流式回调（对话/计划分流：左侧只显示对话，中间只显示 Plan）
            class _PlanStreamSplitter:
                def __init__(self):
                    self.mode = "chat"  # chat | plan
                    self.buf = ""
                    self.plan_marker = "【计划】"
                    self.chat_marker = "【对话】"

                async def push(self, chunk: str):
                    if not chunk:
                        return
                    self.buf += chunk
                    # 逐步处理 marker 切换
                    while True:
                        if self.mode == "chat":
                            idx = self.buf.find(self.plan_marker)
                            if idx >= 0:
                                pre = self.buf[:idx]
                                post = self.buf[idx + len(self.plan_marker):]
                                pre = pre.replace(self.chat_marker, "")
                                if pre:
                                    await broadcast_to_run(run_id, "stream_content", {"content": pre})
                                self.mode = "plan"
                                self.buf = post
                                continue
                            # 没看到 marker：为了兼容分片 marker，保留尾部
                            keep = max(len(self.plan_marker) - 1, len(self.chat_marker) - 1, 8)
                            if len(self.buf) > keep:
                                out = self.buf[:-keep]
                                self.buf = self.buf[-keep:]
                                out = out.replace(self.chat_marker, "")
                                if out:
                                    await broadcast_to_run(run_id, "stream_content", {"content": out})
                            break
                        else:
                            # plan 模式：全部当 plan（同样保留尾部避免丢字符）
                            keep = max(len(self.plan_marker) - 1, 8)
                            if len(self.buf) > keep:
                                out = self.buf[:-keep]
                                self.buf = self.buf[-keep:]
                                if out:
                                    await broadcast_to_run(run_id, "stream_plan", {"content": out})
                            break

                async def flush(self):
                    if not self.buf:
                        return
                    out = self.buf
                    self.buf = ""
                    if self.mode == "plan":
                        await broadcast_to_run(run_id, "stream_plan", {"content": out})
                    else:
                        out = out.replace(self.chat_marker, "")
                        await broadcast_to_run(run_id, "stream_content", {"content": out})

            splitter = _PlanStreamSplitter()

            # 定义流式回调
            async def on_thinking(content: str):
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError()
                # 中控思考内容需要展示（与之前保持一致）
                await broadcast_to_run(run_id, "stream_thinking", {"content": content})
            
            async def on_content(content: str):
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError()
                await splitter.push(content)
            
            # 广播开始思考
            await broadcast_to_run(run_id, "node_update", {
                "node": "controller",
                "status": "thinking",
            })
            
            # 使用流式 controller（A）
            state = await controller.run_streaming(
                initial_state,
                on_thinking=on_thinking,
                on_content=on_content,
            )

            # flush leftover buffer to UI
            await splitter.flush()

            # controller 流式结束
            await broadcast_to_run(run_id, "stream_done", {})
            
            async def _persist_latest_node_run(s: Dict[str, Any], fallback_node: str):
                if s.get("node_runs"):
                    latest = s["node_runs"][-1]
                    nr = WorkflowNodeRun(
                        workflow_run_id=run_id,
                        node_type=latest.get("node_type", fallback_node),
                        status=latest.get("status", "running"),
                        prompt_spec=latest.get("prompt_spec"),
                        result=latest.get("result"),
                        error=latest.get("error"),
                    )
                    db.add(nr)
                    await db.commit()

            # 持久化 controller node_run
            await _persist_latest_node_run(state, "controller")
            
            # Plan 阶段：更新 run 的 doc_variables（保存撰写指南/计划）
            run.current_node = "controller"
            updated_vars = state.get("doc_variables") or {}
            if state.get("chat_history") is not None:
                updated_vars = {**updated_vars, "chat_history": state.get("chat_history")}
            run.doc_variables = updated_vars
            run.status = "completed"
            await db.commit()

            await broadcast_to_run(run_id, "run_complete", {
                "run_id": run_id,
                "final_md": run.final_md,
                "doc_variables": run.doc_variables,
            })
            
        except asyncio.CancelledError:
            # 用户取消
            stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
            run = (await db.execute(stmt)).scalar_one_or_none()
            if run:
                run.status = "cancelled"
                run.error = {"error_type": "cancelled", "error_message": "用户已停止输出"}
                await db.commit()
            await broadcast_to_run(run_id, "run_cancelled", {"run_id": run_id})
        except Exception as e:
            # 更新为失败状态
            stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
            run = (await db.execute(stmt)).scalar_one_or_none()
            if run:
                run.status = "failed"
                run.error = {"error_type": "execution_error", "error_message": str(e)}
                await db.commit()
            
            await broadcast_to_run(run_id, "run_error", {
                "run_id": run_id,
                "error": str(e)
            })
        finally:
            # 清理任务/取消标记
            run_tasks.pop(run_id, None)
            run_cancel_events.pop(run_id, None)


async def execute_workflow_execute_streaming(
    run_id: str,
    initial_state: Dict[str, Any],
    db_url: str,
):
    """
    Execute 阶段：执行 writer（B，流式输出草稿）→ image（D，按 {{image+...}} 生图记录）→ mermaid（中控模型校对 Mermaid，仅有问题才修复）。
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.nodes import writer, image
    from app.nodes import mermaid_guard

    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    cancel_event = run_cancel_events.get(run_id)

    async with async_session() as db:
        try:
            stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
            run = (await db.execute(stmt)).scalar_one()
            run.status = "running"
            await db.commit()
            await broadcast_to_run(run_id, "run_start", {"run_id": run_id})

            async def _persist_latest_node_run(s: Dict[str, Any], fallback_node: str):
                if s.get("node_runs"):
                    latest = s["node_runs"][-1]
                    nr = WorkflowNodeRun(
                        workflow_run_id=run_id,
                        node_type=latest.get("node_type", fallback_node),
                        status=latest.get("status", "running"),
                        prompt_spec=latest.get("prompt_spec"),
                        result=latest.get("result"),
                        error=latest.get("error"),
                    )
                    db.add(nr)
                    await db.commit()

            # B：writer（流式）
            await broadcast_to_run(run_id, "node_update", {"node": "writer", "status": "running"})

            async def on_writer(content: str):
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError()
                await broadcast_to_run(run_id, "stream_writer", {"content": content})

            async def on_chapter(idx: int, title: str):
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError()
                await broadcast_to_run(run_id, "chapter_update", {"index": idx, "title": title})
                # 章节粒度更新（用于刷新进入文档后的恢复）
                try:
                    run.doc_variables = {**(run.doc_variables or {}), "current_step_index": idx}
                    await db.commit()
                except Exception:
                    pass

            # 兼容：如果旧数据没带 write_mode，但有 outline，则默认章节粒度
            if isinstance(initial_state.get("doc_variables"), dict) and initial_state["doc_variables"].get("write_mode") is None:
                initial_state["doc_variables"]["write_mode"] = "chapter"

            state = await writer.run_streaming(
                initial_state,
                on_content=on_writer,
                on_chapter_start=on_chapter,
                cancel_event=cancel_event,
            )
            await _persist_latest_node_run(state, "writer")
            run.current_node = "writer"
            await db.commit()

            # 关键：writer 失败不要当作 completed
            if (state.get("node_status") or "").lower() in ["fail", "failed"] or state.get("error"):
                err = state.get("error") or {}
                raise RuntimeError(err.get("error_message") or "writer 执行失败")

            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()

            # D：image（视需要：仅当正文包含 {{image+...}} 才执行）
            draft_for_img = state.get("draft_md") or ""
            if "{{image+" in (draft_for_img or "").lower():
                await broadcast_to_run(run_id, "node_update", {"node": "image", "status": "running"})
                state = await image.run(state)
                await _persist_latest_node_run(state, "image")
                run.current_node = "image"
                await db.commit()

            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()

            # Mermaid/HTML 校对（无感后台守护：不广播、不写 node_run、不改 current_node；仅在需要时修复代码块）
            try:
                state = await mermaid_guard.run(state)
            except Exception:
                # 守护失败不影响主流程完成（避免用户感知/卡住）
                pass

            final_md = state.get("draft_md") or ""
            run.final_md = final_md

            final_vars = state.get("doc_variables") or {}
            if state.get("chat_history") is not None:
                final_vars = {**final_vars, "chat_history": state.get("chat_history")}
            run.doc_variables = final_vars

            doc_version = DocumentVersion(
                document_id=run.document_id,
                content_md=final_md,
                doc_variables=final_vars,
            )
            db.add(doc_version)

            doc_obj = await db.get(Document, run.document_id)
            if doc_obj:
                doc_obj.status = "completed"
                # 标题自动同步：未命名文档时，用大纲首章/文档类型作为标题
                if (doc_obj.title or "").startswith("未命名"):
                    outline = (final_vars or {}).get("outline")
                    if isinstance(outline, list) and outline and str(outline[0]).strip():
                        doc_obj.title = str(outline[0]).strip()[:200]
                    else:
                        doc_type = (final_vars or {}).get("doc_type")
                        if isinstance(doc_type, str) and doc_type.strip():
                            doc_obj.title = doc_type.strip()[:200]

            run.status = "completed"
            await db.commit()

            await broadcast_to_run(run_id, "run_complete", {
                "run_id": run_id,
                "final_md": run.final_md,
                "doc_variables": run.doc_variables,
            })
        except asyncio.CancelledError:
            stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
            run = (await db.execute(stmt)).scalar_one_or_none()
            if run:
                run.status = "cancelled"
                run.error = {"error_type": "cancelled", "error_message": "用户已停止输出"}
                await db.commit()
            await broadcast_to_run(run_id, "run_cancelled", {"run_id": run_id})
        except Exception as e:
            stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
            run = (await db.execute(stmt)).scalar_one_or_none()
            if run:
                run.status = "failed"
                run.error = {"error_type": "execution_error", "error_message": str(e)}
                await db.commit()
            await broadcast_to_run(run_id, "run_error", {"run_id": run_id, "error": str(e)})
        finally:
            run_tasks.pop(run_id, None)
            run_cancel_events.pop(run_id, None)


async def execute_workflow(
    run_id: str,
    initial_state: Dict[str, Any],
    db_url: str
):
    """
    后台执行工作流
    
    使用 LangGraph 状态机驱动
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # 更新状态为运行中
            stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
            run = (await db.execute(stmt)).scalar_one()
            run.status = "running"
            await db.commit()
            
            await broadcast_to_run(run_id, "run_start", {"run_id": run_id})
            
            # 获取编译后的工作流
            workflow = get_compiled_workflow()
            
            # 执行工作流
            current_state = initial_state
            
            async for event in workflow.astream(current_state):
                # event 是 {node_name: state_update} 的字典
                for node_name, state_obj in event.items():
                    # 统一转为 dict 避免 WorkflowState 对象没有 get 方法
                    state_update = to_dict(state_obj)
                    
                    # 广播节点更新
                    await broadcast_to_run(run_id, "node_update", {
                        "node": node_name,
                        "status": state_update.get("node_status", "running"),
                        "prompt_spec": state_update.get("node_runs", [{}])[-1].get("prompt_spec") if state_update.get("node_runs") else None,
                    })
                    
                    # 保存节点运行记录
                    if state_update.get("node_runs"):
                        latest_node_run = state_update["node_runs"][-1]
                        node_run = WorkflowNodeRun(
                            workflow_run_id=run_id,
                            node_type=latest_node_run.get("node_type", node_name),
                            status=latest_node_run.get("status", "running"),
                            prompt_spec=latest_node_run.get("prompt_spec"),
                            result=latest_node_run.get("result"),
                            error=latest_node_run.get("error"),
                        )
                        db.add(node_run)
                        await db.commit()
                    
                    # 更新工作流状态
                    run.current_node = node_name
                    # 约定：把 chat_history 也持久化到 doc_variables 里，方便前端直接回显对话
                    updated_vars = state_update.get("doc_variables", run.doc_variables) or {}
                    if state_update.get("chat_history") is not None:
                        updated_vars = {**updated_vars, "chat_history": state_update.get("chat_history")}
                    run.doc_variables = updated_vars
                    if state_update.get("final_md"):
                        run.final_md = state_update["final_md"]
                    await db.commit()
                    
                    current_state = {**current_state, **state_update}
            
            # 完成
            # current_state 可能也是对象
            final_state = to_dict(current_state)
            run.status = "completed"
            run.final_md = final_state.get("final_md")
            final_vars = final_state.get("doc_variables") or {}
            if final_state.get("chat_history") is not None:
                final_vars = {**final_vars, "chat_history": final_state.get("chat_history")}
            run.doc_variables = final_vars
            await db.commit()
            
            await broadcast_to_run(run_id, "run_complete", {
                "run_id": run_id,
                "final_md": run.final_md,
                "doc_variables": run.doc_variables,
            })
            
        except Exception as e:
            # 更新为失败状态
            stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
            run = (await db.execute(stmt)).scalar_one_or_none()
            if run:
                run.status = "failed"
                run.error = {"error_type": "execution_error", "error_message": str(e)}
                await db.commit()
            
            await broadcast_to_run(run_id, "run_error", {
                "run_id": run_id,
                "error": str(e)
            })


@router.post("/docs/{doc_id}/run", response_model=WorkflowRunResponse)
async def start_workflow(
    doc_id: str,
    req: WorkflowRunRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """启动工作流"""
    from app.config import settings
    
    # 检查文档
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 获取当前文档变量
    sorted_versions = sorted(doc.versions, key=lambda v: v.created_at, reverse=True) if doc.versions else []
    latest_version = sorted_versions[0] if sorted_versions else None
    doc_variables = latest_version.doc_variables if latest_version else {}
    
    # 创建工作流运行记录
    workflow_run = WorkflowRun(
        document_id=doc_id,
        triggered_by_user_id=user.id,
        status="pending",
        doc_variables=doc_variables
    )
    db.add(workflow_run)
    await db.commit()
    await db.refresh(workflow_run)
    
    # 构造初始状态
    initial_state: WorkflowState = {
        "run_id": workflow_run.id,
        "doc_id": doc_id,
        "user_id": user.id,  # 补上必填字段
        "doc_variables": doc_variables,
        "chat_history": [ChatMessage(role="user", content=req.user_message)] if req.user_message else [],
        "attachments": [],
        "draft_md": "",
        "mermaid_placeholders": [],
        "html_placeholders": [],
        "mermaid_codes": {},
        "html_codes": {},
        "final_md": "",
        "node_runs": [],
        "current_node": "",
        "node_status": "",
        "error": None,
        "retry_count": 0,
        "ready_to_write": False,
    }
    
    # 启动后台任务
    if not _is_pytest_env():
        background_tasks.add_task(
            execute_workflow,
            workflow_run.id,
            initial_state,
            str(settings.database_url)
        )
    
    return WorkflowRunResponse(
        run_id=workflow_run.id,
        status="started"
    )


@router.post("/docs/{doc_id}/chat", response_model=dict)
async def send_chat_message(
    doc_id: str,
    req: WorkflowRunRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    发送对话消息（触发中控节点，流式输出）
    
    这是主要的用户交互入口
    """
    from app.config import settings
    
    # 检查文档
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 获取或创建最新版本
    sorted_versions = sorted(doc.versions, key=lambda v: v.created_at, reverse=True) if doc.versions else []
    latest_version = sorted_versions[0] if sorted_versions else None
    
    if not latest_version:
        # 创建初始版本
        latest_version = DocumentVersion(
            document_id=doc_id,
            doc_variables={},
            content_md=""
        )
        db.add(latest_version)
        await db.commit()
        await db.refresh(latest_version)
    
    # 获取历史对话（简化：从最近的工作流运行中获取）
    recent_run_result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.document_id == doc_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(1)
    )
    recent_run = recent_run_result.scalar_one_or_none()
    
    chat_history = []
    if recent_run and recent_run.doc_variables.get("chat_history"):
        chat_history = recent_run.doc_variables["chat_history"]
    
    # 添加新消息
    chat_history.append({"role": "user", "content": req.user_message})
    
    # 创建新的工作流运行
    workflow_run = WorkflowRun(
        document_id=doc_id,
        triggered_by_user_id=user.id,
        status="pending",
        doc_variables={**(latest_version.doc_variables or {}), "chat_history": chat_history}
    )
    db.add(workflow_run)
    await db.commit()
    await db.refresh(workflow_run)
    
    # 构造初始状态
    initial_state = {
        "run_id": workflow_run.id,
        "doc_id": doc_id,
        "user_id": user.id,  # 补上必填字段
        "doc_variables": latest_version.doc_variables or {},
        "chat_history": chat_history,
        "attachments": req.attachments or [],
        "draft_md": latest_version.content_md or "",
        "mermaid_placeholders": [],
        "html_placeholders": [],
        "mermaid_codes": {},
        "html_codes": {},
        "final_md": "",
        "node_runs": [],
        "current_node": "",
        "node_status": "",
        "error": None,
        "retry_count": 0,
        "ready_to_write": False,
    }
    
    # Plan 阶段：启动后台任务（仅 controller 流式）
    if not _is_pytest_env():
        run_cancel_events[workflow_run.id] = asyncio.Event()
        task = asyncio.create_task(
            execute_workflow_streaming(workflow_run.id, initial_state, str(settings.database_url))
        )
        run_tasks[workflow_run.id] = task
    
    return {
        "run_id": workflow_run.id,
        "status": "started",
        "message": "对话已发送，正在处理中"
    }


@router.post("/docs/{doc_id}/execute", response_model=dict)
async def execute_plan(
    doc_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    从 Plan 进入 Execute：基于最新 doc_variables/chat_history 执行 writer/diagram/assembler。
    """
    from app.config import settings

    # 检查文档
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    sorted_versions = sorted(doc.versions, key=lambda v: v.created_at, reverse=True) if doc.versions else []
    latest_version = sorted_versions[0] if sorted_versions else None
    version_doc_variables = latest_version.doc_variables if latest_version else {}
    content_md = latest_version.content_md if latest_version else ""

    # 从最近一次 workflow_run 的 doc_variables 里取完整变量（Plan 阶段保存的 outline/plan_md 在这里）
    recent_run_result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.document_id == doc_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(1)
    )
    recent_run = recent_run_result.scalar_one_or_none()
    
    # 优先使用 WorkflowRun.doc_variables（包含 Plan 阶段产出的 outline/plan_md 等），再合并 DocumentVersion 的
    run_doc_variables = (recent_run.doc_variables or {}) if recent_run else {}
    doc_variables = {**(version_doc_variables or {}), **run_doc_variables}
    chat_history = doc_variables.get("chat_history", [])

    workflow_run = WorkflowRun(
        document_id=doc_id,
        triggered_by_user_id=user.id,
        status="pending",
        doc_variables=doc_variables,
    )
    db.add(workflow_run)
    await db.commit()
    await db.refresh(workflow_run)

    initial_state = {
        "run_id": workflow_run.id,
        "doc_id": doc_id,
        "user_id": user.id,
        "doc_variables": doc_variables,
        "chat_history": chat_history,
        "attachments": [],
        "draft_md": content_md or "",
        "mermaid_placeholders": [],
        "html_placeholders": [],
        "mermaid_codes": {},
        "html_codes": {},
        "final_md": "",
        "node_runs": [],
        "current_node": "",
        "node_status": "",
        "error": None,
        "retry_count": 0,
        "ready_to_write": True,
    }

    if not _is_pytest_env():
        run_cancel_events[workflow_run.id] = asyncio.Event()
        task = asyncio.create_task(
            execute_workflow_execute_streaming(workflow_run.id, initial_state, str(settings.database_url))
        )
        run_tasks[workflow_run.id] = task

    return {"run_id": workflow_run.id, "status": "started"}


@router.get("/runs/{run_id}", response_model=dict)
async def get_workflow_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取工作流运行状态"""
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id)
        .options(selectinload(WorkflowRun.node_runs))
    )
    run = result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(status_code=404, detail="工作流运行不存在")
    
    return {
        "run_id": run.id,
        "status": run.status,
        "current_node": run.current_node,
        "doc_variables": run.doc_variables,
        "final_md": run.final_md,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "node_runs": [
            {
                "node_type": node.node_type,
                "status": node.status,
                "prompt_spec": node.prompt_spec,
                "result": node.result,
                "error": node.error,
                "timestamp": node.started_at.isoformat() if node.started_at else None
            }
            for node in sorted(run.node_runs, key=lambda n: n.started_at or datetime.min)
        ]
    }


@router.websocket("/runs/{run_id}/stream")
async def workflow_stream(
    websocket: WebSocket,
    run_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    工作流实时状态推送（WebSocket）
    
    消息格式：
    {
        "event": "node_update" | "stream_thinking" | "stream_content" | "stream_done" |
                 "stream_writer" | "run_complete" | "run_error" | "run_cancelled",
        "data": { ... }
    }
    
    流式事件：
    - stream_thinking: {"content": "..."} 中控思考过程增量
    - stream_content: {"content": "..."} 中控对话回复增量（左侧）
    - stream_plan: {"content": "..."} Plan（Markdown）增量（中间）
    - stream_done: {} 中控流式结束
    - stream_writer: {"content": "..."} 撰写草稿增量
    """
    await websocket.accept()
    
    # 添加到活跃连接
    if run_id not in active_connections:
        active_connections[run_id] = []
    active_connections[run_id].append(websocket)
    
    try:
        # 验证 run_id 存在
        result = await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .options(selectinload(WorkflowRun.node_runs))
        )
        run = result.scalar_one_or_none()
        
        if not run:
            await websocket.send_json({
                "event": "error",
                "data": {"message": "工作流运行不存在"}
            })
            await websocket.close()
            return
        
        # 发送当前状态
        await websocket.send_json({
            "event": "connected",
            "data": {
                "run_id": run_id,
                "status": run.status,
                "current_node": run.current_node,
                "doc_variables": run.doc_variables,
                "final_md": run.final_md,
                "node_runs": [
                    {
                        "node_type": node.node_type,
                        "status": node.status,
                        "prompt_spec": node.prompt_spec,
                        "result": node.result,
                    }
                    for node in run.node_runs
                ]
            }
        })
        
        # 保持连接，等待更新
        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
                    continue

                # 支持客户端控制消息：stop
                try:
                    payload = json.loads(data)
                    if isinstance(payload, dict) and payload.get("event") in ["client_stop", "stop"]:
                        ev = run_cancel_events.get(run_id)
                        if ev:
                            ev.set()
                        t = run_tasks.get(run_id)
                        if t and not t.done():
                            t.cancel()
                        await websocket.send_json({"event": "ack_stop", "data": {"run_id": run_id}})
                        continue
                except Exception:
                    # 非 JSON 文本：兼容直接发送 "stop"
                    if data.strip().lower() == "stop":
                        ev = run_cancel_events.get(run_id)
                        if ev:
                            ev.set()
                        t = run_tasks.get(run_id)
                        if t and not t.done():
                            t.cancel()
                        await websocket.send_json({"event": "ack_stop", "data": {"run_id": run_id}})
                        continue
            except WebSocketDisconnect:
                break
                
    except Exception as e:
        try:
            await websocket.send_json({
                "event": "error",
                "data": {"message": str(e)}
            })
        except:
            pass
    finally:
        # 移除连接
        if run_id in active_connections:
            active_connections[run_id] = [
                ws for ws in active_connections[run_id] if ws != websocket
            ]
            if not active_connections[run_id]:
                del active_connections[run_id]
        
        try:
            await websocket.close()
        except:
            pass
