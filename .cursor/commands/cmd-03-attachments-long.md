# skill-03：用户系统（登录/注册 + 我的/抄送）

> 对应开发文档：§7 用户系统与"抄送"功能、§13 API 接口

## 目标

实现最简用户系统：
- 用户名 + 密码注册/登录
- "我的"文档列表
- "抄送"文档列表
- 抄送功能

## 后端实现

### models/user.py

```python
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    documents = relationship("Document", back_populates="owner")
    received_shares = relationship("DocumentShare", foreign_keys="DocumentShare.to_user_id")
```

### models/document.py

```python
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, default="未命名文档")
    status = Column(String, default="draft")  # draft, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    owner = relationship("User", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document")
    shares = relationship("DocumentShare", back_populates="document")

class DocumentShare(Base):
    __tablename__ = "document_shares"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    from_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    document = relationship("Document", back_populates="shares")
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
```

### utils/auth.py

```python
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.jwt_secret,
        algorithm="HS256"
    )

def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload.get("sub")
    except:
        return None
```

### routers/auth.py

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, AuthResponse
from app.utils.auth import hash_password, verify_password, create_token

router = APIRouter()

@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(400, "用户名已存在")
    user = User(username=req.username, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    return {"user_id": user.id, "username": user.username, "token": create_token(user.id)}

@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return {"user_id": user.id, "username": user.username, "token": create_token(user.id)}
```

### routers/documents.py（我的/抄送/分享）

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.document import Document, DocumentShare
from app.models.user import User
from app.dependencies import get_current_user

router = APIRouter()

@router.get("/my")
def get_my_docs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.owner_id == user.id).order_by(Document.updated_at.desc()).all()
    return {"docs": [{"doc_id": d.id, "title": d.title, "status": d.status, "updated_at": d.updated_at} for d in docs]}

@router.get("/cc")
def get_shared_docs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shares = db.query(DocumentShare).filter(DocumentShare.to_user_id == user.id).order_by(DocumentShare.created_at.desc()).all()
    return {"docs": [{
        "doc_id": s.document_id,
        "title": s.document.title,
        "from_user": s.from_user.username,
        "shared_at": s.created_at
    } for s in shares]}

@router.post("")
def create_doc(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = Document(owner_id=user.id)
    db.add(doc)
    db.commit()
    return {"doc_id": doc.id}

@router.post("/{doc_id}/share")
def share_doc(doc_id: str, to_username: str, note: str = None,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.owner_id == user.id).first()
    if not doc:
        raise HTTPException(404, "文档不存在或无权限")
    to_user = db.query(User).filter(User.username == to_username).first()
    if not to_user:
        raise HTTPException(404, "目标用户不存在")
    share = DocumentShare(document_id=doc_id, from_user_id=user.id, to_user_id=to_user.id, note=note)
    db.add(share)
    db.commit()
    return {"share_id": share.id}
```

## 前端实现

### pages/Login.tsx

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/services/api';
import './Auth.css';

export function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await api.auth.login({ username, password });
      localStorage.setItem('token', res.token);
      localStorage.setItem('user', JSON.stringify(res));
      navigate('/my');
    } catch (err: any) {
      setError(err.message || '登录失败');
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>红点集团内部文档工具</h1>
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="用户名"
            value={username}
            onChange={e => setUsername(e.target.value)}
          />
          <input
            type="password"
            placeholder="密码"
            value={password}
            onChange={e => setPassword(e.target.value)}
          />
          {error && <p className="error">{error}</p>}
          <button type="submit">登录</button>
        </form>
        <p>没有账号？<a href="/register">注册</a></p>
      </div>
    </div>
  );
}
```

### pages/MyDocs.tsx

```tsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/services/api';
import './DocList.css';

interface Doc {
  doc_id: string;
  title: string;
  status: string;
  updated_at: string;
}

export function MyDocs() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    api.docs.my().then(res => setDocs(res.docs));
  }, []);

  const handleCreate = async () => {
    const res = await api.docs.create();
    navigate(`/doc/${res.doc_id}`);
  };

  return (
    <div className="doc-list-page">
      <div className="doc-list-header">
        <h2>我的文档</h2>
        <button onClick={handleCreate}>新建文档</button>
      </div>
      <div className="doc-list">
        {docs.map(doc => (
          <div key={doc.doc_id} className="doc-item" onClick={() => navigate(`/doc/${doc.doc_id}`)}>
            <span className="doc-title">{doc.title}</span>
            <span className="doc-status">{doc.status}</span>
            <span className="doc-time">{new Date(doc.updated_at).toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

## 验收标准

- [ ] 注册/登录能正常工作
- [ ] 登录后能看到"我的"文档列表
- [ ] 能创建新文档
- [ ] 能抄送文档给其他用户
- [ ] 被抄送者在"抄送"列表能看到文档
