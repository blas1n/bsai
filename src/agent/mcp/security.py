"""Security validators and encryption for MCP integration."""

from __future__ import annotations

import json
import re
import shlex
from base64 import b64decode, b64encode
from typing import Any

import structlog
from cryptography.fernet import Fernet

from ..api.config import McpSettings
from ..db.models.mcp_server_config import McpServerConfig

logger = structlog.get_logger()


class McpSecurityValidator:
    """Security validation for MCP configurations.

    Provides validation for:
    - stdio command allowlisting (prevent command injection)
    - Server URL validation (prevent SSRF attacks)
    - Tool risk assessment (evaluate risk level of tool calls)
    """

    def __init__(self, settings: McpSettings | None = None):
        """Initialize security validator.

        Args:
            settings: MCP settings (if None, creates default settings)
        """
        self.settings = settings or McpSettings()
        self.allowed_stdio_commands = set(self.settings.allowed_stdio_commands)
        self.blocked_url_patterns = self.settings.blocked_url_patterns
        self.high_risk_keywords = self.settings.high_risk_keywords
        self.medium_risk_keywords = self.settings.medium_risk_keywords

    def validate_stdio_command(self, command: str) -> None:
        """Validate stdio command against allowlist.

        Args:
            command: Command string to validate

        Raises:
            ValueError: If command is not allowed
        """
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        try:
            cmd_parts = shlex.split(command)
        except ValueError as e:
            raise ValueError(f"Invalid command syntax: {e}") from e

        if not cmd_parts:
            raise ValueError("Command cannot be empty")

        base_cmd = cmd_parts[0]

        # Extract base command name (remove path)
        if "/" in base_cmd or "\\" in base_cmd:
            base_cmd = base_cmd.split("/")[-1].split("\\")[-1]

        if base_cmd not in self.allowed_stdio_commands:
            allowed_list = ", ".join(sorted(self.allowed_stdio_commands))
            raise ValueError(
                f"Command '{base_cmd}' not allowed. " f"Allowed commands: {allowed_list}"
            )

    def validate_server_url(self, url: str) -> None:
        """Validate HTTP/SSE URL to prevent SSRF attacks.

        Args:
            url: Server URL to validate

        Raises:
            ValueError: If URL matches blocked patterns
        """
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        url_lower = url.lower().strip()

        # Must use HTTP or HTTPS
        if not url_lower.startswith(("http://", "https://")):
            raise ValueError("URL must use HTTP or HTTPS protocol")

        # Check against blocked patterns
        for pattern in self.blocked_url_patterns:
            if re.match(pattern, url_lower, re.IGNORECASE):
                raise ValueError(
                    f"URL blocked: Cannot access internal/private IP addresses. "
                    f"Matched pattern: {pattern}"
                )

    def assess_tool_risk(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> tuple[str, list[str]]:
        """Assess risk level of a tool call.

        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters

        Returns:
            Tuple of (risk_level, reasons) where risk_level is "low" | "medium" | "high"
        """
        reasons = []
        tool_name_lower = tool_name.lower()

        # Check for high-risk keywords in tool name
        for keyword in self.high_risk_keywords:
            if keyword in tool_name_lower:
                reasons.append(f"Tool name contains high-risk keyword: '{keyword}'")
                return ("high", reasons)

        # Medium-risk indicators
        for keyword in self.medium_risk_keywords:
            if keyword in tool_name_lower:
                reasons.append(f"Tool name contains modification keyword: '{keyword}'")
                break

        # Check tool input for risky patterns
        input_str = json.dumps(tool_input).lower()

        # Check for filesystem paths
        if "/" in input_str or "\\" in input_str:
            reasons.append("Tool operates on filesystem paths")

        # Check for shell commands
        if any(key in tool_input for key in ["command", "cmd", "shell", "exec"]):
            reasons.append("Tool may execute shell commands")
            return ("high", reasons)

        # Check for SQL keywords
        sql_keywords = ["select", "insert", "update", "delete", "drop", "create", "alter"]
        if any(f" {kw} " in f" {input_str} " for kw in sql_keywords):
            reasons.append("Tool may execute SQL queries")
            if any(kw in input_str for kw in ["drop", "delete", "truncate"]):
                return ("high", reasons)
            reasons.append("SQL operations detected")

        # Determine risk level
        if reasons:
            return ("medium", reasons)

        return ("low", [])


class CredentialEncryption:
    """Encrypt and decrypt MCP server credentials.

    Uses Fernet (symmetric encryption) with AES-128-CBC.
    Each instance requires a secret key for encryption/decryption.

    Note: In production, the encryption key should be:
    1. Stored securely (environment variable MCP_ENCRYPTION_KEY)
    2. Rotated periodically
    3. Different per environment (dev/staging/prod)
    """

    def __init__(self, settings: McpSettings | None = None):
        """Initialize credential encryption.

        Args:
            settings: MCP settings containing encryption key.
                     If None or key is empty, generates a new key (WARNING: for development only)
        """
        settings = settings or McpSettings()
        encryption_key = settings.encryption_key

        if encryption_key:
            # Validate key format
            try:
                self.fernet = Fernet(encryption_key.encode())
            except Exception as e:
                raise ValueError(f"Invalid encryption key: {e}") from e
        else:
            # Generate new key (development only!)
            # In production, MCP_ENCRYPTION_KEY must be set
            self.fernet = Fernet(Fernet.generate_key())

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key.

        Returns:
            Base64-encoded key string

        Example:
            >>> key = CredentialEncryption.generate_key()
            >>> encryptor = CredentialEncryption(key)
        """
        return Fernet.generate_key().decode()

    def encrypt(self, credentials: dict[str, Any]) -> str:
        """Encrypt credentials dictionary.

        Args:
            credentials: Credentials to encrypt (e.g., {"api_key": "secret"})

        Returns:
            Encrypted credentials as base64 string
        """
        if not credentials:
            raise ValueError("Credentials cannot be empty")

        # Serialize to JSON
        json_str = json.dumps(credentials)

        # Encrypt
        encrypted_bytes = self.fernet.encrypt(json_str.encode())

        # Return as base64 string
        return b64encode(encrypted_bytes).decode()

    def decrypt(self, encrypted_credentials: str) -> dict[str, Any]:
        """Decrypt credentials string.

        Args:
            encrypted_credentials: Encrypted credentials string

        Returns:
            Decrypted credentials dictionary

        Raises:
            ValueError: If decryption fails
        """
        if not encrypted_credentials:
            raise ValueError("Encrypted credentials cannot be empty")

        try:
            # Decode base64
            encrypted_bytes = b64decode(encrypted_credentials)

            # Decrypt
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)

            # Parse JSON
            return json.loads(decrypted_bytes.decode())
        except Exception as e:
            raise ValueError(f"Failed to decrypt credentials: {e}") from e


def build_mcp_auth_headers(
    server: McpServerConfig,
    settings: McpSettings | None = None,
) -> dict[str, str] | None:
    """Build authentication headers for MCP server requests.

    Decrypts stored credentials and constructs appropriate headers based on auth type.

    Args:
        server: MCP server configuration
        settings: MCP settings for decryption (uses default if None)

    Returns:
        Dictionary of headers or None if no auth configured/decryption fails
    """
    if not server.auth_credentials:
        return None

    if not server.auth_type or server.auth_type == "none":
        return None

    settings = settings or McpSettings()
    encryptor = CredentialEncryption(settings)

    try:
        credentials = encryptor.decrypt(server.auth_credentials)
    except Exception as e:
        logger.warning(
            "mcp_credential_decrypt_failed",
            server_name=server.name,
            error=str(e),
        )
        return None

    headers: dict[str, str] | None = None

    if server.auth_type == "bearer":
        token = credentials.get("token", "")
        if token:
            headers = {"Authorization": f"Bearer {token}"}
    elif server.auth_type == "api_key":
        api_key = credentials.get("api_key", "")
        if api_key:
            headers = {credentials.get("header_name", "X-API-Key"): api_key}
    elif server.auth_type == "oauth2":
        access_token = credentials.get("access_token", "")
        if access_token:
            headers = {"Authorization": f"Bearer {access_token}"}

    if not headers and server.auth_type and server.auth_type != "none":
        logger.warning(
            "mcp_auth_headers_empty",
            server_name=server.name,
            auth_type=server.auth_type,
        )

    return headers
