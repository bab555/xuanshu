# skill-07：图文助手节点（Diagram/HTML）

> 对应开发文档：§5.1 节点 C、§6.1 内容格式约定

## 目标

实现 C：Diagram/HTML 节点：
- 根据占位标记生成 Mermaid 图
- 根据占位标记生成 HTML 原型
- 支持失败后重制（简化语法）

## 节点实现

### nodes/diagram.py

```python
import json
from datetime import datetime
from app.services.model_client import model_client
from app.config import settings
from app.schemas.workflow import WorkflowState, NodePromptSpec

DIAGRAM_SYSTEM_PROMPT = """你是红点集团内部文档工具的图文助手。

你的任务是根据描述生成：
1. Mermaid 图表代码
2. HTML 原型代码

要求：
- Mermaid 使用标准语法，保持简单（避免复杂嵌套）
- HTML 原型只用基础标签和内联样式，不引用外部资源
- 目标是"能看懂"，不追求美观
- 每个输出必须带 id

输出 JSON：
{
  "mermaid_blocks": [
    {"id": "mermaid_xxx", "code": "graph TD\\nA-->B", "description": "描述"}
  ],
  "html_blocks": [
    {"id": "html_xxx", "code": "<div>...</div>", "description": "描述"}
  ]
}

Mermaid 语法提示：
- 流程图：graph TD / graph LR
- 时序图：sequenceDiagram
- 甘特图：gantt
- 避免特殊字符和太长的节点文本"""

async def run(state: WorkflowState) -> WorkflowState:
    """C：图文助手节点"""
    
    mermaid_placeholders = state.get("mermaid_placeholders", [])
    html_placeholders = state.get("html_placeholders", [])
    
    if not mermaid_placeholders and not html_placeholders:
        # 没有需要生成的图表
        return {
            **state,
            "mermaid_blocks": [],
            "html_blocks": [],
            "current_node": "diagram",
            "node_status": "success",
        }
    
    # 构造 node_prompt_spec
    prompt_spec: NodePromptSpec = {
        "node_type": "diagram",
        "goal": "生成文档所需的 Mermaid 图表和 HTML 原型",
        "constraints": [
            "Mermaid 使用简单语法，避免复杂特性",
            "HTML 只用基础标签和内联样式",
            "不引用外部资源",
            "只求能看懂，不追求美观",
        ],
        "materials": [],
        "output_format": "JSON: mermaid_blocks + html_blocks",
        "variables_snapshot": state.get("doc_variables", {}),
        "attachments_snapshot": [],
    }
    
    # 如果是重试（有错误信息），加入重制指导
    retry_guidance = ""
    if state.get("error"):
        error = state["error"]
        if error.get("error_type") in ["mermaid_render_failed", "html_capture_failed"]:
            retry_guidance = f"""
注意：上次生成的代码渲染失败了。
错误信息：{error.get('error_message', '')}
失败的代码：
```
{error.get('block_source', '')}
```
请简化语法，避免：
- 特殊字符
- 太长的文本
- 复杂嵌套
- 不兼容的语法特性
"""
    
    messages = [
        {"role": "system", "content": DIAGRAM_SYSTEM_PROMPT},
        {"role": "user", "content": f"""请生成以下图表和原型：

Mermaid 图表需求：
{json.dumps(mermaid_placeholders, ensure_ascii=False, indent=2) if mermaid_placeholders else "无"}

HTML 原型需求：
{json.dumps(html_placeholders, ensure_ascii=False, indent=2) if html_placeholders else "无"}

{retry_guidance}

请输出 JSON。"""}
    ]
    
    try:
        model = settings.model_diagram
        response = await model_client.call(model, messages)
        result = parse_diagram_response(response)
        
        node_run = {
            "node_type": "diagram",
            "prompt_spec": prompt_spec,
            "result": result,
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **state,
            "mermaid_blocks": result.get("mermaid_blocks", []),
            "html_blocks": result.get("html_blocks", []),
            "node_runs": state.get("node_runs", []) + [node_run],
            "current_node": "diagram",
            "node_status": "success",
            "error": None,  # 清除之前的错误
            "retry_count": 0,  # 重置重试计数
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
            **state,
            "node_runs": state.get("node_runs", []) + [node_run],
            "current_node": "diagram",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": state.get("retry_count", 0) + 1,
        }

def parse_diagram_response(response: str) -> dict:
    """解析图文模型输出"""
    import json
    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        return json.loads(json_str)
    except:
        return {"mermaid_blocks": [], "html_blocks": []}
```

## HTML 原型约束（受控）

```html
<!-- 允许的标签 -->
div, span, p, h1-h4, ul, ol, li, table, tr, td, th, pre, code, strong, em

<!-- 允许的样式属性 -->
color, background-color, border, padding, margin, font-size, font-weight,
display, flex, grid, width, height, text-align

<!-- 禁止 -->
- 外链 JS/CSS
- <script>, <link>, <style> 标签
- 网络请求（img src=http...）
- 复杂动画
```

## 验收标准

- [ ] 能根据占位标记生成 Mermaid 代码
- [ ] 能根据占位标记生成 HTML 原型代码
- [ ] 生成的 Mermaid 能在前端渲染
- [ ] 生成的 HTML 能在受控容器中渲染
- [ ] 渲染失败时，能接收错误信息并重制

