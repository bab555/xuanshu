# skill-01：后端骨架（FastAPI + LangGraph + DashScope）

> 对应开发文档：§4 后端设计、§10 模型配置、§12 LangGraph 状态机、§13 API 接口

## 目标

搭建后端项目骨架，包含：
- FastAPI 应用结构
- DashScope 模型调用封装
- LangGraph 工作流状态机
- 数据库模型（SQLAlchemy）
- 基础 API 路由

## 目录结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 环境变量加载
│   ├── models/                 # SQLAlchemy 模型
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── document.py
│   │   └── workflow.py
│   ├── schemas/                # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── document.py
│   │   └── workflow.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── model_client.py     # DashScope 封装
│   │   ├── workflow_engine.py  # LangGraph 工作流
│   │   └── export_service.py   # 导出服务
│   ├── nodes/                  # LangGraph 节点实现
│   │   ├── __init__.py
│   │   ├── controller.py       # A
│   │   ├── attachment.py       # F
│   │   ├── writer.py           # B
│   │   ├── diagram.py          # C
│   │   ├── assembler.py        # E
│   │   └── export.py           # X
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── documents.py
│   │   ├── workflow.py
│   │   ├── attachments.py
│   │   └── export.py
│   └── utils/
│       ├── __init__.py
│       ├── auth.py             # JWT 工具
│       └── storage.py          # 文件存储
├── requirements.txt
└── .env                        # 从 env.example 复制
```

## 关键文件实现

### config.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # DashScope
    dashscope_api_key: str
    model_controller: str = "deepseek-r1"
    model_writer: str = "deepseek-r1"
    model_diagram: str = "deepseek-r1"
    model_assembler: str = "deepseek-r1"
    model_attachment_long: str = "qwen-long"
    
    # Database
    database_url: str = "sqlite:///./data/doctools.db"
    
    # Storage
    storage_path: str = "./storage"
    
    # JWT
    jwt_secret: str
    jwt_expire_hours: int = 24
    
    # Workflow
    max_retries: int = 3
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### model_client.py

```python
from dashscope import Generation
from app.config import settings

class DashScopeClient:
    def __init__(self):
        self.api_key = settings.dashscope_api_key
    
    async def call(self, model: str, messages: list, **kwargs) -> dict:
        response = Generation.call(
            model=model,
            messages=messages,
            api_key=self.api_key,
            result_format='message',
            **kwargs
        )
        if response.status_code != 200:
            raise Exception(f"Model call failed: {response.message}")
        return response.output.choices[0].message.content
    
    async def call_with_file(self, model: str, messages: list, file_urls: list) -> dict:
        """LONG 模型附件分析"""
        # 按 DashScope 文档实现文件传入
        pass

model_client = DashScopeClient()
```

### workflow_engine.py（LangGraph 状态机）

```python
from langgraph.graph import StateGraph, END
from app.schemas.workflow import WorkflowState
from app.nodes import controller, attachment, writer, diagram, assembler, export

def build_workflow() -> StateGraph:
    workflow = StateGraph(WorkflowState)
    
    # 添加节点
    workflow.add_node("controller", controller.run)
    workflow.add_node("attachment", attachment.run)
    workflow.add_node("writer", writer.run)
    workflow.add_node("diagram", diagram.run)
    workflow.add_node("assembler", assembler.run)
    workflow.add_node("export", export.run)
    workflow.add_node("error_router", error_router)
    
    # 入口
    workflow.set_entry_point("controller")
    
    # 正常边（见开发文档 §12.2）
    # ... 按开发文档实现
    
    return workflow.compile()

def error_router(state: WorkflowState) -> str:
    """失败回流路由"""
    if state["retry_count"] >= state["max_retries"]:
        return "end"
    error_type = state.get("error", {}).get("error_type")
    if error_type in ["mermaid_render_failed", "html_capture_failed"]:
        return "diagram"
    elif error_type == "pandoc_failed":
        return "assembler"
    elif error_type == "validation_failed":
        return "controller"
    return "controller"
```

### main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, documents, workflow, attachments, export

app = FastAPI(title="红点集团内部文档工具")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 内部部署可放宽
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(documents.router, prefix="/api/docs", tags=["文档"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["工作流"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["附件"])
app.include_router(export.router, prefix="/api/exports", tags=["导出"])
```

## requirements.txt

```
fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
sqlalchemy>=2.0.0
python-jose>=3.3.0
passlib>=1.7.4
bcrypt>=4.1.0
dashscope>=1.14.0
langgraph>=0.0.20
playwright>=1.40.0
python-multipart>=0.0.6
aiofiles>=23.2.0
```

## 验收标准

- [ ] `uvicorn app.main:app --reload` 能启动
- [ ] `/docs` 能看到 Swagger 文档
- [ ] DashScopeClient 能调通（用 deepseek-r1 测试）
- [ ] 数据库表能创建
