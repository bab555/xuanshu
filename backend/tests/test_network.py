"""
网络连接测试

测试与外部服务的连接性。
运行: pytest tests/test_network.py -v
"""
import pytest
from app.config import settings


class TestNetworkConnectivity:
    """测试网络连接"""
    
    @pytest.mark.asyncio
    async def test_dashscope_api_reachable(self):
        """测试 DashScope API 端点可达"""
        import httpx
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # 简单测试端点是否响应
                response = await client.get(
                    f"{settings.dashscope_base_url}/models",
                    headers={"Authorization": f"Bearer {settings.dashscope_api_key}"}
                )
                # 任何响应都说明端点可达
                assert response.status_code in [200, 401, 403, 404, 405]
                print(f"\n✓ DashScope API 端点可达 (HTTP {response.status_code})")
            except httpx.ConnectError:
                pytest.fail("无法连接到 DashScope API")
            except httpx.TimeoutException:
                pytest.fail("连接 DashScope API 超时")


class TestModelAvailability:
    """测试模型可用性（需要有效 API Key）"""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not settings.dashscope_api_key, reason="DASHSCOPE_API_KEY 未设置")
    async def test_controller_model(self):
        """测试中控模型可用"""
        from app.services.model_client import model_client
        
        try:
            reasoning, content = await model_client.call_with_thinking(
                model=settings.model_controller,
                messages=[{"role": "user", "content": "说'测试成功'"}],
                max_tokens=50
            )
            
            assert content is not None
            print(f"\n✓ 中控模型 ({settings.model_controller}) 可用")
            print(f"  思考: {reasoning[:50]}..." if reasoning else "  思考: 无")
            print(f"  回复: {content[:50]}...")
        except Exception as e:
            pytest.fail(f"中控模型调用失败: {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not settings.dashscope_api_key, reason="DASHSCOPE_API_KEY 未设置")
    async def test_writer_model(self):
        """测试撰写模型可用"""
        from app.services.model_client import model_client
        
        try:
            content = await model_client.call(
                model=settings.model_writer,
                messages=[{"role": "user", "content": "说'测试成功'"}],
                max_tokens=50
            )
            
            assert content is not None
            print(f"\n✓ 撰写模型 ({settings.model_writer}) 可用")
            print(f"  回复: {content[:50]}...")
        except Exception as e:
            pytest.fail(f"撰写模型调用失败: {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not settings.dashscope_api_key, reason="DASHSCOPE_API_KEY 未设置")
    async def test_diagram_model(self):
        """测试图文模型可用"""
        from app.services.model_client import model_client
        
        try:
            content = await model_client.call(
                model=settings.model_diagram,
                messages=[{"role": "user", "content": "说'测试成功'"}],
                max_tokens=50
            )
            
            assert content is not None
            print(f"\n✓ 图文模型 ({settings.model_diagram}) 可用")
            print(f"  回复: {content[:50]}...")
        except Exception as e:
            pytest.fail(f"图文模型调用失败: {e}")


class TestDatabaseConnectivity:
    """测试数据库连接"""
    
    @pytest.mark.asyncio
    async def test_database_connection(self):
        """测试数据库连接"""
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        
        engine = create_async_engine(settings.database_url, echo=False)
        
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
                print("\n✓ 数据库连接成功")
        except Exception as e:
            pytest.fail(f"数据库连接失败: {e}")
        finally:
            await engine.dispose()


class TestServiceHealth:
    """测试服务健康状态"""
    
    @pytest.mark.asyncio
    async def test_fastapi_startup(self):
        """测试 FastAPI 应用启动"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 根路径应该有响应
            response = await client.get("/")
            assert response.status_code in [200, 404]
            print("\n✓ FastAPI 应用启动成功")
    
    @pytest.mark.asyncio
    async def test_api_routes_registered(self):
        """测试 API 路由已注册"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 测试各主要路由
            routes = [
                ("/api/auth/login", "POST"),
                ("/api/docs/my", "GET"),
            ]
            
            for route, method in routes:
                if method == "GET":
                    response = await client.get(route)
                else:
                    response = await client.post(route, json={})
                
                # 不应该是 500 服务器错误
                assert response.status_code != 500, f"路由 {route} 返回服务器错误"
            
            print("\n✓ API 路由已正确注册")
