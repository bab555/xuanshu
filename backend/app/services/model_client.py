"""
DashScope 模型客户端封装

使用官方 dashscope SDK 统一封装所有模型调用，支持：
- 普通对话
- 带思考模式的对话（deepseek-v3.2 / R1）
- 流式输出
- 带文件的对话（LONG 模型）
- 图片生成（qwen-image-max）
"""
import os
import dashscope
from dashscope import Generation, MultiModalConversation
from typing import List, Dict, Any, Optional, Tuple, AsyncGenerator
from app.config import settings


class DashScopeClient:
    """DashScope 统一客户端"""

    def __init__(self):
        self.api_key = settings.dashscope_api_key
        # 设置全局 API URL
        dashscope.base_http_api_url = settings.dashscope_base_url

    def _ensure_api_key(self):
        """确保 API Key 已设置"""
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY 未设置")
        return self.api_key

    @staticmethod
    def _safe_get_message_field(message: Any, field: str, default: str = "") -> str:
        """
        DashScope SDK 的 message 对象在访问不存在字段时，有些版本会抛 KeyError（不是 AttributeError）。
        这里做统一兜底，兼容：
        - pydantic/对象属性
        - dict
        - 访问缺失字段时抛 KeyError 的对象
        """
        try:
            if isinstance(message, dict):
                v = message.get(field, default)
                return v or default
            v = getattr(message, field)  # 可能抛 KeyError
            return v or default
        except Exception:
            return default

    async def call(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        enable_thinking: bool = False,
        thinking_budget: Optional[int] = None,
        enable_search: bool = False,
        search_options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        调用对话模型（非流式）

        Args:
            model: 模型名称
            messages: 消息列表 [{"role": "user", "content": "..."}]
            max_tokens: 最大输出 token 数
            temperature: 温度参数
            enable_thinking: 是否开启深度思考模式

        Returns:
            模型输出文本
        """
        api_key = self._ensure_api_key()

        # 构建调用参数
        call_kwargs = {
            "api_key": api_key,
            "model": model,
            "messages": messages,
            "result_format": "message",
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # 开启思考模式
        if enable_thinking:
            call_kwargs["enable_thinking"] = True
            if thinking_budget is not None:
                call_kwargs["thinking_budget"] = int(thinking_budget)

        # 联网搜索（按需）
        if enable_search:
            call_kwargs["enable_search"] = True
            if search_options is not None:
                call_kwargs["search_options"] = search_options

        # 合并额外参数
        call_kwargs.update(kwargs)

        # 同步调用（dashscope SDK 是同步的，在异步环境中使用 run_in_executor）
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: Generation.call(**call_kwargs)
        )

        if response.status_code == 200:
            return response.output.choices[0].message.content
        else:
            raise Exception(f"API 调用失败: HTTP {response.status_code}, "
                          f"错误码: {response.code}, 错误信息: {response.message}")

    async def call_with_thinking(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 8192,
        thinking_budget: Optional[int] = None,
        **kwargs
    ) -> Tuple[str, str]:
        """
        调用带思考模式的模型，返回思考过程和最终回复（非流式）

        Args:
            model: 模型名称
            messages: 消息列表
            max_tokens: 最大输出 token 数

        Returns:
            (reasoning_content, content) - 思考过程和最终回复
        """
        api_key = self._ensure_api_key()

        call_kwargs = {
            "api_key": api_key,
            "model": model,
            "messages": messages,
            "result_format": "message",
            "max_tokens": max_tokens,
            "enable_thinking": True,
        }
        if thinking_budget is not None:
            call_kwargs["thinking_budget"] = int(thinking_budget)
        call_kwargs.update(kwargs)

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: Generation.call(**call_kwargs)
        )

        if response.status_code == 200:
            message = response.output.choices[0].message
            reasoning = self._safe_get_message_field(message, "reasoning_content", "")
            content = self._safe_get_message_field(message, "content", "")
            return reasoning, content
        else:
            raise Exception(f"API 调用失败: HTTP {response.status_code}, "
                          f"错误码: {response.code}, 错误信息: {response.message}")

    async def stream_call(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        enable_thinking: bool = False,
        thinking_budget: Optional[int] = None,
        enable_search: bool = False,
        search_options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式调用对话模型

        Args:
            model: 模型名称
            messages: 消息列表
            max_tokens: 最大输出 token 数
            temperature: 温度参数
            enable_thinking: 是否开启深度思考模式

        Yields:
            流式事件字典:
            - {"type": "thinking", "content": "..."} - 思考内容（增量）
            - {"type": "content", "content": "..."} - 回复内容（增量）
            - {"type": "done", "reasoning": "...", "content": "..."} - 完成，包含完整内容
        """
        api_key = self._ensure_api_key()

        call_kwargs = {
            "api_key": api_key,
            "model": model,
            "messages": messages,
            "result_format": "message",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "incremental_output": True,  # 增量输出
        }

        if enable_thinking:
            call_kwargs["enable_thinking"] = True
            if thinking_budget is not None:
                call_kwargs["thinking_budget"] = int(thinking_budget)

        if enable_search:
            call_kwargs["enable_search"] = True
            if search_options is not None:
                call_kwargs["search_options"] = search_options

        call_kwargs.update(kwargs)

        import asyncio
        import queue
        import threading

        # 使用队列在同步生成器和异步生成器之间传递数据
        q: queue.Queue = queue.Queue()
        full_reasoning = ""
        full_content = ""

        def sync_stream():
            nonlocal full_reasoning, full_content
            try:
                responses = Generation.call(**call_kwargs)
                for response in responses:
                    if response.status_code == 200:
                        choice = response.output.choices[0] if response.output.choices else None
                        if choice:
                            message = choice.message
                            # 思考内容
                            reasoning_delta = self._safe_get_message_field(message, "reasoning_content", "")
                            if reasoning_delta:
                                full_reasoning += reasoning_delta
                                q.put({"type": "thinking", "content": reasoning_delta})
                            # 回复内容
                            content_delta = self._safe_get_message_field(message, "content", "")
                            if content_delta:
                                full_content += content_delta
                                q.put({"type": "content", "content": content_delta})
                    else:
                        q.put({"type": "error", "message": f"API 错误: {response.code} - {response.message}"})
                        break
                # 完成
                q.put({"type": "done", "reasoning": full_reasoning, "content": full_content})
            except Exception as e:
                q.put({"type": "error", "message": str(e)})
            finally:
                q.put(None)  # 结束标记

        # 在线程中运行同步流式调用
        thread = threading.Thread(target=sync_stream)
        thread.start()

        # 异步读取队列
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is None:
                break
            yield item

        thread.join()

    async def call_with_file(
        self,
        model: str,
        messages: List[Dict[str, str]],
        file_urls: List[str],
        max_tokens: int = 8192,
        **kwargs
    ) -> str:
        """
        调用支持文件的模型（如 qwen-long）

        Args:
            model: 模型名称
            messages: 消息列表
            file_urls: 文件 URL 列表（DashScope 文件服务 URL）
            max_tokens: 最大输出 token 数

        Returns:
            模型输出文本
        """
        api_key = self._ensure_api_key()

        # 构造带文件引用的消息
        enhanced_messages = []

        if file_urls:
            # 添加文件引用到 system 消息
            file_refs = "\n".join([f"fileid://{url}" for url in file_urls])
            enhanced_messages.append({
                "role": "system",
                "content": f"请分析以下文件：\n{file_refs}"
            })

        enhanced_messages.extend(messages)

        call_kwargs = {
            "api_key": api_key,
            "model": model,
            "messages": enhanced_messages,
            "result_format": "message",
            "max_tokens": max_tokens,
        }
        call_kwargs.update(kwargs)

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: Generation.call(**call_kwargs)
        )

        if response.status_code == 200:
            return response.output.choices[0].message.content
        else:
            raise Exception(f"API 调用失败: HTTP {response.status_code}, "
                          f"错误码: {response.code}, 错误信息: {response.message}")

    async def upload_file(self, filepath: str) -> str:
        """
        上传文件到 DashScope 获取 file_id

        Args:
            filepath: 本地文件路径

        Returns:
            DashScope 文件 ID
        """
        api_key = self._ensure_api_key()

        import asyncio
        from dashscope import Files

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: Files.upload(
                api_key=api_key,
                file=filepath,
                purpose="file-extract"
            )
        )

        if hasattr(response, 'id'):
            return response.id
        else:
            raise Exception(f"文件上传失败: {response}")

    async def generate_image(
        self,
        model: str,
        prompt: str,
        size: str = "1328*1328",
        negative_prompt: str = "",
        **kwargs
    ) -> List[str]:
        """
        调用图片生成模型（qwen-image-max）

        Args:
            model: 模型名称 (如 qwen-image-max)
            prompt: 图片描述
            size: 图片尺寸
            negative_prompt: 负面提示词

        Returns:
            图片 URL 列表
        """
        api_key = self._ensure_api_key()

        # 构造多模态消息格式
        messages = [
            {
                "role": "user",
                "content": [
                    {"text": prompt}
                ]
            }
        ]

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: MultiModalConversation.call(
                api_key=api_key,
                model=model,
                messages=messages,
                result_format='message',
                stream=False,
                watermark=False,
                prompt_extend=True,
                negative_prompt=negative_prompt,
                size=size,
                **kwargs
            )
        )

        if response.status_code == 200:
            # 从响应中提取图片 URL
            # 根据不同模型返回格式可能不同
            try:
                content = response.output.choices[0].message.content
                if isinstance(content, list):
                    urls = []
                    for item in content:
                        if isinstance(item, dict) and 'image' in item:
                            urls.append(item['image'])
                    return urls
                return []
            except Exception as e:
                raise Exception(f"解析图片响应失败: {e}")
        else:
            raise Exception(f"图片生成失败: HTTP {response.status_code}, "
                          f"错误码: {response.code}, 错误信息: {response.message}")


# 全局客户端实例
model_client = DashScopeClient()


# ===== 便捷函数 =====

async def call_controller(messages: List[Dict[str, str]], **kwargs) -> Tuple[str, str]:
    """调用中控模型（带思考模式）"""
    return await model_client.call_with_thinking(
        model=settings.model_controller,
        messages=messages,
        **kwargs
    )


async def call_writer(messages: List[Dict[str, str]], **kwargs) -> str:
    """调用文档撰写模型"""
    return await model_client.call(
        model=settings.model_writer,
        messages=messages,
        **kwargs
    )


async def call_diagram(messages: List[Dict[str, str]], **kwargs) -> str:
    """调用图文助手模型（Mermaid/HTML）"""
    return await model_client.call(
        model=settings.model_diagram,
        messages=messages,
        **kwargs
    )


async def call_assembler(messages: List[Dict[str, str]], **kwargs) -> str:
    """调用全文整合模型"""
    return await model_client.call(
        model=settings.model_assembler,
        messages=messages,
        **kwargs
    )


async def call_attachment(messages: List[Dict[str, str]], file_urls: List[str], **kwargs) -> str:
    """调用附件分析模型"""
    return await model_client.call_with_file(
        model=settings.model_attachment_long,
        messages=messages,
        file_urls=file_urls,
        **kwargs
    )


async def generate_image(prompt: str, **kwargs) -> List[str]:
    """调用图片生成模型"""
    return await model_client.generate_image(
        model=settings.model_image,
        prompt=prompt,
        **kwargs
    )
