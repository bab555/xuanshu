import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.abspath("backend"))

import httpx
from websockets.client import connect
from app.config import settings

async def test_full_link():
    print("=== 开始全链路联通自检 ===")
    base_url = "http://127.0.0.1:8001"
    ws_base_url = "ws://127.0.0.1:8001"
    
    # 1. 检查后端健康
    print(f"\n1. 检查后端健康 ({base_url}/health)...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{base_url}/health")
            if resp.status_code == 200:
                print("   [OK] 后端存活")
            else:
                print(f"   [FAIL] 后端返回 {resp.status_code}: {resp.text}")
                return
    except Exception as e:
        print(f"   [FAIL] 无法连接后端: {e}")
        print("   建议：请确保已在 backend 目录下运行 'uvicorn app.main:app --port 8001'")
        return

    # 2. 模拟登录
    print("\n2. 模拟用户登录...")
    token = ""
    user_id = ""
    try:
        async with httpx.AsyncClient() as client:
            # 注册个测试用户
            reg_data = {"username": "link_test_user", "password": "password123"}
            await client.post(f"{base_url}/api/auth/register", json=reg_data)
            
            # 登录
            resp = await client.post(f"{base_url}/api/auth/login", json=reg_data)
            if resp.status_code == 200:
                data = resp.json()
                token = data["token"]
                user_id = data["user_id"]
                print(f"   [OK] 登录成功, UserID: {user_id}")
            else:
                print(f"   [FAIL] 登录失败 {resp.status_code}: {resp.text}")
                return
    except Exception as e:
        print(f"   [FAIL] 认证请求异常: {e}")
        return

    # 3. 创建文档
    print("\n3. 创建测试文档...")
    doc_id = ""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base_url}/api/docs", json={"title": "联通测试文档"}, headers=headers)
            if resp.status_code == 200:
                doc_id = resp.json()["doc_id"]
                print(f"   [OK] 文档创建成功, DocID: {doc_id}")
            else:
                print(f"   [FAIL] 文档创建失败 {resp.status_code}: {resp.text}")
                return
    except Exception as e:
        print(f"   [FAIL] 文档请求异常: {e}")
        return

    # 4. 发起对话 (触发工作流)
    print("\n4. 发起对话请求...")
    run_id = ""
    try:
        async with httpx.AsyncClient() as client:
            chat_data = {"user_message": "你好，这是一条测试消息", "attachments": []}
            resp = await client.post(
                f"{base_url}/api/workflow/docs/{doc_id}/chat", 
                json=chat_data, 
                headers=headers
            )
            if resp.status_code == 200:
                run_id = resp.json()["run_id"]
                print(f"   [OK] 对话请求成功, RunID: {run_id}")
            else:
                print(f"   [FAIL] 对话请求失败 {resp.status_code}: {resp.text}")
                if "no such table" in resp.text:
                    print("   原因推测：数据库表未正确创建。请检查 backend/app/database.py 的 init_db")
                return
    except Exception as e:
        print(f"   [FAIL] 对话请求异常: {e}")
        return

    # 5. 连接 WebSocket
    print("\n5. 尝试 WebSocket 连接...")
    ws_url = f"{ws_base_url}/api/workflow/runs/{run_id}/stream"
    try:
        async with connect(ws_url) as websocket:
            print(f"   [OK] WebSocket 连接成功")
            
            # 等待第一条消息
            print("   等待消息推送...")
            msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            print(f"   [OK] 收到消息: {msg[:100]}...")
            
            # 简单验证是不是 connected
            if "connected" in msg:
                print("   [PASS] 协议握手正常")
            else:
                print("   [WARN] 收到的第一条消息不是 connected 事件")
                
    except asyncio.TimeoutError:
        print("   [FAIL] WebSocket 连接成功但 10秒内未收到任何消息 (后端可能卡死/未推送)")
    except Exception as e:
        print(f"   [FAIL] WebSocket 连接失败: {e}")
        print("   原因推测：CORS 问题 / 路径错误 / 后端 WS 路由挂了")

    print("\n=== 自检完成 ===")

if __name__ == "__main__":
    try:
        asyncio.run(test_full_link())
    except KeyboardInterrupt:
        pass

