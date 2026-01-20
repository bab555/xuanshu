"""
E：终审校验节点（Checker / DeepSeek）

职责：
- 不询问用户、不改变内容逻辑
- 仅修正：明显语法错误、mermaid 代码错误、章节号/格式错误、上下文断裂、明显计算错误
- 输出 final_md
"""

from datetime import datetime
from typing import Dict, Any, Optional, Callable

import asyncio

from app.services.model_client import model_client
from app.config import settings


def _to_dict(state: Any) -> Dict[str, Any]:
    """将 state 统一转为 dict（兼容 Pydantic 模型和普通 dict）"""
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if hasattr(state, "dict"):
        return state.dict()
    if isinstance(state, dict):
        return state
    return {}


CHECKER_SYSTEM_PROMPT = """你是红点集团内部文档工具的终审校验助手（DeepSeek）。

你只做“技术性校验与修正”，不做需求追问，不新增章节，不改变观点与逻辑。

你需要检查并修正以下问题：
1) Markdown 语法问题（列表/标题/代码块闭合/多余空行导致的断裂）
2) Mermaid 代码块语法错误（尽量做最小修正使其可渲染；无法修正则保留原样并在代码块上方加一行简短注释说明）
3) 章节编号/格式明显错误（如 1/1.1/2 跳号、标题层级混乱）
4) 上下文衔接明显错误（如段落被截断、句子不完整）
5) 明显的计算错误（只改算式/数字，不扩写解释）

重要保留项：
- 文本中的图片占位符 `{{image+...}}` 必须原样保留，不要改写/不要删除/不要替换

输出要求：
- 只输出修正后的 Markdown 全文
- 不要输出解释、不输出 JSON、不输出代码块包裹"""

async def run_streaming(
    state: Any,
    on_content: Optional[Callable[[str], Any]] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """终审校验（流式）：把最终 Markdown 全文增量输出给前端"""
    s = _to_dict(state)
    draft_md = (s.get("draft_md") or s.get("final_md") or "").strip()

    prompt_spec = {
        "node_type": "checker",
        "goal": "对全文做技术性终审校验与最小修正（流式输出最终正文）",
        "constraints": [
            "不询问用户、不改变内容逻辑",
            "只修语法/格式/mermaid/明显计算错误",
            "只输出最终 Markdown 全文",
        ],
        "materials": [],
        "output_format": "Markdown 全文（流式）",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": [],
    }

    try:
        messages = [
            {"role": "system", "content": CHECKER_SYSTEM_PROMPT},
            {"role": "user", "content": draft_md},
        ]
        model = settings.model_controller
        fixed = ""

        async for ev in model_client.stream_call(
            model=model,
            messages=messages,
            enable_thinking=False,
            max_tokens=8192,
        ):
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                raise asyncio.CancelledError()
            if ev["type"] == "content":
                chunk = ev["content"]
                fixed += chunk
                if on_content:
                    res = on_content(chunk)
                    if asyncio.iscoroutine(res):
                        await res
            elif ev["type"] == "error":
                raise Exception(ev["message"])
            elif ev["type"] == "done":
                break

        node_run = {
            "node_type": "checker",
            "prompt_spec": prompt_spec,
            "result": {"final_md_preview": (fixed or "")[:500] + ("..." if fixed and len(fixed) > 500 else "")},
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "final_md": fixed,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "checker",
            "node_status": "success",
            "error": None,
        }
    except asyncio.CancelledError:
        node_run = {
            "node_type": "checker",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "cancelled",
                "error_message": "用户已停止输出",
                "retry_guidance": "修改计划后可重新执行",
            },
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "checker",
            "node_status": "fail",
            "error": node_run["error"],
        }
    except Exception as e:
        node_run = {
            "node_type": "checker",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "检查终审模型配置后重试",
            },
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "checker",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


async def run(state: Any) -> Dict[str, Any]:
    s = _to_dict(state)
    draft_md = (s.get("draft_md") or s.get("final_md") or "").strip()

    prompt_spec = {
        "node_type": "checker",
        "goal": "对全文做技术性终审校验与最小修正",
        "constraints": [
            "不询问用户、不改变内容逻辑",
            "只修语法/格式/mermaid/明显计算错误",
        ],
        "materials": [],
        "output_format": "Markdown 全文",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": [],
    }

    try:
        messages = [
            {"role": "system", "content": CHECKER_SYSTEM_PROMPT},
            {"role": "user", "content": draft_md},
        ]
        # 终审不需要思考链
        model = settings.model_controller
        fixed = await model_client.call(model, messages, max_tokens=8192, enable_thinking=False)

        node_run = {
            "node_type": "checker",
            "prompt_spec": prompt_spec,
            "result": {"final_md_preview": (fixed or "")[:500] + ("..." if fixed and len(fixed) > 500 else "")},
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }

        return {
            **s,
            "final_md": fixed,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "checker",
            "node_status": "success",
            "error": None,
        }
    except Exception as e:
        node_run = {
            "node_type": "checker",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "检查终审模型配置后重试",
            },
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "checker",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


