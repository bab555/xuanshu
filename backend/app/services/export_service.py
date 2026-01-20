"""
导出服务：Markdown -> DOCX

使用 Playwright 渲染 Mermaid/HTML -> PNG
使用 Pandoc 转换 Markdown -> DOCX
"""
import os
import re
import tempfile
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime
import uuid

from app.config import settings


class ExportService:
    """DOCX 导出服务"""
    
    def __init__(self):
        self._playwright = None
        self._browser = None
    
    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch()
    
    async def export_to_docx(
        self, 
        markdown: str, 
        output_path: str,
        title: str = "文档"
    ) -> Dict[str, Any]:
        """
        将 Markdown 导出为 DOCX
        
        Args:
            markdown: Markdown 内容
            output_path: 输出 DOCX 路径
            title: 文档标题
            
        Returns:
            {success: bool, output_path: str, errors: list}
        """
        errors = []
        
        try:
            # 1. 提取并渲染 Mermaid/HTML 代码块
            processed_md, images = await self._process_code_blocks(markdown)
            
            # 2. 创建临时目录
            with tempfile.TemporaryDirectory() as tmpdir:
                # 2.1 将 /storage/... 的图片引用拷贝到临时目录，确保 Pandoc 可读取本地文件
                processed_md, copied = await self._materialize_storage_images(processed_md, tmpdir)
                images.update(copied)

                # 保存图片
                for img_name, img_data in images.items():
                    img_path = Path(tmpdir) / img_name
                    img_path.write_bytes(img_data)
                
                # 更新 Markdown 中的图片引用
                for img_name in images.keys():
                    processed_md = processed_md.replace(
                        f"{{{{IMG:{img_name}}}}}",
                        f"![]({img_name})"
                    )
                
                # 保存 Markdown
                md_path = Path(tmpdir) / "document.md"
                md_path.write_text(processed_md, encoding="utf-8")
                
                # 3. 调用 Pandoc 转换
                success = await self._convert_with_pandoc(
                    str(md_path), 
                    output_path,
                    tmpdir,
                    title
                )
                
                if not success:
                    errors.append("Pandoc 转换失败")
            
            return {
                "success": len(errors) == 0,
                "output_path": output_path if len(errors) == 0 else None,
                "errors": errors
            }
            
        except Exception as e:
            return {
                "success": False,
                "output_path": None,
                "errors": [str(e)]
            }
    
    async def _process_code_blocks(
        self, 
        markdown: str
    ) -> Tuple[str, Dict[str, bytes]]:
        """
        处理代码块：将 Mermaid/HTML 渲染为图片
        
        Returns:
            (processed_markdown, {image_name: image_bytes})
        """
        images = {}
        processed = markdown
        
        # 处理 Mermaid 代码块
        mermaid_pattern = re.compile(r'```mermaid\n(.*?)\n```', re.DOTALL)
        mermaid_blocks = mermaid_pattern.findall(markdown)
        
        for i, code in enumerate(mermaid_blocks):
            img_name = f"mermaid_{i}.png"
            try:
                img_data = await self._render_mermaid(code)
                images[img_name] = img_data
                # 替换代码块为图片占位
                processed = processed.replace(
                    f"```mermaid\n{code}\n```",
                    f"{{{{IMG:{img_name}}}}}",
                    1
                )
            except Exception as e:
                # 渲染失败，保留代码块
                pass
        
        # 处理 HTML 代码块
        html_pattern = re.compile(r'```html\n(.*?)\n```', re.DOTALL)
        html_blocks = html_pattern.findall(markdown)
        
        for i, code in enumerate(html_blocks):
            img_name = f"html_{i}.png"
            try:
                img_data = await self._render_html(code)
                images[img_name] = img_data
                processed = processed.replace(
                    f"```html\n{code}\n```",
                    f"{{{{IMG:{img_name}}}}}",
                    1
                )
            except Exception as e:
                pass
        
        return processed, images

    async def _materialize_storage_images(self, markdown: str, tmpdir: str) -> Tuple[str, Dict[str, bytes]]:
        """
        将 Markdown 中引用的 /storage/... 图片拷贝为本地文件，并替换链接为本地文件名。
        避免 Pandoc 读取不到 /storage URL。
        """
        images: Dict[str, bytes] = {}
        processed = markdown

        # ![alt](/storage/xxx.png) 或 ![](/storage/xxx.jpg)
        pattern = re.compile(r"!\[[^\]]*\]\((/storage/[^)]+)\)")
        matches = pattern.findall(markdown)
        if not matches:
            return processed, images

        for url in matches:
            # 映射到本地存储路径
            rel = url.replace("/storage/", "").lstrip("/")
            local_path = os.path.join(settings.storage_path, rel.replace("/", os.sep))
            if not os.path.exists(local_path):
                continue
            # 文件名去重
            base = os.path.basename(local_path)
            img_name = f"asset_{uuid.uuid4().hex}_{base}"
            with open(local_path, "rb") as f:
                images[img_name] = f.read()
            processed = processed.replace(f"({url})", f"({img_name})")

        return processed, images
    
    async def _render_mermaid(self, code: str) -> bytes:
        """使用 Playwright 渲染 Mermaid 为 PNG"""
        await self._ensure_browser()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
            <style>
                body {{ margin: 0; padding: 20px; background: white; }}
                .mermaid {{ background: white; }}
            </style>
        </head>
        <body>
            <div class="mermaid">
{code}
            </div>
            <script>
                mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
            </script>
        </body>
        </html>
        """
        
        page = await self._browser.new_page()
        try:
            await page.set_content(html)
            await page.wait_for_selector(".mermaid svg", timeout=10000)
            
            # 截取 mermaid 元素
            element = await page.query_selector(".mermaid")
            screenshot = await element.screenshot(type="png")
            return screenshot
        finally:
            await page.close()
    
    async def _render_html(self, code: str, width: int = 800) -> bytes:
        """使用 Playwright 渲染 HTML 为 PNG"""
        await self._ensure_browser()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ margin: 0; padding: 0; background: white; }}
                .container {{ width: {width}px; }}
            </style>
        </head>
        <body>
            <div class="container">
                {code}
            </div>
        </body>
        </html>
        """
        
        page = await self._browser.new_page()
        try:
            await page.set_viewport_size({"width": width + 40, "height": 1200})
            await page.set_content(html)
            
            # 等待渲染
            await asyncio.sleep(0.5)
            
            # 截取容器
            element = await page.query_selector(".container")
            screenshot = await element.screenshot(type="png")
            return screenshot
        finally:
            await page.close()
    
    async def _convert_with_pandoc(
        self, 
        md_path: str, 
        output_path: str,
        resource_dir: str,
        title: str
    ) -> bool:
        """调用 Pandoc 转换"""
        
        cmd = [
            settings.pandoc_path or "pandoc",
            md_path,
            "-o", output_path,
            f"--resource-path={resource_dir}",
            f"--metadata=title:{title}",
            "--standalone",
        ]
        
        # 如果有参考模板
        if settings.docx_template and os.path.exists(settings.docx_template):
            cmd.extend(["--reference-doc", settings.docx_template])
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            return process.returncode == 0
            
        except FileNotFoundError:
            raise RuntimeError("Pandoc 未安装或路径错误")
    
    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


# 单例
export_service = ExportService()

