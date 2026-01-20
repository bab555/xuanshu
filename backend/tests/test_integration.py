"""
Integration tests - End-to-end workflow tests
"""
import pytest
from httpx import AsyncClient


class TestEndToEndWorkflow:
    """End-to-end workflow tests"""
    
    @pytest.mark.asyncio
    async def test_full_document_creation_flow(self, auth_client: tuple[AsyncClient, dict]):
        """Test complete document creation workflow"""
        client, user_data = auth_client
        
        # 1. Create a new document
        doc_response = await client.post("/api/docs", json={
            "title": "E2E Test Document"
        })
        assert doc_response.status_code == 200
        doc_id = doc_response.json()["doc_id"]
        
        # 2. Verify document appears in my documents
        my_docs_response = await client.get("/api/docs/my")
        assert my_docs_response.status_code == 200
        docs = my_docs_response.json()["docs"]
        assert any(d["doc_id"] == doc_id for d in docs)
        
        # 3. Update document content
        update_response = await client.put(f"/api/docs/{doc_id}", json={
            "content_md": "# E2E Test\n\nThis is test content.",
            "doc_variables": {"doc_type": "test"}
        })
        assert update_response.status_code == 200
        
        # 4. Verify update
        detail_response = await client.get(f"/api/docs/{doc_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["title"] == "E2E Test Document"
    
    @pytest.mark.asyncio
    async def test_document_sharing_flow(self, client: AsyncClient):
        """Test document sharing between users"""
        # Create two users
        user1_response = await client.post("/api/auth/register", json={
            "username": "sharer",
            "password": "password123"
        })
        user1_token = user1_response.json()["token"]
        
        user2_response = await client.post("/api/auth/register", json={
            "username": "recipient",
            "password": "password123"
        })
        user2_token = user2_response.json()["token"]
        
        # User 1 creates a document
        client.headers["Authorization"] = f"Bearer {user1_token}"
        doc_response = await client.post("/api/docs", json={
            "title": "Shared Document"
        })
        doc_id = doc_response.json()["doc_id"]
        
        # User 1 shares with User 2
        share_response = await client.post(f"/api/docs/{doc_id}/share", json={
            "to_username": "recipient",
            "note": "Please review"
        })
        assert share_response.status_code == 200
        
        # User 2 checks shared documents
        client.headers["Authorization"] = f"Bearer {user2_token}"
        cc_response = await client.get("/api/docs/cc")
        assert cc_response.status_code == 200
        cc_docs = cc_response.json()["docs"]
        assert any(d["doc_id"] == doc_id for d in cc_docs)
    
    @pytest.mark.asyncio
    async def test_workflow_status_tracking(self, auth_client: tuple[AsyncClient, dict]):
        """Test workflow status tracking"""
        client, _ = auth_client
        
        # Create document
        doc_response = await client.post("/api/docs", json={
            "title": "Workflow Tracking Test"
        })
        doc_id = doc_response.json()["doc_id"]
        
        # Start workflow
        run_response = await client.post(f"/api/workflow/docs/{doc_id}/run", json={
            "user_message": "Create a simple test document"
        })
        assert run_response.status_code == 200
        run_id = run_response.json()["run_id"]
        
        # Check status
        status_response = await client.get(f"/api/workflow/runs/{run_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["run_id"] == run_id
        assert "status" in status
        assert "node_runs" in status


class TestAPIErrorHandling:
    """Test API error handling"""
    
    @pytest.mark.asyncio
    async def test_invalid_json_request(self, auth_client: tuple[AsyncClient, dict]):
        """Test handling of invalid JSON"""
        client, _ = auth_client
        
        response = await client.post(
            "/api/docs",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_missing_required_fields(self, auth_client: tuple[AsyncClient, dict]):
        """Test handling of missing required fields"""
        client, _ = auth_client
        
        # Try to share without specifying recipient
        doc_response = await client.post("/api/docs", json={"title": "Test"})
        doc_id = doc_response.json()["doc_id"]
        
        response = await client.post(f"/api/docs/{doc_id}/share", json={
            # Missing to_username
        })
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_rate_limiting_resilience(self, auth_client: tuple[AsyncClient, dict]):
        """Test multiple rapid requests"""
        client, _ = auth_client
        
        # Make many requests rapidly
        responses = []
        for _ in range(10):
            response = await client.get("/api/docs/my")
            responses.append(response.status_code)
        
        # All should succeed (no rate limiting in test)
        assert all(code == 200 for code in responses)


