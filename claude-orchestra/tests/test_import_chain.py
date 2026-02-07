"""Test 5.2: Import chain verification for all lib modules."""
import importlib
import sys

import pytest


MODULE_NAMES = [
    "path_utils",
    "output_schemas",
    "resilience",
    "cli_finder",
    "context_guard",
    "budget",
    "env_check",
    "codex_wrapper",
    "gemini_wrapper",
    "vault_sync",
    "bootstrap",
]


class TestImportChain:
    """Verify all library modules can be imported."""

    @pytest.mark.parametrize("module_name", MODULE_NAMES)
    def test_module_imports(self, module_name):
        mod = importlib.import_module(module_name)
        assert mod is not None

    def test_init_reexports(self):
        """__init__.py declares all expected module names in __all__."""
        # __init__.py uses relative imports so can't be loaded as standalone.
        # Instead, read and verify __all__ list is complete.
        from pathlib import Path
        init_path = Path.home() / ".claude" / "lib" / "__init__.py"
        content = init_path.read_text(encoding="utf-8")
        expected = [
            "bootstrap", "codex_wrapper", "gemini_wrapper", "vault_sync",
            "path_utils", "context_guard", "resilience", "output_schemas",
            "env_check", "budget", "cli_finder",
        ]
        for name in expected:
            assert f'"{name}"' in content, f"Missing in __all__: {name}"

    def test_no_circular_imports(self):
        """Ensure importing all modules together doesn't crash."""
        for name in MODULE_NAMES:
            if name in sys.modules:
                del sys.modules[name]
        for name in MODULE_NAMES:
            importlib.import_module(name)
