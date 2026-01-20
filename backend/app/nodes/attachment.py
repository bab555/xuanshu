"""
F：附件分析节点（Attachment LONG）

职责：
- 对用户上传的文件/图片做分析
- 使用 DashScope LONG 模型（支持文件直传）
- 输出 attachment_summary + doc_variables_patch
"""
import json
from datetime import datetime
from typing import Dict, Any, List

from app.services.model_client import model_client
from app.config import settings

ATTACHMENT_ANALYSIS_PROMPT = """请分析用户上传的文件/图片，提取可用于文档撰写的信息。

你需要输出 JSON 格式：
```json
{
  "summary": "面向写作的摘要（分条列出要点）",
  "doc_variables_patch": {
    // 可以合并到文档变量的信息
    // 比如从文件中提取的：主题、结构、术语、流程、关键点等
  },
  "citations": [
    // 引用定位（页码/章节/区域，如果适用）
  ]
}
```

规则：
- 只提取文件中实际存在的信息，不要编造
- 输出尽量结构化，便于写入变量
- 目标是帮助用户"说清楚一件事"
- 如果是图片，描述图片内容和可能的用途"""


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
    F：附件分析节点
    
    输入：待分析的附件列表
    输出：附件摘要、doc_variables 补丁
    """
    # 统一转为 dict
    s = _to_dict(state)
    
    # 找到未分析的附件
    attachments = s.get("attachments", [])
    pending_attachments = [
        a for a in attachments
        if not a.get("summary")
    ]
    
    if not pending_attachments:
        # 没有待分析附件，直接通过
        node_run = {
            "node_type": "attachment",
            "prompt_spec": {"node_type": "attachment", "goal": "无待分析附件"},
            "result": {"message": "没有待分析的附件"},
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "attachment",
            "node_status": "success",
        }
    
    # 构造 node_prompt_spec
    prompt_spec = {
        "node_type": "attachment",
        "goal": "分析用户上传的附件，提取可用于写作的信息",
        "constraints": [
            "只提取附件中实际存在的信息",
            "不编造",
            "输出结构化，便于写入变量"
        ],
        "materials": [],
        "output_format": "JSON: summary + doc_variables_patch + citations",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": pending_attachments,
    }
    
    try:
        updated_attachments = []
        all_patches = {}
        all_summaries = []
        
        for att in attachments:
            if att.get("summary"):
                # 已分析过
                updated_attachments.append(att)
                continue
            
            # 调用 LONG 模型分析
            result = await _analyze_single_attachment(att)
            
            # 更新附件
            updated_att = {
                **att,
                "summary": result.get("summary", ""),
                "analysis_result": result
            }
            updated_attachments.append(updated_att)
            all_summaries.append(result.get("summary", ""))
            
            # 合并 patches
            if result.get("doc_variables_patch"):
                all_patches.update(result["doc_variables_patch"])
        
        # 更新状态
        new_variables = {**s.get("doc_variables", {}), **all_patches}
        attachment_analysis = "\n\n".join([sm for sm in all_summaries if sm]).strip()
        
        node_run = {
            "node_type": "attachment",
            "prompt_spec": prompt_spec,
            "result": {
                "attachment_summaries": all_summaries,
                "doc_variables_patch": all_patches,
                "analyzed_count": len(pending_attachments),
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "attachments": updated_attachments,
            "doc_variables": new_variables,
            # 兼容：给工作流/测试一个聚合字段
            "attachment_analysis": attachment_analysis,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "attachment",
            "node_status": "success",
            "error": None,
        }
        
    except Exception as e:
        node_run = {
            "node_type": "attachment",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "model_error",
                "error_message": str(e),
                "retry_guidance": "重试调用 LONG 模型分析附件",
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "attachment",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


async def _analyze_single_attachment(attachment: Dict[str, Any]) -> Dict[str, Any]:
    """分析单个附件"""
    
    messages = [
        {"role": "system", "content": ATTACHMENT_ANALYSIS_PROMPT},
        {"role": "user", "content": f"请分析这个文件：{attachment.get('filename', '未知文件')}"}
    ]
    
    # 调用 LONG 模型
    model = settings.model_attachment_long
    
    # 如果有文件路径，使用带文件的调用
    file_urls = []
    if attachment.get("filepath") or attachment.get("url"):
        file_urls = [attachment.get("filepath") or attachment.get("url")]
    
    if file_urls:
        response = await model_client.call_with_file(model, messages, file_urls)
    else:
        response = await model_client.call(model, messages)
    
    # 解析响应
    return _parse_analysis_response(response)


def _parse_analysis_response(response: str) -> Dict[str, Any]:
    """解析分析响应"""
    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        
        return json.loads(json_str.strip())
        
    except (json.JSONDecodeError, IndexError):
        return {
            "summary": response,
            "doc_variables_patch": {},
            "citations": []
        }
