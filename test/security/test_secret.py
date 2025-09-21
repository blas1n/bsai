"""Security tests for secret management"""
import pytest
import os
from unittest.mock import patch, MagicMock


def test_secret_manager_init():
    """Test secret manager initialization"""
    from secrets.secret_manager import SecretManager
    
    manager = SecretManager()
    assert manager.project_root.exists()


def test_environment_detection():
    """Test environment detection logic"""
    from secrets.secret_manager import SecretManager
    
    manager = SecretManager()
    
    # Test demo mode (default)
    with patch.dict(os.environ, {}, clear=True):
        env_type = manager._detect_environment()
        assert env_type == "demo"
    
    # Test codespaces
    with patch.dict(os.environ, {"CODESPACES": "true"}):
        env_type = manager._detect_environment()
        assert env_type == "codespaces"
    
    # Test CI
    with patch.dict(os.environ, {"CI": "true"}):
        env_type = manager._detect_environment()
        assert env_type == "ci"


def test_secret_key_generation():
    """Test secret key generation"""
    from secrets.secret_manager import SecretManager
    
    manager = SecretManager()
    key1 = manager._generate_secret_key()
    key2 = manager._generate_secret_key()
    
    assert len(key1) > 32
    assert len(key2) > 32
    assert key1 != key2  # Should be random


@pytest.mark.integration
def test_demo_mode_setup():
    """Test demo mode setup creates safe defaults"""
    from secrets.secret_manager import SecretManager
    
    manager = SecretManager()
    
    # Mock the file operations for testing
    with patch.object(manager, '_create_env_file') as mock_create:
        manager._setup_demo()
        
        # Verify it was called with demo values
        mock_create.assert_called_once()
        call_args = mock_create.call_args[0][0]
        
        assert "demo_key_safe_mode" in call_args["ANTHROPIC_API_KEY"]
        assert call_args["BSAI_MODE"] == "demo"