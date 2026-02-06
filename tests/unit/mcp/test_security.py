"""Unit tests for MCP security validators and encryption."""

import pytest

from bsai.api.config import McpSettings
from bsai.mcp.security import CredentialEncryption, McpSecurityValidator


class TestMcpSecurityValidator:
    """Test MCP security validation."""

    def test_validate_stdio_command_allowed(self):
        """Test validation succeeds for allowed commands."""
        settings = McpSettings(allowed_stdio_commands=["node", "python3", "npx"])
        validator = McpSecurityValidator(settings)

        # Should not raise for allowed commands
        validator.validate_stdio_command("node")
        validator.validate_stdio_command("python3")
        validator.validate_stdio_command("npx")

    def test_validate_stdio_command_with_path(self):
        """Test validation extracts base command from path."""
        settings = McpSettings(allowed_stdio_commands=["node"])
        validator = McpSecurityValidator(settings)

        # Should extract 'node' from Unix paths
        validator.validate_stdio_command("/usr/bin/node")
        validator.validate_stdio_command("/usr/local/bin/node")
        validator.validate_stdio_command("node")  # Without path

    def test_validate_stdio_command_not_allowed(self):
        """Test validation fails for disallowed commands."""
        settings = McpSettings(allowed_stdio_commands=["node", "python3"])
        validator = McpSecurityValidator(settings)

        with pytest.raises(ValueError, match="Command 'bash' not allowed"):
            validator.validate_stdio_command("bash")

        with pytest.raises(ValueError, match="Command 'curl' not allowed"):
            validator.validate_stdio_command("curl")

    def test_validate_stdio_command_empty(self):
        """Test validation fails for empty command."""
        validator = McpSecurityValidator()

        with pytest.raises(ValueError, match="Command cannot be empty"):
            validator.validate_stdio_command("")

        with pytest.raises(ValueError, match="Command cannot be empty"):
            validator.validate_stdio_command("   ")

    def test_validate_stdio_command_invalid_syntax(self):
        """Test validation fails for invalid shell syntax."""
        validator = McpSecurityValidator()

        with pytest.raises(ValueError, match="Invalid command syntax"):
            validator.validate_stdio_command('node "unclosed quote')

    def test_validate_server_url_valid(self):
        """Test validation succeeds for valid URLs."""
        validator = McpSecurityValidator()

        # Should not raise for valid external URLs
        validator.validate_server_url("https://api.example.com")
        validator.validate_server_url("http://public-server.com")
        validator.validate_server_url("https://mcp.service.io/api")

    def test_validate_server_url_blocks_localhost(self):
        """Test validation blocks localhost URLs."""
        validator = McpSecurityValidator()

        with pytest.raises(ValueError, match="URL blocked"):
            validator.validate_server_url("http://localhost:8080")

        with pytest.raises(ValueError, match="URL blocked"):
            validator.validate_server_url("https://localhost/api")

    def test_validate_server_url_blocks_127_0_0_1(self):
        """Test validation blocks 127.0.0.1 URLs."""
        validator = McpSecurityValidator()

        with pytest.raises(ValueError, match="URL blocked"):
            validator.validate_server_url("http://127.0.0.1:8080")

        with pytest.raises(ValueError, match="URL blocked"):
            validator.validate_server_url("https://127.0.0.1/api")

    def test_validate_server_url_blocks_private_ips(self):
        """Test validation blocks private IP ranges."""
        validator = McpSecurityValidator()

        # Class A private: 10.0.0.0/8
        with pytest.raises(ValueError, match="URL blocked"):
            validator.validate_server_url("http://10.0.0.1")

        # Class B private: 172.16.0.0/12
        with pytest.raises(ValueError, match="URL blocked"):
            validator.validate_server_url("http://172.16.0.1")

        with pytest.raises(ValueError, match="URL blocked"):
            validator.validate_server_url("http://172.31.255.255")

        # Class C private: 192.168.0.0/16
        with pytest.raises(ValueError, match="URL blocked"):
            validator.validate_server_url("http://192.168.1.1")

    def test_validate_server_url_empty(self):
        """Test validation fails for empty URL."""
        validator = McpSecurityValidator()

        with pytest.raises(ValueError, match="URL cannot be empty"):
            validator.validate_server_url("")

        with pytest.raises(ValueError, match="URL cannot be empty"):
            validator.validate_server_url("   ")

    def test_validate_server_url_invalid_protocol(self):
        """Test validation fails for non-HTTP(S) protocols."""
        validator = McpSecurityValidator()

        with pytest.raises(ValueError, match="URL must use HTTP or HTTPS protocol"):
            validator.validate_server_url("ftp://example.com")

        with pytest.raises(ValueError, match="URL must use HTTP or HTTPS protocol"):
            validator.validate_server_url("file:///etc/passwd")

        with pytest.raises(ValueError, match="URL must use HTTP or HTTPS protocol"):
            validator.validate_server_url("gopher://example.com")

    def test_assess_tool_risk_low(self):
        """Test risk assessment for low-risk tools."""
        validator = McpSecurityValidator()

        risk_level, reasons = validator.assess_tool_risk(
            tool_name="get_weather",
            tool_input={"city": "New York"},
        )

        assert risk_level == "low"
        assert len(reasons) == 0

    def test_assess_tool_risk_medium_tool_name(self):
        """Test risk assessment for medium-risk tool names."""
        settings = McpSettings(medium_risk_keywords=["write", "update", "create"])
        validator = McpSecurityValidator(settings)

        risk_level, reasons = validator.assess_tool_risk(
            tool_name="write_file",
            tool_input={"content": "hello"},
        )

        assert risk_level == "medium"
        assert any("modification keyword" in r for r in reasons)

    def test_assess_tool_risk_medium_filesystem(self):
        """Test risk assessment for filesystem operations."""
        validator = McpSecurityValidator()

        risk_level, reasons = validator.assess_tool_risk(
            tool_name="read_data",
            tool_input={"path": "/home/user/data.json"},
        )

        assert risk_level == "medium"
        assert any("filesystem paths" in r for r in reasons)

    def test_assess_tool_risk_high_tool_name(self):
        """Test risk assessment for high-risk tool names."""
        settings = McpSettings(high_risk_keywords=["delete", "remove", "destroy"])
        validator = McpSecurityValidator(settings)

        risk_level, reasons = validator.assess_tool_risk(
            tool_name="delete_file",
            tool_input={"path": "/data/file.txt"},
        )

        assert risk_level == "high"
        assert any("high-risk keyword" in r for r in reasons)

    def test_assess_tool_risk_high_shell_command(self):
        """Test risk assessment for shell command execution."""
        validator = McpSecurityValidator()

        # Test with tool input containing shell command key
        risk_level, reasons = validator.assess_tool_risk(
            tool_name="run_tool",  # Not in high-risk keywords
            tool_input={"command": "rm -rf /"},  # "command" key triggers high risk
        )

        assert risk_level == "high"
        assert any("shell" in r.lower() for r in reasons)

    def test_assess_tool_risk_high_destructive_sql(self):
        """Test risk assessment for destructive SQL operations."""
        validator = McpSecurityValidator()

        risk_level, reasons = validator.assess_tool_risk(
            tool_name="run_query",
            tool_input={"query": " drop table users "},  # Spaces required for matching
        )

        assert risk_level == "high"
        assert any("SQL" in r or "sql" in r.lower() for r in reasons)

    def test_assess_tool_risk_medium_safe_sql(self):
        """Test risk assessment for safe SQL operations."""
        validator = McpSecurityValidator()

        risk_level, reasons = validator.assess_tool_risk(
            tool_name="query_data",
            tool_input={
                "query": " select * from users where id = 1 "
            },  # Spaces required for matching
        )

        assert risk_level == "medium"
        assert any("SQL" in r or "sql" in r.lower() for r in reasons)


class TestCredentialEncryption:
    """Test credential encryption and decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test encryption and decryption roundtrip."""
        # Generate a valid Fernet key
        from cryptography.fernet import Fernet

        valid_key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=valid_key)
        encryptor = CredentialEncryption(settings)

        credentials = {"api_key": "secret123", "token": "bearer-token"}

        encrypted = encryptor.encrypt(credentials)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == credentials

    def test_encrypt_different_keys_fail(self):
        """Test that different keys produce different ciphertexts."""
        from cryptography.fernet import Fernet

        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        settings1 = McpSettings(encryption_key=key1)
        settings2 = McpSettings(encryption_key=key2)

        encryptor1 = CredentialEncryption(settings1)
        encryptor2 = CredentialEncryption(settings2)

        credentials = {"api_key": "secret123"}

        encrypted = encryptor1.encrypt(credentials)

        # Different key should fail to decrypt
        with pytest.raises(ValueError, match="Failed to decrypt credentials"):
            encryptor2.decrypt(encrypted)

    def test_encrypt_empty_credentials_fails(self):
        """Test that empty credentials fail validation."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)
        encryptor = CredentialEncryption(settings)

        with pytest.raises(ValueError, match="Credentials cannot be empty"):
            encryptor.encrypt({})

    def test_decrypt_empty_string_fails(self):
        """Test that empty encrypted string fails validation."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)
        encryptor = CredentialEncryption(settings)

        with pytest.raises(ValueError, match="Encrypted credentials cannot be empty"):
            encryptor.decrypt("")

    def test_decrypt_invalid_format_fails(self):
        """Test that invalid encrypted format fails."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)
        encryptor = CredentialEncryption(settings)

        with pytest.raises(ValueError, match="Failed to decrypt credentials"):
            encryptor.decrypt("not-a-valid-encrypted-string")

    def test_generate_key(self):
        """Test key generation produces valid Fernet keys."""
        from cryptography.fernet import Fernet

        key = CredentialEncryption.generate_key()

        # Should be able to create Fernet instance with generated key
        Fernet(key.encode())

        # Should be base64 encoded
        assert isinstance(key, str)
        assert len(key) > 0

    def test_encryption_produces_different_outputs(self):
        """Test that encrypting same data twice produces different ciphertexts."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)
        encryptor = CredentialEncryption(settings)

        credentials = {"api_key": "secret123"}

        encrypted1 = encryptor.encrypt(credentials)
        encrypted2 = encryptor.encrypt(credentials)

        # Different ciphertexts due to random IV
        assert encrypted1 != encrypted2

        # But both decrypt to same value
        assert encryptor.decrypt(encrypted1) == credentials
        assert encryptor.decrypt(encrypted2) == credentials

    def test_default_settings_generates_key(self):
        """Test that missing encryption key generates a new one."""
        settings = McpSettings(encryption_key="")
        encryptor = CredentialEncryption(settings)

        credentials = {"api_key": "test"}

        # Should work even without explicit key (generates one)
        encrypted = encryptor.encrypt(credentials)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == credentials


class TestBuildMcpAuthHeaders:
    """Tests for build_mcp_auth_headers function."""

    from unittest.mock import MagicMock

    from bsai.mcp.security import build_mcp_auth_headers

    def _create_mock_server(self, **kwargs):
        """Create mock MCP server config."""
        from unittest.mock import MagicMock

        server = MagicMock()
        server.name = kwargs.get("name", "test-server")
        server.auth_type = kwargs.get("auth_type", "none")
        server.auth_credentials = kwargs.get("auth_credentials")
        return server

    def test_no_credentials_returns_none(self):
        """Test returns None when no credentials."""
        from bsai.mcp.security import build_mcp_auth_headers

        server = self._create_mock_server(auth_credentials=None)
        result = build_mcp_auth_headers(server)
        assert result is None

    def test_auth_type_none_returns_none(self):
        """Test returns None when auth type is 'none'."""
        from bsai.mcp.security import build_mcp_auth_headers

        server = self._create_mock_server(auth_type="none", auth_credentials="encrypted")
        result = build_mcp_auth_headers(server)
        assert result is None

    def test_no_auth_type_returns_none(self):
        """Test returns None when auth type is not set."""
        from bsai.mcp.security import build_mcp_auth_headers

        server = self._create_mock_server(auth_type=None, auth_credentials="encrypted")
        result = build_mcp_auth_headers(server)
        assert result is None

    def test_bearer_auth_builds_headers(self):
        """Test bearer token authentication builds headers."""
        from cryptography.fernet import Fernet

        from bsai.mcp.security import CredentialEncryption, build_mcp_auth_headers

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)
        encryptor = CredentialEncryption(settings)
        encrypted = encryptor.encrypt({"token": "my-bearer-token"})

        server = self._create_mock_server(auth_type="bearer", auth_credentials=encrypted)

        result = build_mcp_auth_headers(server, settings=settings)
        assert result == {"Authorization": "Bearer my-bearer-token"}

    def test_api_key_auth_builds_headers(self):
        """Test API key authentication builds headers."""
        from cryptography.fernet import Fernet

        from bsai.mcp.security import CredentialEncryption, build_mcp_auth_headers

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)
        encryptor = CredentialEncryption(settings)
        encrypted = encryptor.encrypt({"api_key": "my-api-key", "header_name": "X-Custom-Key"})

        server = self._create_mock_server(auth_type="api_key", auth_credentials=encrypted)

        result = build_mcp_auth_headers(server, settings=settings)
        assert result == {"X-Custom-Key": "my-api-key"}

    def test_api_key_auth_default_header_name(self):
        """Test API key uses default header name."""
        from cryptography.fernet import Fernet

        from bsai.mcp.security import CredentialEncryption, build_mcp_auth_headers

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)
        encryptor = CredentialEncryption(settings)
        encrypted = encryptor.encrypt({"api_key": "my-api-key"})

        server = self._create_mock_server(auth_type="api_key", auth_credentials=encrypted)

        result = build_mcp_auth_headers(server, settings=settings)
        assert result == {"X-API-Key": "my-api-key"}

    def test_oauth2_auth_builds_headers(self):
        """Test OAuth2 authentication builds headers."""
        from cryptography.fernet import Fernet

        from bsai.mcp.security import CredentialEncryption, build_mcp_auth_headers

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)
        encryptor = CredentialEncryption(settings)
        encrypted = encryptor.encrypt({"access_token": "oauth-token"})

        server = self._create_mock_server(auth_type="oauth2", auth_credentials=encrypted)

        result = build_mcp_auth_headers(server, settings=settings)
        assert result == {"Authorization": "Bearer oauth-token"}

    def test_decryption_failure_returns_none(self):
        """Test returns None when decryption fails."""
        from cryptography.fernet import Fernet

        from bsai.mcp.security import build_mcp_auth_headers

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)

        server = self._create_mock_server(auth_type="bearer", auth_credentials="invalid-encrypted")
        result = build_mcp_auth_headers(server, settings=settings)
        assert result is None

    def test_empty_token_returns_none(self):
        """Test returns None when token is empty."""
        from cryptography.fernet import Fernet

        from bsai.mcp.security import CredentialEncryption, build_mcp_auth_headers

        key = Fernet.generate_key().decode()
        settings = McpSettings(encryption_key=key)
        encryptor = CredentialEncryption(settings)
        encrypted = encryptor.encrypt({"token": ""})

        server = self._create_mock_server(auth_type="bearer", auth_credentials=encrypted)

        result = build_mcp_auth_headers(server, settings=settings)
        assert result is None
