"""
E：全文整合节点（Assembler）

职责：
- 将占位标记替换为实际 Mermaid / HTML
- 做一致性检查
- 输出 final_md
"""
import re
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple

MERMAID_PATTERN = re.compile(r'\{\{MERMAID:([^}]+)\}\}')
HTML_PATTERN = re.compile(r'\{\{HTML:([^}]+)\}\}')


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
    E：全文整合节点
    
    输入：draft_md、mermaid_codes、html_codes
    输出：final_md、验证报告
    """
    # 统一转为 dict
    s = _to_dict(state)
    
    draft_md = s.get("draft_md", "")
    mermaid_codes = s.get("mermaid_codes", {})
    html_codes = s.get("html_codes", {})
    mermaid_placeholders = s.get("mermaid_placeholders", [])
    html_placeholders = s.get("html_placeholders", [])
    
    if not draft_md:
        return {
            **s,
            "current_node": "assembler",
            "node_status": "fail",
            "error": {
                "error_type": "missing_draft",
                "error_message": "没有待整合的草稿",
                "retry_guidance": "返回撰写节点生成草稿",
            },
        }
    
    # 构造 node_prompt_spec
    prompt_spec = {
        "node_type": "assembler",
        "goal": "整合文档：替换占位标记，一致性检查",
        "constraints": [
            "所有占位必须被替换",
            "替换后格式正确",
            "失败不降级，返回对应节点重做",
        ],
        "materials": [],
        "output_format": "final_md + validation_report",
        "variables_snapshot": s.get("doc_variables", {}),
        "attachments_snapshot": [],
    }
    
    try:
        final_md = draft_md
        errors = []
        replacements = []
        
        # 替换 Mermaid 占位
        for ph in mermaid_placeholders:
            placeholder = f"{{{{MERMAID:{ph['description']}}}}}"
            
            if ph["id"] in mermaid_codes:
                code = mermaid_codes[ph["id"]].get("code", "")
                # 包裹为代码块
                replacement = f"```mermaid\n{code}\n```"
                final_md = final_md.replace(placeholder, replacement)
                replacements.append({
                    "type": "mermaid",
                    "id": ph["id"],
                    "description": ph["description"],
                    "status": "replaced"
                })
            else:
                errors.append({
                    "type": "mermaid",
                    "id": ph["id"],
                    "description": ph["description"],
                    "error": "找不到对应的代码"
                })
        
        # 替换 HTML 占位
        for ph in html_placeholders:
            placeholder = f"{{{{HTML:{ph['description']}}}}}"
            
            if ph["id"] in html_codes:
                code = html_codes[ph["id"]].get("code", "")
                # 包裹为 HTML 代码块
                replacement = f"```html\n{code}\n```"
                final_md = final_md.replace(placeholder, replacement)
                replacements.append({
                    "type": "html",
                    "id": ph["id"],
                    "description": ph["description"],
                    "status": "replaced"
                })
            else:
                errors.append({
                    "type": "html",
                    "id": ph["id"],
                    "description": ph["description"],
                    "error": "找不到对应的代码"
                })
        
        # 检查是否还有未替换的占位符
        remaining_mermaid = MERMAID_PATTERN.findall(final_md)
        remaining_html = HTML_PATTERN.findall(final_md)
        
        for desc in remaining_mermaid:
            errors.append({
                "type": "mermaid",
                "id": "unknown",
                "description": desc,
                "error": "占位符未被替换"
            })
        
        for desc in remaining_html:
            errors.append({
                "type": "html",
                "id": "unknown",
                "description": desc,
                "error": "占位符未被替换"
            })
        
        # 一致性检查
        consistency_issues = _check_consistency(final_md, s.get("doc_variables", {}))
        
        validation_report = {
            "replacements": replacements,
            "errors": errors,
            "consistency_issues": consistency_issues,
            "total_mermaid": len(mermaid_placeholders),
            "total_html": len(html_placeholders),
            "replaced_mermaid": len([r for r in replacements if r["type"] == "mermaid"]),
            "replaced_html": len([r for r in replacements if r["type"] == "html"]),
        }
        
        # 如果有错误，不降级，返回给 diagram 节点重做
        if errors:
            node_run = {
                "node_type": "assembler",
                "prompt_spec": prompt_spec,
                "result": validation_report,
                "status": "fail",
                "error": {
                    "error_type": "assembly_failed",
                    "error_message": f"{len(errors)} 个占位符无法替换",
                    "retry_guidance": "返回图文节点重新生成缺失的代码",
                    "failed_items": errors,
                },
                "timestamp": datetime.now().isoformat(),
            }
            
            return {
                **s,
                "assembly_errors": errors,
                "node_runs": s.get("node_runs", []) + [node_run],
                "current_node": "assembler",
                "node_status": "fail",
                "error": node_run["error"],
                "retry_count": s.get("retry_count", 0) + 1,
            }
        
        # 成功
        node_run = {
            "node_type": "assembler",
            "prompt_spec": prompt_spec,
            "result": {
                **validation_report,
                "final_md_preview": final_md[:500] + "..." if len(final_md) > 500 else final_md,
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "final_md": final_md,
            "validation_report": validation_report,
            "assembly_errors": [],
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "assembler",
            "node_status": "success",
            "error": None,
        }
        
    except Exception as e:
        node_run = {
            "node_type": "assembler",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": {
                "error_type": "assembly_error",
                "error_message": str(e),
                "retry_guidance": "检查占位符格式",
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **s,
            "node_runs": s.get("node_runs", []) + [node_run],
            "current_node": "assembler",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": s.get("retry_count", 0) + 1,
        }


def _check_consistency(final_md: str, doc_variables: Dict[str, Any]) -> List[Dict[str, Any]]:
    """一致性检查"""
    issues = []
    
    # 检查关键点是否被提及
    key_points = doc_variables.get("key_points", [])
    for point in key_points:
        if isinstance(point, str) and point and point.lower() not in final_md.lower():
            issues.append({
                "type": "missing_key_point",
                "description": f"关键点 '{point}' 可能未在文档中体现",
                "severity": "warning"
            })
    
    # 检查大纲结构
    outline = doc_variables.get("outline", [])
    for section in outline:
        if isinstance(section, str) and section:
            # 检查是否有对应标题
            if f"# {section}" not in final_md and f"## {section}" not in final_md:
                issues.append({
                    "type": "missing_section",
                    "description": f"大纲章节 '{section}' 可能缺失",
                    "severity": "warning"
                })
    
    # 检查空代码块
    if "```mermaid\n\n```" in final_md or "```html\n\n```" in final_md:
        issues.append({
            "type": "empty_code_block",
            "description": "发现空的代码块",
            "severity": "error"
        })
    
    return issues
