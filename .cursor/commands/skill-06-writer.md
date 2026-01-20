# skill-06：文档撰写节点（Writer）

> 对应开发文档：§5.1 节点 B

## 目标

实现 B：Writer 节点：
- 根据 `doc_variables` 和参考材料撰写文档主体
- 输出 `draft_md`（允许 Mermaid/HTML 占位）

## 节点实现

### nodes/writer.py

```python
import json
from datetime import datetime
from app.services.model_client import model_client
from app.config import settings
from app.schemas.workflow import WorkflowState, NodePromptSpec

WRITER_SYSTEM_PROMPT = """你是红点集团内部文档工具的文档撰写助手。

根据提供的文档变量（doc_variables）和参考材料，撰写文档主体。

输出格式：
- 使用 Markdown 格式
- 需要图表的地方，用占位标记：`{{MERMAID:图表描述}}` 或 `{{HTML:原型描述}}`
- 保持结构清晰，逻辑严谨
- 只根据提供的信息撰写，不要编造
- 目标是"说清楚一件事"，不追求华丽辞藻

输出 JSON：
{
  "draft_md": "完整的 Markdown 文档内容",
  "mermaid_placeholders": [{"id": "xxx", "description": "图表描述"}],
  "html_placeholders": [{"id": "xxx", "description": "原型描述"}]
}"""

async def run(state: WorkflowState) -> WorkflowState:
    """B：文档撰写节点"""
    
    doc_vars = state.get("doc_variables", {})
    
    # 构造 node_prompt_spec
    prompt_spec: NodePromptSpec = {
        "node_type": "writer",
        "goal": f"撰写文档：{doc_vars.get('doc_type', '未知主题')}",
        "constraints": [
            f"受众：{doc_vars.get('audience', '未指定')}",
            "只根据提供的信息撰写，不编造",
            "需要图表的地方用占位标记",
            "只求说清楚，不追求华丽",
        ],
        "materials": [
            a.get("summary", "") for a in state.get("attachments", []) if a.get("summary")
        ],
        "output_format": "JSON: draft_md + placeholders",
        "variables_snapshot": doc_vars,
        "attachments_snapshot": state.get("attachments", []),
    }
    
    # 构造消息
    messages = [
        {"role": "system", "content": WRITER_SYSTEM_PROMPT},
        {"role": "user", "content": f"""请根据以下信息撰写文档：

文档变量：
```json
{json.dumps(doc_vars, ensure_ascii=False, indent=2)}
```

{f"参考材料摘要：" + chr(10).join(prompt_spec["materials"]) if prompt_spec["materials"] else ""}

请开始撰写。"""}
    ]
    
    try:
        model = settings.model_writer
        response = await model_client.call(model, messages)
        result = parse_writer_response(response)
        
        node_run = {
            "node_type": "writer",
            "prompt_spec": prompt_spec,
            "result": result,
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **state,
            "draft_md": result.get("draft_md", ""),
            "mermaid_placeholders": result.get("mermaid_placeholders", []),
            "html_placeholders": result.get("html_placeholders", []),
            "node_runs": state.get("node_runs", []) + [node_run],
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
            **state,
            "node_runs": state.get("node_runs", []) + [node_run],
            "current_node": "writer",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": state.get("retry_count", 0) + 1,
        }

def parse_writer_response(response: str) -> dict:
    """解析撰写模型输出"""
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
        # 降级：把整个输出当作 draft_md
        return {
            "draft_md": response,
            "mermaid_placeholders": [],
            "html_placeholders": []
        }
```

## 验收标准

- [ ] 能根据 `doc_variables` 生成 `draft_md`
- [ ] 图表/原型位置用占位标记表示
- [ ] 中间栏能展示撰写节点的输入输出
- [ ] 失败时记录错误并触发回流

