"""
文档路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.document import Document, DocumentVersion, DocumentShare
from app.models.workflow import WorkflowRun
from app.schemas.document import DocumentCreate, DocumentUpdate, DocumentInfo, DocumentDetail, ShareRequest
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/my", response_model=dict)
async def get_my_documents(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取我的文档列表"""
    result = await db.execute(
        select(Document)
        .where(Document.owner_id == user.id, Document.owner_deleted_at.is_(None))
        .order_by(Document.updated_at.desc())
    )
    docs = result.scalars().all()
    
    return {
        "docs": [
            {
                "doc_id": doc.id,
                "title": doc.title,
                "status": doc.status,
                "updated_at": doc.updated_at.isoformat()
            }
            for doc in docs
        ]
    }


@router.get("/cc", response_model=dict)
async def get_shared_documents(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取抄送给我的文档列表"""
    result = await db.execute(
        select(DocumentShare)
        .where(DocumentShare.to_user_id == user.id, DocumentShare.deleted_at.is_(None))
        .options(
            selectinload(DocumentShare.document),
            selectinload(DocumentShare.from_user)
        )
        .order_by(DocumentShare.created_at.desc())
    )
    shares = result.scalars().all()
    
    return {
        "docs": [
            {
                "doc_id": share.document_id,
                "title": share.document.title,
                "from_user": share.from_user.username,
                "shared_at": share.created_at.isoformat()
            }
            for share in shares
        ]
    }


@router.post("", response_model=dict)
async def create_document(
    req: DocumentCreate = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建新文档"""
    doc = Document(
        owner_id=user.id,
        title=req.title if req else "未命名文档"
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    
    # 创建初始版本
    version = DocumentVersion(
        document_id=doc.id,
        content_md="",
        doc_variables={}
    )
    db.add(version)
    await db.commit()
    
    return {"doc_id": doc.id}


@router.put("/{doc_id}", response_model=dict)
async def update_document(
    doc_id: str,
    req: DocumentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新文档（创建新版本）"""
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    if doc.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权修改此文档")

    # 更新标题（可选）
    if req.title is not None and req.title.strip():
        doc.title = req.title.strip()

    latest_version = doc.versions[0] if doc.versions else None
    new_content = req.content_md if req.content_md is not None else (latest_version.content_md if latest_version else "")
    new_vars = req.doc_variables if req.doc_variables is not None else (latest_version.doc_variables if latest_version else {})

    # 创建新版本
    version = DocumentVersion(
        document_id=doc.id,
        content_md=new_content or "",
        doc_variables=new_vars or {}
    )
    db.add(version)
    await db.commit()

    return {"ok": True}


@router.get("/{doc_id}", response_model=dict)
async def get_document(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取文档详情"""
    # 查询文档（包含关系）
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .options(
            selectinload(Document.owner),
            selectinload(Document.versions),
            selectinload(Document.shares).selectinload(DocumentShare.to_user),
            selectinload(Document.workflow_runs).selectinload(WorkflowRun.node_runs)
        )
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 检查权限（owner 或被抄送者）
    is_owner = doc.owner_id == user.id
    is_shared = any(share.to_user_id == user.id and share.deleted_at is None for share in doc.shares)
    
    if not is_owner and not is_shared:
        raise HTTPException(status_code=403, detail="无权访问此文档")
    
    # 获取最新版本
    latest_version = doc.versions[0] if doc.versions else None
    
    # 最新一次工作流（用于前端恢复节点状态/小灯）
    latest_run = doc.workflow_runs[0] if doc.workflow_runs else None
    latest_run_payload = None
    if latest_run:
        latest_run_payload = {
            "run_id": latest_run.id,
            "status": latest_run.status,
            "current_node": latest_run.current_node,
            "node_runs": [
                {
                    "node_type": nr.node_type,
                    "status": nr.status,
                    "prompt_spec": nr.prompt_spec,
                    "result": nr.result,
                    "error": nr.error,
                    "timestamp": (nr.started_at or nr.ended_at or datetime.utcnow()).isoformat(),
                }
                for nr in (latest_run.node_runs or [])
            ],
        }

    return {
        "doc_id": doc.id,
        "title": doc.title,
        "status": doc.status,
        "owner": {
            "user_id": doc.owner.id,
            "username": doc.owner.username
        },
        "latest_version": {
            "version_id": latest_version.id,
            "content_md": latest_version.content_md,
            "doc_variables": latest_version.doc_variables
        } if latest_version else None,
        "workflow_runs": [
            {
                "run_id": run.id,
                "status": run.status,
                "started_at": run.started_at.isoformat(),
                "ended_at": run.ended_at.isoformat() if run.ended_at else None
            }
            for run in doc.workflow_runs[:5]  # 只返回最近 5 次
        ],
        "latest_run": latest_run_payload,
        "shares": [
            {
                "to_user": share.to_user.username,
                "shared_at": share.created_at.isoformat()
            }
            for share in doc.shares
        ]
    }


@router.post("/{doc_id}/share", response_model=dict)
async def share_document(
    doc_id: str,
    req: ShareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """抄送文档给其他用户"""
    # 检查文档所有权
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.owner_id == user.id)
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在或无权限")
    
    # 查找目标用户
    result = await db.execute(
        select(User).where(User.username == req.to_username)
    )
    to_user = result.scalar_one_or_none()
    
    if not to_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")
    
    if to_user.id == user.id:
        raise HTTPException(status_code=400, detail="不能抄送给自己")
    
    # 检查是否已抄送
    result = await db.execute(
        select(DocumentShare).where(
            DocumentShare.document_id == doc_id,
            DocumentShare.to_user_id == to_user.id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        # 如果接收者曾“删除”过抄送，则恢复
        if existing.deleted_at is not None:
            existing.deleted_at = None
            existing.note = req.note
            existing.created_at = datetime.utcnow()
            await db.commit()
            return {"share_id": existing.id}
        raise HTTPException(status_code=400, detail="已抄送给该用户")
    
    # 创建抄送记录
    share = DocumentShare(
        document_id=doc_id,
        from_user_id=user.id,
        to_user_id=to_user.id,
        note=req.note
    )
    db.add(share)
    await db.commit()
    
    return {"share_id": share.id}


@router.delete("/{doc_id}", response_model=dict)
async def delete_my_document(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除我的文档（软删除：仅对 owner 隐藏，不影响已抄送者）"""
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.owner_id == user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在或无权限")
    doc.owner_deleted_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


from app.nodes.repair import run_repair

# ... (existing imports)

class RepairRequest(BaseModel):
    errors: List[Dict[str, Any]] # [{"code": "...", "error": "...", "type": "mermaid"}]

@router.post("/{doc_id}/repair", response_model=dict)
async def repair_document(
    doc_id: str,
    req: RepairRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    修复文档中的代码块错误 (Mermaid/HTML)
    由前端渲染失败后自动触发
    """
    # 1. 获取文档
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
        
    # 2. 获取最新版本内容
    sorted_versions = sorted(doc.versions, key=lambda v: v.created_at, reverse=True) if doc.versions else []
    latest_version = sorted_versions[0] if sorted_versions else None
    
    if not latest_version:
        raise HTTPException(status_code=400, detail="文档内容为空")
        
    content_md = latest_version.content_md
    
    # 3. 调用修复节点
    fixed_md = await run_repair(content_md, req.errors)
    
    # 4. 如果内容有变化，保存新版本
    if fixed_md != content_md:
        new_version = DocumentVersion(
            document_id=doc_id,
            content_md=fixed_md,
            doc_variables=latest_version.doc_variables, # 继承变量
        )
        db.add(new_version)
        await db.commit()
        await db.refresh(new_version)
        
        # 重新加载文档以返回最新状态
        await db.refresh(doc)
        # 手动更新 doc.latest_version (因为 selectinload 可能缓存)
        doc.versions.append(new_version) 
        
    return doc


