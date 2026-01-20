"""
Document API tests
"""
import pytest
from httpx import AsyncClient


class TestDocumentAPI:
    """Test document endpoints"""
    
    @pytest.mark.asyncio
    async def test_create_document(self, auth_client: tuple[AsyncClient, dict]):
        """Test creating a new document"""
        client, _ = auth_client
        
        response = await client.post("/api/docs", json={
            "title": "Test Document"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "doc_id" in data
    
    @pytest.mark.asyncio
    async def test_create_document_default_title(self, auth_client: tuple[AsyncClient, dict]):
        """Test creating document with default title"""
        client, _ = auth_client
        
        response = await client.post("/api/docs", json={})
        
        assert response.status_code == 200
        data = response.json()
        assert "doc_id" in data
    
    @pytest.mark.asyncio
    async def test_get_my_documents(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting user's documents"""
        client, _ = auth_client
        
        # Create some documents
        await client.post("/api/docs", json={"title": "Doc 1"})
        await client.post("/api/docs", json={"title": "Doc 2"})
        
        # Get my documents
        response = await client.get("/api/docs/my")
        
        assert response.status_code == 200
        data = response.json()
        assert "docs" in data
        assert len(data["docs"]) >= 2
    
    @pytest.mark.asyncio
    async def test_get_document_detail(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting document details"""
        client, _ = auth_client
        
        # Create a document
        create_response = await client.post("/api/docs", json={"title": "Detail Test"})
        doc_id = create_response.json()["doc_id"]
        
        # Get details
        response = await client.get(f"/api/docs/{doc_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Detail Test"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_document(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting nonexistent document"""
        client, _ = auth_client
        
        response = await client.get("/api/docs/nonexistent-id")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_update_document(self, auth_client: tuple[AsyncClient, dict]):
        """Test updating a document"""
        client, _ = auth_client
        
        # Create a document
        create_response = await client.post("/api/docs", json={"title": "Original Title"})
        doc_id = create_response.json()["doc_id"]
        
        # Update it
        response = await client.put(f"/api/docs/{doc_id}", json={
            "title": "Updated Title",
            "content_md": "# Hello World"
        })
        
        assert response.status_code == 200
        
        # Verify update
        get_response = await client.get(f"/api/docs/{doc_id}")
        assert get_response.json()["title"] == "Updated Title"
    
    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client: AsyncClient):
        """Test accessing documents without auth"""
        response = await client.get("/api/docs/my")
        
        assert response.status_code == 401


