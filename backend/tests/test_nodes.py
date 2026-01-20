"""
LangGraph 节点单元测试
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class MockResponse:
    """模拟 DashScope SDK 响应"""
    def __init__(self, status_code=200, content="", reasoning_content=""):
        self.status_code = status_code
        self.code = "" if status_code == 200 else "Error"
        self.message = "" if status_code == 200 else "错误"
        
        mock_message = MagicMock()
        mock_message.content = content
        mock_message.reasoning_content = reasoning_content
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_output = MagicMock()
        mock_output.choices = [mock_choice]
        
        self.output = mock_output


class TestControllerNode:
    """测试中控节点"""
    
    @pytest.mark.asyncio
    async def test_controller_basic_input(self):
        """测试中控节点基本输入"""
        mock_content = '''```json
{
    "doc_variables_patch": {
        "doc_type": "project_proposal"
    },
    "validation_report": {
        "missing_fields": ["audience"],
        "conflicts": [],
        "next_questions": ["目标受众是谁？"]
    },
    "reply": "我理解您需要写一份项目提案。请问目标受众是谁？",
    "ready_to_write": false
}
```'''
        mock_response = MockResponse(
            content=mock_content,
            reasoning_content="用户想写项目提案，需要收集更多信息..."
        )
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            from app.nodes.controller import run, _parse_controller_response
            
            state = {
                "doc_variables": {},
                "chat_history": [{"role": "user", "content": "帮我写一份项目提案"}],
                "attachments": [],
                "node_runs": [],
            }
            
            result = await run(state)
            
            assert result["node_status"] == "success"
            assert "doc_type" in result["doc_variables"]
            assert result["ready_to_write"] == False
    
    def test_parse_controller_response_valid_json(self):
        """测试解析有效 JSON 响应"""
        from app.nodes.controller import _parse_controller_response
        
        response = '''```json
{
    "doc_variables_patch": {"key": "value"},
    "validation_report": {"missing_fields": []},
    "reply": "好的",
    "ready_to_write": true
}
```'''
        
        result = _parse_controller_response(response)
        
        assert result["doc_variables_patch"] == {"key": "value"}
        assert result["ready_to_write"] == True
    
    def test_parse_controller_response_invalid_json(self):
        """测试解析无效 JSON 响应"""
        from app.nodes.controller import _parse_controller_response
        
        response = "这只是普通文本，不是 JSON"
        
        result = _parse_controller_response(response)
        
        # 应该优雅降级
        assert result["reply"] == response
        assert result["ready_to_write"] == False


class TestWriterNode:
    """测试撰写节点"""
    
    @pytest.mark.asyncio
    async def test_writer_generates_draft(self):
        """测试撰写节点生成草稿"""
        mock_content = '''```json
{
    "draft_md": "# 项目提案\\n\\n这是简介。\\n\\n{{MERMAID:流程图}}",
    "mermaid_placeholders": [
        {"id": "mermaid_1", "description": "流程图"}
    ],
    "html_placeholders": []
}
```'''
        mock_response = MockResponse(content=mock_content)
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            from app.nodes.writer import run
            
            state = {
                "doc_variables": {
                    "doc_type": "project_proposal",
                    "outline": ["简介", "目标"]
                },
                "attachments": [],
                "node_runs": [],
            }
            
            result = await run(state)
            
            assert result["node_status"] == "success"
            assert "draft_md" in result
            assert len(result["mermaid_placeholders"]) == 1
    
    @pytest.mark.asyncio
    async def test_writer_insufficient_info(self):
        """测试撰写节点信息不足"""
        from app.nodes.writer import run
        
        state = {
            "doc_variables": {},  # 空的，信息不足
            "attachments": [],
            "node_runs": [],
        }
        
        result = await run(state)
        
        assert result["node_status"] == "fail"
        assert "error" in result


class TestDiagramNode:
    """测试图表节点"""
    
    @pytest.mark.asyncio
    async def test_diagram_generates_mermaid(self):
        """测试生成 Mermaid 代码"""
        mock_content = '''```json
{
    "code": "graph TD\\n    A[开始] --> B[结束]",
    "type": "flowchart"
}
```'''
        mock_response = MockResponse(content=mock_content)
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            from app.nodes.diagram import run
            
            state = {
                "mermaid_placeholders": [
                    {"id": "mermaid_1", "description": "简单流程图"}
                ],
                "html_placeholders": [],
                "doc_variables": {},
                "node_runs": [],
            }
            
            result = await run(state)
            
            assert result["node_status"] == "success"
            assert "mermaid_1" in result["mermaid_codes"]
    
    @pytest.mark.asyncio
    async def test_diagram_no_placeholders(self):
        """测试无占位符时的处理"""
        from app.nodes.diagram import run
        
        state = {
            "mermaid_placeholders": [],
            "html_placeholders": [],
            "doc_variables": {},
            "node_runs": [],
        }
        
        result = await run(state)
        
        assert result["node_status"] == "success"
        assert result["mermaid_codes"] == {}


class TestAssemblerNode:
    """测试组装节点"""
    
    @pytest.mark.asyncio
    async def test_assembler_replaces_placeholders(self):
        """测试组装节点替换占位符"""
        from app.nodes.assembler import run
        
        state = {
            "draft_md": "# 文档\n\n{{MERMAID:流程图}}\n\n结束。",
            "mermaid_placeholders": [
                {"id": "mermaid_1", "description": "流程图"}
            ],
            "html_placeholders": [],
            "mermaid_codes": {
                "mermaid_1": {"code": "graph TD\n    A --> B", "type": "flowchart"}
            },
            "html_codes": {},
            "doc_variables": {},
            "node_runs": [],
        }
        
        result = await run(state)
        
        assert result["node_status"] == "success"
        assert "```mermaid" in result["final_md"]
        assert "{{MERMAID:" not in result["final_md"]
    
    @pytest.mark.asyncio
    async def test_assembler_missing_code(self):
        """测试缺少代码时的处理"""
        from app.nodes.assembler import run
        
        state = {
            "draft_md": "# 文档\n\n{{MERMAID:缺失}}\n\n结束。",
            "mermaid_placeholders": [
                {"id": "mermaid_1", "description": "缺失"}
            ],
            "html_placeholders": [],
            "mermaid_codes": {},  # 没有代码
            "html_codes": {},
            "doc_variables": {},
            "node_runs": [],
        }
        
        result = await run(state)
        
        # 应该失败因为代码缺失
        assert result["node_status"] == "fail"
        assert "assembly_errors" in result
    
    @pytest.mark.asyncio
    async def test_assembler_no_draft(self):
        """测试无草稿时的处理"""
        from app.nodes.assembler import run
        
        state = {
            "draft_md": "",
            "mermaid_placeholders": [],
            "html_placeholders": [],
            "mermaid_codes": {},
            "html_codes": {},
            "doc_variables": {},
            "node_runs": [],
        }
        
        result = await run(state)
        
        assert result["node_status"] == "fail"


class TestAttachmentNode:
    """测试附件分析节点"""
    
    @pytest.mark.asyncio
    async def test_attachment_analyze(self):
        """测试附件分析"""
        mock_response = MockResponse(content="这是一份项目计划书，主要包含...")
        
        with patch('dashscope.Generation.call', return_value=mock_response):
            from app.nodes.attachment import run
            
            state = {
                "attachments": [
                    {"id": "att_1", "file_id": "file_123", "filename": "plan.pdf"}
                ],
                "doc_variables": {},
                "node_runs": [],
            }
            
            result = await run(state)
            
            assert result["node_status"] == "success"
            assert "attachment_analysis" in result
    
    @pytest.mark.asyncio
    async def test_attachment_no_files(self):
        """测试无附件时的处理"""
        from app.nodes.attachment import run
        
        state = {
            "attachments": [],
            "doc_variables": {},
            "node_runs": [],
        }
        
        result = await run(state)
        
        assert result["node_status"] == "success"
        assert result.get("attachment_analysis", "") == ""
