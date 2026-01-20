# skill-10：导出 DOCX（Playwright 渲染 + Pandoc + 失败回流）

> 对应开发文档：§8 MD 转 DOCX 下载方案

## 目标

实现 DOCX 导出节点：
- Mermaid/HTML → PNG（Playwright 渲染）
- MD → DOCX（Pandoc 转换）
- 失败不降级，回流给对应模型重制

## 后端实现

### services/export_service.py

```python
import os
import re
import uuid
import subprocess
import asyncio
from playwright.async_api import async_playwright
from app.config import settings

class ExportService:
    def __init__(self):
        self.storage_path = settings.storage_path
        self.render_width = int(os.getenv("RENDER_WIDTH_PX", "1200"))
        self.render_timeout = int(os.getenv("RENDER_TIMEOUT_MS", "30000"))
    
    async def export_docx(self, final_md: str, doc_id: str, version_id: str) -> dict:
        """导出 DOCX 主流程"""
        export_id = str(uuid.uuid4())
        artifacts_dir = os.path.join(self.storage_path, "exports", export_id)
        os.makedirs(artifacts_dir, exist_ok=True)
        
        errors = []
        
        # 1. 渲染 Mermaid 为 PNG
        export_md, mermaid_errors = await self._render_mermaid_blocks(final_md, artifacts_dir)
        errors.extend(mermaid_errors)
        
        # 2. 渲染 HTML 为 PNG
        export_md, html_errors = await self._render_html_blocks(export_md, artifacts_dir)
        errors.extend(html_errors)
        
        # 如果有渲染错误，返回错误信息（触发回流）
        if errors:
            return {
                "status": "failed",
                "errors": errors,
            }
        
        # 3. 保存 export_md
        export_md_path = os.path.join(artifacts_dir, "export.md")
        with open(export_md_path, "w", encoding="utf-8") as f:
            f.write(export_md)
        
        # 4. 调用 Pandoc 转换
        docx_path = os.path.join(artifacts_dir, f"{doc_id}.docx")
        pandoc_result = await self._run_pandoc(export_md_path, docx_path)
        
        if not pandoc_result["success"]:
            return {
                "status": "failed",
                "errors": [{
                    "error_type": "pandoc_failed",
                    "error_message": pandoc_result["error"],
                    "retry_guidance": "检查 Markdown 结构和资源引用",
                }],
            }
        
        return {
            "status": "completed",
            "download_url": f"/api/exports/{export_id}/download",
            "docx_path": docx_path,
        }
    
    async def _render_mermaid_blocks(self, md: str, artifacts_dir: str) -> tuple[str, list]:
        """渲染所有 Mermaid 块为 PNG"""
        errors = []
        
        # 匹配 mermaid 代码块
        pattern = r'```mermaid\n([\s\S]*?)```'
        matches = list(re.finditer(pattern, md))
        
        if not matches:
            return md, errors
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": self.render_width, "height": 800})
            
            for i, match in enumerate(matches):
                mermaid_code = match.group(1).strip()
                block_id = f"mermaid_{i}"
                png_path = os.path.join(artifacts_dir, f"{block_id}.png")
                
                try:
                    # 渲染 Mermaid
                    html = self._mermaid_html_template(mermaid_code)
                    await page.set_content(html)
                    await page.wait_for_selector(".mermaid svg", timeout=self.render_timeout)
                    
                    # 截图
                    element = await page.query_selector(".mermaid")
                    await element.screenshot(path=png_path)
                    
                    # 替换为图片引用
                    md = md.replace(match.group(0), f"![{block_id}]({png_path})")
                    
                except Exception as e:
                    errors.append({
                        "error_type": "mermaid_render_failed",
                        "error_message": str(e),
                        "block_id": block_id,
                        "block_source": mermaid_code,
                        "retry_guidance": "简化 Mermaid 语法，避免特殊字符和复杂嵌套",
                    })
            
            await browser.close()
        
        return md, errors
    
    async def _render_html_blocks(self, md: str, artifacts_dir: str) -> tuple[str, list]:
        """渲染所有 HTML 原型块为 PNG"""
        errors = []
        
        # 匹配 PROTO_HTML 块
        pattern = r'<!--PROTO_HTML:id=([^>]+)-->([\s\S]*?)<!--/PROTO_HTML-->'
        matches = list(re.finditer(pattern, md))
        
        if not matches:
            return md, errors
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": self.render_width, "height": 800})
            
            for match in matches:
                block_id = match.group(1).strip()
                html_code = match.group(2).strip()
                png_path = os.path.join(artifacts_dir, f"{block_id}.png")
                
                try:
                    # 渲染 HTML
                    html = self._html_render_template(html_code)
                    await page.set_content(html)
                    await page.wait_for_load_state("networkidle", timeout=self.render_timeout)
                    
                    # 截图
                    element = await page.query_selector("#render-container")
                    await element.screenshot(path=png_path)
                    
                    # 替换为图片引用
                    md = md.replace(match.group(0), f"![{block_id}]({png_path})")
                    
                except Exception as e:
                    errors.append({
                        "error_type": "html_capture_failed",
                        "error_message": str(e),
                        "block_id": block_id,
                        "block_source": html_code[:500],
                        "retry_guidance": "简化 HTML，移除外部依赖和复杂样式",
                    })
            
            await browser.close()
        
        return md, errors
    
    async def _run_pandoc(self, md_path: str, docx_path: str) -> dict:
        """调用 Pandoc 转换"""
        try:
            cmd = [
                "pandoc",
                md_path,
                "-o", docx_path,
                "--from", "markdown",
                "--to", "docx",
            ]
            
            # 如果有模板
            template_path = os.getenv("DOCX_TEMPLATE_PATH")
            if template_path and os.path.exists(template_path):
                cmd.extend(["--reference-doc", template_path])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                return {"success": False, "error": result.stderr}
            
            return {"success": True}
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Pandoc 执行超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _mermaid_html_template(self, code: str) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {{ margin: 0; padding: 20px; background: #fff; }}
        .mermaid {{ display: inline-block; }}
    </style>
</head>
<body>
    <div class="mermaid">{code}</div>
    <script>mermaid.initialize({{ startOnLoad: true, theme: 'default' }});</script>
</body>
</html>"""
    
    def _html_render_template(self, html: str) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ margin: 0; padding: 0; background: #fff; }}
        #render-container {{
            width: {self.render_width}px;
            padding: 20px;
            font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
        }}
    </style>
</head>
<body>
    <div id="render-container">{html}</div>
</body>
</html>"""

export_service = ExportService()
```

### nodes/export.py（LangGraph 节点）

```python
from datetime import datetime
from app.services.export_service import export_service
from app.schemas.workflow import WorkflowState, NodePromptSpec

async def run(state: WorkflowState) -> WorkflowState:
    """X：导出节点"""
    
    final_md = state.get("final_md", "")
    
    if not final_md:
        return {
            **state,
            "current_node": "export",
            "node_status": "fail",
            "error": {
                "error_type": "validation_failed",
                "error_message": "没有最终文档可导出",
                "retry_guidance": "请先完成文档整合",
            },
        }
    
    prompt_spec: NodePromptSpec = {
        "node_type": "export",
        "goal": "导出 DOCX 文档",
        "constraints": ["Mermaid/HTML 渲染为 PNG", "使用 Pandoc 转换"],
        "materials": [],
        "output_format": "DOCX 文件",
        "variables_snapshot": {},
        "attachments_snapshot": [],
    }
    
    # 调用导出服务
    result = await export_service.export_docx(
        final_md=final_md,
        doc_id=state["doc_id"],
        version_id=state.get("run_id", ""),
    )
    
    if result["status"] == "failed":
        # 找到第一个错误，触发回流
        first_error = result["errors"][0]
        
        node_run = {
            "node_type": "export",
            "prompt_spec": prompt_spec,
            "result": None,
            "status": "fail",
            "error": first_error,
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **state,
            "node_runs": state.get("node_runs", []) + [node_run],
            "current_node": "export",
            "node_status": "fail",
            "error": first_error,
            "retry_count": state.get("retry_count", 0) + 1,
        }
    
    # 成功
    node_run = {
        "node_type": "export",
        "prompt_spec": prompt_spec,
        "result": {
            "download_url": result["download_url"],
        },
        "status": "success",
        "timestamp": datetime.now().isoformat(),
    }
    
    return {
        **state,
        "export_url": result["download_url"],
        "node_runs": state.get("node_runs", []) + [node_run],
        "current_node": "export",
        "node_status": "success",
        "error": None,
    }
```

### routers/export.py

```python
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.document import Document
from app.models.export import Export
from app.services.export_service import export_service
import uuid

router = APIRouter()

@router.post("/docs/{doc_id}/export/docx")
async def create_export(
    doc_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")
    
    # 获取最新版本的 final_md
    latest_version = doc.versions[-1] if doc.versions else None
    if not latest_version or not latest_version.content_md:
        raise HTTPException(400, "文档内容为空")
    
    export_id = str(uuid.uuid4())
    export_record = Export(
        id=export_id,
        document_id=doc_id,
        user_id=user.id,
        status="processing"
    )
    db.add(export_record)
    db.commit()
    
    # 后台执行导出
    background_tasks.add_task(
        run_export,
        export_id,
        latest_version.content_md,
        doc_id,
        db
    )
    
    return {"export_id": export_id, "status": "processing"}

async def run_export(export_id: str, final_md: str, doc_id: str, db: Session):
    export_record = db.query(Export).filter(Export.id == export_id).first()
    
    result = await export_service.export_docx(final_md, doc_id, export_id)
    
    if result["status"] == "completed":
        export_record.status = "completed"
        export_record.download_path = result["docx_path"]
    else:
        export_record.status = "failed"
        export_record.error = str(result["errors"])
    
    db.commit()

@router.get("/{export_id}")
async def get_export_status(export_id: str, db: Session = Depends(get_db)):
    export_record = db.query(Export).filter(Export.id == export_id).first()
    if not export_record:
        raise HTTPException(404, "导出记录不存在")
    
    return {
        "export_id": export_id,
        "status": export_record.status,
        "download_url": f"/api/exports/{export_id}/download" if export_record.status == "completed" else None,
        "error": export_record.error if export_record.status == "failed" else None,
    }

@router.get("/{export_id}/download")
async def download_export(export_id: str, db: Session = Depends(get_db)):
    export_record = db.query(Export).filter(Export.id == export_id).first()
    if not export_record or export_record.status != "completed":
        raise HTTPException(404, "文件不存在或尚未完成")
    
    return FileResponse(
        export_record.download_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"document.docx"
    )
```

## 前端对接

### components/preview/ExportButton.tsx

```tsx
import { useState } from 'react';
import { api } from '@/services/api';

interface Props {
  docId: string;
}

export function ExportButton({ docId }: Props) {
  const [status, setStatus] = useState<'idle' | 'exporting' | 'done' | 'error'>('idle');
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async () => {
    setStatus('exporting');
    setError(null);
    
    try {
      const { export_id } = await api.exports.create(docId);
      
      // 轮询状态
      const pollStatus = async () => {
        const result = await api.exports.status(export_id);
        
        if (result.status === 'completed') {
          setStatus('done');
          setDownloadUrl(result.download_url);
        } else if (result.status === 'failed') {
          setStatus('error');
          setError(result.error || '导出失败');
        } else {
          setTimeout(pollStatus, 1000);
        }
      };
      
      pollStatus();
    } catch (err: any) {
      setStatus('error');
      setError(err.message || '导出失败');
    }
  };

  return (
    <div className="export-button-wrapper">
      {status === 'idle' && (
        <button onClick={handleExport} className="export-btn">
          导出 DOCX
        </button>
      )}
      
      {status === 'exporting' && (
        <button disabled className="export-btn exporting">
          导出中...
        </button>
      )}
      
      {status === 'done' && downloadUrl && (
        <a href={downloadUrl} download className="export-btn done">
          下载 DOCX
        </a>
      )}
      
      {status === 'error' && (
        <div className="export-error">
          <span>{error}</span>
          <button onClick={handleExport}>重试</button>
        </div>
      )}
    </div>
  );
}
```

## 失败回流规则（核心）

```
Mermaid 渲染失败 → 回流 C（图文助手）→ 重制 Mermaid → 重跑 Export
HTML 截图失败 → 回流 C → 重制 HTML → 重跑 Export
Pandoc 失败 → 回流 E（全文助手）→ 修正文稿 → 重跑 Export
```

## 验收标准

- [ ] Mermaid 能渲染为 PNG
- [ ] HTML 原型能截图为 PNG
- [ ] Pandoc 能把处理后的 MD 转为 DOCX
- [ ] 渲染失败时返回详细错误信息
- [ ] 错误信息能触发 LangGraph 回流
- [ ] 前端能显示导出状态并下载

