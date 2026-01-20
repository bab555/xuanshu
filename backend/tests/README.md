# 测试说明

## 准备工作

1. 确保已安装依赖：
```powershell
cd backend
pip install -r requirements.txt
```

2. 复制并配置环境变量：
```powershell
copy ..\env.example ..\.env
# 编辑 .env 文件填入实际的 API Key
```

## 测试类型

### 1. API 连接测试（推荐先运行）

验证 DashScope API 连接和各模型可用性：

```powershell
cd backend
python -m tests.test_api_connection
```

此脚本会：
- 检查配置是否正确
- 测试中控模型（带思考模式）
- 测试撰写模型
- 测试图文模型
- （可选）测试图片生成模型

### 2. 单元测试

运行所有单元测试：
```powershell
pytest tests/ -v
```

只运行特定测试：
```powershell
# 模型客户端测试
pytest tests/test_model_client.py -v

# 节点测试
pytest tests/test_nodes.py -v

# 工具函数测试
pytest tests/test_utils.py -v
```

### 3. API 接口测试

测试 REST API 接口：
```powershell
# 认证测试
pytest tests/test_auth.py -v

# 文档测试
pytest tests/test_documents.py -v

# 工作流测试
pytest tests/test_workflow.py -v

# 附件测试
pytest tests/test_attachments.py -v

# 导出测试
pytest tests/test_export.py -v
```

### 4. 集成测试

端到端集成测试：
```powershell
pytest tests/test_integration.py -v
```

### 5. 网络连接测试

测试外部服务连接（需要有效 API Key）：
```powershell
pytest tests/test_network.py -v
```

## 测试覆盖率

生成测试覆盖率报告：
```powershell
pytest tests/ --cov=app --cov-report=html
```

报告将生成在 `htmlcov/` 目录。

## 跳过特定测试

跳过需要真实 API 的测试：
```powershell
pytest tests/ -v -k "not test_real"
```

跳过慢速测试：
```powershell
pytest tests/ -v -m "not slow"
```

## 测试文件说明

| 文件 | 说明 |
|-----|------|
| `conftest.py` | pytest 配置和 fixtures |
| `test_api_connection.py` | API 连接验证脚本 |
| `test_auth.py` | 认证 API 测试 |
| `test_documents.py` | 文档 API 测试 |
| `test_workflow.py` | 工作流 API 测试 |
| `test_attachments.py` | 附件 API 测试 |
| `test_export.py` | 导出 API 测试 |
| `test_model_client.py` | DashScope 客户端测试 |
| `test_nodes.py` | LangGraph 节点测试 |
| `test_utils.py` | 工具函数测试 |
| `test_network.py` | 网络连接测试 |
| `test_integration.py` | 集成测试 |

## 常见问题

### Q: 测试报 "DASHSCOPE_API_KEY 未设置"
A: 确保 `.env` 文件存在且包含正确的 API Key。

### Q: 连接测试超时
A: 检查网络连接，确认可以访问 `dashscope.aliyuncs.com`。

### Q: 模型调用失败
A: 检查模型名称是否正确，确认 API Key 有对应模型的权限。

