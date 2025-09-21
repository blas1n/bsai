#!/usr/bin/env python3
"""
BSAI Secret Management System
Uses 1Password Python SDK for clean secret management
"""

import base64
import os
import secrets as crypto_secrets
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

# TYPE_CHECKING을 사용하여 타입 힌트만을 위한 import
if TYPE_CHECKING:
    from onepassword import Client

try:
    from onepassword import Client, new_default_client
    ONEPASSWORD_AVAILABLE = True
except ImportError:
    ONEPASSWORD_AVAILABLE = False
    # TYPE_CHECKING이 아닐 때는 더미 클래스 생성
    Client = None


class SecretManager:
    """Automated secret management with 1Password SDK integration"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.env_file = self.project_root / ".env"
        self._op_client = None

    @property
    def op_client(self) -> Optional["Client"]:  # 문자열로 타입 힌트
        """Lazy 1Password client initialization"""
        if not ONEPASSWORD_AVAILABLE:
            return None

        if self._op_client is None:
            try:
                # Use service account token from environment
                service_account_token = os.getenv("OP_SERVICE_ACCOUNT_TOKEN")
                if service_account_token:
                    self._op_client = Client.authenticate(
                        auth=service_account_token,
                        integration_name="BSAI",
                        integration_version="0.1.0"
                    )
                else:
                    # Try default client (requires op CLI signin)
                    self._op_client = new_default_client()
            except Exception as e:
                print(f"1Password client initialization failed: {e}")
                return None

        return self._op_client

    def init(self):
        """Initialize secret management system automatically"""
        print("Secret management system initializing...")

        env_type = self._detect_environment()
        print(f"Environment detected: {env_type}")

        if env_type == "codespaces":
            self._setup_codespaces()
        elif env_type == "local":
            self._setup_local()
        elif env_type == "ci":
            self._setup_ci()
        else:
            self._setup_demo()

    def _detect_environment(self) -> str:
        """Auto-detect current environment"""
        if os.getenv("CODESPACES"):
            return "codespaces"
        elif os.getenv("CI"):
            return "ci"
        elif os.path.exists("/workspace") and not os.getenv("CI"):
            return "local"
        else:
            return "demo"

    def _setup_codespaces(self):
        """GitHub Codespaces environment setup"""
        print("GitHub Codespaces environment detected")

        secrets = {
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
            "SECRET_KEY": os.getenv("SECRET_KEY") or self._generate_secret_key(),
            "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY") or self._generate_secret_key(),
        }

        self._create_env_file(secrets)

    def _setup_local(self):
        """Local development environment setup"""
        print("Local development environment detected")

        if self._check_1password():
            print("1Password SDK available, using for secret management")
            self._setup_1password()
        else:
            print("1Password SDK not available, using demo mode")
            self._setup_demo()

    def _setup_ci(self):
        """CI/CD environment setup"""
        print("CI/CD environment detected")

        secrets = {
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
            "SECRET_KEY": os.getenv("SECRET_KEY"),
            "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY"),
        }

        missing = [k for k, v in secrets.items() if not v]
        if missing:
            print(f"Missing required secrets: {missing}")
            sys.exit(1)

        self._create_env_file(secrets)

    def _setup_demo(self):
        """Demo/safe mode setup (no real API calls)"""
        print("Demo mode setup - safe for development without real API keys")

        secrets = {
            "ANTHROPIC_API_KEY": "demo_key_safe_mode",
            "SECRET_KEY": self._generate_secret_key(),
            "JWT_SECRET_KEY": self._generate_secret_key(),
            "BSAI_MODE": "demo",
        }

        self._create_env_file(secrets)

    def _check_1password(self) -> bool:
        """Check if 1Password SDK is available and working"""
        try:
            client = self.op_client
            if client is None:
                return False

            # Test with a simple operation
            vaults = client.vaults.list_all()
            return True
        except Exception:
            return False

    def _setup_1password(self):
        """Setup using 1Password SDK"""
        try:
            client = self.op_client
            if not client:
                raise Exception("1Password client not available")

            # Define our secret mapping
            secret_mapping = {
                "ANTHROPIC_API_KEY": ("BSAI Secrets", "Claude API Key"),
                "SECRET_KEY": ("BSAI Secrets", "Application Secret"),
                "JWT_SECRET_KEY": ("BSAI Secrets", "JWT Secret"),
            }

            secrets = {}
            for env_var, (vault_name, item_title) in secret_mapping.items():
                try:
                    value = self._get_from_1password(vault_name, item_title)
                    secrets[env_var] = value or self._generate_fallback_secret(
                        env_var)
                except Exception as e:
                    print(f"Failed to get {env_var} from 1Password: {e}")
                    secrets[env_var] = self._generate_fallback_secret(env_var)

            self._create_env_file(secrets)

        except Exception as e:
            print(f"1Password SDK integration failed: {e}")
            self._setup_demo()

    def _get_from_1password(self, vault_name: str, item_title: str) -> str | None:
        """Get secret from 1Password using SDK"""
        client = self.op_client
        if not client:
            return None

        try:
            # Find the vault
            vaults = client.vaults.list_all()
            vault = next((v for v in vaults if v.name == vault_name), None)
            if not vault:
                print(f"Vault '{vault_name}' not found")
                return None

            # Find the item
            items = client.items.list_all(vault.id)
            item = next((i for i in items if i.title == item_title), None)
            if not item:
                print(f"Item '{item_title}' not found in vault '{vault_name}'")
                return None

            # Get the item details
            full_item = client.items.get(vault.id, item.id)

            # Extract the secret value (usually in the first field)
            if full_item.fields and len(full_item.fields) > 0:
                return full_item.fields[0].value

            return None

        except Exception as e:
            print(f"Error retrieving secret from 1Password: {e}")
            return None

    def _generate_fallback_secret(self, env_var: str) -> str:
        """Generate appropriate fallback for each secret type"""
        if env_var == "ANTHROPIC_API_KEY":
            return "demo_key_1password_not_found"
        else:
            return self._generate_secret_key()

    def _generate_secret_key(self) -> str:
        """Generate secure secret key"""
        return base64.b64encode(crypto_secrets.token_bytes(32)).decode()

    def _create_env_file(self, secrets: dict[str, Any]) -> None:
        """Create environment file with secrets"""
        env_content = [
            "# BSAI Environment Configuration (Auto-generated)",
            "ENVIRONMENT=development",
            "LOG_LEVEL=DEBUG",
            "",
        ]

        for key, value in secrets.items():
            if value:
                env_content.append(f"{key}={value}")

        env_content.extend([
            "",
            "# Features",
            "ENABLE_WEB_UI=true",
            "ENABLE_MONITORING=false",
        ])

        with open(self.env_file, "w") as f:
            f.write("\n".join(env_content))

        print(f"Environment file created: {self.env_file}")

    def create_1password_items(self):
        """Helper method to create initial 1Password items"""
        client = self.op_client
        if not client:
            print("1Password client not available")
            return

        try:
            # Find or create vault
            vaults = client.vaults.list_all()
            vault = next((v for v in vaults if v.name == "BSAI Secrets"), None)

            if not vault:
                print("Please create a vault named 'BSAI Secrets' in 1Password first")
                return

            # Items to create
            items_to_create = [
                {
                    "title": "Claude API Key",
                    "category": "API_CREDENTIAL",
                    "fields": [
                        {"label": "API Key", "type": "CONCEALED",
                            "value": "your_claude_api_key_here"}
                    ]
                },
                {
                    "title": "Application Secret",
                    "category": "PASSWORD",
                    "fields": [
                        {"label": "Secret", "type": "CONCEALED",
                            "value": self._generate_secret_key()}
                    ]
                },
                {
                    "title": "JWT Secret",
                    "category": "PASSWORD",
                    "fields": [
                        {"label": "Secret", "type": "CONCEALED",
                            "value": self._generate_secret_key()}
                    ]
                }
            ]

            for item_data in items_to_create:
                # Check if item already exists
                existing_items = client.items.list_all(vault.id)
                if any(item.title == item_data["title"] for item in existing_items):
                    print(f"Item '{item_data['title']}' already exists")
                    continue

                print(f"Creating 1Password item: {item_data['title']}")
                # Note: Actual item creation would require the full 1Password SDK
                # This is a placeholder for the creation logic

        except Exception as e:
            print(f"Error creating 1Password items: {e}")


def main():
    """CLI entry point"""
    manager = SecretManager()

    if len(sys.argv) < 2:
        manager.init()
        return

    command = sys.argv[1]

    if command == "init":
        manager.init()
    elif command == "setup":
        manager._setup_demo()
    elif command == "sync":
        manager._setup_1password()
    elif command == "create-items":
        manager.create_1password_items()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: init, setup, sync, create-items")
        sys.exit(1)


if __name__ == "__main__":
    main()
