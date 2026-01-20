"""
Authentication API tests
"""
import pytest
from httpx import AsyncClient


class TestAuthAPI:
    """Test authentication endpoints"""
    
    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """Test successful user registration"""
        response = await client.post("/api/auth/register", json={
            "username": "newuser",
            "password": "password123"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert data["username"] == "newuser"
        assert "token" in data
    
    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, client: AsyncClient):
        """Test registration with duplicate username"""
        user_data = {"username": "duplicateuser", "password": "password123"}
        
        # First registration
        response = await client.post("/api/auth/register", json=user_data)
        assert response.status_code == 200
        
        # Duplicate registration
        response = await client.post("/api/auth/register", json=user_data)
        assert response.status_code == 400
        detail = str(response.json().get("detail", ""))
        assert ("already exists" in detail.lower()) or ("已存在" in detail)
    
    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient):
        """Test successful login"""
        # Register first
        await client.post("/api/auth/register", json={
            "username": "loginuser",
            "password": "password123"
        })
        
        # Login
        response = await client.post("/api/auth/login", json={
            "username": "loginuser",
            "password": "password123"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["username"] == "loginuser"
    
    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient):
        """Test login with wrong password"""
        # Register first
        await client.post("/api/auth/register", json={
            "username": "wrongpassuser",
            "password": "correctpass"
        })
        
        # Login with wrong password
        response = await client.post("/api/auth/login", json={
            "username": "wrongpassuser",
            "password": "wrongpass"
        })
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with nonexistent user"""
        response = await client.post("/api/auth/login", json={
            "username": "nonexistent",
            "password": "password123"
        })
        
        assert response.status_code == 401


