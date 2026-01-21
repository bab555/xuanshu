"""
A：中控对话节点（Controller）

职责：
- 引导用户把文档需要写的内容说清楚
- 记录为 doc_variables JSON
- 校验完整性（缺什么就追问）
- 支持流式输出
- 支持工具调用：update_plan, edit_document
"""
import json
from datetime import datetime
from typing import Dict, Any, AsyncGenerator, Optional, Callable, List

from app.services.model_client import model_client
from app.config import settings

CONTROLLER_SYSTEM_PROMPT = """你是红点公司的文档规划助手（Qwen，中控）。

你的职责：
1) 通过对话引导用户制定“文档写作计划（Plan）”
2) 当用户信息不足时，你可以给出你的见解，并配合或用户制定计划
3) 你拥有规划权：可以自行决定章节结构、章节数量、每章重点

你可以规划的内容：
- 章节：按章节粒度给出大纲与每章要点
- 图表：如需图表，在 Plan 中标注（此处插入 mermaid），并描述图表意图；正文里会用 Mermaid 代码块输出
- 示例图片：如需文生图，在 Plan 中标注（此处插入示意图片），并提供占位符 `{{image+提示词}}`（慎用这个功能，除非是你觉得需要扩散模型生图才能明确表达或是用户明确要求，否则不用）
- 搜索图片：如需搜索图片，在 Plan 中标注（此处插入搜索图片），并写明图片主题/关键词/偏好
- 用户需要数据/新闻内容时，你可以按需帮助用户搜索

系统执行方式（供你写在 Plan 中，方便用户理解）：
- 系统会按章节顺序逐章撰写
- 如正文中出现 `{{image+...}}`，系统会按需生成图片，并记录生成结果；正文预览阶段仍保留占位符
- Mermaid 会进行“可渲染性校对”，有问题才会修复

关键工作方式：
- 先通过对话把需求聊清楚，（必要时，可以直接给出建议问用户是否可以）
- 在信息足够时，**调用 update_plan 工具**生成或更新 Plan（通过章节和内容提要的方式制作一份大纲）
- Plan 允许反复修改
- 在完成plan以后，提示用户可以点击“执行”按钮，开始撰写。

可调用工具（Function Calling）：
1) update_plan(content_md, outline): 创建或更新 Plan。
2) edit_document(operation, content, section): 修改最终文档（仅当已有正文时可用）。

输出要求：
- 正常对话：直接输出文本回答用户。
- 更新计划：当你收集到足够信息，或用户要求修改计划时，**必须调用 `update_plan` 工具**将计划发送给系统。
- 不要在输出里复述"提示词本身"或"字段清单/格式说明"。"""

# --- Tools Definition ---

CONTROLLER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_plan",
            "description": "创建或更新文档写作计划（Plan）。当用户需求变更，或你需要展示新的计划时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content_md": {
                        "type": "string",
                        "description": "完整的计划内容（Markdown格式），包含章节大纲、要点等。"
                    },
                    "outline": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "提取出的章节标题列表（用于生成 Skills）。"
                    }
                },
                "required": ["content_md"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_document",
            "description": "修改最终文档内容 (Content)",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["replace", "append", "update_section"],
                        "description": "操作类型：replace(全量替换), append(追加), update_section(更新特定章节)"
                    },
                    "content": {
                        "type": "string",
                        "description": "新的文档内容"
                    },
                    "section": {
                        "type": "string",
                        "description": "章节标题（仅 update_section 时需要）"
                    }
                },
                "required": ["operation", "content"]
            }
        }
    }
]

def _normalize_decision(value: Any, ready_to_write: bool) -> str:
    """统一 decision 到内部使用的英文值：chat/write（兼容中文/英文输入）"""
    v = (value or "").strip().lower()
    if v in ["write", "start_write", "start_writing"]:
        return "write"
    if v in ["chat", "ask", "clarify"]:
        return "chat"
    # 中文兼容
    if value in ["开始撰写", "开始写作", "写作", "撰写", "开始写"]:
        return "write"
    if value in ["继续对话", "继续问", "追问", "澄清", "继续澄清"]:
        return "chat"
    # 回退：看 ready_to_write
    return "write" if ready_to_write else "chat"


def _to_dict(state: Any) -> Dict[str, Any]:
    """将 state 统一转为 dict（兼容 Pydantic 模型和普通 dict）"""
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if hasattr(state, "dict"):
        return state.dict()
    if isinstance(state, dict):
        return state
    return {}


async def run(state: Any) -> Dict[str, Any]:
    """
    A：中控对话节点（非流式，用于 LangGraph 状态机）
    """
    # 统一转为 dict
    s = _to_dict(state)
    
    # 构造 node_prompt_spec（写入中间栏）
    prompt_spec = {
        "node_type": "controller",
        "goal": "把用户需求澄清到可执行，形成 doc_variables",
        "constraints": [
            "只根据用户信息填写，不编造",
            "只求说清楚，不追求排版好看",
            "变量必须可被后续节点直接消费"
        ],
        "materials": [
            a.get("summary", "") 
            for a in s.get("attachments", []) 
            if a.get("summary")
        ],
        "output_format": "对话文本 + 工具调用（update_plan）",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": s.get("attachments", []),
    }
    
    # 构造消息
    messages = _build_messages(s, prompt_spec)
    
    try:
        # 调用模型（中控使用思考模式）
        model = settings.model_controller
        if settings.model_controller_enable_thinking:
            reasoning, response = await model_client.call_with_thinking(
                model,
                messages,
                thinking_budget=settings.model_controller_thinking_budget,
                enable_search=settings.model_controller_enable_search,
                search_options={"search_strategy": settings.model_controller_search_strategy},
                tools=CONTROLLER_TOOLS,
            )
        else:
            response = await model_client.call(
                model,
                messages,
                enable_search=settings.model_controller_enable_search,
                search_options={"search_strategy": settings.model_controller_search_strategy},
                tools=CONTROLLER_TOOLS,
            )
            reasoning = ""
        
        # 解析输出（这里简化处理，非流式主要靠 run_streaming）
        # 如果是工具调用，DashScope 非流式返回格式需要适配，这里暂略，主要逻辑在 run_streaming
        result = {"reply": response, "decision": "继续对话", "ready_to_write": False}
        
        # 记录到 node_runs（包含思考过程）
        node_run = {
            "node_type": "controller",
            "prompt_spec": prompt_spec,
            "result": {
                "reply": result.get("reply", ""),
                "decision": "chat",
                "reasoning": reasoning if settings.model_controller_enable_thinking else None,
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "chat_history": s.get("chat_history", []) + [{"role": "assistant", "content": response}],
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "controller",
            "node_status": "success",
            "error": None,
        }
        
    except Exception as e:
        # 失败处理
        node_run = {
            "node_type": "controller",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "重试调用模型",
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "controller",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


async def run_streaming_generator(state: Any) -> AsyncGenerator[Dict[str, Any], None]:
    """
    A：中控对话节点（流式生成器版本）
    
    Yields:
        {"type": "thinking", "content": "..."}
        {"type": "content", "content": "..."}
        {"type": "tool_call", "tool_calls": [...]}
        {"type": "done", "state": {...}}
    """
    # 统一转为 dict
    s = _to_dict(state)
    
    # 构造 node_prompt_spec
    prompt_spec = {
        "node_type": "controller",
        "goal": "把用户需求澄清到可执行，形成 doc_variables",
        "constraints": [
            "只根据用户信息填写，不编造",
            "只求说清楚，不追求排版好看",
            "变量必须可被后续节点直接消费"
        ],
        "materials": [
            a.get("summary", "") 
            for a in s.get("attachments", []) 
            if a.get("summary")
        ],
        "output_format": "对话文本 + 工具调用（update_plan）",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": s.get("attachments", []),
    }
    
    # 构造消息
    messages = _build_messages(s, prompt_spec)
    
    try:
        model = settings.model_controller
        full_reasoning = ""
        full_content = ""
        sent_content_len = 0
        reasoning_preview_cap = 1000
        reasoning_preview_sent = 0
        
        tool_calls = []

        # 流式调用
        async for event in model_client.stream_call(
            model=model,
            messages=messages,
            enable_thinking=settings.model_controller_enable_thinking,
            thinking_budget=settings.model_controller_thinking_budget,
            enable_search=settings.model_controller_enable_search,
            search_options={"search_strategy": settings.model_controller_search_strategy},
            max_tokens=8192,
            tools=CONTROLLER_TOOLS, # 启用工具调用
        ):
            if event["type"] == "thinking":
                full_reasoning += event["content"]
                if reasoning_preview_sent < reasoning_preview_cap:
                    remaining = reasoning_preview_cap - reasoning_preview_sent
                    chunk = _sanitize_thinking_preview(event["content"][:remaining])
                    if chunk:
                        reasoning_preview_sent += len(chunk)
                        yield {"type": "thinking", "content": chunk}
            
            elif event["type"] == "content":
                full_content += event["content"]
                yield {"type": "content", "content": event["content"]}
                sent_content_len += len(event["content"])
            
            elif event["type"] == "tool_call":
                # 透传工具调用增量
                if event.get("tool_calls"):
                    tool_calls = event["tool_calls"] # 注意：DashScope SDK 这里通常是累积的
                    yield {"type": "tool_call", "tool_calls": tool_calls}
            
            elif event["type"] == "error":
                raise Exception(event["message"])
            
            elif event["type"] == "done":
                full_reasoning = event.get("reasoning", full_reasoning)
                full_content = event.get("content", full_content)
                if event.get("tool_calls"):
                     tool_calls = event["tool_calls"]

        # 兜底：补发 content
        if full_content and sent_content_len < len(full_content):
            yield {"type": "content", "content": full_content[sent_content_len:]}
            sent_content_len = len(full_content)
        
        # 处理工具调用 (Tool Execution)
        current_vars = s.get("doc_variables", {})
        current_plan = current_vars.get("plan_md", "")
        current_outline = current_vars.get("outline", [])
        current_content = s.get("final_md", "") or s.get("draft_md", "")
        
        tool_outputs = []
        
        if tool_calls:
            for tool_call in tool_calls:
                func_name = tool_call.get("function", {}).get("name")
                args_str = tool_call.get("function", {}).get("arguments", "{}")
                try:
                    # 最终解析需要完整的 JSON
                    args = json.loads(args_str)
                    
                    if func_name == "update_plan":
                        content_md = args.get("content_md", "")
                        outline = args.get("outline", [])
                        if content_md:
                            current_plan = content_md
                            current_outline = outline
                            tool_outputs.append("已更新计划")

                    elif func_name == "edit_document":
                        op = args.get("operation")
                        content = args.get("content")
                        if op == "replace":
                            current_content = content
                            tool_outputs.append(f"已全量替换文档内容")
                        elif op == "append":
                            current_content += f"\n\n{content}"
                            tool_outputs.append(f"已追加文档内容")
                        elif op == "update_section":
                             current_content += f"\n\n(更新章节 {args.get('section')}): {content}"
                             tool_outputs.append(f"已更新文档章节")
                             
                except Exception as e:
                    tool_outputs.append(f"工具 {func_name} 执行失败: {e}")

        # 构造最终回复
        final_reply = full_content
        if tool_outputs:
            final_reply += "\n\n(系统操作: " + "; ".join(tool_outputs) + ")"

        # 添加助手回复到对话历史
        new_chat_history = s.get("chat_history", []) + [
            {"role": "assistant", "content": final_reply}
        ]
        
        # 更新变量
        new_variables = {
            **current_vars,
            "plan_md": current_plan,
            "outline": current_outline,
        }
        if new_variables.get("write_mode") is None:
            new_variables["write_mode"] = "chapter"

        # 记录到 node_runs
        node_run = {
            "node_type": "controller",
            "prompt_spec": prompt_spec,
            "result": {
                "reply": final_reply,
                "tool_calls": tool_calls,
                "plan_md_preview": current_plan[:500] + ("..." if len(current_plan) > 500 else ""),
                "reasoning": full_reasoning if settings.model_controller_enable_thinking else None,
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        final_state = {
            **s,
            "doc_variables": new_variables,
            "chat_history": new_chat_history,
            "draft_md": current_content,
            "final_md": current_content,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "controller",
            "node_status": "success",
            "error": None,
        }
        
        yield {"type": "done", "state": final_state}
        
    except Exception as e:
        node_run = {
            "node_type": "controller",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "重试调用模型",
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        error_state = {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "controller",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }
        # 即使出错也 yield done 状态
        yield {"type": "done", "state": error_state}


async def run_streaming(
    state: Any,
    on_thinking: Optional[Callable[[str], Any]] = None,
    on_content: Optional[Callable[[str], Any]] = None,
    on_tool_call: Optional[Callable[[Dict[str, Any]], Any]] = None, # 预留
) -> Dict[str, Any]:
    """
    兼容旧接口的 run_streaming（非生成器模式）
    """
    final_state = state
    async for event in run_streaming_generator(state):
        if event["type"] == "thinking" and on_thinking:
            await _safe_callback(on_thinking, event["content"])
        elif event["type"] == "content" and on_content:
            await _safe_callback(on_content, event["content"])
        elif event["type"] == "tool_call" and on_tool_call:
            await _safe_callback(on_tool_call, {"tool_calls": event["tool_calls"]})
        elif event["type"] == "done":
            final_state = event["state"]
    return final_state


async def _safe_callback(callback: Callable, *args):
    """安全调用回调（支持同步和异步）"""
    import asyncio
    result = callback(*args)
    if asyncio.iscoroutine(result):
        await result


def _sanitize_thinking_preview(text: str) -> str:
    """
    避免把提示词/字段清单等内容透出到前端思考区（轻量过滤）。
    注意：这是“展示层过滤”，不影响模型真实推理。
    """
    if not text:
        return ""
    banned = [
        "输出格式",
        "字段建议",
        "doc_variables_patch",
        "plan_md",
        "next_questions",
        "ready_to_write",
        "decision",
        "如果不输出",
        "你必须",
    ]
    for b in banned:
        if b in text:
            return ""
    return text


def _build_messages(s: Dict[str, Any], prompt_spec: Dict[str, Any]) -> list:
    """构造发送给模型的消息列表"""
    messages = [{"role": "system", "content": CONTROLLER_SYSTEM_PROMPT}]
    
    # 添加对话历史
    for msg in s.get("chat_history", []):
        messages.append(msg)
    
    # 把"上下文/快照"放到 user 角色，避免被当作系统规则复述到 thinking
    context_parts = []
    
    # 优先展示已有 Plan（让模型知道不需要重复输出）
    doc_vars = s.get("doc_variables") or {}
    existing_plan = doc_vars.get("plan_md") or ""
    if existing_plan.strip():
        context_parts.append(
            "【当前已有的 Plan（Markdown）】\n"
            "如果用户只是在讨论/澄清细节，你可以直接回复；\n"
            "只有当用户明确要求修改 Plan，或你认为需要根据新信息调整 Plan 时，才调用 update_plan 工具。\n"
            "---\n"
            + existing_plan.strip()
        )
    
    # 关键：展示当前已生成的文档内容（如果有），让模型可以修改
    existing_content = s.get("final_md") or s.get("draft_md") or ""
    if existing_content.strip():
        # 截断过长内容，或提供摘要
        content_preview = existing_content
        if len(content_preview) > 5000:
            content_preview = content_preview[:2000] + "\n... (中间省略) ...\n" + content_preview[-2000:]
        
        context_parts.append(
            "【当前已生成的文档内容（Markdown）】\n"
            "你可以使用 edit_document 工具来修改它。\n"
            "---\n"
            + content_preview
        )

    # 其他文档变量（排除 plan_md 避免重复）
    other_vars = {k: v for k, v in doc_vars.items() if k not in ("plan_md", "chat_history", "outline")}
    if other_vars:
        context_parts.append(
            "当前已收集的文档变量（仅供参考，可修改/补全）：\n"
            + json.dumps(other_vars, ensure_ascii=False, indent=2)
        )
    
    if prompt_spec.get("materials"):
        context_parts.append("用户上传的附件摘要（仅供参考）：\n" + "\n".join(prompt_spec["materials"]))
    if context_parts:
        messages.append({"role": "user", "content": "\n\n".join(context_parts)})
    
    return messages
