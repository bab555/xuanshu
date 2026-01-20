# skill-08：全文整合节点（Assembler）

> 对应开发文档：§5.1 节点 E

## 目标

实现 E：Assembler 节点：
- 整合 Writer 的文稿 + Diagram 的图表/原型
- 做一致性检查
- 输出 `final_md`

## 节点实现

### nodes/assembler.py

```python
import json
import re
from datetime import datetime
from app.services.model_client import model_client
from app.config import settings
from app.schemas.workflow import WorkflowState, NodePromptSpec

ASSEMBLER_SYSTEM_PROMPT = """你是红点集团内部文档工具的全文整合助手。

你的任务是：
1. 把草稿（draft_md）中的占位标记替换为实际的 Mermaid/HTML 代码
2. 做一致性检查（标题层级、术语一致、引用完整）
3. 生成最终版本

替换规则：
- `{{MERMAID:xxx}}` → 对应的 mermaid 代码块
- `{{HTML:xxx}}` → 对应的 HTML 原型块（用 <!--PROTO_HTML:id=xxx--> 包裹）

输出 JSON：
{
  "final_md": "完整的最终 Markdown",
  "consistency_report": {
    "issues": [],  // 发现的问题
    "fixes": []    // 已自动修复的问题
  }
}"""

async def run(state: WorkflowState) -> WorkflowState:
    """E：全文整合节点"""
    
    draft_md = state.get("draft_md", "")
    mermaid_blocks = state.get("mermaid_blocks", [])
    html_blocks = state.get("html_blocks", [])
    image_urls = state.get("image_urls", [])
    
    if not draft_md:
        return {
            **state,
            "current_node": "assembler",
            "node_status": "fail",
            "error": {
                "error_type": "validation_failed",
                "error_message": "没有草稿可整合",
                "retry_guidance": "请先运行 Writer 节点生成草稿",
            },
        }
    
    # 构造 node_prompt_spec
    prompt_spec: NodePromptSpec = {
        "node_type": "assembler",
        "goal": "整合所有内容，生成最终文档",
        "constraints": [
            "正确替换所有占位标记",
            "保持文档结构完整",
            "检查一致性（标题/术语/引用）",
        ],
        "materials": [],
        "output_format": "JSON: final_md + consistency_report",
        "variables_snapshot": state.get("doc_variables", {}),
        "attachments_snapshot": [],
    }
    
    # 尝试先做简单替换
    final_md = draft_md
    
    # 替换 Mermaid 占位
    for block in mermaid_blocks:
        block_id = block.get("id", "")
        code = block.get("code", "")
        # 匹配 {{MERMAID:xxx}} 或 {{MERMAID:描述}}
        pattern = r'\{\{MERMAID:[^}]*' + re.escape(block_id.replace("mermaid_", "")) + r'[^}]*\}\}'
        if re.search(pattern, final_md, re.IGNORECASE):
            replacement = f"```mermaid\n{code}\n```"
            final_md = re.sub(pattern, replacement, final_md, flags=re.IGNORECASE)
        else:
            # 按顺序替换第一个未替换的 MERMAID 占位
            final_md = re.sub(r'\{\{MERMAID:[^}]+\}\}', f"```mermaid\n{code}\n```", final_md, count=1)
    
    # 替换 HTML 占位
    for block in html_blocks:
        block_id = block.get("id", "")
        code = block.get("code", "")
        pattern = r'\{\{HTML:[^}]*' + re.escape(block_id.replace("html_", "")) + r'[^}]*\}\}'
        replacement = f"<!--PROTO_HTML:id={block_id}-->\n{code}\n<!--/PROTO_HTML-->"
        if re.search(pattern, final_md, re.IGNORECASE):
            final_md = re.sub(pattern, replacement, final_md, flags=re.IGNORECASE)
        else:
            final_md = re.sub(r'\{\{HTML:[^}]+\}\}', replacement, final_md, count=1)
    
    # 检查是否还有未替换的占位
    remaining_placeholders = re.findall(r'\{\{(?:MERMAID|HTML):[^}]+\}\}', final_md)
    
    if remaining_placeholders:
        # 调用模型处理剩余问题
        messages = [
            {"role": "system", "content": ASSEMBLER_SYSTEM_PROMPT},
            {"role": "user", "content": f"""请整合以下内容：

草稿（已部分替换）：
```markdown
{final_md}
```

未使用的 Mermaid 块：
{json.dumps([b for b in mermaid_blocks if b.get("id") not in final_md], ensure_ascii=False)}

未使用的 HTML 块：
{json.dumps([b for b in html_blocks if b.get("id") not in final_md], ensure_ascii=False)}

请完成替换并检查一致性。"""}
        ]
        
        try:
            model = settings.model_assembler
            response = await model_client.call(model, messages)
            result = parse_assembler_response(response)
            final_md = result.get("final_md", final_md)
        except Exception as e:
            # 模型调用失败，使用已有的 final_md
            pass
    
    # 记录节点运行
    node_run = {
        "node_type": "assembler",
        "prompt_spec": prompt_spec,
        "result": {
            "final_md": final_md[:500] + "..." if len(final_md) > 500 else final_md,
            "mermaid_count": len(mermaid_blocks),
            "html_count": len(html_blocks),
        },
        "status": "success",
        "timestamp": datetime.now().isoformat(),
    }
    
    return {
        **state,
        "final_md": final_md,
        "node_runs": state.get("node_runs", []) + [node_run],
        "current_node": "assembler",
        "node_status": "success",
        "error": None,
    }

def parse_assembler_response(response: str) -> dict:
    """解析整合模型输出"""
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
        return {"final_md": response, "consistency_report": {"issues": [], "fixes": []}}
```

## 验收标准

- [ ] 能正确替换 Mermaid 占位为实际代码块
- [ ] 能正确替换 HTML 占位为受控标记块
- [ ] 未匹配的占位能通过模型补全
- [ ] 输出的 `final_md` 结构完整
- [ ] 中间栏能展示整合节点的输入输出

