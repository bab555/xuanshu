"""
Unit tests for utility functions
"""
import os
import tempfile
import pytest
from datetime import timedelta

from app.utils.auth import create_access_token, decode_access_token
from app.utils.storage import save_file, get_file_url, ensure_dir
from app.config import settings


class TestAuthUtils:
    """Test authentication utilities"""
    
    def test_create_access_token(self):
        """Test creating JWT token"""
        token = create_access_token(
            data={"sub": "test_user_id"},
            expires_delta=timedelta(hours=1)
        )
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_decode_access_token(self):
        """Test decoding JWT token"""
        user_id = "test_user_123"
        token = create_access_token(
            data={"sub": user_id},
            expires_delta=timedelta(hours=1)
        )
        
        payload = decode_access_token(token)
        
        assert payload is not None
        assert payload.get("sub") == user_id
    
    def test_decode_invalid_token(self):
        """Test decoding invalid token"""
        payload = decode_access_token("invalid_token")
        
        assert payload is None
    
    def test_token_expiration(self):
        """Test token with very short expiration"""
        token = create_access_token(
            data={"sub": "user"},
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        payload = decode_access_token(token)
        
        # Should fail to decode expired token
        assert payload is None


class TestStorageUtils:
    """Test storage utilities"""
    
    @pytest.mark.asyncio
    async def test_save_file(self, tmp_path):
        """Test saving file"""
        # Temporarily change storage path
        original_storage = settings.storage_path
        settings.storage_path = str(tmp_path)
        
        try:
            content = b"Test file content"
            filepath = await save_file(content, "test.txt", "test_subdir")
            
            assert os.path.exists(filepath)
            with open(filepath, "rb") as f:
                assert f.read() == content
        finally:
            settings.storage_path = original_storage
    
    @pytest.mark.asyncio
    async def test_save_file_unique_names(self, tmp_path):
        """Test that saved files get unique names"""
        original_storage = settings.storage_path
        settings.storage_path = str(tmp_path)
        
        try:
            content1 = b"Content 1"
            content2 = b"Content 2"
            
            path1 = await save_file(content1, "same.txt", "test")
            path2 = await save_file(content2, "same.txt", "test")
            
            # Should be different paths
            assert path1 != path2
            assert os.path.exists(path1)
            assert os.path.exists(path2)
        finally:
            settings.storage_path = original_storage
    
    def test_get_file_url(self, tmp_path):
        """Test getting file URL"""
        original_storage = settings.storage_path
        settings.storage_path = str(tmp_path)
        
        try:
            filepath = os.path.join(str(tmp_path), "attachments", "test.txt")
            url = get_file_url(filepath)
            
            assert url.startswith("/storage/")
            assert "attachments" in url
        finally:
            settings.storage_path = original_storage
    
    def test_ensure_dir(self, tmp_path):
        """Test ensuring directory exists"""
        new_dir = os.path.join(str(tmp_path), "new", "nested", "dir")
        
        assert not os.path.exists(new_dir)
        
        ensure_dir(new_dir)
        
        assert os.path.exists(new_dir)
        assert os.path.isdir(new_dir)
    
    def test_ensure_dir_existing(self, tmp_path):
        """Test ensuring existing directory (should not fail)"""
        existing_dir = str(tmp_path)
        
        # Should not raise
        ensure_dir(existing_dir)
        
        assert os.path.exists(existing_dir)


