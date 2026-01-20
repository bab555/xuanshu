"""
C：图文助手节点（Diagram / HTML Assistant）

职责：
- 将占位标记转换为实际的 Mermaid / HTML 代码
- 输出可渲染的代码块
- 失败时不降级，返回给对应模型重做
"""
import json
from datetime import datetime
from typing import Dict, Any, List

from app.services.model_client import model_client
from app.config import settings

MERMAID_SYSTEM_PROMPT = """你是 Mermaid 图表生成专家。

根据描述生成 Mermaid 代码，要求：
1. 使用标准 Mermaid 语法
2. 图表清晰、简洁
3. 节点标签简短明了
4. 只生成最终代码，不要解释

输出格式：
```json
{
  "code": "完整的 Mermaid 代码",
  "type": "flowchart|sequence|class|er|gantt|...",
  "notes": "生成说明（可选）"
}
```"""

HTML_SYSTEM_PROMPT = """你是 HTML 原型生成专家。

根据描述生成简洁的 HTML 原型代码，要求：
1. 使用最小化 HTML + 内联 CSS
2. 只展示布局和结构概念
3. 不追求美观，只求清晰表达意图
4. 宽度控制在 800px 以内，便于截图
5. 使用简单颜色块表示不同区域
6. 添加文字标注说明各区域用途

输出格式：
```json
{
  "code": "完整的 HTML 代码（包含内联 CSS）",
  "width": 800,
  "notes": "生成说明（可选）"
}
```

示例风格：
```html
<div style="width:800px;border:1px solid #333;padding:10px;font-family:sans-serif;">
  <div style="background:#ddd;padding:20px;text-align:center;">顶部导航区</div>
  <div style="display:flex;margin-top:10px;">
    <div style="background:#eef;flex:1;padding:40px;text-align:center;">左侧边栏</div>
    <div style="background:#efe;flex:3;padding:40px;text-align:center;">主内容区</div>
  </div>
</div>
```"""


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
    C：图文助手节点
    
    输入：占位标记列表
    输出：生成的 Mermaid/HTML 代码
    """
    # 统一转为 dict
    s = _to_dict(state)
    
    mermaid_placeholders = s.get("mermaid_placeholders", [])
    html_placeholders = s.get("html_placeholders", [])
    
    if not mermaid_placeholders and not html_placeholders:
        # 没有占位标记，跳过
        node_run = {
            "node_type": "diagram",
            "prompt_spec": {"node_type": "diagram", "goal": "无图表占位"},
            "result": {"message": "没有图表/原型占位标记"},
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "mermaid_codes": {},
            "html_codes": {},
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "diagram",
            "node_status": "success",
        }
    
    # 构造 node_prompt_spec
    prompt_spec = {
        "node_type": "diagram",
        "goal": f"生成 {len(mermaid_placeholders)} 个 Mermaid 图表，{len(html_placeholders)} 个 HTML 原型",
        "constraints": [
            "Mermaid: 使用标准语法，清晰简洁",
            "HTML: 宽度 ≤ 800px，只展示布局概念",
            "失败不降级，返回重做",
        ],
        "materials": [],
        "output_format": "JSON: code + type/width",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": [],
    }
    
    try:
        mermaid_codes = {}
        html_codes = {}
        errors = []
        
        # 生成 Mermaid
        for ph in mermaid_placeholders:
            result = await _generate_mermaid(ph["description"])
            if result.get("code"):
                mermaid_codes[ph["id"]] = result
            else:
                errors.append({
                    "type": "mermaid",
                    "id": ph["id"],
                    "description": ph["description"],
                    "error": result.get("error", "生成失败")
                })
        
        # 生成 HTML
        for ph in html_placeholders:
            result = await _generate_html(ph["description"])
            if result.get("code"):
                html_codes[ph["id"]] = result
            else:
                errors.append({
                    "type": "html",
                    "id": ph["id"],
                    "description": ph["description"],
                    "error": result.get("error", "生成失败")
                })
        
        # 如果有失败，需要重做（不降级）
        if errors:
            node_run = {
                "node_type": "diagram",
                "prompt_spec": prompt_spec,
                "result": {
                    "mermaid_generated": len(mermaid_codes),
                    "html_generated": len(html_codes),
                    "errors": errors,
                },
                "status": "partial",
                "error": {
                    "error_type": "generation_failed",
                    "error_message": f"{len(errors)} 个图表生成失败",
                    "retry_guidance": "重新生成失败的图表",
                    "failed_items": errors,
                },
                "timestamp": datetime.now().isoformat(),
            }
            
            return {
                **s,
                "mermaid_codes": mermaid_codes,
                "html_codes": html_codes,
                "diagram_errors": errors,  # 保存错误信息，便于重试
                "node_runs": s.get("node_runs", []) + [node_run],
                "current_node": "diagram",
                "node_status": "partial",  # 部分成功，需要重试失败的
                "error": node_run["error"],
                "retry_count": s.get("retry_count", 0) + 1,
            }
        
        # 全部成功
        node_run = {
            "node_type": "diagram",
            "prompt_spec": prompt_spec,
            "result": {
                "mermaid_generated": len(mermaid_codes),
                "html_generated": len(html_codes),
                "mermaid_preview": {k: v.get("type", "") for k, v in mermaid_codes.items()},
                "html_preview": {k: f"宽度={v.get('width', 800)}px" for k, v in html_codes.items()},
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "mermaid_codes": mermaid_codes,
            "html_codes": html_codes,
            "diagram_errors": [],
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "diagram",
            "node_status": "success",
            "error": None,
        }
        
    except Exception as e:
        node_run = {
            "node_type": "diagram",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "重试调用图文模型",
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "diagram",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


async def _generate_mermaid(description: str) -> Dict[str, Any]:
    """生成 Mermaid 代码"""
    messages = [
        {"role": "system", "content": MERMAID_SYSTEM_PROMPT},
        {"role": "user", "content": f"请生成图表：{description}"}
    ]
    
    try:
        model = settings.model_diagram
        response = await model_client.call(model, messages)
        return _parse_code_response(response)
    except Exception as e:
        return {"error": str(e)}


async def _generate_html(description: str) -> Dict[str, Any]:
    """生成 HTML 原型"""
    messages = [
        {"role": "system", "content": HTML_SYSTEM_PROMPT},
        {"role": "user", "content": f"请生成原型：{description}"}
    ]
    
    try:
        model = settings.model_diagram
        response = await model_client.call(model, messages)
        return _parse_code_response(response)
    except Exception as e:
        return {"error": str(e)}


def _parse_code_response(response: str) -> Dict[str, Any]:
    """解析代码生成响应"""
    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        
        return json.loads(json_str.strip())
        
    except (json.JSONDecodeError, IndexError):
        # 尝试直接提取代码块
        if "```mermaid" in response:
            code = response.split("```mermaid")[1].split("```")[0]
            return {"code": code.strip(), "type": "auto"}
        elif "```html" in response:
            code = response.split("```html")[1].split("```")[0]
            return {"code": code.strip(), "width": 800}
        
        return {"error": "无法解析响应"}
