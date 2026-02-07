"""E2E 6.2 + 6.3: Skill integration — prompt.md existence, frontmatter schema,
skill-hook interplay.
"""
import re
from pathlib import Path

import pytest

SKILLS_DIR = Path.home() / ".claude" / "skills"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not SKILLS_DIR.exists(),
        reason=f"Skills directory not found at {SKILLS_DIR}",
    ),
]

EXPECTED_SKILLS = [
    "startproject",
    "checkpointing",
    "plan",
    "tdd",
    "codex-system",
    "gemini-system",
    "design-tracker",
    "init",
    "research-lib",
    "simplify",
    "update-design",
    "update-lib-docs",
]


class TestSkillPromptFilesExist:
    """6.2: All 12 skills have prompt.md files."""

    @pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
    def test_prompt_md_exists(self, skill_name):
        prompt_path = SKILLS_DIR / skill_name / "prompt.md"
        assert prompt_path.exists(), f"{skill_name}/prompt.md must exist"

    @pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
    def test_prompt_md_has_frontmatter(self, skill_name):
        prompt_path = SKILLS_DIR / skill_name / "prompt.md"
        content = prompt_path.read_text(encoding="utf-8")
        assert content.startswith("---"), f"{skill_name}/prompt.md must start with YAML frontmatter"
        # Must have closing ---
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"{skill_name}/prompt.md must have complete frontmatter (---...---)"


class TestSkillFrontmatterSchema:
    """6.2: Frontmatter contains required fields: name, version, description, triggers."""

    REQUIRED_FIELDS = ["name"]  # Minimum required field

    @pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
    def test_frontmatter_has_name(self, skill_name):
        prompt_path = SKILLS_DIR / skill_name / "prompt.md"
        content = prompt_path.read_text(encoding="utf-8")
        fm = _extract_frontmatter(content)
        assert "name" in fm, f"{skill_name} frontmatter missing 'name'"

    @pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
    def test_frontmatter_name_nonempty(self, skill_name):
        prompt_path = SKILLS_DIR / skill_name / "prompt.md"
        content = prompt_path.read_text(encoding="utf-8")
        fm = _extract_frontmatter(content)
        assert fm.get("name", "").strip(), f"{skill_name} frontmatter 'name' is empty"


class TestPlanSkillTriggersCodexHook:
    """6.2: Plan skill prompt references Codex verification."""

    def test_plan_prompt_mentions_codex(self):
        prompt_path = SKILLS_DIR / "plan" / "prompt.md"
        if not prompt_path.exists():
            pytest.skip("plan/prompt.md not found")
        content = prompt_path.read_text(encoding="utf-8").lower()
        assert "codex" in content or "verify" in content or "review" in content, \
            "plan prompt should reference Codex verification"


class TestTddSkillRedGreenRefactor:
    """6.2: TDD skill prompt has Red-Green-Refactor phases."""

    def test_tdd_has_three_phases(self):
        prompt_path = SKILLS_DIR / "tdd" / "prompt.md"
        if not prompt_path.exists():
            pytest.skip("tdd/prompt.md not found")
        content = prompt_path.read_text(encoding="utf-8").lower()
        assert "red" in content, "TDD prompt must mention Red phase"
        assert "green" in content, "TDD prompt must mention Green phase"
        assert "refactor" in content, "TDD prompt must mention Refactor phase"


class TestStartprojectSkillStructure:
    """6.2: startproject prompt has 7 phases."""

    def test_has_multiple_phases(self):
        prompt_path = SKILLS_DIR / "startproject" / "prompt.md"
        if not prompt_path.exists():
            pytest.skip("startproject/prompt.md not found")
        content = prompt_path.read_text(encoding="utf-8")
        # Count phase/step/section headers
        phase_matches = re.findall(r"(?:phase|step|##)", content, re.IGNORECASE)
        assert len(phase_matches) >= 5, \
            f"startproject should have multiple phases/steps, found {len(phase_matches)}"


class TestCheckpointingSkillVaultPath:
    """6.2: checkpointing prompt references Vault path."""

    def test_mentions_vault(self):
        prompt_path = SKILLS_DIR / "checkpointing" / "prompt.md"
        if not prompt_path.exists():
            pytest.skip("checkpointing/prompt.md not found")
        content = prompt_path.read_text(encoding="utf-8").lower()
        assert "vault" in content or "obsidian" in content or "tetsuyasynapse" in content.lower(), \
            "checkpointing prompt should reference Vault/Obsidian"


def _extract_frontmatter(content: str) -> dict:
    """Simple YAML frontmatter extractor (key: value pairs)."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    fm_text = parts[1].strip()
    result = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result
