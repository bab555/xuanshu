"""
代码修复节点（Repair Node）

职责：
- 接收前端上报的 Mermaid/HTML 渲染错误
- 调用 DeepSeek-V3 模型进行针对性修复
- 返回修复后的文档内容
"""

import json
import re
from typing import Dict, Any, List
from datetime import datetime

from app.config import settings
from app.services.model_client import model_client

REPAIR_SYSTEM_PROMPT = """你是代码修复专家（DeepSeek-V3）。

任务：根据报错信息，修复 Markdown 文档中的 Mermaid 或 HTML 代码块。

输入：
1. 原始 Markdown 文档片段（包含出错的代码块）
2. 错误列表（包含出错代码块的内容、错误信息）

要求：
1. 仔细分析错误信息（如 Syntax error, Layout error 等）。
2. 只修改出错的代码块，**绝对不要**修改其他正文内容。
3. 如果是 Mermaid 语法错误，尝试修正为正确的语法。
4. 如果是 Mermaid 布局/渲染错误，尝试简化图表或更换图表类型（如 flowchat, sequenceDiagram）。
5. 直接返回修复后的**完整 Markdown 文档内容**，不要包含任何解释、前言或后语。不要使用 ```markdown``` 包裹。

注意：
- 保持文档结构不变。
- 只修复报错的部分。
"""

async def run_repair(
    content_md: str,
    errors: List[Dict[str, Any]]
) -> str:
    """
    执行修复逻辑
    
    Args:
        content_md: 当前 Markdown 内容
        errors: 错误列表 [{"code": "...", "error": "...", "type": "mermaid"}]
        
    Returns:
        修复后的 Markdown 内容
    """
    if not content_md or not errors:
        return content_md

    # 构造 Prompt
    user_prompt = f"【原始文档】\n{content_md}\n\n【错误列表】\n"
    for i, err in enumerate(errors):
        user_prompt += f"错误 #{i+1} ({err.get('type')}):\n"
        user_prompt += f"代码片段:\n{err.get('code')}\n"
        user_prompt += f"报错信息:\n{err.get('error')}\n\n"
        
    user_prompt += "请修复上述错误，并返回完整的 Markdown 文档。"

    try:
        # 调用 DeepSeek-V3 (不开启思考)
        response = await model_client.call(
            model=settings.model_repair, # deepseek-v3
            messages=[
                {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            enable_thinking=False, # 不开启思考
            max_tokens=8192,
        )
        
        fixed_content = response.strip()
        
        # 简单的后处理：如果模型还是加了 ```markdown ... ```，去掉它
        if fixed_content.startswith("```markdown"):
            fixed_content = fixed_content[11:]
        elif fixed_content.startswith("```"):
            fixed_content = fixed_content[3:]
            
        if fixed_content.endswith("```"):
            fixed_content = fixed_content[:-3]
            
        return fixed_content.strip()

    except Exception as e:
        print(f"Repair failed: {e}")
        return content_md # 修复失败返回原文

