"""
Writer 节点 (Execution Engine)

职责：
- 接收 Skills 序列
- 逐个执行 Skill (Search -> Write -> Image -> Chart)
- 维护 Execution Context
- 流式输出结果
"""
import json
import re
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List

from app.services.model_client import model_client
from app.config import settings
from app.schemas.workflow import Skill

# --- Prompts ---

WRITER_BASE_SYSTEM_PROMPT = """你是红点集团内部文档工具的【执行引擎】。
你的任务是根据用户的指令（Skill Instruction）和上下文（Context）执行具体操作。
"""

WRITER_TEXT_PROMPT_TEMPLATE = """
【当前任务】：撰写文档内容
【指令】：{instruction}

【上下文信息】：
{context}

【已写内容摘要】：
{draft_summary}

【要求】：
1. 直接输出 Markdown 正文。
2. 严格基于上下文信息撰写，不要编造数据。
3. 如果指令要求插入图表或图片，请忽略（会有专门的 Skill 处理），你只负责文字。
4. 保持风格专业、简洁。
"""

SEARCH_PROMPT_TEMPLATE = """
【当前任务】：根据搜索结果提取信息
【搜索词】：{query}
【搜索结果】：
{search_results}

【要求】：
请根据搜索结果，总结出与"{purpose}"相关的关键信息。
输出一段简练的摘要，这段摘要将被注入到后续的写作上下文中。
"""

CHART_PROMPT_TEMPLATE = """
【当前任务】：生成 Mermaid 图表代码
【指令】：{instruction}
【图表类型】：{chart_type}
【上下文数据】：
{context}

【要求】：
1. 只输出 Mermaid 代码块 (```mermaid ... ```)。
2. 确保语法正确，节点名称不要包含特殊字符。
"""

UI_PROMPT_TEMPLATE = """
【当前任务】：生成 HTML 界面代码
【指令】：{instruction}

【要求】：
1. 输出一段 HTML 代码块 (```html ... ```)。
2. 使用 Tailwind CSS 进行样式设计（假设环境支持）。
3. 仅输出 HTML 结构，不需要完整的 <html> 标签。
"""

IMAGE_GENERATION_TEMPLATE = """
【当前任务】：生成图片占位符
【提示词】：{prompt}
【位置】：{placement}

【要求】：
请输出一个 Markdown 图片占位符，格式如下：
![{prompt}](/storage/generated/placeholder.png)
"""

# --- Helper Functions ---

def _to_dict(state: Any) -> Dict[str, Any]:
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if hasattr(state, "dict"):
        return state.dict()
    if isinstance(state, dict):
        return state
    return {}

async def _safe_callback(callback: Callable, *args):
    res = callback(*args)
    if asyncio.iscoroutine(res):
        await res

def _format_context(context_items: List[str]) -> str:
    if not context_items:
        return "无"
    return "\n---\n".join(context_items)

# --- Node Implementation ---

async def run(state: Any) -> Dict[str, Any]:
    """
    非流式入口（占位，主要使用 run_streaming）
    """
    return state

async def run_streaming(
    state: Any,
    on_content: Optional[Callable[[str], Any]] = None,
    on_skill_update: Optional[Callable[[Dict[str, Any]], Any]] = None, # 新的回调: 通知当前 Skill 状态
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    流式执行引擎
    """
    s = _to_dict(state)
    skills_data = s.get("skills", [])
    doc_vars = s.get("doc_variables", {})
    
    # 转换 skills dict 为 Skill 对象 (如果需要)
    skills: List[Skill] = []
    for item in skills_data:
        if isinstance(item, dict):
            # 兼容处理：确保有 id 和 status
            if "id" not in item: item["id"] = f"s_{len(skills)}"
            if "status" not in item: item["status"] = "pending"
            try:
                skills.append(Skill(**item))
            except Exception:
                 # 如果校验失败，构造一个基础 Skill
                 skills.append(Skill(id=item.get("id"), type=item.get("type", "write_text"), desc=item.get("desc", ""), args=item.get("args", {})))
        else:
            skills.append(item)

    if not skills:
        return {
            **s,
            "current_node": "writer",
            "node_status": "fail",
            "error": {"error_type": "validation_failed", "error_message": "没有可执行的 Skills"},
        }

    draft_md = ""
    context_items = [] # 累积的上下文 (Search Results, etc.)
    # 初始上下文：Plan 和 Materials
    if doc_vars.get("plan_md"):
        context_items.append(f"【写作计划】\n{doc_vars['plan_md']}")
    for m in s.get("attachments", []):
         if m.get("summary"):
             context_items.append(f"【参考材料】\n{m['summary']}")

    try:
        for i, skill in enumerate(skills):
            # 检查取消
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                raise asyncio.CancelledError()

            # 1. 更新 UI 状态 (灯亮)
            skill.status = "running"
            if on_skill_update:
                await _safe_callback(on_skill_update, skill.dict())

            # 2. 执行 Skill
            print(f"[Executor] Running skill: {skill.type} - {skill.desc}")
            
            skill_output = ""
            
            if skill.type == "search_web":
                # 执行搜索 (模拟或真实调用)
                query = skill.args.get("query", "")
                purpose = skill.args.get("purpose", "")
                
                if on_content:
                    await _safe_callback(on_content, f"\n\n> 🔍 **正在搜索**: {query}...\n\n")

                # 这里应该调用真实的 search_tool，目前先模拟或使用 model_client 的搜索能力
                # 由于 model_client.stream_call 支持 search，我们可以利用它
                search_messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": f"请搜索以下内容：{query}。目的是：{purpose}"}
                ]
                
                search_result_text = ""
                # 使用启用搜索的模型调用
                async for ev in model_client.stream_call(
                    model=settings.model_writer, # 使用 Writer 模型进行搜索总结
                    messages=search_messages,
                    enable_search=True,
                    search_options={"search_strategy": "standard"},
                    max_tokens=1000
                ):
                     if ev["type"] == "content":
                         search_result_text += ev["content"]
                
                # 总结搜索结果存入 Context
                summary_prompt = SEARCH_PROMPT_TEMPLATE.format(
                    query=query, 
                    search_results=search_result_text,
                    purpose=purpose
                )
                context_items.append(f"【搜索结果-{query}】\n{search_result_text[:1000]}...") # 限制长度
                skill.result = "搜索完成"
                
                if on_content:
                    await _safe_callback(on_content, f"> ✅ **搜索完成**\n\n")


            elif skill.type == "write_text":
                instruction = skill.args.get("instruction", "")
                
                prompt = WRITER_TEXT_PROMPT_TEMPLATE.format(
                    instruction=instruction,
                    context=_format_context(context_items),
                    draft_summary=draft_md[-1000:] if draft_md else "（暂无）"
                )
                
                messages = [
                    {"role": "system", "content": WRITER_BASE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
                
                async for ev in model_client.stream_call(
                    model=settings.model_writer,
                    messages=messages,
                    enable_thinking=settings.model_writer_enable_thinking,
                    thinking_budget=settings.model_writer_thinking_budget,
                    max_tokens=4096
                ):
                    if ev["type"] == "content":
                        chunk = ev["content"]
                        draft_md += chunk
                        skill_output += chunk
                        if on_content:
                            await _safe_callback(on_content, chunk)
                
                draft_md += "\n\n"
                if on_content: await _safe_callback(on_content, "\n\n")
                skill.result = "撰写完成"


            elif skill.type == "generate_image":
                prompt = skill.args.get("prompt", "")
                placement = skill.args.get("placement", "")
                
                if on_content:
                    await _safe_callback(on_content, f"\n\n> 🎨 **正在生成图片**: {prompt}...\n\n")

                # TODO: 调用真正的生图 API (如 flux-schnell / dall-e)
                # 这里先生成 Markdown 占位符，由后续逻辑或前端处理
                # 如果我们有 image_node，可以在这里直接调用 image node 的逻辑，或者只生成 {{IMG:...}}
                
                # 方案：直接生成 {{IMG:...}} 占位符，让现有的 export 服务处理，或者直接生成 mock URL
                img_markdown = f"{{{{IMG:{prompt}}}}}"
                draft_md += f"\n{img_markdown}\n"
                
                if on_content:
                    await _safe_callback(on_content, f"![{prompt}](/storage/generated/placeholder_loading.png)\n") # 前端可以显示一个 loading 图
                
                skill.result = "生图指令已发送"


            elif skill.type == "create_chart":
                instruction = skill.args.get("instruction", "")
                chart_type = skill.args.get("chart_type", "")
                
                if on_content:
                    await _safe_callback(on_content, f"\n\n> 📊 **正在构建图表**: {chart_type}...\n\n")
                
                prompt = CHART_PROMPT_TEMPLATE.format(
                    instruction=instruction,
                    chart_type=chart_type,
                    context=_format_context(context_items)
                )
                
                messages = [{"role": "system", "content": WRITER_BASE_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
                
                chart_code = ""
                async for ev in model_client.stream_call(model=settings.model_writer, messages=messages):
                    if ev["type"] == "content":
                        chart_code += ev["content"]
                
                # 清洗代码块标记
                if "```mermaid" in chart_code:
                    chart_code = chart_code.split("```mermaid")[1].split("```")[0].strip()
                elif "```" in chart_code:
                    chart_code = chart_code.split("```")[1].split("```")[0].strip()
                
                final_block = f"\n```mermaid\n{chart_code}\n```\n"
                draft_md += final_block
                if on_content:
                    await _safe_callback(on_content, final_block)
                
                skill.result = "图表生成完成"


            elif skill.type == "create_ui":
                instruction = skill.args.get("instruction", "")
                
                if on_content:
                     await _safe_callback(on_content, f"\n\n> 🖥️ **正在设计界面**...\n\n")

                prompt = UI_PROMPT_TEMPLATE.format(instruction=instruction)
                messages = [{"role": "system", "content": WRITER_BASE_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
                
                html_code = ""
                async for ev in model_client.stream_call(model=settings.model_writer, messages=messages):
                    if ev["type"] == "content":
                        html_code += ev["content"]
                
                if "```html" in html_code:
                    html_code = html_code.split("```html")[1].split("```")[0].strip()
                
                final_block = f"\n```html\n{html_code}\n```\n"
                draft_md += final_block
                if on_content:
                    await _safe_callback(on_content, final_block)
                
                skill.result = "UI 生成完成"

            # 3. 更新 Skill 状态 (完成)
            skill.status = "completed"
            if on_skill_update:
                await _safe_callback(on_skill_update, skill.dict())
        
        # 循环结束
        node_run = {
            "node_type": "writer",
            "status": "success",
            "result": {"draft_len": len(draft_md)},
            "timestamp": datetime.now().isoformat()
        }
        
        return {
            **s,
            "draft_md": draft_md,
            "skills": [sk.dict() for sk in skills], # 更新状态后的 skills
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "writer",
            "node_status": "success"
        }

    except asyncio.CancelledError:
        # 处理取消
        return {
             **s,
            "current_node": "writer",
            "node_status": "fail",
            "error": {"error_type": "cancelled", "error_message": "用户停止执行"}
        }
    except Exception as e:
        print(f"[Writer] Error: {e}")
        return {
            **s,
             "current_node": "writer",
            "node_status": "fail",
            "error": {"error_type": "model_error", "error_message": str(e)}
        }
