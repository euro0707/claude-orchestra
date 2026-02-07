"""
Orchestra library for Claude Code.

Provides shared utilities for multi-agent coordination (Claude Code, Codex, Gemini).
"""

__version__ = "1.0.0"

# Re-export main modules for convenience
from . import bootstrap
from . import codex_wrapper
from . import gemini_wrapper
from . import vault_sync
from . import path_utils
from . import context_guard
from . import resilience
from . import output_schemas
from . import env_check
from . import budget
from . import cli_finder

__all__ = [
    "bootstrap",
    "codex_wrapper",
    "gemini_wrapper",
    "vault_sync",
    "path_utils",
    "context_guard",
    "resilience",
    "output_schemas",
    "env_check",
    "budget",
    "cli_finder",
]
