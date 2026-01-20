"""
附件路由
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.document import Document
from app.models.attachment import Attachment
from app.dependencies import get_current_user
from app.utils.storage import save_file, get_file_url
from app.config import settings

router = APIRouter()


@router.post("", response_model=dict)
async def upload_attachment(
    file: UploadFile = File(...),
    doc_id: str = Form(...),
    background_tasks: BackgroundTasks = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """上传附件"""
    # 检查文档
    result = await db.execute(
        select(Document).where(Document.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 保存文件
    content = await file.read()
    filepath = await save_file(content, file.filename, "attachments")
    
    # 创建附件记录
    attachment = Attachment(
        document_id=doc_id,
        filename=file.filename,
        file_type=file.content_type,
        filepath=filepath,
        status="pending"
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    
    # TODO: 添加后台任务调用 LONG 模型分析
    # background_tasks.add_task(analyze_attachment, attachment.id)
    
    return {
        "attachment_id": attachment.id,
        "filename": attachment.filename,
        "url": get_file_url(filepath),
        "analysis_status": "pending"
    }


@router.get("/{attachment_id}", response_model=dict)
async def get_attachment(
    attachment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取附件信息"""
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()
    
    if not attachment:
        raise HTTPException(status_code=404, detail="附件不存在")
    
    return {
        "attachment_id": attachment.id,
        "filename": attachment.filename,
        "file_type": attachment.file_type,
        "url": get_file_url(attachment.filepath),
        "analysis_status": attachment.status,
        "summary": attachment.summary,
        "created_at": attachment.created_at.isoformat()
    }


@router.get("/doc/{doc_id}", response_model=dict)
async def get_document_attachments(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取文档的所有附件"""
    result = await db.execute(
        select(Attachment)
        .where(Attachment.document_id == doc_id)
        .order_by(Attachment.created_at.desc())
    )
    attachments = result.scalars().all()
    
    return {
        "attachments": [
            {
                "attachment_id": att.id,
                "filename": att.filename,
                "url": get_file_url(att.filepath),
                "analysis_status": att.status,
                "summary": att.summary
            }
            for att in attachments
        ]
    }

