"""
导出路由
"""
import os
import asyncio
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.document import Document, DocumentVersion
from app.models.export import Export
from app.dependencies import get_current_user
from app.config import settings
from app.services.export_service import export_service

router = APIRouter()

def _apply_generated_images(markdown: str, doc_variables: dict) -> str:
    """
    将 {{image+...}} 占位符替换为实际图片链接（仅用于导出/下载阶段）。
    正文预览阶段仍保留占位符。
    """
    md = markdown or ""
    gen = (doc_variables or {}).get("generated_images")
    if not isinstance(gen, list) or not gen:
        return md
    for item in gen:
        if not isinstance(item, dict):
            continue
        placeholder = item.get("placeholder")
        url = item.get("url")
        if isinstance(placeholder, str) and placeholder and isinstance(url, str) and url:
            md = md.replace(placeholder, f"![]({url})")
    return md


async def run_export_task(
    export_id: str,
    content_md: str,
    doc_title: str,
    doc_variables: dict,
    db_url: str
):
    """后台导出任务"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # 创建输出目录
            export_dir = Path(settings.export_dir or "exports")
            export_dir.mkdir(parents=True, exist_ok=True)
            
            # 输出文件路径
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{doc_title}_{timestamp}.docx"
            output_path = str(export_dir / filename)
            
            # 执行导出
            result = await export_service.export_to_docx(
                markdown=_apply_generated_images(content_md, doc_variables),
                output_path=output_path,
                title=doc_title
            )
            
            # 更新导出记录
            stmt = select(Export).where(Export.id == export_id)
            record = (await db.execute(stmt)).scalar_one()
            
            if result["success"]:
                record.status = "completed"
                record.download_path = output_path
            else:
                record.status = "failed"
                record.error = "; ".join(result["errors"])
            
            await db.commit()
            
        except Exception as e:
            # 更新为失败状态
            stmt = select(Export).where(Export.id == export_id)
            record = (await db.execute(stmt)).scalar_one_or_none()
            if record:
                record.status = "failed"
                record.error = str(e)
                await db.commit()


@router.post("/docs/{doc_id}/docx", response_model=dict)
async def create_export(
    doc_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建 DOCX 导出任务"""
    # 检查文档
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 获取最新版本
    latest_version = doc.versions[0] if doc.versions else None
    if not latest_version or not latest_version.content_md:
        raise HTTPException(status_code=400, detail="文档内容为空")
    
    # 创建导出记录
    export_record = Export(
        document_id=doc_id,
        user_id=user.id,
        version_id=latest_version.id,
        status="processing"
    )
    db.add(export_record)
    await db.commit()
    await db.refresh(export_record)
    
    # 添加后台任务
    background_tasks.add_task(
        run_export_task,
        export_record.id,
        latest_version.content_md,
        doc.title,
        latest_version.doc_variables or {},
        str(settings.database_url)
    )
    
    return {
        "export_id": export_record.id,
        "status": "processing"
    }


@router.post("/{doc_id}")
async def export_doc_sync(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """同步导出 DOCX（直接返回文件）"""
    # 检查文档
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 获取最新版本
    sorted_versions = sorted(doc.versions, key=lambda v: v.created_at, reverse=True)
    latest_version = sorted_versions[0] if sorted_versions else None
    
    if not latest_version or not latest_version.content_md:
        raise HTTPException(status_code=400, detail="文档内容为空")
    
    try:
        # 创建临时目录
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{doc.title}_{timestamp}.docx"
            output_path = os.path.join(tmpdir, filename)
            
            # 执行导出
            result = await export_service.export_to_docx(
                markdown=_apply_generated_images(latest_version.content_md, latest_version.doc_variables or {}),
                output_path=output_path,
                title=doc.title
            )
            
            if not result["success"]:
                raise HTTPException(
                    status_code=500, 
                    detail=f"导出失败: {'; '.join(result['errors'])}"
                )
            
            # 读取文件内容
            with open(output_path, "rb") as f:
                file_content = f.read()
            
            # 返回文件
            return StreamingResponse(
                iter([file_content]),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/{export_id}", response_model=dict)
async def get_export_status(
    export_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取导出状态"""
    result = await db.execute(
        select(Export).where(Export.id == export_id)
    )
    export_record = result.scalar_one_or_none()
    
    if not export_record:
        raise HTTPException(status_code=404, detail="导出记录不存在")
    
    return {
        "export_id": export_record.id,
        "status": export_record.status,
        "download_url": f"/api/exports/{export_id}/download" if export_record.status == "completed" else None,
        "error": export_record.error if export_record.status == "failed" else None,
        "created_at": export_record.created_at.isoformat()
    }


@router.get("/{export_id}/download")
async def download_export(
    export_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """下载导出的 DOCX 文件"""
    result = await db.execute(
        select(Export).where(Export.id == export_id)
    )
    export_record = result.scalar_one_or_none()
    
    if not export_record:
        raise HTTPException(status_code=404, detail="导出记录不存在")
    
    if export_record.status != "completed":
        raise HTTPException(status_code=400, detail="导出尚未完成")
    
    if not export_record.download_path or not os.path.exists(export_record.download_path):
        raise HTTPException(status_code=404, detail="导出文件不存在")
    
    filename = os.path.basename(export_record.download_path)
    
    return FileResponse(
        export_record.download_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename
    )
