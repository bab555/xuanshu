"""
D：生图节点（Image）

职责：
- 扫描 Markdown 中的图片占位符：{{IMG:提示词}}
- 调用 qwen-image-max 生成图片
- 下载图片并保存到 storage
- 不修改正文：保留占位符，插入/替换由程序在导出/渲染阶段执行
"""

import re
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

import httpx

from app.config import settings
from app.services.model_client import model_client
from app.utils.storage import save_file, get_file_url


IMAGE_PATTERN = re.compile(r"\{\{image\+([^}]+)\}\}", re.IGNORECASE)


def _to_dict(state: Any) -> Dict[str, Any]:
    """将 state 统一转为 dict（兼容 Pydantic 模型和普通 dict）"""
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if hasattr(state, "dict"):
        return state.dict()
    if isinstance(state, dict):
        return state
    return {}


async def _download_image(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


async def run(state: Any) -> Dict[str, Any]:
    """
    D：生图节点

    输入：draft_md（来自 writer）
    输出：image_urls + doc_variables.generated_images（占位符->URL 映射）；不修改 draft_md
    """
    s = _to_dict(state)
    draft_md = s.get("draft_md") or ""

    placeholders = [m.group(1).strip() for m in IMAGE_PATTERN.finditer(draft_md)]
    placeholders = [p for p in placeholders if p]

    prompt_spec = {
        "node_type": "image",
        "goal": f"生成 {len(placeholders)} 张图片并插入到文档",
        "constraints": [
            "只处理 {{IMG:...}} 占位符",
            "生成完成后必须替换为 Markdown 图片链接",
        ],
        "materials": [],
        "output_format": "替换后的 Markdown + image_urls",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": [],
    }

    if not placeholders:
        node_run = {
            "node_type": "image",
            "prompt_spec": prompt_spec,
            "result": {"message": "没有发现图片占位符"},
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "image_urls": s.get("image_urls", []),
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "image",
            "node_status": "success",
            "error": None,
        }

    try:
        urls: List[str] = []
        generated: List[Dict[str, str]] = []

        # 逐个生成（避免并发触发限流）
        for prompt in placeholders:
            # 生成图片 URL
            gen_urls = await model_client.generate_image(
                model=settings.model_image,
                prompt=prompt,
            )
            if not gen_urls:
                raise Exception("图片生成失败：未返回图片 URL")
            img_url = gen_urls[0]

            # 下载并保存
            data = await _download_image(img_url)
            filename = f"img_{uuid.uuid4().hex}.png"
            filepath = await save_file(data, filename=filename, subdir="generated")
            public_url = get_file_url(filepath)
            urls.append(public_url)
            generated.append({"placeholder": f"{{{{image+{prompt}}}}}", "prompt": prompt, "url": public_url})

        node_run = {
            "node_type": "image",
            "prompt_spec": prompt_spec,
            "result": {
                "count": len(urls),
                "image_urls": urls,
                "generated_images": generated,
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }

        new_doc_vars = {**(s.get("doc_variables") or {})}
        prev = new_doc_vars.get("generated_images")
        if isinstance(prev, list):
            new_doc_vars["generated_images"] = prev + generated
        else:
            new_doc_vars["generated_images"] = generated

        return {
            **s,
            "doc_variables": new_doc_vars,
            "image_urls": urls,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "image",
            "node_status": "success",
            "error": None,
        }
    except Exception as e:
        node_run = {
            "node_type": "image",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "检查图片模型配置/网络后重试",
            },
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "image",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


