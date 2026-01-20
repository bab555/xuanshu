"""
Export API tests
"""
import pytest
from httpx import AsyncClient


class TestExportAPI:
    """Test export endpoints"""
    
    @pytest.mark.asyncio
    async def test_create_export_task(self, auth_client: tuple[AsyncClient, dict]):
        """Test creating an export task"""
        client, _ = auth_client
        
        # Create a document with content
        doc_response = await client.post("/api/docs", json={"title": "Export Test"})
        doc_id = doc_response.json()["doc_id"]
        
        # Add some content
        await client.put(f"/api/docs/{doc_id}", json={
            "content_md": "# Test Document\n\nThis is test content."
        })
        
        # Create export task
        response = await client.post(f"/api/exports/docs/{doc_id}/docx")
        
        assert response.status_code == 200
        data = response.json()
        assert "export_id" in data
        assert data["status"] == "processing"
    
    @pytest.mark.asyncio
    async def test_export_empty_document(self, auth_client: tuple[AsyncClient, dict]):
        """Test exporting empty document"""
        client, _ = auth_client
        
        # Create empty document
        doc_response = await client.post("/api/docs", json={"title": "Empty Doc"})
        doc_id = doc_response.json()["doc_id"]
        
        # Try to export
        response = await client.post(f"/api/exports/docs/{doc_id}/docx")
        
        assert response.status_code == 400
        detail = str(response.json().get("detail", ""))
        assert ("empty" in detail.lower()) or ("为空" in detail)
    
    @pytest.mark.asyncio
    async def test_get_export_status(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting export status"""
        client, _ = auth_client
        
        # Create document with content
        doc_response = await client.post("/api/docs", json={"title": "Status Test"})
        doc_id = doc_response.json()["doc_id"]
        
        await client.put(f"/api/docs/{doc_id}", json={
            "content_md": "# Test\n\nContent here."
        })
        
        # Create export
        export_response = await client.post(f"/api/exports/docs/{doc_id}/docx")
        export_id = export_response.json()["export_id"]
        
        # Get status
        response = await client.get(f"/api/exports/{export_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["export_id"] == export_id
        assert "status" in data
    
    @pytest.mark.asyncio
    async def test_export_nonexistent_document(self, auth_client: tuple[AsyncClient, dict]):
        """Test exporting nonexistent document"""
        client, _ = auth_client
        
        response = await client.post("/api/exports/docs/nonexistent-id/docx")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_export(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting nonexistent export"""
        client, _ = auth_client
        
        response = await client.get("/api/exports/nonexistent-export-id")
        
        assert response.status_code == 404


