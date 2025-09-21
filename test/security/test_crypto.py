"""Cryptographic security tests"""
import pytest


def test_secret_masking():
    """Test secret masking functionality"""
    from secrets.validators import mask_secret

    # Test normal secret
    secret = "sk-ant-1234567890abcdef"
    masked = mask_secret(secret, 4)
    assert masked.startswith("sk-a")
    assert masked.endswith("cdef")
    assert "*" in masked

    # Test short secret
    short_secret = "abc"
    masked_short = mask_secret(short_secret)
    assert masked_short == "********"

    # Test empty secret
    assert mask_secret("") == "********"


def test_secret_detection():
    """Test secret detection in text"""
    from secrets.validators import detect_secret_in_text

    # Test with Anthropic key
    text_with_secret = "ANTHROPIC_API_KEY=sk-ant-" + "x" * 100
    result = detect_secret_in_text(text_with_secret)
    assert result == "Potential secret detected"

    # Test with clean text
    clean_text = "This is just normal text"
    result = detect_secret_in_text(clean_text)
    assert result is None

    # Test with AWS key
    aws_text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    result = detect_secret_in_text(aws_text)
    assert result == "Potential secret detected"


@pytest.mark.security
def test_no_hardcoded_secrets():
    """Ensure no hardcoded secrets in codebase"""
    import ast
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent

    dangerous_patterns = [
        "sk-ant-",
        "AKIA",
        "-----BEGIN PRIVATE KEY-----"
    ]

    python_files = list(project_root.rglob("*.py"))

    for py_file in python_files:
        if "test" in str(py_file) and "hardcoded" in str(py_file):
            continue  # Skip this test file itself

        content = py_file.read_text()

        for pattern in dangerous_patterns:
            if pattern in content and "example" not in content.lower():
                pytest.fail(
                    f"Potential hardcoded secret found in {py_file}: {pattern}")
