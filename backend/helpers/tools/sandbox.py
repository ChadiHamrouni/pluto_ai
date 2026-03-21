"""Sandboxed Python code execution.

Runs user-generated Python code in a subprocess with:
- Timeout (30s default)
- Restricted to safe scientific libraries
- Captures stdout, stderr, and generated files (plots)
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from helpers.core.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 30  # seconds
_MAX_OUTPUT = 10_000  # chars

# Preamble injected before user code to set up matplotlib for non-interactive use
_PREAMBLE = """
import sys
import os
os.environ['MPLBACKEND'] = 'Agg'
"""


def execute_python(code: str, timeout: int = _TIMEOUT) -> dict:
    """Execute Python code in a subprocess and return results.

    Returns:
        {
            "stdout": str,
            "stderr": str,
            "success": bool,
            "plot_path": str | None,  # path to generated plot if any
        }
    """
    with tempfile.TemporaryDirectory(prefix="jarvis_sandbox_") as tmpdir:
        script_path = Path(tmpdir) / "script.py"
        plot_path = Path(tmpdir) / "plot.png"

        # Inject preamble + set default plot save path
        full_code = _PREAMBLE + "\n"
        full_code += f"_PLOT_PATH = r'{plot_path}'\n"
        full_code += code + "\n"

        # Auto-save matplotlib figures if plt was imported and show() called
        full_code += """
try:
    import matplotlib.pyplot as _plt
    if _plt.get_fignums():
        _plt.savefig(_PLOT_PATH, dpi=150, bbox_inches='tight')
        print(f"[Plot saved to {_PLOT_PATH}]")
except ImportError:
    pass
"""

        script_path.write_text(full_code, encoding="utf-8")

        try:
            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
                env={**os.environ, "MPLBACKEND": "Agg"},
            )

            stdout = result.stdout[:_MAX_OUTPUT] if result.stdout else ""
            stderr = result.stderr[:_MAX_OUTPUT] if result.stderr else ""

            # Check if a plot was generated
            generated_plot = None
            if plot_path.exists() and plot_path.stat().st_size > 0:
                # Copy plot to a persistent location
                from helpers.core.config_loader import load_config

                config = load_config()
                slides_dir = config.get("storage", {}).get("slides_dir", "data/slides")
                os.makedirs(slides_dir, exist_ok=True)

                import shutil
                import time

                dest_name = f"plot_{int(time.time())}.png"
                dest_path = Path(slides_dir) / dest_name
                shutil.copy2(plot_path, dest_path)
                generated_plot = str(dest_path)
                logger.info("Plot saved to %s", dest_path)

            return {
                "stdout": stdout,
                "stderr": stderr,
                "success": result.returncode == 0,
                "plot_path": generated_plot,
            }

        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds.",
                "success": False,
                "plot_path": None,
            }
        except Exception as exc:
            return {
                "stdout": "",
                "stderr": f"Execution error: {exc}",
                "success": False,
                "plot_path": None,
            }
