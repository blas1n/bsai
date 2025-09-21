"""Secret validation utilities"""
import re
from typing import Optional


def validate_anthropic_key(key: str) -> bool:
    """Validate Anthropic API key format"""
    if not key:
        return False
    return key.startswith("sk-ant-") and len(key) > 100


def validate_secret_key(key: str) -> bool:
    """Validate secret key strength"""
    if not key:
        return False
    return len(key) >= 32


def mask_secret(secret: str, show_chars: int = 4) -> str:
    """Mask secret for safe display"""
    if not secret or len(secret) <= show_chars:
        return "*" * 8
    
    return secret[:show_chars] + "*" * (len(secret) - show_chars * 2) + secret[-show_chars:]


def detect_secret_in_text(text: str) -> Optional[str]:
    """Detect potential secrets in text"""
    patterns = [
        r'sk-ant-[a-zA-Z0-9\-_]{95,}',  # Anthropic API key
        r'sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20}',  # OpenAI API key
        r'AKIA[0-9A-Z]{16}',  # AWS Access Key
    ]
    
    for pattern in patterns:
        if re.search(pattern, text):
            return "Potential secret detected"
    
    return None