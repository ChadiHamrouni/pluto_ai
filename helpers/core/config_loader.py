import json
import os

_config = None


def load_config(path: str = "config.json") -> dict:
    """Load configuration from JSON file. Caches result after first load."""
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
    return _config


def reload_config(path: str = "config.json") -> dict:
    """Force reload of config from disk, bypassing the cache."""
    global _config
    _config = None
    return load_config(path)
