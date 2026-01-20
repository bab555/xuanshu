"""
语法/渲染守护（使用中控模型 Qwen）

目标：
- 检查并修复 Markdown 内的 Mermaid 与 HTML 代码块，尽量保证可渲染/可运行
- 没问题：直接返回原文
- 有问题：返回修复后的 Markdown（只修改代码块，其他内容不动）
"""

import json
import re
from datetime import datetime
from typing import Dict, Any, List

from app.config import settings
from app.services.model_client import model_client


MERMAID_BLOCK_RE = re.compile(r"```mermaid\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
HTML_BLOCK_RE = re.compile(r"```html\n(.*?)\n```", re.DOTALL | re.IGNORECASE)


def _to_dict(state: Any) -> Dict[str, Any]:
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if hasattr(state, "dict"):
        return state.dict()
    if isinstance(state, dict):
        return state
    return {}


SYSTEM_PROMPT = """你是文档的代码块校对助手。

任务：只检查并修复 Markdown 中的 Mermaid 与 HTML 代码块，尽量保证可渲染/可运行。

约束（必须遵守）：
1) 只修改 mermaid/html 代码块内容；不要改动其他正文、标题、段落、图片占位符、其他代码块。
2) 如果没有明显问题，返回 ok=true。
3) 如果需要修复，返回每个 block 的修复结果（按原始 index 对应）。

输出必须是严格 JSON（不要 Markdown、不要解释）：
{
  "ok": true
}
或
{
  "ok": false,
  "fixed_mermaid_blocks": [
    {"index": 0, "code": "修复后的 mermaid 代码（不含 ```mermaid``` 包裹）"}
  ],
  "fixed_html_blocks": [
    {"index": 0, "code": "修复后的 html 代码（不含 ```html``` 包裹）"}
  ]
}
"""


async def run(state: Any) -> Dict[str, Any]:
    s = _to_dict(state)
    draft_md = (s.get("draft_md") or "").strip()

    mermaid_blocks = MERMAID_BLOCK_RE.findall(draft_md or "")
    html_blocks = HTML_BLOCK_RE.findall(draft_md or "")

    prompt_spec = {
        "node_type": "guard",
        "goal": f"校对 Mermaid({len(mermaid_blocks)}) + HTML({len(html_blocks)}) 代码块",
        "constraints": [
            "只修改 mermaid/html 代码块",
            "无问题则跳过",
        ],
        "materials": [],
        "output_format": "JSON: ok / fixed_mermaid_blocks / fixed_html_blocks",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": [],
    }

    if not mermaid_blocks and not html_blocks:
        node_run = {
            "node_type": "guard",
            "prompt_spec": prompt_spec,
            "result": {"ok": True, "message": "无 Mermaid/HTML 代码块，跳过"},
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "guard",
            "node_status": "success",
            "error": None,
        }

    user_payload = {
        "mermaid_blocks": [{"index": i, "code": code} for i, code in enumerate(mermaid_blocks)],
        "html_blocks": [{"index": i, "code": code} for i, code in enumerate(html_blocks)],
    }

    try:
        res = await model_client.call(
            model=settings.model_controller,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            enable_thinking=False,
            enable_search=False,
            max_tokens=4096,
        )

        text = (res or "").strip()
        if "```" in text:
            # 兼容模型包裹
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        result = json.loads(text)

        if result.get("ok") is True:
            node_run = {
                "node_type": "guard",
                "prompt_spec": prompt_spec,
                "result": {"ok": True},
                "status": "success",
                "timestamp": datetime.now().isoformat(),
            }
            return {
                **s,
                "node_runs": s.get("node_runs", []) + [node_run],
                "current_node": "guard",
                "node_status": "success",
                "error": None,
            }

        fixed_mermaid_blocks: List[dict] = result.get("fixed_mermaid_blocks") or []
        fixed_html_blocks: List[dict] = result.get("fixed_html_blocks") or []
        if (not isinstance(fixed_mermaid_blocks, list)) or (not isinstance(fixed_html_blocks, list)):
            raise ValueError("mermaid_guard: fixed_*_blocks 必须为 list")
        if not fixed_mermaid_blocks and not fixed_html_blocks:
            raise ValueError("mermaid_guard: ok=false 但未给出任何修复块")

        # 用替换方式应用修复：按 index 替换对应 block
        new_md = draft_md
        mermaid_matches = list(MERMAID_BLOCK_RE.finditer(draft_md))
        for item in fixed_mermaid_blocks:
            idx = item.get("index")
            code = item.get("code")
            if not isinstance(idx, int) or idx < 0 or idx >= len(mermaid_matches):
                continue
            if not isinstance(code, str) or not code.strip():
                continue
            old_code = mermaid_matches[idx].group(1)
            new_md = new_md.replace(
                f"```mermaid\n{old_code}\n```",
                f"```mermaid\n{code.strip()}\n```",
                1,
            )

        html_matches = list(HTML_BLOCK_RE.finditer(draft_md))
        for item in fixed_html_blocks:
            idx = item.get("index")
            code = item.get("code")
            if not isinstance(idx, int) or idx < 0 or idx >= len(html_matches):
                continue
            if not isinstance(code, str) or not code.strip():
                continue
            old_code = html_matches[idx].group(1)
            new_md = new_md.replace(
                f"```html\n{old_code}\n```",
                f"```html\n{code.strip()}\n```",
                1,
            )

        node_run = {
            "node_type": "guard",
            "prompt_spec": prompt_spec,
            "result": {
                "ok": False,
                "fixed_mermaid_count": len(fixed_mermaid_blocks),
                "fixed_html_count": len(fixed_html_blocks),
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }

        return {
            **s,
            "draft_md": new_md,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "guard",
            "node_status": "success",
            "error": None,
        }
    except Exception as e:
        node_run = {
            "node_type": "guard",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "检查 mermaid 校对模型/输出格式后重试",
            },
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "guard",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


