"""
红点集团内部文档工具 - FastAPI 入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path

from app.config import settings
from app.database import init_db
from app.routers import auth, documents, workflow, attachments, export, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    await init_db()
    
    # 确保存储目录存在
    os.makedirs(settings.storage_path, exist_ok=True)
    os.makedirs(os.path.join(settings.storage_path, "attachments"), exist_ok=True)
    os.makedirs(os.path.join(settings.storage_path, "exports"), exist_ok=True)
    
    yield
    
    # 关闭时（如果需要清理）


# 创建应用
app = FastAPI(
    title="红点集团内部文档工具",
    description="对话驱动 + 工作流可视化 + 文档生产与整合",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置（内部部署可放宽）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(users.router, prefix="/api/users", tags=["用户"])
app.include_router(documents.router, prefix="/api/docs", tags=["文档"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["工作流"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["附件"])
app.include_router(export.router, prefix="/api/exports", tags=["导出"])

# 静态文件（存储的附件和导出）
if os.path.exists(settings.storage_path):
    app.mount("/storage", StaticFiles(directory=settings.storage_path), name="storage")

@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}

# ===== 前端静态托管 (放在最后，作为兜底) =====
# 寻找前端 dist 目录：尝试从 backend/app 上级找到 frontend/dist
# 兼容：在 backend/ 目录运行，或在根目录运行
BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
PROJECT_ROOT = BASE_DIR.parent                     # project_root/
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

if FRONTEND_DIST.exists():
    print(f"Serving frontend from: {FRONTEND_DIST}")
    # 挂载静态资源
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
    
    # 所有的根路径和其他未匹配路径都返回 index.html (SPA)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # 排除 API 和 storage
        if full_path.startswith("api") or full_path.startswith("storage") or full_path.startswith("health"):
            return {"detail": "Not Found"}
        
        # 返回 index.html
        # 关键：index.html 不要缓存，否则前端发布后仍可能加载旧的 hashed bundle，表现为“改了但没生效/WS 逻辑异常”。
        return FileResponse(
            str(FRONTEND_DIST / "index.html"),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )
else:
    print(f"Frontend dist not found at: {FRONTEND_DIST}")
    @app.get("/")
    async def root():
        return {
            "name": "红点集团内部文档工具",
            "status": "backend_only",
            "message": "Frontend build not found. Run 'npm run build' in frontend directory."
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.debug,
    )
