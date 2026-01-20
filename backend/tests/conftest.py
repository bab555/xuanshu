"""
Pytest fixtures and configuration
"""
import os
import sys
import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.database import Base, get_db
from app.config import settings


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db(tmp_path) -> AsyncGenerator[AsyncSession, None]:
    """Create test database and session"""
    # Use file-based SQLite so background tasks / new connections can see the same DB.
    # In-memory SQLite is per-connection and will break background tasks.
    db_file = tmp_path / "test.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    old_db_url = settings.database_url
    settings.database_url = test_db_url

    engine = create_async_engine(test_db_url, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()
    settings.database_url = old_db_url


@pytest_asyncio.fixture(scope="function")
async def client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with test database"""
    
    async def override_get_db():
        yield test_db
    
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def auth_client(client: AsyncClient) -> AsyncGenerator[tuple[AsyncClient, dict], None]:
    """Create authenticated test client"""
    # Register a test user
    register_data = {
        "username": "testuser",
        "password": "testpass123"
    }
    response = await client.post("/api/auth/register", json=register_data)
    assert response.status_code == 200
    
    auth_data = response.json()
    token = auth_data["token"]
    
    # Set authorization header
    client.headers["Authorization"] = f"Bearer {token}"
    
    yield client, auth_data


@pytest.fixture
def test_user_data() -> dict:
    """Test user data"""
    return {
        "username": "testuser",
        "password": "testpass123"
    }


@pytest.fixture
def test_doc_variables() -> dict:
    """Test document variables"""
    return {
        "doc_type": "project_proposal",
        "audience": "internal_team",
        "outline": ["Introduction", "Goals", "Timeline", "Budget"],
        "key_points": ["ROI analysis", "Risk assessment"],
        "tone": "professional"
    }


