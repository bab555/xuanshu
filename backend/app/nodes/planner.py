"""
Skills Planner 节点

职责：
- 接收 plan_md（自然语言计划）
- 拆解为可执行的 atomic skills 序列（Search -> Write -> Image -> Chart）
- 输出结构化的 skills 列表供 Writer 执行
"""
import json
from datetime import datetime
from typing import Dict, Any, List

from app.services.model_client import model_client
from app.config import settings
from app.schemas.workflow import Skill

PLANNER_SYSTEM_PROMPT = """你是红点集团内部文档工具的【执行规划师】。

你的任务：
根据提供的【文档计划 (Plan)】和【大纲 (Outline)】，将其拆解为一系列可执行的原子步骤（Skills），供执行引擎按顺序执行。

可用的 Skill 类型（Atomic Skills）：
1. `search_web`: 需要联网搜索数据、事实、图片素材时使用。
   - args: {"query": "搜索关键词", "purpose": "搜索目的（找数据/找图）"}
2. `write_text`: 撰写文档正文段落/章节。
   - args: {"instruction": "具体撰写要求，包含要引用的数据或上下文"}
3. `generate_image`: 需要 AI 生成创意配图时使用（注意：如果是找真实图片，请用 search_web）。
   - args: {"prompt": "生图提示词", "placement": "图片插入位置描述"}
4. `create_chart`: 需要制作图表（Mermaid）时使用。
   - args: {"chart_type": "flowchart/sequence/pie/...", "instruction": "图表描述和数据"}
5. `create_ui`: 需要制作 HTML/原型界面时使用。
   - args: {"instruction": "界面布局和样式描述"}

规划原则：
- **粒度适中**：通常以“章”为单位进行规划，但如果一章里包含复杂的图表或需要先搜索，请拆分为多个步骤。
  - 例如：先 `search_web` (找数据) -> 然后 `write_text` (写正文，引用数据) -> 最后 `create_chart` (画图)。
- **逻辑连贯**：步骤之间要有逻辑顺序。
- **覆盖全面**：确保 Plan 中的所有要求（包括图片、图表、搜索）都被转化为具体的 Skill。

输出格式：
严格的 JSON 列表（List[Skill]），不要包含 markdown 代码块标记。
示例：
[
  {
    "id": "step_1",
    "type": "search_web",
    "desc": "搜索：2026 AI市场规模数据",
    "args": {"query": "2026 AI market size forecast", "purpose": "data"}
  },
  {
    "id": "step_2",
    "type": "write_text",
    "desc": "撰写：第一章 市场概况",
    "args": {"instruction": "撰写第一章，引用刚才搜索到的市场规模数据..."}
  }
]
"""

def _to_dict(state: Any) -> Dict[str, Any]:
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if hasattr(state, "dict"):
        return state.dict()
    if isinstance(state, dict):
        return state
    return {}

async def run(state: Any) -> Dict[str, Any]:
    """
    Planner 节点执行入口
    """
    s = _to_dict(state)
    doc_vars = s.get("doc_variables", {})
    plan_md = doc_vars.get("plan_md", "")
    outline = doc_vars.get("outline", [])

    if not plan_md and not outline:
        # 如果没有计划，直接生成一个默认的写作步骤
        default_skills = [
            {
                "id": "default_1",
                "type": "write_text",
                "desc": "撰写全文",
                "args": {"instruction": "根据当前信息撰写文档全文"}
            }
        ]
        return {
            **s,
            "skills": default_skills,
            "current_node": "planner",
            "node_status": "success"
        }

    # 构造 Prompt
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": f"""请根据以下计划生成执行步骤 (Skills)：

【Plan (Markdown)】:
{plan_md}

【Outline】:
{json.dumps(outline, ensure_ascii=False)}

请输出 JSON 列表。"""}
    ]

    try:
        # 调用模型 (使用 Writer 模型，通常也是 Qwen-Max)
        response = await model_client.call(
            model=settings.model_writer, 
            messages=messages,
            max_tokens=4096,
            enable_thinking=False, # 规划任务不需要太长的 CoT，直接指令跟随即可
            temperature=0.5
        )

        # 解析 JSON
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        
        skills_data = json.loads(text)
        
        # 验证并补全 ID
        skills = []
        for idx, item in enumerate(skills_data):
            if "id" not in item:
                item["id"] = f"skill_{idx+1}"
            if "status" not in item:
                item["status"] = "pending"
            skills.append(item)

        # 记录运行日志
        node_run = {
            "node_type": "planner",
            "status": "success",
            "result": {"skills_count": len(skills), "skills_preview": skills[:2]},
            "timestamp": datetime.now().isoformat()
        }

        return {
            **s,
            "skills": skills, # 存入 state
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "planner",
            "node_status": "success"
        }

    except Exception as e:
        # 降级：如果生成失败，回退到按 outline 生成简单的 write_text skills
        fallback_skills = []
        if outline:
            for idx, title in enumerate(outline):
                fallback_skills.append({
                    "id": f"fallback_{idx}",
                    "type": "write_text",
                    "desc": f"撰写：{title}",
                    "args": {"instruction": f"撰写章节：{title}"}
                })
        else:
             fallback_skills.append({
                "id": "fallback_full",
                "type": "write_text",
                "desc": "撰写全文",
                "args": {"instruction": "撰写文档全文"}
            })
            
        node_run = {
            "node_type": "planner",
            "status": "fail",
            "error": {"error_type": "model_error", "error_message": str(e)},
            "timestamp": datetime.now().isoformat()
        }
        
        return {
            **s,
            "skills": fallback_skills,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "planner",
            "node_status": "success" # 即使降级也算成功，保证后续能执行
        }

