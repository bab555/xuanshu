"""
Workflow API tests
"""
import pytest
from httpx import AsyncClient


class TestWorkflowAPI:
    """Test workflow endpoints"""
    
    @pytest.mark.asyncio
    async def test_start_workflow(self, auth_client: tuple[AsyncClient, dict]):
        """Test starting a workflow"""
        client, _ = auth_client
        
        # Create a document first
        doc_response = await client.post("/api/docs", json={"title": "Workflow Test"})
        doc_id = doc_response.json()["doc_id"]
        
        # Start workflow
        response = await client.post(f"/api/workflow/docs/{doc_id}/run", json={
            "user_message": "Help me write a project proposal"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "started"
    
    @pytest.mark.asyncio
    async def test_send_chat_message(self, auth_client: tuple[AsyncClient, dict]):
        """Test sending chat message"""
        client, _ = auth_client
        
        # Create a document
        doc_response = await client.post("/api/docs", json={"title": "Chat Test"})
        doc_id = doc_response.json()["doc_id"]
        
        # Send chat message
        response = await client.post(f"/api/workflow/docs/{doc_id}/chat", json={
            "user_message": "I want to write a technical document about AI"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
    
    @pytest.mark.asyncio
    async def test_get_workflow_status(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting workflow status"""
        client, _ = auth_client
        
        # Create and start workflow
        doc_response = await client.post("/api/docs", json={"title": "Status Test"})
        doc_id = doc_response.json()["doc_id"]
        
        run_response = await client.post(f"/api/workflow/docs/{doc_id}/run", json={
            "user_message": "Test message"
        })
        run_id = run_response.json()["run_id"]
        
        # Get status
        response = await client.get(f"/api/workflow/runs/{run_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert "status" in data
    
    @pytest.mark.asyncio
    async def test_workflow_nonexistent_document(self, auth_client: tuple[AsyncClient, dict]):
        """Test starting workflow on nonexistent document"""
        client, _ = auth_client
        
        response = await client.post("/api/workflow/docs/nonexistent-id/run", json={
            "user_message": "Test"
        })
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_workflow(self, auth_client: tuple[AsyncClient, dict]):
        """Test getting nonexistent workflow"""
        client, _ = auth_client
        
        response = await client.get("/api/workflow/runs/nonexistent-run-id")
        
        assert response.status_code == 404


