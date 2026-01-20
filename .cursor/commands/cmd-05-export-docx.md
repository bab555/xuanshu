# skill-05：附件分析节点（Attachment LONG）

> 对应开发文档：§5.1 节点 F、§10 模型配置

## 目标

实现 F：Attachment 节点：
- 用户上传文件/图片
- 调用 DashScope LONG 模型直接分析
- 输出 `attachment_summary` + `doc_variables_patch`

## 后端实现

### routers/attachments.py

```python
from fastapi import APIRouter, UploadFile, File, Form, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.attachment import Attachment
from app.services.attachment_service import analyze_attachment
from app.config import settings
import uuid
import aiofiles
import os

router = APIRouter()

@router.post("")
async def upload_attachment(
    file: UploadFile = File(...),
    doc_id: str = Form(...),
    background_tasks: BackgroundTasks = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 保存文件
    attachment_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    filepath = os.path.join(settings.storage_path, "attachments", f"{attachment_id}{ext}")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    async with aiofiles.open(filepath, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # 创建记录
    attachment = Attachment(
        id=attachment_id,
        document_id=doc_id,
        filename=file.filename,
        file_type=file.content_type,
        filepath=filepath,
        status="pending"
    )
    db.add(attachment)
    db.commit()
    
    # 后台任务：调用 LONG 分析
    background_tasks.add_task(analyze_attachment, attachment_id, db)
    
    return {
        "attachment_id": attachment_id,
        "filename": file.filename,
        "url": f"/api/attachments/{attachment_id}/file",
        "analysis_status": "pending"
    }

@router.get("/{attachment_id}")
async def get_attachment(attachment_id: str, db: Session = Depends(get_db)):
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(404, "附件不存在")
    return {
        "attachment_id": attachment.id,
        "filename": attachment.filename,
        "analysis_status": attachment.status,
        "summary": attachment.summary
    }
```

### services/attachment_service.py

```python
from app.services.model_client import model_client
from app.config import settings
from app.models.attachment import Attachment
from sqlalchemy.orm import Session

ATTACHMENT_ANALYSIS_PROMPT = """请分析这个文件/图片，提取可用于文档撰写的信息。

你需要输出 JSON 格式：
{
  "summary": "面向写作的摘要（分条列出要点）",
  "doc_variables_patch": {
    // 可以合并到文档变量的信息
    // 比如从图中提取的流程、结构、术语等
  },
  "citations": [
    // 引用定位（页码/区域，如果适用）
  ]
}

只提取文件中实际存在的信息，不要编造。目标是帮助用户"说清楚一件事"。"""

async def analyze_attachment(attachment_id: str, db: Session):
    """后台任务：调用 LONG 分析附件"""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        return
    
    try:
        attachment.status = "analyzing"
        db.commit()
        
        # 调用 LONG 模型（支持文件直传）
        model = settings.model_attachment_long
        messages = [
            {"role": "system", "content": ATTACHMENT_ANALYSIS_PROMPT},
            {"role": "user", "content": "请分析这个文件"}
        ]
        
        # LONG 模型文件传入方式（按 DashScope 文档）
        response = await model_client.call_with_file(
            model=model,
            messages=messages,
            file_urls=[attachment.filepath]  # 或 file content
        )
        
        # 解析结果
        result = parse_analysis_response(response)
        
        attachment.summary = result.get("summary", "")
        attachment.analysis_result = result
        attachment.status = "completed"
        db.commit()
        
    except Exception as e:
        attachment.status = "failed"
        attachment.error = str(e)
        db.commit()

def parse_analysis_response(response: str) -> dict:
    """解析 LONG 模型输出"""
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
        return {"summary": response, "doc_variables_patch": {}, "citations": []}
```

### nodes/attachment.py（LangGraph 节点）

```python
from datetime import datetime
from app.schemas.workflow import WorkflowState, NodePromptSpec

async def run(state: WorkflowState) -> WorkflowState:
    """F：附件分析节点"""
    
    # 找到未分析的附件
    pending_attachments = [
        a for a in state.get("attachments", [])
        if not a.get("summary")
    ]
    
    if not pending_attachments:
        # 没有待分析附件，直接通过
        return {
            **state,
            "current_node": "attachment",
            "node_status": "success",
        }
    
    # 构造 node_prompt_spec
    prompt_spec: NodePromptSpec = {
        "node_type": "attachment",
        "goal": "分析用户上传的附件，提取可用于写作的信息",
        "constraints": [
            "只提取附件中实际存在的信息",
            "不编造",
            "输出结构化，便于写入变量"
        ],
        "materials": [],
        "output_format": "JSON: summary + doc_variables_patch + citations",
        "variables_snapshot": state.get("doc_variables", {}),
        "attachments_snapshot": pending_attachments,
    }
    
    try:
        # 对每个附件调用分析
        updated_attachments = []
        all_patches = {}
        
        for att in state.get("attachments", []):
            if att.get("summary"):
                updated_attachments.append(att)
            else:
                # 这里应该从数据库获取分析结果（由上传时的后台任务完成）
                # 或者同步调用分析
                result = await analyze_single_attachment(att)
                updated_att = {**att, "summary": result.get("summary", "")}
                updated_attachments.append(updated_att)
                
                # 合并 patches
                if result.get("doc_variables_patch"):
                    all_patches.update(result["doc_variables_patch"])
        
        # 更新状态
        new_variables = {**state.get("doc_variables", {}), **all_patches}
        
        node_run = {
            "node_type": "attachment",
            "prompt_spec": prompt_spec,
            "result": {
                "attachment_summaries": [a.get("summary") for a in updated_attachments],
                "doc_variables_patch": all_patches,
            },
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            **state,
            "attachments": updated_attachments,
            "doc_variables": new_variables,
            "node_runs": state.get("node_runs", []) + [node_run],
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
            **state,
            "node_runs": state.get("node_runs", []) + [node_run],
            "current_node": "attachment",
            "node_status": "fail",
            "error": node_run["error"],
            "retry_count": state.get("retry_count", 0) + 1,
        }
```

## 前端对接

### ChatInput 上传入口

```tsx
// components/chat/ChatInput.tsx
import { useRef } from 'react';
import { api } from '@/services/api';

interface Props {
  docId: string;
  onSend: (message: string, attachments?: string[]) => void;
}

export function ChatInput({ docId, onSend }: Props) {
  const [message, setMessage] = useState('');
  const [attachments, setAttachments] = useState<{ id: string; name: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    const res = await api.attachments.upload(docId, file);
    setAttachments(prev => [...prev, { id: res.attachment_id, name: file.name }]);
  };

  const handleSend = () => {
    if (!message.trim() && attachments.length === 0) return;
    onSend(message, attachments.map(a => a.id));
    setMessage('');
    setAttachments([]);
  };

  return (
    <div className="chat-input">
      {attachments.length > 0 && (
        <div className="attachments-preview">
          {attachments.map(a => (
            <span key={a.id} className="attachment-tag">{a.name}</span>
          ))}
        </div>
      )}
      <div className="input-row">
        <button onClick={() => fileInputRef.current?.click()}>📎</button>
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleUpload}
          style={{ display: 'none' }}
        />
        <input
          type="text"
          value={message}
          onChange={e => setMessage(e.target.value)}
          placeholder="输入消息..."
          onKeyDown={e => e.key === 'Enter' && handleSend()}
        />
        <button onClick={handleSend}>发送</button>
      </div>
    </div>
  );
}
```

## 验收标准

- [ ] 用户能上传文件/图片
- [ ] 后台自动调用 LONG 模型分析
- [ ] 分析结果（summary）能写入附件记录
- [ ] `doc_variables_patch` 能合并到文档变量
- [ ] 中间栏能展示附件分析节点的输入输出
