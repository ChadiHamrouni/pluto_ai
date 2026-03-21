import json
import os

_config = None

# Environment variable overrides for secrets (never commit these to config.json)
_ENV_OVERRIDES = {
    ("auth", "secret_key"):     "AUTH_SECRET_KEY",
    ("auth", "password_hash"):  "AUTH_PASSWORD_HASH",
    ("auth", "username"):       "AUTH_USERNAME",
    ("ollama", "base_url"):     "OLLAMA_BASE_URL",
}


def _apply_env_overrides(config: dict) -> dict:
    """Override config values with environment variables when set."""
    for (section, key), env_var in _ENV_OVERRIDES.items():
        value = os.environ.get(env_var)
        if value is not None:
            config.setdefault(section, {})[key] = value
    return config


def load_config(path: str = "config.json") -> dict:
    """Load configuration from JSON file. Caches result after first load.

    Secrets can be overridden via environment variables:
        AUTH_SECRET_KEY, AUTH_PASSWORD_HASH, AUTH_USERNAME, OLLAMA_BASE_URL
    """
    global _config
    if _config is None:
        # Support both absolute paths and paths relative to project root
        if not os.path.isabs(path):
            # Try relative to the directory of this file (helpers/ -> project root)
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            resolved = os.path.join(base_dir, path)
            if os.path.exists(resolved):
                path = resolved
        with open(path) as f:
            _config = json.load(f)
        _apply_env_overrides(_config)
    return _config


def reload_config(path: str = "config.json") -> dict:
    """Force reload of config from disk, bypassing the cache."""
    global _config
    _config = None
    return load_config(path)
