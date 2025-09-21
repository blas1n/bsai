"""Secret management abstraction layer with 1Password SDK"""
from typing import Optional
import os


try:
    from onepassword import Client, new_default_client
    ONEPASSWORD_AVAILABLE = True
except ImportError:
    ONEPASSWORD_AVAILABLE = False

from .settings import settings


class SecretProvider:
    """Abstract secret provider"""
    
    def get_secret(self, key: str) -> Optional[str]:
        """Get secret value"""
        raise NotImplementedError


class EnvironmentSecretProvider(SecretProvider):
    """Get secrets from environment variables"""
    
    def get_secret(self, key: str) -> Optional[str]:
        return os.getenv(key)


class OnePasswordSecretProvider(SecretProvider):
    """Get secrets from 1Password SDK"""
    
    def __init__(self):
        self._client = None
        self.available = self._check_availability()
    
    @property 
    def client(self) -> Optional[Client]:
        """Lazy client initialization"""
        if not ONEPASSWORD_AVAILABLE or not self.available:
            return None
            
        if self._client is None:
            try:
                service_account_token = os.getenv("OP_SERVICE_ACCOUNT_TOKEN")
                if service_account_token:
                    self._client = Client.authenticate(
                        auth=service_account_token,
                        integration_name="BSAI",
                        integration_version="0.1.0"
                    )
                else:
                    self._client = new_default_client()
            except Exception:
                self.available = False
                return None
        
        return self._client
    
    def _check_availability(self) -> bool:
        """Check if 1Password SDK is available"""
        if not ONEPASSWORD_AVAILABLE:
            return False
        
        try:
            # Try to create a client to test availability
            client = self.client
            if client is None:
                return False
            
            # Test with a simple operation
            vaults = client.vaults.list_all()
            return True
        except Exception:
            return False
    
    def get_secret(self, key: str) -> Optional[str]:
        """Get secret from 1Password"""
        if not self.available:
            return None
        
        # Map environment variable names to 1Password items
        op_mapping = {
            "ANTHROPIC_API_KEY": ("BSAI Secrets", "Claude API Key"),
            "SECRET_KEY": ("BSAI Secrets", "Application Secret"),
            "JWT_SECRET_KEY": ("BSAI Secrets", "JWT Secret"),
        }
        
        if key not in op_mapping:
            return None
        
        vault_name, item_title = op_mapping[key]
        
        try:
            client = self.client
            if not client:
                return None
            
            # Find vault
            vaults = client.vaults.list_all()
            vault = next((v for v in vaults if v.name == vault_name), None)
            if not vault:
                return None
            
            # Find item
            items = client.items.list_all(vault.id)
            item = next((i for i in items if i.title == item_title), None)
            if not item:
                return None
            
            # Get item details
            full_item = client.items.get(vault.id, item.id)
            
            # Extract secret value
            if full_item.fields and len(full_item.fields) > 0:
                return full_item.fields[0].value
            
            return None
            
        except Exception:
            return None


class SecretManager:
    """Unified secret management with multiple providers"""
    
    def __init__(self):
        self.providers = [
            EnvironmentSecretProvider(),
            OnePasswordSecretProvider(),
        ]
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get secret from available providers"""
        for provider in self.providers:
            try:
                value = provider.get_secret(key)
                if value:
                    return value
            except Exception:
                continue
        return default
    
    def is_1password_available(self) -> bool:
        """Check if 1Password provider is available"""
        for provider in self.providers:
            if isinstance(provider, OnePasswordSecretProvider):
                return provider.available
        return False


# Global secret manager
secret_manager = SecretManager()