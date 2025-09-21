# Secret Management Guide

## Automatic Setup

BSAI automatically detects your environment and configures secrets appropriately:

- **Demo Mode**: Safe default values for testing without real API keys
- **Local Development**: 1Password CLI integration (if available)
- **GitHub Codespaces**: Uses Codespaces secrets
- **CI/CD**: Uses environment variables

## Manual Setup (if needed)

### Local Development

1. Copy `.env.example` to `.env`
2. Add your actual API keys
3. The file is automatically ignored by git

### GitHub Codespaces

1. Go to your repository settings
2. Navigate to Codespaces
3. Add secrets: `ANTHROPIC_API_KEY`, `SECRET_KEY`

### 1Password CLI (Optional)
```bash
# Install 1Password CLI
# https://developer.1password.com/docs/cli/get-started/

# Sign in
op signin

# Create items (one-time setup)
op item create --category "API Credential" --title "BSAI-Claude-API" --field label="API Key",type=concealed,value="your_key_here"