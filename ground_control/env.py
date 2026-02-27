"""Environment configuration loader."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_environment(workspace_dir: str | Path | None = None) -> None:
    """Load environment variables from .env file.
    
    Searches for .env in:
    1. The specified workspace_dir
    2. Current working directory
    3. Ground control package directory
    """
    search_paths = []
    
    if workspace_dir:
        search_paths.append(Path(workspace_dir) / ".env")
    
    search_paths.append(Path.cwd() / ".env")
    
    # Also check the ground-control installation directory
    package_dir = Path(__file__).parent.parent
    search_paths.append(package_dir / ".env")
    
    for env_path in search_paths:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            return
    
    # If no .env found, that's okay - environment variables might be set externally


def get_api_key(provider: str) -> str | None:
    """Get API key for a specific provider.
    
    Args:
        provider: Provider name ('anthropic', 'openai')
    
    Returns:
        API key or None if not set
    """
    key_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    
    env_var = key_map.get(provider.lower())
    if not env_var:
        return None
    
    return os.getenv(env_var)


def check_required_keys(providers: list[str]) -> dict[str, bool]:
    """Check if required API keys are set.
    
    Args:
        providers: List of provider names to check
    
    Returns:
        Dict mapping provider name to whether key is set
    """
    return {
        provider: bool(get_api_key(provider))
        for provider in providers
    }
