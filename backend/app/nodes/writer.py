"""
B：文档撰写节点（Writer）

职责：
- 依据 doc_variables + 材料，撰写/润色文档主体
- 输出 draft_md（允许内嵌 Mermaid/HTML 占位）
"""
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List, Tuple
import asyncio

from app.services.model_client import model_client
from app.config import settings

WRITER_SYSTEM_PROMPT = """你是红点集团内部文档工具的文档撰写助手。

根据提供的文档变量（doc_variables）和参考材料，撰写文档主体。

输出格式要求：
1. 使用 Markdown 格式
2. 需要图表的地方，用占位标记：`{{MERMAID:图表描述}}` 或 `{{HTML:原型描述}}`
3. 保持结构清晰，逻辑严谨
4. 只根据提供的信息撰写，不要编造
5. 目标是"说清楚一件事"，不追求华丽辞藻

你必须输出 JSON 格式：
```json
{
  "draft_md": "完整的 Markdown 文档内容",
  "mermaid_placeholders": [
    {"id": "mermaid_1", "description": "流程图：用户注册流程"}
  ],
  "html_placeholders": [
    {"id": "html_1", "description": "原型：登录页面布局"}
  ],
  "notes": "撰写说明（可选）"
}
```

占位标记示例：
- `{{MERMAID:用户注册流程图}}` - 后续由图文助手生成实际 Mermaid 代码
- `{{HTML:首页布局原型}}` - 后续由图文助手生成实际 HTML 代码"""

WRITER_STREAMING_SYSTEM_PROMPT = """你是红点集团内部文档工具的文档撰写助手（Qwen）。

请根据文档变量（doc_variables）和参考材料，直接输出一份 Markdown 草稿正文（不要 JSON，不要代码块包裹 JSON）。
如果你认为需要配图，可以在文中使用占位符：`{{image+提示词}}`（提示词要足够让文生图模型生成合适图片）；如果不需要图片，可以完全不使用。
如需图表，直接输出 Mermaid 代码块（```mermaid ... ```）。
如用户明确要求原型/界面示意/HTML，则可以输出 ```html``` 代码块，前端会自动渲染。

要求：
1. 结构清晰、逻辑严谨，目标是“说清楚一件事”
2. 允许合理补全用户未指定的细节，但必须在文中用“【假设】/【建议】”标注
3. 输出必须是 Markdown 正文（可以包含 Mermaid/HTML 代码块与 {{image+...}} 占位标记）"""

MERMAID_PATTERN = re.compile(r"\{\{MERMAID:([^}]+)\}\}")
HTML_PATTERN = re.compile(r"\{\{HTML:([^}]+)\}\}")


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
    B：文档撰写节点
    
    输入：doc_variables、附件摘要
    输出：draft_md、占位标记列表
    """
    # 统一转为 dict
    s = _to_dict(state)
    
    doc_vars = s.get("doc_variables", {})
    
    # 检查是否有足够信息
    # 放宽检查：只要有 doc_type/outline/plan_md 任一项，就可以开始撰写
    if not doc_vars.get("doc_type") and not doc_vars.get("outline") and not doc_vars.get("plan_md"):
        return {
            **s,
            "current_node": "writer",
            "node_status": "fail",
            "error": {
                "error_type": "validation_failed",
                "error_message": "文档信息不足，请先通过中控澄清需求（缺少 doc_type/outline/plan_md）",
                "retry_guidance": "返回中控节点补充文档类型和大纲",
            },
        }
    
    # 构造 node_prompt_spec
    prompt_spec = {
        "node_type": "writer",
        "goal": f"撰写文档：{doc_vars.get('doc_type', '未知主题')}",
        "constraints": [
            f"受众：{doc_vars.get('audience', '未指定')}",
            f"风格：{doc_vars.get('tone', '专业')}",
            "只根据提供的信息撰写，不编造",
            "需要图表的地方用占位标记",
            "只求说清楚，不追求华丽",
        ],
        "materials": [
            a.get("summary", "") 
            for a in s.get("attachments", []) 
            if a.get("summary")
        ],
        "output_format": "JSON: draft_md + placeholders",
        "variables_snapshot": doc_vars,
        "attachments_snapshot": s.get("attachments", []),
    }
    
    # 构造消息
    messages = [
        {"role": "system", "content": WRITER_SYSTEM_PROMPT},
        {"role": "user", "content": f"""请根据以下信息撰写文档：

文档变量：
```json
{json.dumps(doc_vars, ensure_ascii=False, indent=2)}
```

{_format_materials(prompt_spec["materials"])}

请开始撰写，输出 JSON 格式。"""}
    ]
    
    try:
        model = settings.model_writer
        response = await model_client.call(model, messages, max_tokens=8192)
        result = _parse_writer_response(response)
        
        node_run = {
            "node_type": "writer",
            "prompt_spec": prompt_spec,
            "result": {
                "draft_md_preview": result.get("draft_md", "")[:500] + "...",
                "mermaid_count": len(result.get("mermaid_placeholders", [])),
                "html_count": len(result.get("html_placeholders", [])),
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "draft_md": result.get("draft_md", ""),
            "mermaid_placeholders": result.get("mermaid_placeholders", []),
            "html_placeholders": result.get("html_placeholders", []),
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "writer",
            "node_status": "success",
            "error": None,
        }
        
    except Exception as e:
        node_run = {
            "node_type": "writer",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "重试调用撰写模型",
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "writer",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }

async def run_streaming(
    state: Any,
    on_content: Optional[Callable[[str], Any]] = None,
    on_chapter_start: Optional[Callable[[int, str], Any]] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    B：文档撰写节点（流式版本）

    - 流式输出 Markdown 草稿（实时推送给前端）
    - 结束后自动解析占位标记生成 placeholders
    """
    s = _to_dict(state)
    doc_vars = s.get("doc_variables", {})

    # 放宽检查：只要有 doc_type/outline/plan_md 任一项，就可以开始撰写
    if not doc_vars.get("doc_type") and not doc_vars.get("outline") and not doc_vars.get("plan_md"):
        return {
            **s,
            "current_node": "writer",
            "node_status": "fail",
            "error": {
                "error_type": "validation_failed",
                "error_message": "文档信息不足，无法开始撰写（缺少 doc_type/outline/plan_md）",
                "retry_guidance": "返回中控节点补充撰写指南/大纲",
            },
        }

    prompt_spec = {
        "node_type": "writer",
        "goal": f"撰写草稿：{doc_vars.get('doc_type', '未命名主题')}",
        "constraints": [
            f"受众：{doc_vars.get('audience', '未指定')}",
            f"风格：{doc_vars.get('tone', '专业')}",
            "输出 Markdown 草稿（非 JSON）",
            "需要图表/原型用占位标记",
        ],
        "materials": [
            a.get("summary", "")
            for a in s.get("attachments", [])
            if a.get("summary")
        ],
        "output_format": "Markdown 草稿（含占位标记）",
        "variables_snapshot": doc_vars,
        "attachments_snapshot": s.get("attachments", []),
    }

    messages = [
        {"role": "system", "content": WRITER_STREAMING_SYSTEM_PROMPT},
        {"role": "user", "content": f"""请根据以下信息撰写文档草稿：

文档变量：
```json
{json.dumps(doc_vars, ensure_ascii=False, indent=2)}
```

{_format_materials(prompt_spec["materials"])}

参考计划（Plan）：
{doc_vars.get("plan_md", "")}

请直接输出 Markdown 草稿正文。"""},
    ]

    try:
        model = settings.model_writer
        draft = ""

        # 章节粒度：只要 outline 存在且非空，就优先按章节执行（忽略 write_mode 标记，确保大纲被利用）
        # 兼容旧逻辑：如果显式设置了 write_mode="full"，则跳过
        has_outline = isinstance(doc_vars.get("outline"), list) and doc_vars.get("outline")
        force_full = doc_vars.get("write_mode") == "full"
        
        use_chapter_mode = has_outline and not force_full
        print(f"[Writer] mode={'chapter' if use_chapter_mode else 'full'}, outline_len={len(doc_vars.get('outline', []))}")

        if use_chapter_mode:
            outline: List[str] = [str(x) for x in doc_vars.get("outline") if str(x).strip()]
            plan_md = str(doc_vars.get("plan_md") or "")

            # 逐章生成
            for idx, title in enumerate(outline):
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    raise asyncio.CancelledError()
                if on_chapter_start:
                    await _safe_callback(on_chapter_start, idx, title)

                chapter_messages = [
                    {"role": "system", "content": WRITER_STREAMING_SYSTEM_PROMPT},
                    {"role": "user", "content": f"""请根据以下信息，只撰写第 {idx+1} 章《{title}》的内容（Markdown）。

要求：
- 以二级标题开头：## {title}
- 只写本章，不要写其他章节
- 如需图表，使用 mermaid 代码块
- 如需配图，可使用 {{IMG:提示词}} 占位符；不需要则不用

Plan（供参考，可引用其中的约束/要点）：
{plan_md}

已写内容（供保持风格一致，可简要参考，不要重复输出）：
{draft[-2000:]}
"""},
                ]

                async for ev in model_client.stream_call(
                    model=model,
                    messages=chapter_messages,
                    enable_thinking=settings.model_writer_enable_thinking,
                    thinking_budget=settings.model_writer_thinking_budget,
                    enable_search=settings.model_writer_enable_search,
                    search_options={"search_strategy": settings.model_writer_search_strategy},
                    max_tokens=8192,
                ):
                    if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                        raise asyncio.CancelledError()
                    if ev["type"] == "thinking":
                        # 丢弃思考内容（不展示）
                        continue
                    if ev["type"] == "content":
                        chunk = ev["content"]
                        draft += chunk
                        if on_content:
                            await _safe_callback(on_content, chunk)
                    elif ev["type"] == "error":
                        raise Exception(ev["message"])
                    elif ev["type"] == "done":
                        break

                # 章节之间空一行
                draft += "\n\n"
                if on_content:
                    await _safe_callback(on_content, "\n\n")
        else:
            async for ev in model_client.stream_call(
                model=model,
                messages=messages,
                enable_thinking=settings.model_writer_enable_thinking,
                thinking_budget=settings.model_writer_thinking_budget,
                enable_search=settings.model_writer_enable_search,
                search_options={"search_strategy": settings.model_writer_search_strategy},
                max_tokens=8192,
            ):
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    raise asyncio.CancelledError()
                if ev["type"] == "thinking":
                    continue
                if ev["type"] == "content":
                    chunk = ev["content"]
                    draft += chunk
                    if on_content:
                        await _safe_callback(on_content, chunk)
                elif ev["type"] == "error":
                    raise Exception(ev["message"])
                elif ev["type"] == "done":
                    break

        mermaid_placeholders, html_placeholders = _extract_placeholders(draft)

        node_run = {
            "node_type": "writer",
            "prompt_spec": prompt_spec,
            "result": {
                "draft_md_preview": (draft[:500] + "...") if len(draft) > 500 else draft,
                "mermaid_count": len(mermaid_placeholders),
                "html_count": len(html_placeholders),
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }

        return {
            **s,
            "draft_md": draft,
            "mermaid_placeholders": mermaid_placeholders,
            "html_placeholders": html_placeholders,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "writer",
            "node_status": "success",
            "error": None,
        }

    except asyncio.CancelledError:
        node_run = {
            "node_type": "writer",
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
            "current_node": "writer",
            "node_status": "fail",
            "error": node_run["error"],
        }
    except Exception as e:
        node_run = {
            "node_type": "writer",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "重试调用撰写模型",
            },
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "writer",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


async def _safe_callback(callback: Callable, *args):
    import asyncio
    res = callback(*args)
    if asyncio.iscoroutine(res):
        await res


def _extract_placeholders(draft_md: str):
    mermaids = []
    htmls = []

    mermaid_descs = MERMAID_PATTERN.findall(draft_md or "")
    html_descs = HTML_PATTERN.findall(draft_md or "")

    for idx, desc in enumerate(mermaid_descs, start=1):
        mermaids.append({"id": f"mermaid_{idx}", "description": desc.strip()})
    for idx, desc in enumerate(html_descs, start=1):
        htmls.append({"id": f"html_{idx}", "description": desc.strip()})

    return mermaids, htmls


def _format_materials(materials: list) -> str:
    """格式化参考材料"""
    if not materials:
        return ""
    return "参考材料摘要：\n" + "\n---\n".join(materials)


def _parse_writer_response(response: str) -> Dict[str, Any]:
    """解析撰写模型输出"""
    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        
        return json.loads(json_str.strip())
        
    except (json.JSONDecodeError, IndexError):
        # 降级：把整个输出当作 draft_md
        return {
            "draft_md": response,
            "mermaid_placeholders": [],
            "html_placeholders": []
        }
