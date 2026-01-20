"""
API 连接测试脚本

用法：
    cd backend
    python -m tests.test_api_connection

此脚本会测试：
1. DashScope API 连接
2. 各模型是否可用
3. 思考模式是否正常
"""
import os
import sys
import asyncio

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()


def print_header(title: str):
    print("\n" + "=" * 50)
    print(f"  {title}")
    print("=" * 50)


def print_success(msg: str):
    print(f"  ✓ {msg}")


def print_error(msg: str):
    print(f"  ✗ {msg}")


def print_info(msg: str):
    print(f"  → {msg}")


async def test_basic_connection():
    """测试基本连接"""
    print_header("测试 DashScope 基本连接")
    
    from app.config import settings
    
    if not settings.dashscope_api_key:
        print_error("DASHSCOPE_API_KEY 未设置！请在 .env 文件中配置")
        return False
    
    print_info(f"API Key: {settings.dashscope_api_key[:10]}...")
    print_info(f"Base URL: {settings.dashscope_base_url}")
    print_success("配置已加载")
    return True


async def test_controller_model():
    """测试中控模型（带思考模式）"""
    print_header("测试中控模型 (deepseek-v3.2 + 思考模式)")
    
    from app.config import settings
    from app.services.model_client import model_client
    
    print_info(f"模型: {settings.model_controller}")
    print_info(f"思考模式: {'开启' if settings.model_controller_enable_thinking else '关闭'}")
    
    try:
        reasoning, content = await model_client.call_with_thinking(
            model=settings.model_controller,
            messages=[
                {"role": "system", "content": "你是一个文档助手"},
                {"role": "user", "content": "请用一句话说明你是谁"}
            ],
            max_tokens=500
        )
        
        if reasoning:
            print_success("思考过程获取成功")
            print_info(f"思考内容: {reasoning[:100]}..." if len(reasoning) > 100 else f"思考内容: {reasoning}")
        
        print_success("回复获取成功")
        print_info(f"回复: {content[:100]}..." if len(content) > 100 else f"回复: {content}")
        
        return True
    except Exception as e:
        print_error(f"调用失败: {e}")
        return False


async def test_writer_model():
    """测试文档撰写模型"""
    print_header("测试文档撰写模型 (qwen3-max)")
    
    from app.config import settings
    from app.services.model_client import call_writer
    
    print_info(f"模型: {settings.model_writer}")
    
    try:
        content = await call_writer(
            messages=[
                {"role": "user", "content": "请用一句话介绍Markdown"}
            ],
            max_tokens=200
        )
        
        print_success("调用成功")
        print_info(f"回复: {content[:100]}..." if len(content) > 100 else f"回复: {content}")
        return True
    except Exception as e:
        print_error(f"调用失败: {e}")
        return False


async def test_diagram_model():
    """测试图文助手模型"""
    print_header("测试图文助手模型 (qwen3-max)")
    
    from app.config import settings
    from app.services.model_client import call_diagram
    
    print_info(f"模型: {settings.model_diagram}")
    
    try:
        content = await call_diagram(
            messages=[
                {"role": "user", "content": "生成一个简单的mermaid流程图代码，展示：开始->处理->结束"}
            ],
            max_tokens=500
        )
        
        print_success("调用成功")
        print_info(f"回复:\n{content[:200]}..." if len(content) > 200 else f"回复:\n{content}")
        return True
    except Exception as e:
        print_error(f"调用失败: {e}")
        return False


async def test_image_model():
    """测试图片生成模型"""
    print_header("测试图片生成模型 (qwen-image-max)")
    
    from app.config import settings
    from app.services.model_client import generate_image
    
    print_info(f"模型: {settings.model_image}")
    print_info("注意: 图片生成可能需要较长时间...")
    
    try:
        urls = await generate_image(
            prompt="一个简单的蓝色圆形图标",
            size="512*512"
        )
        
        if urls:
            print_success(f"生成成功，获得 {len(urls)} 张图片")
            for i, url in enumerate(urls):
                print_info(f"图片 {i+1}: {url[:80]}...")
        else:
            print_info("未返回图片 URL（可能是响应格式不同）")
        return True
    except Exception as e:
        print_error(f"调用失败: {e}")
        return False


async def main():
    print("\n" + "=" * 60)
    print("        红点集团内部文档工具 - API 连接测试")
    print("=" * 60)
    
    results = {}
    
    # 测试基本连接
    results["基本连接"] = await test_basic_connection()
    
    if not results["基本连接"]:
        print("\n⚠️  基本配置失败，请先配置 .env 文件")
        return
    
    # 测试各模型
    results["中控模型"] = await test_controller_model()
    results["撰写模型"] = await test_writer_model()
    results["图文模型"] = await test_diagram_model()
    
    # 图片生成测试（可选，耗时较长）
    print("\n是否测试图片生成模型？(y/n): ", end="")
    try:
        choice = input().strip().lower()
        if choice == 'y':
            results["图片模型"] = await test_image_model()
        else:
            results["图片模型"] = "跳过"
    except EOFError:
        results["图片模型"] = "跳过"
    
    # 输出总结
    print_header("测试结果总结")
    
    all_passed = True
    for name, result in results.items():
        if result is True:
            print_success(f"{name}: 通过")
        elif result == "跳过":
            print_info(f"{name}: 跳过")
        else:
            print_error(f"{name}: 失败")
            all_passed = False
    
    if all_passed:
        print("\n🎉 所有测试通过！API 连接正常。")
    else:
        print("\n⚠️  部分测试失败，请检查配置和网络。")


if __name__ == "__main__":
    asyncio.run(main())

