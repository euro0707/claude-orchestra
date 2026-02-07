"""Test 5.5: output_schemas module - validation and error responses."""
import pytest

import output_schemas


class TestValidateOutput:
    def test_valid_review(self):
        data = {
            "approved": True,
            "confidence": 8,
            "issues": [],
            "summary": "Looks good",
        }
        result = output_schemas.validate_output(data, "review")
        assert result["valid"] is True
        assert result["errors"] == []

    def test_missing_required_field(self):
        data = {"approved": True, "confidence": 8}
        result = output_schemas.validate_output(data, "review")
        assert result["valid"] is False
        assert any("issues" in e for e in result["errors"])

    def test_wrong_type(self):
        data = {
            "approved": "yes",  # should be bool
            "confidence": 8,
            "issues": [],
            "summary": "ok",
        }
        result = output_schemas.validate_output(data, "review")
        assert result["valid"] is False
        assert any("approved" in e for e in result["errors"])

    def test_confidence_out_of_range_high(self):
        data = {
            "approved": True,
            "confidence": 15,
            "issues": [],
            "summary": "ok",
        }
        result = output_schemas.validate_output(data, "review")
        assert result["valid"] is False
        assert any("confidence" in e for e in result["errors"])

    def test_confidence_out_of_range_low(self):
        data = {
            "approved": True,
            "confidence": 0,
            "issues": [],
            "summary": "ok",
        }
        result = output_schemas.validate_output(data, "review")
        assert result["valid"] is False

    def test_confidence_valid_boundaries(self):
        for conf in [1, 5, 10]:
            data = {"approved": True, "confidence": conf, "issues": [], "summary": "ok"}
            result = output_schemas.validate_output(data, "review")
            assert result["valid"] is True, f"Failed for confidence={conf}"

    def test_issue_missing_severity(self):
        data = {
            "approved": False,
            "confidence": 3,
            "issues": [{"description": "bug"}],
            "summary": "bad",
        }
        result = output_schemas.validate_output(data, "review")
        assert result["valid"] is False
        assert any("severity" in e for e in result["errors"])

    def test_issue_invalid_severity(self):
        data = {
            "approved": False,
            "confidence": 3,
            "issues": [{"severity": "blocker", "description": "bug"}],
            "summary": "bad",
        }
        result = output_schemas.validate_output(data, "review")
        assert result["valid"] is False
        assert any("severity" in e.lower() for e in result["errors"])

    def test_issue_not_dict(self):
        data = {
            "approved": False,
            "confidence": 3,
            "issues": ["just a string"],
            "summary": "bad",
        }
        result = output_schemas.validate_output(data, "review")
        assert result["valid"] is False

    def test_verify_mode(self):
        data = {"approved": True, "confidence": 7, "issues": []}
        result = output_schemas.validate_output(data, "verify")
        assert result["valid"] is True

    def test_research_mode(self):
        data = {"result": "some findings"}
        result = output_schemas.validate_output(data, "research")
        assert result["valid"] is True

    def test_research_confidence_float(self):
        data = {"result": "findings", "confidence": 7.5}
        result = output_schemas.validate_output(data, "research")
        assert result["valid"] is True

    def test_unknown_mode_passthrough(self):
        data = {"anything": "goes"}
        result = output_schemas.validate_output(data, "opinion")
        assert result["valid"] is True

    def test_architecture_uses_review_schema(self):
        data = {
            "approved": True,
            "confidence": 8,
            "issues": [],
            "summary": "ok",
        }
        result = output_schemas.validate_output(data, "architecture")
        assert result["valid"] is True


class TestMakeErrorResponse:
    def test_review_error(self):
        resp = output_schemas.make_error_response("review", "parse failed")
        assert resp["success"] is False
        assert resp["approved"] is False
        assert resp["confidence"] == 1
        assert len(resp["issues"]) == 1
        assert resp["issues"][0]["severity"] == "high"

    def test_verify_error(self):
        resp = output_schemas.make_error_response("verify", "timeout")
        assert resp["approved"] is False

    def test_research_error(self):
        resp = output_schemas.make_error_response("research", "timeout")
        assert resp["success"] is False
        assert "approved" not in resp

    def test_raw_output_truncated(self):
        long_output = "x" * 5000
        resp = output_schemas.make_error_response("review", "err", long_output)
        assert len(resp["raw_output"]) <= 2000

    def test_no_raw_output(self):
        resp = output_schemas.make_error_response("review", "err")
        assert "raw_output" not in resp
