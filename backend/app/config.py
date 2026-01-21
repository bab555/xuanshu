"""
配置管理 - 从环境变量加载所有配置
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    
    # ===== DashScope =====
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    
    # ===== 模型配置 =====
    # A：中控（Qwen）
    model_controller: str = "qwen3-max"
    model_controller_enable_thinking: bool = True
    model_controller_thinking_budget: int = 500
    model_controller_enable_search: bool = True
    model_controller_search_strategy: str = "turbo"  # turbo|max|agent（按需）

    # B：撰写（Qwen，另一实例/调用）
    model_writer: str = "qwen3-max"
    model_writer_enable_thinking: bool = True
    model_writer_thinking_budget: int = 100
    model_writer_enable_search: bool = True
    model_writer_search_strategy: str = "turbo"

    model_diagram: str = "qwen3-max"                   # C：图文助手（Mermaid/HTML）
    model_image: str = "qwen-image-max"                # D：生图
    model_assembler: str = "qwen3-max"                 # E：全文整合
    model_attachment_long: str = "qwen-long"           # F：附件分析（待定）
    model_repair: str = "deepseek-v3"                  # G：代码修复（Mermaid/HTML）
    
    # ===== 数据库 =====
    database_url: str = "sqlite+aiosqlite:///./data/doctools.db"
    
    # ===== 存储 =====
    storage_path: str = "./storage"
    attachments_path: str = "./storage/attachments"
    export_dir: str = "./storage/exports"
    
    # ===== JWT =====
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    
    # ===== 服务配置 =====
    backend_host: str = "0.0.0.0"
    backend_port: int = 8001
    debug: bool = False
    
    # ===== 工作流 =====
    max_retries: int = 3
    
    # ===== 渲染配置 =====
    render_width_px: int = 1200
    render_timeout_ms: int = 30000
    
    # ===== 导出配置 =====
    pandoc_path: Optional[str] = None  # Pandoc 可执行文件路径，None 表示使用系统 PATH
    docx_template: Optional[str] = None  # DOCX 参考模板路径
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 全局配置实例
settings = Settings()
