"""Basic tests to ensure everything works"""
import pytest


def test_bsai_import():
    """Test that BSAI can be imported"""
    import bsai
    assert bsai.__version__ == "0.1.0"


def test_cli_import():
    """Test that CLI can be imported"""
    from bsai.cli.main import app
    assert app is not None


def test_logger_import():
    """Test that logger utilities work"""
    from bsai.utils.logger import setup_logger
    
    logger = setup_logger("test", "INFO", rich_handler=False)
    assert logger is not None
    assert logger.name == "test"


def test_config_import():
    """Test that core config can be imported"""
    from bsai.core.config.settings import Settings
    
    settings = Settings()
    assert settings.environment == "development"
    assert settings.log_level == "DEBUG"


@pytest.mark.unit
def test_secret_validation():
    """Test secret validation functions"""
    from secrets.validators import validate_anthropic_key, validate_secret_key
    
    # Test Anthropic key validation
    assert not validate_anthropic_key("")
    assert not validate_anthropic_key("invalid_key")
    assert validate_anthropic_key("sk-ant-" + "x" * 100)
    
    # Test secret key validation
    assert not validate_secret_key("")
    assert not validate_secret_key("short")
    assert validate_secret_key("a" * 32)