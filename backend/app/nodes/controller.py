"""
A：中控对话节点（Controller）

职责：
- 引导用户把文档需要写的内容说清楚
- 记录为 doc_variables JSON
- 校验完整性（缺什么就追问）
- 支持流式输出
"""
import json
from datetime import datetime
from typing import Dict, Any, AsyncGenerator, Optional, Callable

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
- 示例图片：如需示意图，在 Plan 中标注（此处插入示意图片），并提供占位符 `{{image+提示词}}`（提示词写得可直接用于文生图）
- 搜索图片：如需搜索图片，在 Plan 中标注（此处插入搜索图片），并写明图片主题/关键词/偏好
- 用户需要数据/新闻内容时，你可以按需帮助用户搜索

系统执行方式（供你写在 Plan 中，方便用户理解）：
- 系统会按章节顺序逐章撰写
- 如正文中出现 `{{image+...}}`，系统会按需生成图片，并记录生成结果；正文预览阶段仍保留占位符
- Mermaid 会进行“可渲染性校对”，有问题才会修复

关键工作方式：
- 先通过对话把需求聊清楚，（必要时，可以直接给出建议问用户是否可以）
- 在信息足够时，再输出一份MD格式的的 Plan（通过章节和内容提要的方式制作一份大纲）
- Plan 允许反复修改
- 在完成plan以后，提示用户可以点击“执行”按钮，开始撰写。

可调用工具（你可以提出调用请求）：
1) 修改 Plan：edit_plan(instruction)
2) 修改最终文档：edit_document(instruction)
3) 修复 Mermaid：fix_mermaid()

输出要求：
- 你的输出必须分成两段，并用如下标记（用于 UI 分栏显示）：
【对话】
（只写对用户的对话回复/提问，短一些）
【计划】
（只写 Plan 的 Markdown；如果 Plan 没变化，可以写"（Plan 保持不变）"）

- 关于【计划】部分的处理规则：
  · 如果用户提供的上下文里已经有"当前已有的 Plan"，且用户只是在讨论/澄清细节，【计划】部分写"（Plan 保持不变）"即可
  · 只有当用户明确要求修改 Plan，或你认为需要根据新信息调整 Plan 时，才输出修改后的完整 Plan
  · 不要每次都重复输出相同的 Plan

- Plan（Markdown）首次产出时应包含：
  1) 标题（主题）
  2) 目标与受众
  3) 【假设】与【约束】（可选）
  4) 章节大纲（outline，按章节列出标题）
  5) 分章要点（每章 5~8 条要点）
  6) 需要插入的图表/图片/搜索图片（可选，写清楚放在哪一章）
- 不要在输出里复述"提示词本身"或"字段清单/格式说明"。"""


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


def _is_plan_unchanged(plan_text: str) -> bool:
    """检查 plan_text 是否表示"Plan 保持不变"（模型选择不修改现有 Plan）"""
    if not plan_text:
        return True
    normalized = plan_text.strip().lower().replace(" ", "").replace("（", "(").replace("）", ")")
    unchanged_markers = [
        "(plan保持不变)",
        "(plan不变)",
        "(保持不变)",
        "(不变)",
        "(无修改)",
        "(planunchanged)",
        "(unchanged)",
    ]
    return any(marker in normalized for marker in unchanged_markers)


def _fallback_plan_from_text(text: str) -> Dict[str, Any]:
    """当模型未输出 JSON 时，支持【对话】/【计划】分段；避免把 Plan 同步到聊天。"""
    raw = (text or "").strip()

    def _split_marked(s: str) -> tuple[str, str]:
        chat_marker = "【对话】"
        plan_marker = "【计划】"
        if plan_marker not in s:
            return s.strip(), ""
        pre, post = s.split(plan_marker, 1)
        pre = pre.replace(chat_marker, "").strip()
        post = post.strip()
        return pre, post

    reply, plan_md = _split_marked(raw)

    # 如果模型明确表示"Plan 保持不变"，则不更新 plan_md
    if _is_plan_unchanged(plan_md):
        return {
            "plan_md": "",  # 空字符串表示不更新，后续合并时会保留原有 plan_md
            "doc_variables_patch": {},
            "next_questions": [],
            "reply": reply,
            "decision": "继续对话",
            "ready_to_write": False,
            "plan_unchanged": True,  # 标记：Plan 未变化
        }

    # 如果没有明确 Plan 段，尝试做轻量判别：长 Markdown/有章节结构 -> 当作 Plan
    if not plan_md:
        looks_like_plan = ("章节" in raw) or ("大纲" in raw) or ("## " in raw) or (raw.startswith("#") and len(raw) > 200)
        if looks_like_plan:
            plan_md = raw
            reply = "我已根据当前信息更新了计划，请在中间栏查看；如需我继续追问，我也可以先问几个关键问题。"

    # outline 提取：增强版，支持 Markdown 标题和数字列表
    outline: list[str] = []
    if plan_md:
        lines = [ln.strip() for ln in plan_md.splitlines() if ln.strip()]
        for ln in lines:
            # 1. Markdown 标题
            if ln.startswith(("#", "##", "###")):
                outline.append(ln.lstrip("#").strip())
                continue
            
            # 2. 数字列表标题 (1. 标题 / 1、标题)
            # 简单的正则匹配：数字开头，后面跟 . 或 、
            import re
            if re.match(r"^\d+[\.、]\s*", ln):
                # 去掉开头的数字和符号
                clean_ln = re.sub(r"^\d+[\.、]\s*", "", ln)
                # 去掉可能的加粗标记
                clean_ln = clean_ln.replace("**", "").replace("__", "").strip()
                if clean_ln:
                    outline.append(clean_ln)
                continue
                
        # 兜底：如果没提取到任何结构化标题，且行数适中，才取前几行
        if not outline and len(lines) > 0:
            # 只有当看起来确实像是一个短的大纲时才全取，否则只取前几行
            outline = lines[:8]

    patch: Dict[str, Any] = {}
    if plan_md:
        patch = {"plan_md": plan_md, "outline": outline}

    return {
        "plan_md": plan_md,
        "doc_variables_patch": patch,
        "next_questions": [],
        "reply": reply,
        "decision": "继续对话",
        "ready_to_write": False,
    }


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
    
    输入：用户消息、当前 doc_variables、附件摘要
    输出：更新后的 doc_variables、验证报告、回复
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
        "output_format": "按【对话】/【计划】分段输出（用于 UI 分栏），不输出 skills，不输出正文",
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
            )
        else:
            response = await model_client.call(
                model,
                messages,
                enable_search=settings.model_controller_enable_search,
                search_options={"search_strategy": settings.model_controller_search_strategy},
            )
            reasoning = ""
        
        # 解析输出
        result = _parse_controller_response(response)
        ready = bool(result.get("ready_to_write", False))
        decision = _normalize_decision(result.get("decision"), ready)
        ready = ready or (decision == "write")
        
        # 合并变量（Plan 永远写入）
        plan_md = (result.get("plan_md") or "").strip()
        patch = result.get("doc_variables_patch", {}) or {}
        new_variables = {
            **s.get("doc_variables", {}),
            **patch,
            **({"plan_md": plan_md} if plan_md else {}),
        }
        # 默认章节粒度执行（符合产品预期；旧数据不强制）
        if new_variables.get("write_mode") is None:
            new_variables["write_mode"] = "chapter"
        
        # 添加助手回复到对话历史
        new_chat_history = s.get("chat_history", []) + [
            {"role": "assistant", "content": result.get("reply", "")}
        ]
        
        # 记录到 node_runs（包含思考过程）
        node_run = {
            "node_type": "controller",
            "prompt_spec": prompt_spec,
            "result": {
                "doc_variables_patch": result.get("doc_variables_patch", {}),
                "reply": result.get("reply", ""),
                "decision": decision,
                "missing_fields": result.get("missing_fields", []),
                "next_questions": result.get("next_questions", []),
                "ready_to_write": ready,
                "plan_md_preview": plan_md[:500] + ("..." if len(plan_md) > 500 else ""),
                "reasoning": reasoning if settings.model_controller_enable_thinking else None,
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "doc_variables": new_variables,
            "chat_history": new_chat_history,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "controller",
            "node_status": "success",
            "error": None,
            "decision": decision,
            "ready_to_write": ready,
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


async def run_streaming(
    state: Any,
    on_thinking: Optional[Callable[[str], Any]] = None,
    on_content: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """
    A：中控对话节点（流式版本）
    
    支持实时推送思考过程和回复内容
    
    Args:
        state: 工作流状态
        on_thinking: 思考内容回调（增量）
        on_content: 回复内容回调（增量）
    
    Returns:
        更新后的状态
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
        "output_format": "按【对话】/【计划】分段输出（用于 UI 分栏），不输出 skills，不输出正文",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": s.get("attachments", []),
    }
    
    # 构造消息
    messages = _build_messages(s, prompt_spec)
    
    try:
        model = settings.model_controller
        full_reasoning = ""
        full_content = ""
        # 限制前端展示的思考长度（避免思维链过长影响体验）
        reasoning_preview_cap = 1000
        reasoning_preview_sent = 0
        
        # 流式调用
        async for event in model_client.stream_call(
            model=model,
            messages=messages,
            enable_thinking=settings.model_controller_enable_thinking,
            thinking_budget=settings.model_controller_thinking_budget,
            enable_search=settings.model_controller_enable_search,
            search_options={"search_strategy": settings.model_controller_search_strategy},
            max_tokens=8192,
        ):
            if event["type"] == "thinking":
                full_reasoning += event["content"]
                if on_thinking and reasoning_preview_sent < reasoning_preview_cap:
                    # 只推送前 reasoning_preview_cap 字符，避免过长
                    remaining = reasoning_preview_cap - reasoning_preview_sent
                    chunk = _sanitize_thinking_preview(event["content"][:remaining])
                    if chunk:
                        reasoning_preview_sent += len(chunk)
                        await _safe_callback(on_thinking, chunk)
            elif event["type"] == "content":
                full_content += event["content"]
                if on_content:
                    await _safe_callback(on_content, event["content"])
            elif event["type"] == "error":
                raise Exception(event["message"])
            elif event["type"] == "done":
                full_reasoning = event.get("reasoning", full_reasoning)
                full_content = event.get("content", full_content)
        
        # 解析输出
        result = _parse_controller_response(full_content)
        ready = bool(result.get("ready_to_write", False))
        decision = _normalize_decision(result.get("decision"), ready)
        ready = ready or (decision == "write")
        
        # 合并变量（Plan 永远写入）
        plan_md = (result.get("plan_md") or "").strip()
        patch = result.get("doc_variables_patch", {}) or {}
        new_variables = {
            **s.get("doc_variables", {}),
            **patch,
            **({"plan_md": plan_md} if plan_md else {}),
        }
        # 默认章节粒度执行（符合产品预期；旧数据不强制）
        if new_variables.get("write_mode") is None:
            new_variables["write_mode"] = "chapter"
        
        # 添加助手回复到对话历史
        new_chat_history = s.get("chat_history", []) + [
            {"role": "assistant", "content": result.get("reply", "")}
        ]
        
        # 记录到 node_runs
        node_run = {
            "node_type": "controller",
            "prompt_spec": prompt_spec,
            "result": {
                "doc_variables_patch": result.get("doc_variables_patch", {}),
                "reply": result.get("reply", ""),
                "decision": decision,
                "missing_fields": result.get("missing_fields", []),
                "next_questions": result.get("next_questions", []),
                "ready_to_write": ready,
                "plan_md_preview": plan_md[:500] + ("..." if len(plan_md) > 500 else ""),
                "reasoning": full_reasoning if settings.model_controller_enable_thinking else None,
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "doc_variables": new_variables,
            "chat_history": new_chat_history,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "controller",
            "node_status": "success",
            "error": None,
            "decision": decision,
            "ready_to_write": ready,
        }
        
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
        
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "controller",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


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
            "如果用户只是在讨论/澄清细节，【计划】部分可以留空或写（Plan 保持不变）；\n"
            "只有当用户明确要求修改 Plan，或你认为需要根据新信息调整 Plan 时，才在【计划】部分输出修改后的版本。\n"
            "---\n"
            + existing_plan.strip()
        )
    
    # 其他文档变量（排除 plan_md 避免重复）
    other_vars = {k: v for k, v in doc_vars.items() if k not in ("plan_md", "chat_history")}
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


def _parse_controller_response(response: str) -> Dict[str, Any]:
    """解析模型输出"""
    try:
        text = (response or "").strip()

        # 兼容：从 markdown code fence 中提取 JSON
        if "```json" in text:
            text = text.split("```json", 1)[1]
            text = text.split("```", 1)[0].strip()
        elif text.startswith("```") and "```" in text[3:]:
            text = text.split("```", 1)[1]
            text = text.split("```", 1)[0].strip()

        # 兼容：提取首个 JSON 对象片段
        if not text.startswith("{") and "{" in text and "}" in text:
            text = text[text.find("{") : text.rfind("}") + 1]

        result = json.loads(text)

        # 兼容旧字段：validation_report -> missing_fields / next_questions
        vr = result.get("validation_report") or {}
        if "missing_fields" not in result and isinstance(vr, dict):
            result["missing_fields"] = vr.get("missing_fields", [])
        if "next_questions" not in result and isinstance(vr, dict):
            result["next_questions"] = vr.get("next_questions", [])

        # 补齐 decision（保持模型输出的中文语义；内部会再 normalize）
        if "decision" not in result:
            result["decision"] = "开始撰写" if result.get("ready_to_write") else "继续对话"

        # plan_md 兜底：优先使用模型给出的 plan_md；否则尝试从 doc_variables_patch 里拼出来
        if not result.get("plan_md"):
            patch = result.get("doc_variables_patch") or {}
            outline = patch.get("outline") or []
            plan = patch.get("plan") or patch.get("plan_text") or ""
            skills = patch.get("skills") or patch.get("global_skills") or []
            parts = []
            if outline:
                parts.append("## 大纲\n" + "\n".join([f"- {x}" for x in outline]))
            if skills:
                if isinstance(skills, list):
                    parts.append("## 全局 skills\n" + "\n".join([f"- {x}" for x in skills]))
                else:
                    parts.append("## 全局 skills\n" + str(skills))
            if plan:
                if isinstance(plan, list):
                    parts.append("## 写作计划\n" + "\n".join([f"- {x}" for x in plan]))
                else:
                    parts.append("## 写作计划\n" + str(plan))
            if parts:
                result["plan_md"] = "\n\n".join(parts).strip()

        return result
        
    except (json.JSONDecodeError, IndexError):
        # 降级：把全文当作 Plan（保证“无论如何都产出 Plan”）
        return _fallback_plan_from_text(response or "")
