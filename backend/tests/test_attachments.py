"""
Attachment API tests
"""
import io
import pytest
from httpx import AsyncClient


class TestAttachmentAPI:
    """Test attachment endpoints"""
    
    @pytest.mark.asyncio
    async def test_upload_attachment(self, auth_client: tuple[AsyncClient, dict]):
        """Test uploading an attachment"""
        client, _ = auth_client
        
        # Create a document first
        doc_response = await client.post("/api/docs", json={"title": "Attachment Test"})
        doc_id = doc_response.json()["doc_id"]
        
        # Create a fake file
        file_content = b"This is a test file content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
        data = {"doc_id": doc_id}
        
        response = await client.post("/api/attachments", files=files, data=data)
        
        assert response.status_code == 200
        result = response.json()
        assert "attachment_id" in result
        assert result["filename"] == "test.txt"
    
    @pytest.mark.asyncio
    async def test_get_attachment(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting attachment info"""
        client, _ = auth_client
        
        # Create doc and upload attachment
        doc_response = await client.post("/api/docs", json={"title": "Get Attachment Test"})
        doc_id = doc_response.json()["doc_id"]
        
        file_content = b"Test content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
        upload_response = await client.post("/api/attachments", files=files, data={"doc_id": doc_id})
        attachment_id = upload_response.json()["attachment_id"]
        
        # Get attachment info
        response = await client.get(f"/api/attachments/{attachment_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["attachment_id"] == attachment_id
        assert data["filename"] == "test.txt"
    
    @pytest.mark.asyncio
    async def test_get_document_attachments(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting all attachments for a document"""
        client, _ = auth_client
        
        # Create doc
        doc_response = await client.post("/api/docs", json={"title": "List Attachments Test"})
        doc_id = doc_response.json()["doc_id"]
        
        # Upload multiple attachments
        for i in range(3):
            files = {"file": (f"test{i}.txt", io.BytesIO(f"Content {i}".encode()), "text/plain")}
            await client.post("/api/attachments", files=files, data={"doc_id": doc_id})
        
        # Get all attachments
        response = await client.get(f"/api/attachments/doc/{doc_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "attachments" in data
        assert len(data["attachments"]) == 3
    
    @pytest.mark.asyncio
    async def test_upload_to_nonexistent_document(self, auth_client: tuple[AsyncClient, dict]):
        """Test uploading to nonexistent document"""
        client, _ = auth_client
        
        files = {"file": ("test.txt", io.BytesIO(b"content"), "text/plain")}
        response = await client.post("/api/attachments", files=files, data={"doc_id": "nonexistent"})
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_attachment(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting nonexistent attachment"""
        client, _ = auth_client
        
        response = await client.get("/api/attachments/nonexistent-id")
        
        assert response.status_code == 404


