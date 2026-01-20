"""
DashScope 模型客户端单元测试
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class MockResponse:
    """模拟 DashScope SDK 响应"""
    def __init__(self, status_code=200, content="测试回复", reasoning_content=""):
        self.status_code = status_code
        self.code = "" if status_code == 200 else "Error"
        self.message = "" if status_code == 200 else "测试错误"
        
        # 构造 output.choices[0].message 结构
        mock_message = MagicMock()
        mock_message.content = content
        mock_message.reasoning_content = reasoning_content
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_output = MagicMock()
        mock_output.choices = [mock_choice]
        
        self.output = mock_output


class TestDashScopeClient:
    """测试 DashScope 客户端"""
    
    @pytest.mark.asyncio
    async def test_call_success(self):
        """测试普通对话调用成功"""
        from app.services.model_client import DashScopeClient
        
        mock_response = MockResponse(content="你好，我是 AI 助手")
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            client = DashScopeClient()
            client.api_key = "test_key"
            
            result = await client.call(
                model="qwen3-max",
                messages=[{"role": "user", "content": "你好"}]
            )
            
            assert result == "你好，我是 AI 助手"
    
    @pytest.mark.asyncio
    async def test_call_without_api_key(self):
        """测试无 API Key 时抛出异常"""
        from app.services.model_client import DashScopeClient
        
        client = DashScopeClient()
        client.api_key = ""
        
        with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
            await client.call(
                model="qwen3-max",
                messages=[{"role": "user", "content": "你好"}]
            )
    
    @pytest.mark.asyncio
    async def test_call_api_error(self):
        """测试 API 返回错误"""
        from app.services.model_client import DashScopeClient
        
        mock_response = MockResponse(status_code=400)
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            client = DashScopeClient()
            client.api_key = "test_key"
            
            with pytest.raises(Exception, match="API 调用失败"):
                await client.call(
                    model="qwen3-max",
                    messages=[{"role": "user", "content": "你好"}]
                )
    
    @pytest.mark.asyncio
    async def test_call_with_thinking(self):
        """测试带思考模式的调用"""
        from app.services.model_client import DashScopeClient
        
        mock_response = MockResponse(
            content="最终回复",
            reasoning_content="这是思考过程..."
        )
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            client = DashScopeClient()
            client.api_key = "test_key"
            
            reasoning, content = await client.call_with_thinking(
                model="deepseek-v3.2",
                messages=[{"role": "user", "content": "分析一下"}]
            )
            
            assert reasoning == "这是思考过程..."
            assert content == "最终回复"
    
    @pytest.mark.asyncio
    async def test_call_with_file(self):
        """测试带文件的调用"""
        from app.services.model_client import DashScopeClient
        
        mock_response = MockResponse(content="文件分析结果")
        
        with patch('dashscope.Generation.call', return_value=mock_response) as mock_call:
            client = DashScopeClient()
            client.api_key = "test_key"
            
            result = await client.call_with_file(
                model="qwen-long",
                messages=[{"role": "user", "content": "分析这个文件"}],
                file_urls=["file_123"]
            )
            
            assert result == "文件分析结果"
            # 验证消息中包含了文件引用
            call_args = mock_call.call_args
            messages = call_args[1]["messages"]
            assert any("fileid://" in msg.get("content", "") for msg in messages)


class TestConvenienceFunctions:
    """测试便捷函数"""
    
    @pytest.mark.asyncio
    async def test_call_controller(self):
        """测试中控模型调用"""
        mock_response = MockResponse(
            content="回复",
            reasoning_content="思考"
        )
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            with patch('app.services.model_client.settings') as mock_settings:
                mock_settings.model_controller = "deepseek-v3.2"
                mock_settings.dashscope_api_key = "test_key"
                mock_settings.dashscope_base_url = "https://test.com"
                
                from app.services.model_client import call_controller
                
                reasoning, content = await call_controller(
                    messages=[{"role": "user", "content": "测试"}]
                )
                
                assert reasoning == "思考"
                assert content == "回复"
    
    @pytest.mark.asyncio
    async def test_call_writer(self):
        """测试撰写模型调用"""
        mock_response = MockResponse(content="文档内容")
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            with patch('app.services.model_client.settings') as mock_settings:
                mock_settings.model_writer = "qwen3-max"
                mock_settings.dashscope_api_key = "test_key"
                mock_settings.dashscope_base_url = "https://test.com"
                
                from app.services.model_client import call_writer
                
                result = await call_writer(
                    messages=[{"role": "user", "content": "写一篇文章"}]
                )
                
                assert result == "文档内容"
    
    @pytest.mark.asyncio
    async def test_call_diagram(self):
        """测试图文模型调用"""
        mock_response = MockResponse(content="```mermaid\ngraph TD\nA-->B\n```")
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            with patch('app.services.model_client.settings') as mock_settings:
                mock_settings.model_diagram = "qwen3-max"
                mock_settings.dashscope_api_key = "test_key"
                mock_settings.dashscope_base_url = "https://test.com"
                
                from app.services.model_client import call_diagram
                
                result = await call_diagram(
                    messages=[{"role": "user", "content": "画个流程图"}]
                )
                
                assert "mermaid" in result


class TestImageGeneration:
    """测试图片生成"""
    
    @pytest.mark.asyncio
    async def test_generate_image_success(self):
        """测试图片生成成功"""
        from app.services.model_client import DashScopeClient
        
        # 模拟图片生成响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        mock_content = [{"image": "https://example.com/image.png"}]
        mock_message = MagicMock()
        mock_message.content = mock_content
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_output = MagicMock()
        mock_output.choices = [mock_choice]
        
        mock_response.output = mock_output
        
        with patch('dashscope.MultiModalConversation.call', return_value=mock_response):
            client = DashScopeClient()
            client.api_key = "test_key"
            
            urls = await client.generate_image(
                model="qwen-image-max",
                prompt="一只猫"
            )
            
            assert len(urls) == 1
            assert "example.com" in urls[0]
    
    @pytest.mark.asyncio
    async def test_generate_image_error(self):
        """测试图片生成失败"""
        from app.services.model_client import DashScopeClient
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.code = "InvalidParameter"
        mock_response.message = "参数错误"
        
        with patch('dashscope.MultiModalConversation.call', return_value=mock_response):
            client = DashScopeClient()
            client.api_key = "test_key"
            
            with pytest.raises(Exception, match="图片生成失败"):
                await client.generate_image(
                    model="qwen-image-max",
                    prompt="测试"
                )
