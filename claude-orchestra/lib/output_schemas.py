"""
Output schema definitions and validation for sub-agent responses.

Ensures consistent, structured output from Codex and Gemini
with required fields and type validation.
"""


# Expected schema for Codex review mode output
CODEX_REVIEW_SCHEMA = {
    "required": ["approved", "confidence", "issues", "summary"],
    "types": {
        "approved": bool,
        "confidence": int,
        "issues": list,
        "summary": str,
    },
    "issue_required": ["severity", "description"],
    "issue_types": {
        "severity": str,
        "description": str,
        "suggestion": str,  # optional
    },
    "severity_values": {"critical", "high", "medium", "low"},
}

# Expected schema for Codex verify mode output
CODEX_VERIFY_SCHEMA = {
    "required": ["approved", "confidence", "issues"],
    "types": {
        "approved": bool,
        "confidence": int,
        "issues": list,
    },
}

# Expected schema for Gemini research output
GEMINI_RESEARCH_SCHEMA = {
    "required": ["result"],
    "types": {
        "result": str,
        "sources": list,
        "confidence": (int, float),
    },
}

# Mode-to-schema mapping
MODE_SCHEMAS = {
    "review": CODEX_REVIEW_SCHEMA,
    "verify": CODEX_VERIFY_SCHEMA,
    "architecture": CODEX_REVIEW_SCHEMA,  # Same structure as review
    "research": GEMINI_RESEARCH_SCHEMA,  # v19 L-5
}


def validate_output(data: dict, mode: str) -> dict:
    """
    Validate sub-agent output against expected schema.

    Args:
        data: Parsed JSON output from sub-agent
        mode: Operation mode (review, verify, architecture, research, etc.)

    Returns:
        {
            "valid": bool,
            "errors": list[str],
            "data": dict (original or with defaults filled)
        }
    """
    schema = MODE_SCHEMAS.get(mode)
    if not schema:
        # No schema defined for this mode - pass through
        return {"valid": True, "errors": [], "data": data}

    errors = []

    # Check required fields
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Check types
    for field, expected_type in schema.get("types", {}).items():
        if field in data:
            if isinstance(expected_type, tuple):
                if not isinstance(data[field], expected_type):
                    errors.append(f"Field '{field}' expected {expected_type}, got {type(data[field])}")
            elif not isinstance(data[field], expected_type):
                errors.append(f"Field '{field}' expected {expected_type.__name__}, got {type(data[field]).__name__}")

    # v13 C-6: Validate confidence range (1-10)
    if "confidence" in data and isinstance(data["confidence"], (int, float)):
        if not (1 <= data["confidence"] <= 10):
            errors.append(f"Field 'confidence' must be 1-10, got {data['confidence']}")

    # Validate issues array items
    if "issues" in data and isinstance(data["issues"], list):
        issue_required = schema.get("issue_required", [])
        severity_values = schema.get("severity_values", set())
        for i, issue in enumerate(data["issues"]):
            if not isinstance(issue, dict):
                errors.append(f"Issue[{i}] is not a dict")
                continue
            for field in issue_required:
                if field not in issue:
                    errors.append(f"Issue[{i}] missing required field: {field}")
            if severity_values and "severity" in issue:
                if issue["severity"] not in severity_values:
                    errors.append(f"Issue[{i}] invalid severity: {issue['severity']}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "data": data,
    }


def make_error_response(mode: str, error_msg: str, raw_output: str = "") -> dict:
    """
    Create a structured error response when output validation fails.

    For review/verify modes, returns approved=false with a pseudo-issue
    so downstream never silently skips a failed review.

    Args:
        mode: Operation mode
        error_msg: Description of what went wrong
        raw_output: The original unparsed output (truncated for safety)

    Returns:
        Structured response dict appropriate for the mode
    """
    base = {
        "success": False,
        "error": "invalid_output",
        "error_detail": error_msg,
    }

    if mode in ("review", "verify", "architecture"):
        base.update({
            "approved": False,
            "confidence": 1,  # v14 D-5: minimum valid value (1-10 range)
            "issues": [{
                "severity": "high",
                "description": f"Output validation failed: {error_msg}",
                "suggestion": "Re-run the review or inspect the raw output manually.",
            }],
            "summary": f"Review failed due to output error: {error_msg}",
        })

    if raw_output:
        base["raw_output"] = raw_output[:2000]

    return base
