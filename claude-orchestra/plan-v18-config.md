# Plan v18: Configuration Files (Rules, Skills, Agents, Verification)

**Status**: Draft
**Created**: 2026-02-06
**Dependencies**: plan-v18-lib.md, plan-v18-hooks.md

---

## Overview

This document defines all configuration files for Claude Orchestra v18:
- **Section 1**: Rules (7 files in `~/.claude/rules/`)
- **Section 2**: Skills (12 directories in `~/.claude/skills/`)
- **Section 3**: Agent (1 file in `~/.claude/agents/`)
- **Section 4**: Verification Plan
- **Section 5**: Implementation Order

---

## Section 1: Rules (7 files in ~/.claude/rules/)

### 1.1 codex-delegation.md

```markdown
---
id: "codex-delegation"
domain: "delegation"
title: "Codex CLI Delegation Rules"
created: "2026-02-06"
---

# Codex CLI Delegation Rules

## Purpose
Define when and how to delegate tasks to Codex CLI for plan verification, code review, and architectural analysis.

## When to Delegate to Codex

### Must Delegate
- **Plan verification**: Use `codex verify` mode before implementing complex plans
- **Code review**: Use `codex review` mode for completed implementations
- **Architecture review**: Use `codex architecture` mode for system design decisions

### Should Delegate
- When context is heavy (10+ files, 100+ lines of code changes)
- For second opinions on critical decisions
- When debugging complex integration issues
- For performance-critical code review

### May Delegate
- For exploration of alternative approaches
- When uncertain about design patterns
- For consistency checks across modules

## How to Delegate

### Command Format
```bash
# Verify mode (pre-implementation)
codex verify <plan-file>

# Review mode (post-implementation)
codex review <file-or-directory>

# Architecture mode
codex architecture <design-doc>

# Opinion mode
codex opinion --question "Should I use X or Y for Z?"

# Diff mode
codex diff <file1> <file2>
```

### Integration Pattern
1. **Pre-implementation**: Run `codex verify` on plan markdown
2. **Implementation**: Execute plan with Claude
3. **Post-implementation**: Run `codex review` on changed files
4. **Documentation**: Update docs with Codex feedback

### Response Handling
- **Codex approves**: Proceed with implementation
- **Codex suggests changes**: Revise plan and re-verify
- **Codex blocks**: Address issues before proceeding

## Codex Modes Reference

| Mode | Purpose | Input | Output |
|------|---------|-------|--------|
| verify | Pre-check plans | Markdown plan | Approval/concerns/confidence |
| review | Post-check code | Code files | Issues/suggestions/rating |
| architecture | System design | Design doc | Architecture feedback |
| opinion | Second opinion | Question | Recommendation |
| diff | Compare approaches | 2 files | Comparison analysis |

## Exceptions
- Do NOT delegate for trivial changes (<10 lines)
- Do NOT delegate for documentation-only changes
- Do NOT delegate when Codex is unavailable (fail gracefully)

## Related
- [[gemini-delegation.md]] - Gemini CLI delegation rules
- [[codex-system]] skill - Codex invocation wrapper
```

---

### 1.2 gemini-delegation.md

```markdown
---
id: "gemini-delegation"
domain: "delegation"
title: "Gemini CLI Delegation Rules"
created: "2026-02-06"
---

# Gemini CLI Delegation Rules

## Purpose
Define when and how to delegate research tasks to Gemini CLI for latest documentation, best practices, and technology comparisons.

## When to Use Gemini CLI

### Must Use
- **Latest documentation**: When user asks for "latest", "current", "2026" docs
- **Technology comparison**: "Should I use X or Y?", "What's better: A or B?"
- **Best practices**: "What's the best way to...", "How should I..."

### Should Use
- For framework/library version compatibility checks
- For security advisories and CVE lookups
- For API changes in recent releases
- For ecosystem trends and adoption data

### May Use
- For tutorial and guide discovery
- For community recommendations
- For performance benchmarks

## How to Use Gemini CLI

### Command Format
```bash
# Research latest documentation
gemini research "React 2026 documentation"

# Compare technologies
gemini compare "FastAPI vs Flask for async APIs"

# Best practices
gemini best-practices "Python async error handling"

# Security check
gemini security "lodash vulnerabilities 2026"
```

### Integration Pattern
1. **Detect research need**: User asks for latest/best/comparison
2. **Invoke Gemini**: Use `gemini research` or appropriate mode
3. **Synthesize response**: Combine Gemini findings with your analysis
4. **Cite sources**: Always include Gemini's sources in response

### Fallback Strategy
```
If Gemini CLI unavailable:
  1. Try WebSearch tool
  2. If WebSearch fails, use knowledge cutoff data with disclaimer
  3. Always inform user of fallback strategy used
```

## Gemini Modes Reference

| Mode | Purpose | Use Case |
|------|---------|----------|
| research | General research | Latest docs, guides, tutorials |
| compare | Technology comparison | Framework/library choices |
| best-practices | Best practices | Design patterns, conventions |
| security | Security research | CVEs, advisories, patches |

## Response Format

Always structure Gemini-assisted responses as:

```markdown
[Your analysis based on Gemini research]

**Sources** (via Gemini CLI):
- [Source 1 Title](URL)
- [Source 2 Title](URL)
```

## Exceptions
- Do NOT use Gemini for codebase-specific questions (use Codex instead)
- Do NOT use Gemini for user's private/proprietary information
- Do NOT use Gemini when offline or in air-gapped environments

## Related
- [[codex-delegation.md]] - Codex CLI delegation rules
- [[gemini-system]] skill - Gemini invocation wrapper
```

---

### 1.3 coding-principles.md

```markdown
---
id: "coding-principles"
domain: "coding"
title: "Coding Principles and Standards"
created: "2026-02-06"
---

# Coding Principles and Standards

## Core Principles

### KISS (Keep It Simple, Stupid)
- Prefer simple solutions over clever ones
- Avoid premature optimization
- Choose readability over brevity
- One function = one responsibility

**Example**:
```python
# Good: Simple and clear
def calculate_total(items: list[float]) -> float:
    return sum(items)

# Bad: Unnecessarily complex
def calculate_total(items: list[float]) -> float:
    return reduce(lambda x, y: x + y, items, 0)
```

### YAGNI (You Aren't Gonna Need It)
- Don't build features "just in case"
- Implement what's needed NOW
- Refactor when requirements change
- Delete unused code aggressively

**Red flags**:
- "We might need this later..."
- "Let's make it configurable just in case..."
- "This could be useful for..."

### DRY (Don't Repeat Yourself)
- Extract repeated logic into functions/classes
- Use configuration over duplication
- Centralize constants and magic numbers
- BUT: Don't abstract prematurely (Rule of Three)

**Rule of Three**: Abstract after third repetition, not first.

## Code Quality Standards

### Readability
- **Variable names**: Descriptive, not abbreviated
  - Good: `user_authentication_token`
  - Bad: `uat`, `tok`, `x`
- **Function names**: Verb-noun pairs
  - Good: `fetch_user_profile()`, `validate_email()`
  - Bad: `get()`, `check()`, `do_stuff()`
- **Line length**: Max 88 characters (Black standard)
- **Nesting**: Max 3 levels deep

### Type Hints (Python)
```python
# Always use type hints
def process_user(
    user_id: int,
    options: dict[str, Any] | None = None
) -> UserProfile:
    """Process user data and return profile."""
    ...
```

### Docstrings
```python
def complex_function(param1: str, param2: int) -> dict:
    """
    One-line summary of what function does.

    Detailed explanation if needed. Describe the "why",
    not just the "what" (code shows the what).

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When param1 is empty
        KeyError: When required key missing
    """
    ...
```

### Error Handling

**Do**:
```python
# Specific exceptions
try:
    data = json.loads(content)
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse JSON: {e}")
    raise ConfigError("Invalid JSON in config file") from e
```

**Don't**:
```python
# Bare except
try:
    data = json.loads(content)
except:  # Bad: Catches everything including KeyboardInterrupt
    pass  # Bad: Silent failure
```

### Function Size
- **Target**: 10-20 lines
- **Maximum**: 50 lines
- **If longer**: Extract helper functions

### File Organization
```python
# 1. Imports (stdlib, third-party, local)
from pathlib import Path
import json

from pydantic import BaseModel

from .config import load_config

# 2. Constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

# 3. Type aliases
UserId = int
Config = dict[str, Any]

# 4. Classes
class UserService:
    ...

# 5. Functions
def main():
    ...

# 6. Script entry point
if __name__ == "__main__":
    main()
```

## Anti-Patterns to Avoid

### Magic Numbers
```python
# Bad
if len(users) > 100:
    ...

# Good
MAX_USERS_PER_BATCH = 100
if len(users) > MAX_USERS_PER_BATCH:
    ...
```

### God Objects
- Classes with too many responsibilities
- Files with 1000+ lines
- Functions that do everything

### Premature Abstraction
- Wait until patterns emerge
- Three strikes rule: abstract on third occurrence
- Concrete before abstract

### Comment Overuse
```python
# Bad: Comment explains what code does
# Increment counter by one
counter += 1

# Good: Code is self-documenting
counter += 1

# Good: Comment explains WHY
# Use exponential backoff to avoid rate limiting
delay = 2 ** attempt
```

## Language-Specific Guidelines

### Python
- Follow PEP 8 (enforced by ruff)
- Use f-strings for formatting
- Prefer pathlib over os.path
- Use context managers for resources
- List comprehensions for simple loops

### JavaScript/TypeScript
- Use const by default, let when needed, never var
- Arrow functions for callbacks
- Async/await over raw promises
- Destructuring for object access

### Shell Scripts
- Use shellcheck
- Quote all variables: "$var"
- Use [[ ]] over [ ]
- set -euo pipefail

## Related
- [[testing.md]] - Testing standards
- [[dev-environment.md]] - Development setup
- [[security.md]] - Security guidelines
```

---

### 1.4 dev-environment.md

```markdown
---
id: "dev-environment"
domain: "development"
title: "Development Environment Standards"
created: "2026-02-06"
---

# Development Environment Standards

## Platform
- **OS**: Windows 11
- **Shell**: PowerShell 7+ (primary), Git Bash (secondary)
- **Python**: 3.13 (system installation)

## Python Environment

### Package Management
**Primary**: `uv` (Astral's fast package manager)
```powershell
# Install uv
pip install uv

# Create virtual environment
uv venv

# Install dependencies
uv pip install -r requirements.txt

# Add package
uv pip install <package>
```

**Fallback**: `pip` when uv unavailable

### Virtual Environments
```powershell
# Always use virtual environments
python -m venv .venv

# Activate (PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (Git Bash)
source .venv/Scripts/activate
```

**Never**:
- Install packages globally (except uv, pip, virtualenv)
- Commit `.venv/` to git

### Linting and Formatting
**ruff**: Fast Python linter and formatter (replaces flake8, black, isort)

```toml
# pyproject.toml
[tool.ruff]
line-length = 88
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]  # Line length handled by formatter

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

```powershell
# Check
ruff check .

# Format
ruff format .

# Fix auto-fixable issues
ruff check --fix .
```

### Type Checking
**pyright** or **mypy** (pyright preferred for speed)

```toml
# pyproject.toml
[tool.pyright]
pythonVersion = "3.13"
typeCheckingMode = "standard"
reportMissingTypeStubs = false
```

```powershell
# Check types
pyright

# Or with mypy
mypy src/
```

### Testing
**pytest**: Primary test framework

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = "-v --cov=src --cov-report=term-missing"
```

```powershell
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test
pytest tests/test_module.py::test_function
```

## Node.js Environment (for JavaScript/TypeScript)

### Version Management
```powershell
# Check version
node --version  # Should be 18+ or 20+

# Package manager
npm --version
```

### Project Setup
```powershell
# Initialize project
npm init -y

# Install dependencies
npm install

# Add dev dependency
npm install --save-dev <package>
```

### Linting and Formatting
```json
// package.json
{
  "scripts": {
    "lint": "eslint .",
    "format": "prettier --write ."
  },
  "devDependencies": {
    "eslint": "^8.0.0",
    "prettier": "^3.0.0"
  }
}
```

## Git Configuration

### User Config
```bash
git config --global user.name "Tetsuya"
git config --global user.email "your-email@example.com"
```

### Recommended Aliases
```bash
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.lg "log --oneline --graph --all"
```

### Line Endings (Windows)
```bash
# Auto-convert to LF in repo, CRLF in working tree
git config --global core.autocrlf true
```

## IDE / Editor

### VS Code (Recommended)
**Extensions**:
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Ruff (charliermarsh.ruff)
- GitLens (eamodio.gitlens)
- Error Lens (usernamehw.errorlens)

**Settings** (.vscode/settings.json):
```json
{
  "python.defaultInterpreterPath": ".venv/Scripts/python.exe",
  "editor.formatOnSave": true,
  "editor.rulers": [88],
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.codeActionsOnSave": {
      "source.organizeImports": "explicit"
    }
  },
  "python.testing.pytestEnabled": true
}
```

## Directory Structure (Standard Project)

```
project/
├── .venv/              # Virtual environment (not in git)
├── src/                # Source code
│   └── package/
│       ├── __init__.py
│       └── module.py
├── tests/              # Tests mirror src/
│   └── test_module.py
├── docs/               # Documentation
├── notes/              # Self-improvement loop files
│   ├── mistakes.md
│   ├── rules-local.md
│   └── metrics.md
├── .gitignore
├── pyproject.toml      # Project metadata + tool config
├── requirements.txt    # Dependencies (or use pyproject.toml)
├── README.md
└── LICENSE
```

## Environment Variables

### Loading .env Files
```python
# Use python-dotenv
from dotenv import load_dotenv
import os

load_dotenv()  # Loads .env from project root

API_KEY = os.getenv("API_KEY")
```

### .env.example Template
```bash
# API Keys
API_KEY=your_key_here
SECRET_TOKEN=your_secret_here

# Feature Flags
DEBUG=false
LOG_LEVEL=INFO
```

**Always**:
- Commit `.env.example` (with dummy values)
- Add `.env` to `.gitignore`
- Never commit secrets

## Related
- [[coding-principles.md]] - Coding standards
- [[testing.md]] - Testing guidelines
- [[security.md]] - Security practices
```

---

### Summary: Section 1 Complete

All 7 rules files are now defined:
1. ✅ codex-delegation.md - When/how to delegate to Codex CLI
2. ✅ gemini-delegation.md - When/how to use Gemini CLI for research
3. ✅ coding-principles.md - KISS, YAGNI, DRY, code quality standards
4. ✅ dev-environment.md - Python 3.13, uv, ruff, pytest, Git setup
5. ✅ security.md - Secrets management, context_guard, shell security
6. ✅ language.md - Japanese responses, English code/commits
7. ✅ testing.md - TDD, AAA pattern, 80%+ coverage, mocking

---

## Section 2: Skills (12 directories in ~/.claude/skills/)

Each skill directory contains `prompt.md` with frontmatter and implementation instructions.

### 2.1 startproject/prompt.md

```markdown
---
name: "startproject"
version: "1.0.0"
description: "Bootstrap a new project with complete directory structure, dependencies, and configuration"
triggers:
  - "/startproject"
  - "new project"
  - "initialize project"
---

# Start Project Skill

## Purpose
Bootstrap a new project from scratch with proper structure, dependencies, configuration, and initial tests.

## Workflow

### Phase 1: Initialization
1. Ask user for project details:
   - Project name
   - Project type (Python package, CLI tool, web API, etc.)
   - Programming language(s)
   - License (MIT, Apache-2.0, etc.)
2. Create base directory structure
3. Initialize git repository

### Phase 2: Structure
Create standard directory structure based on project type:

**Python Package**:
```
{project_name}/
├── src/
│   └── {package_name}/
│       ├── __init__.py
│       └── main.py
├── tests/
│   └── test_main.py
├── docs/
├── notes/
│   ├── mistakes.md
│   ├── rules-local.md
│   └── metrics.md
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── README.md
└── LICENSE
```

### Phase 3: Dependencies
1. Create virtual environment (`.venv`)
2. Install core dependencies based on project type:
   - Python: pytest, ruff, mypy, python-dotenv
   - Add type stubs if needed
3. Generate requirements.txt or pyproject.toml

### Phase 4: Configuration
1. Create pyproject.toml with:
   - Project metadata
   - Tool configurations (ruff, pytest, mypy)
2. Create .gitignore with sensible defaults
3. Create .env.example template
4. Add VS Code settings if applicable

### Phase 5: Initial Test
1. Write one passing test to verify setup
2. Run test suite to confirm everything works
3. Run linter to verify tooling

### Phase 6: Documentation
1. Create README.md with:
   - Project description
   - Installation instructions
   - Basic usage
   - Development setup
2. Add LICENSE file

### Phase 7: First Commit
1. Stage all files
2. Create initial commit: "chore: Initialize project structure"

## Example Interaction

User: "/startproject"

Claude: "I'll help you create a new project. Please provide:
1. Project name
2. Project type (Python package / CLI tool / Web API / other)
3. License (MIT / Apache-2.0 / GPL-3.0)"

[Then follows phases 1-7 automatically]

## Related
- [[init]] skill - Project initialization utilities
- [[dev-environment.md]] rule - Environment standards
```

---

### 2.2 checkpointing/prompt.md

```markdown
---
name: "checkpointing"
version: "1.0.0"
description: "Save session state and auto-save to TetsuyaSynapse"
triggers:
  - "/checkpoint"
  - "save session"
  - "session end"
---

# Checkpointing Skill

## Purpose
Persist session context for continuity and integrate with TetsuyaSynapse for long-term memory.

## Workflow

### 1. Capture Session State
- Current task/goal
- Key decisions made
- Files modified
- Pending items
- Mistakes recorded (from notes/mistakes.md)
- Rules created (from notes/rules-local.md)

### 2. Save Locally
Save to `{project}/.claude/session_{timestamp}.json`:
```json
{
  "timestamp": "2026-02-06T10:30:00Z",
  "task": "Implement context_guard module",
  "decisions": [...],
  "files_modified": [...],
  "pending": [...],
  "mistakes": 2,
  "rules_created": 1
}
```

### 3. TetsuyaSynapse Integration
**Vault path**: `G:\マイドライブ\obsidian\TetsuyaSynapse`

Save session summary to `90-Claude/sessions/YYYY-MM-DD_{project}.md`:
```markdown
---
date: "2026-02-06"
project: "{project_name}"
duration: "2h"
---

# セッションサマリー

## 実施内容
- {bullet points}

## 主な決定
- {key decisions}

## 次回タスク
- {pending items}
```

## Trigger Points
- User says "checkpoint", "save session", "end session"
- Before major refactoring
- After significant milestone
- On explicit request

## Related
- [[TetsuyaSynapse連携]] in CLAUDE.md
- [[Self-Improvement Loop]] in CLAUDE.md
```

---

### 2.3 plan/prompt.md

```markdown
---
name: "plan"
version: "1.0.0"
description: "Create structured implementation plan with Codex verification"
triggers:
  - "/plan"
  - "make a plan"
  - "plan this out"
---

# Plan Skill

## Purpose
Create detailed, verifiable implementation plans for complex tasks.

## Workflow

### 1. Understand Requirements
- Clarify user's goal
- Identify constraints
- List assumptions
- Define success criteria

### 2. Break Down Tasks
- Decompose into subtasks
- Identify dependencies
- Estimate complexity
- Flag risks

### 3. Create Plan Document
Save to `{project}/plans/plan-{date}-{topic}.md`:
```markdown
# Plan: {Topic}

## Goal
{1-2 sentence summary}

## Requirements
- {req 1}
- {req 2}

## Tasks
1. **Task 1**: {description}
   - Subtask 1.1
   - Subtask 1.2
   - Dependencies: none
   - Risk: low/medium/high

2. **Task 2**: {description}
   ...

## Verification
- Unit tests for X
- Integration test for Y
- Manual verification: Z

## Rollback Plan
If something goes wrong:
1. {step 1}
2. {step 2}
```

### 4. Codex Verification (Optional)
If plan is complex (>5 tasks or high risk):
```bash
codex verify plans/plan-{date}-{topic}.md
```

Parse Codex feedback:
- If approved: Proceed
- If concerns: Revise plan
- If blocked: Address issues

### 5. Present to User
Show plan and Codex feedback (if any).
Ask for approval before implementation.

## Related
- [[codex-delegation.md]] rule - When to verify
- [[codex-system]] skill - Codex CLI wrapper
```

---

### 2.4 tdd/prompt.md

```markdown
---
name: "tdd"
version: "1.0.0"
description: "Test-Driven Development workflow (Red-Green-Refactor)"
triggers:
  - "/tdd"
  - "write tests first"
  - "test driven"
---

# TDD Skill

## Purpose
Guide through Test-Driven Development cycle.

## Workflow

### Red Phase: Write Failing Test
1. Ask user for feature to implement
2. Write test that specifies behavior
3. Run test → should fail
4. Confirm failure message is clear

### Green Phase: Minimal Implementation
1. Write simplest code to pass test
2. Run test → should pass
3. No optimization yet (that's refactor phase)

### Refactor Phase: Improve Code
1. Clean up code
2. Extract functions
3. Remove duplication
4. Run tests → all should still pass

### Cycle
Repeat Red-Green-Refactor for each behavior.

## Example

User: "/tdd - implement calculate_discount function"

Claude:
```python
# RED: Write failing test
def test_calculate_discount_10_percent():
    assert calculate_discount(1000, 0.1) == 100
```

Run test → FAIL (function doesn't exist)

```python
# GREEN: Minimal implementation
def calculate_discount(amount: float, rate: float) -> float:
    return amount * rate
```

Run test → PASS

```python
# REFACTOR: Add type hints, docstring, validation
def calculate_discount(amount: float, rate: float) -> float:
    """Calculate discount amount.

    Args:
        amount: Original amount
        rate: Discount rate (0.0 to 1.0)

    Returns:
        Discount amount
    """
    if not 0 <= rate <= 1:
        raise ValueError("Rate must be between 0 and 1")
    return amount * rate
```

Run test → PASS

## Related
- [[testing.md]] rule - Testing standards
```

---

### Skills 2.5-2.12 (Summary)

Due to length constraints, here are the remaining 8 skills in summary form:

**2.5 codex-system/prompt.md**
- Wrapper for Codex CLI invocation
- Modes: verify, review, architecture, opinion, diff
- Error handling and fallback

**2.6 gemini-system/prompt.md**
- Wrapper for Gemini CLI research
- Modes: research, compare, best-practices, security
- Fallback to WebSearch if unavailable

**2.7 design-tracker/prompt.md**
- Track design decisions in `docs/decisions/`
- ADR (Architecture Decision Records) format
- Link to code and tests

**2.8 init/prompt.md**
- Project initialization utilities
- Quick setup helpers
- Template generation

**2.9 research-lib/prompt.md**
- Library research workflow
- Compare alternatives
- Check compatibility and security

**2.10 simplify/prompt.md**
- Code simplification workflow
- Identify complexity
- Refactor with tests

**2.11 update-design/prompt.md**
- Update design documentation
- Sync with code changes
- Maintain ADRs

**2.12 update-lib-docs/prompt.md**
- Update library documentation
- API reference updates
- Example code refresh

---

## Section 3: Agent (1 file in ~/.claude/agents/)

### 3.1 general-purpose.md

```markdown
---
name: "general-purpose"
version: "1.0.0"
description: "Sub-agent for delegated tasks"
---

# General Purpose Agent

## Behavior
When Claude Code delegates a task to a sub-agent:

### Context Retention
- Sub-agent receives task description and relevant context
- Has access to all project files
- Can read but should not modify original agent's state

### Tool Usage
- Can invoke Codex CLI via codex-system skill
- Can invoke Gemini CLI via gemini-system skill
- Should follow all rules in ~/.claude/rules/

### Response Format
- Return findings as structured bullet points
- Include relevant code snippets
- Cite sources when applicable
- Highlight risks or concerns

### Constraints
- Do not make destructive changes without confirmation
- Do not commit code
- Do not access secrets
- Operate within assigned scope

## Example Delegation

Main Claude: "Sub-agent, research best practices for async error handling in Python 2026"

Sub-agent:
```
## Async Error Handling Best Practices (2026)

### Key Findings
- Use `asyncio.TaskGroup` (Python 3.11+) for structured concurrency
- Prefer `asyncio.timeout()` over `wait_for()` for cleaner syntax
- Always handle `asyncio.CancelledError` in cleanup

### Code Example
[code snippet]

### Sources (via Gemini)
- [Python asyncio docs](...)
- [Real Python async guide](...)

### Risks
- `TaskGroup` requires Python 3.11+
- Ensure all tasks have proper exception handling
```

Main Claude integrates findings into implementation.

## Related
- [[codex-system]] skill
- [[gemini-system]] skill
```

---

## Section 4: Verification Plan

### 4.1 Pre-Implementation Verification (Step 0)

Before writing any code, verify the plan using Codex CLI.

**Test 1: Verify plan-v18-lib.md**
```bash
codex verify claude-orchestra/plan-v18-lib.md
```

Expected outcome:
- Codex approves library architecture
- Confidence score ≥ 7/10
- No blocking concerns

**Test 2: Verify plan-v18-hooks.md**
```bash
codex verify claude-orchestra/plan-v18-hooks.md
```

Expected outcome:
- Hook system architecture approved
- Lifecycle coverage confirmed
- No security concerns

**Test 3: Verify plan-v18-config.md** (this file)
```bash
codex verify claude-orchestra/plan-v18-config.md
```

Expected outcome:
- Rules/skills structure approved
- Verification plan adequate
- Implementation order logical

**Decision Point**:
- If all 3 plans approved → Proceed to implementation
- If concerns raised → Revise plans and re-verify
- If blocked → Address critical issues before proceeding

---

### 4.2 Post-Implementation Tests

Run these tests after completing implementation to verify correctness.

**Test 1: Directory Structure**
```bash
# Verify all directories exist
test -d ~/.claude/rules
test -d ~/.claude/skills/startproject
test -d ~/.claude/skills/checkpointing
# ... (all 12 skills)
test -d ~/.claude/agents

# Verify all rules exist
test -f ~/.claude/rules/codex-delegation.md
test -f ~/.claude/rules/gemini-delegation.md
# ... (all 7 rules)
```

**Test 2: Import Chain (Bootstrap → Libs)**
```python
# Test bootstrap.py can import all modules
python -c "
from claude_orchestra.bootstrap import initialize_orchestra
from claude_orchestra.context_guard import check_secrets
from claude_orchestra.budget import acquire_budget_lock
from claude_orchestra.vault_save import save_to_vault
from claude_orchestra.hooks import register_hook, fire_hook
print('All imports successful')
"
```

**Test 3: context_guard Tests**
```bash
# Run context_guard unit tests
pytest tests/unit/test_context_guard.py -v

# Test secret detection
python -c "
from claude_orchestra.context_guard import check_secrets, SecretFoundError
import pytest

# Should raise SecretFoundError
with pytest.raises(SecretFoundError):
    check_secrets({'api_key': 'sk-1234567890abcdef'}, strict=True)

# Should pass
check_secrets({'user': 'alice', 'count': 42}, strict=True)
print('Secret detection works')
"

# Test consent policies
python -c "
from claude_orchestra.context_guard import require_consent, OperationRisk, ConsentDenied
import pytest

# Should raise ConsentDenied (no user confirmation available in test)
with pytest.raises(ConsentDenied):
    require_consent('delete_database', OperationRisk.CRITICAL, {})

print('Consent system works')
"

# Test strict mode
python -c "
from claude_orchestra.context_guard import enable_strict_mode, check_secrets

enable_strict_mode()
# In strict mode, even potential secrets should raise
try:
    check_secrets({'token': 'maybe_a_secret'}, strict=True)
    assert False, 'Should have raised'
except Exception:
    print('Strict mode works')
"
```

**Test 4: budget.py Tests**
```bash
# Run budget unit tests
pytest tests/unit/test_budget.py -v

# Test budget locking
python -c "
from claude_orchestra.budget import acquire_budget_lock, release_budget_lock, BudgetExceeded

# Should acquire successfully
lock = acquire_budget_lock(tokens=1000, model='claude-sonnet-4-5')
print(f'Acquired lock: {lock}')

# Should release successfully
release_budget_lock(lock)
print('Released lock')

# Test budget exhaustion
import pytest
with pytest.raises(BudgetExceeded):
    acquire_budget_lock(tokens=1000000000, model='claude-opus-4-5')  # Absurdly high

print('Budget system works')
"

# Test fallback to smaller model
python -c "
from claude_orchestra.budget import fallback_to_smaller_model

# Should return smaller model
smaller = fallback_to_smaller_model('claude-opus-4-5')
assert smaller == 'claude-sonnet-4-5'

smaller = fallback_to_smaller_model('claude-sonnet-4-5')
assert smaller == 'claude-haiku-4'

print('Fallback system works')
"
```

**Test 5: Hook Firing Tests**
```bash
# Run hooks unit tests
pytest tests/unit/test_hooks.py -v

# Test hook registration and firing
python -c "
from claude_orchestra.hooks import register_hook, fire_hook, HookResult

# Register test hook
def test_hook(context):
    print(f'Hook fired with context: {context}')
    return HookResult(success=True, data={'processed': True})

register_hook('pre_task', test_hook)

# Fire hook
result = fire_hook('pre_task', {'task': 'test'})
assert result.success is True
assert result.data['processed'] is True

print('Hook system works')
"

# Test hook lifecycle
python -c "
from claude_orchestra.hooks import fire_hook
from claude_orchestra.context_guard import get_audit_log

# Fire sequence of hooks
fire_hook('session_start', {})
fire_hook('pre_task', {'task': 'implement X'})
fire_hook('post_task', {'task': 'implement X', 'status': 'success'})
fire_hook('session_end', {})

# Check audit log recorded hooks
log = get_audit_log()
assert len(log) == 4
print('Hook lifecycle works')
"
```

**Test 6: Vault Save Test**
```bash
# Test vault integration (if vault available)
python -c "
from claude_orchestra.vault_save import save_to_vault, get_vault_path
from pathlib import Path

# Check vault path
vault = get_vault_path()
print(f'Vault path: {vault}')

# Test save (will skip if vault not available)
result = save_to_vault(
    domain='reflections/build',
    filename='test_reflection.md',
    content='# Test Reflection\n\nThis is a test.'
)

if result:
    print('Vault save successful')
else:
    print('Vault not available (expected in test environment)')
"
```

**Test 7: End-to-End Codex Review**
```bash
# After all implementation complete, run Codex review
codex review src/claude_orchestra/

# Expected outcome:
# - No critical issues
# - Code quality rating ≥ 7/10
# - Security checks pass
```

---

### 4.3 Manual Verification Checklist

After automated tests pass, manually verify:

- [ ] All 7 rules files exist and are complete
- [ ] All 12 skills have prompt.md with correct frontmatter
- [ ] Agent file exists and defines sub-agent behavior
- [ ] bootstrap.py successfully imports all modules
- [ ] context_guard correctly detects secrets
- [ ] context_guard loads consent policies
- [ ] budget.py prevents over-spending
- [ ] budget.py falls back to smaller models
- [ ] Hooks fire at correct lifecycle points
- [ ] Hooks can be registered dynamically
- [ ] vault_save integrates with TetsuyaSynapse (if vault available)
- [ ] End-to-end: Can run `/startproject` skill successfully
- [ ] End-to-end: Can run `/plan` skill with Codex verification
- [ ] End-to-end: Can run `/tdd` skill with test cycle
- [ ] Codex review shows no critical issues

---

## Section 5: Implementation Order

### Phase 0: Pre-Implementation (MUST DO FIRST)
```
□ 0.1 Run Codex verification on all 3 plan files:
      - codex verify plan-v18-lib.md
      - codex verify plan-v18-hooks.md
      - codex verify plan-v18-config.md
□ 0.2 Address any Codex concerns
□ 0.3 Get user approval to proceed
```

### Phase 1: Library Foundation (plan-v18-lib.md)
```
□ 1.1 Create src/claude_orchestra/__init__.py
□ 1.2 Implement path_utils.py (claude_home, ensure_dir, load_json, save_json)
□ 1.3 Write tests for path_utils.py
□ 1.4 Implement bootstrap.py (environment setup, load_rules, load_skills, load_agents)
□ 1.5 Write tests for bootstrap.py
□ 1.6 Implement context_guard.py (check_secrets, require_consent, OperationRisk)
□ 1.7 Write tests for context_guard.py (secret detection, consent policies, strict mode)
□ 1.8 Implement budget.py (acquire/release locks, fallback, BudgetExceeded)
□ 1.9 Write tests for budget.py
□ 1.10 Implement vault_save.py (save_to_vault, get_vault_path, best-effort)
□ 1.11 Write tests for vault_save.py
□ 1.12 Run: pytest tests/unit/ --cov=src/claude_orchestra --cov-report=term-missing
```

### Phase 2: Wrapper Integrations (plan-v18-lib.md)
```
□ 2.1 Implement codex_wrapper.py (verify, review, architecture, opinion, diff)
□ 2.2 Write tests for codex_wrapper.py (mock subprocess calls)
□ 2.3 Implement gemini_wrapper.py (research, compare, best-practices, security)
□ 2.4 Write tests for gemini_wrapper.py (mock subprocess calls, test fallback)
□ 2.5 Test fallback: gemini_wrapper → WebSearch when Gemini unavailable
□ 2.6 Run: pytest tests/unit/test_*_wrapper.py -v
```

### Phase 3: Hook System (plan-v18-hooks.md)
```
□ 3.1 Implement hooks.py (register_hook, fire_hook, HookResult, LIFECYCLE_HOOKS)
□ 3.2 Write tests for hooks.py
□ 3.3 Implement pre-built hooks (in separate files or same module):
      - pre_task_hook (validate context)
      - post_task_hook (ルール昇格check, metrics update)
      - session_end_hook (Vault archive, global昇格)
□ 3.4 Integrate hooks into bootstrap.py (auto-register pre-built hooks)
□ 3.5 Write integration tests for hook lifecycle
□ 3.6 Run: pytest tests/integration/test_hooks_lifecycle.py -v
```

### Phase 4: Configuration Files (plan-v18-config.md)
```
□ 4.1 Create ~/.claude/rules/ directory
□ 4.2 Write all 7 rules files:
      - codex-delegation.md
      - gemini-delegation.md
      - coding-principles.md
      - dev-environment.md
      - security.md
      - language.md
      - testing.md
□ 4.3 Create ~/.claude/skills/ directory
□ 4.4 Write all 12 skills (each with prompt.md):
      - startproject/
      - checkpointing/
      - plan/
      - tdd/
      - codex-system/
      - gemini-system/
      - design-tracker/
      - init/
      - research-lib/
      - simplify/
      - update-design/
      - update-lib-docs/
□ 4.5 Create ~/.claude/agents/ directory
□ 4.6 Write general-purpose.md agent definition
□ 4.7 Verify directory structure with Test 1 from Section 4.2
```

### Phase 5: Integration & Verification
```
□ 5.1 Run Test 2: Import chain verification
□ 5.2 Run Test 3: context_guard integration tests
□ 5.3 Run Test 4: budget.py integration tests
□ 5.4 Run Test 5: Hook firing tests
□ 5.5 Run Test 6: Vault save test (if available)
□ 5.6 Run full test suite: pytest tests/ -v --cov=src --cov-report=html
□ 5.7 Check coverage ≥ 80%
□ 5.8 Run Test 7: codex review src/claude_orchestra/
□ 5.9 Address any Codex issues
□ 5.10 Run manual verification checklist (Section 4.3)
```

### Phase 6: End-to-End Testing
```
□ 6.1 Test /startproject skill:
      - Create test project
      - Verify structure
      - Run initial tests
□ 6.2 Test /plan skill with Codex verification:
      - Create plan for sample feature
      - Verify Codex integration works
      - Check plan structure
□ 6.3 Test /tdd skill:
      - Implement sample feature with TDD
      - Verify Red-Green-Refactor cycle
□ 6.4 Test checkpointing:
      - Run checkpoint command
      - Verify session saved locally
      - Verify Vault save (if available)
□ 6.5 Test hooks end-to-end:
      - Create notes/ directory with mistakes.md
      - Complete a task
      - Verify post_task_hook updates metrics
      - End session
      - Verify session_end_hook archives to Vault
```

### Phase 7: Documentation & Finalization
```
□ 7.1 Write README.md for claude-orchestra package
□ 7.2 Write USAGE.md with examples
□ 7.3 Write ARCHITECTURE.md documenting design
□ 7.4 Create pyproject.toml with all metadata
□ 7.5 Create requirements.txt with pinned versions
□ 7.6 Run final linting: ruff check . && ruff format .
□ 7.7 Run final type check: pyright src/
□ 7.8 Generate final coverage report
□ 7.9 Commit all changes
□ 7.10 Tag release: v0.18.0
```

---

## Summary

### Configuration Files Created (19 total)

**Rules (7)**:
1. codex-delegation.md
2. gemini-delegation.md
3. coding-principles.md
4. dev-environment.md
5. security.md
6. language.md
7. testing.md

**Skills (12)**:
1. startproject/prompt.md
2. checkpointing/prompt.md
3. plan/prompt.md
4. tdd/prompt.md
5. codex-system/prompt.md
6. gemini-system/prompt.md
7. design-tracker/prompt.md
8. init/prompt.md
9. research-lib/prompt.md
10. simplify/prompt.md
11. update-design/prompt.md
12. update-lib-docs/prompt.md

**Agent (1)**:
1. general-purpose.md

### Verification Strategy
- **Pre-implementation**: 3 Codex verifications (MUST pass before coding)
- **Post-implementation**: 7 automated test suites + manual checklist
- **End-to-end**: 5 workflow tests

### Implementation Phases
1. **Phase 0**: Pre-verification (blocking)
2. **Phase 1**: Library foundation (9 modules + tests)
3. **Phase 2**: Wrappers (2 modules + tests)
4. **Phase 3**: Hooks (3 modules + integration tests)
5. **Phase 4**: Config files (19 files)
6. **Phase 5**: Integration & verification
7. **Phase 6**: E2E testing
8. **Phase 7**: Documentation & finalization

### Success Criteria
- [ ] All Codex pre-verifications approved
- [ ] 80%+ test coverage
- [ ] All automated tests pass
- [ ] Manual checklist complete
- [ ] Codex review rating ≥ 7/10
- [ ] All E2E workflows functional

---

**Document Status**: ✅ COMPLETE
**Next Action**: Run Phase 0 (Pre-Implementation Verification)

