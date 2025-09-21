"""Pytest configuration and fixtures"""
import pytest
import os
from pathlib import Path


@pytest.fixture(scope="session")
def project_root():
    """Get project root directory"""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_env():
    """Setup test environment"""
    os.environ["ENVIRONMENT"] = "test"
    os.environ["LOG_LEVEL"] = "DEBUG"
    os.environ["BSAI_MODE"] = "test"
    yield
    # Cleanup if needed


@pytest.fixture
def mock_api_key():
    """Mock API key for testing"""
    return "test_api_key_mock"


@pytest.fixture
def sample_config():
    """Sample configuration for testing"""
    return {
        "environment": "test",
        "log_level": "DEBUG",
        "anthropic_api_key": "test_key",
        "bsai_mode": "test"
    }