"""Unit tests for the Gemini response coercion helper."""
import pytest

from backend.services.gemini_client import _coerce_to_json


def test_plain_json():
    raw = '{"Calculus AB": [{"min_score": 3, "max_score": 5, "units": 4.0, "courses": ["MATH 1A"], "notes": []}]}'
    out = _coerce_to_json(raw)
    assert "Calculus AB" in out


def test_code_fence_wrapped():
    raw = """```json
{
  "Biology": [{"min_score": 4, "max_score": 5, "units": 8.0,
              "courses": ["BIO 1A"], "notes": []}],
  "SiteNotes": [{"notes": "AP Bio max 8 units toward major."}]
}
```"""
    out = _coerce_to_json(raw)
    assert out["Biology"][0]["min_score"] == 4
    assert out["SiteNotes"][0]["notes"].startswith("AP Bio")


def test_single_quoted_payload():
    raw = "{'Chemistry': [{'min_score': 3, 'max_score': 4, 'units': 6.0, 'courses': ['CHEM 1A'], 'notes': []}], 'SiteNotes': [{'notes': 'No other relevant comments found from the institution page.'}]}"
    out = _coerce_to_json(raw)
    assert out["Chemistry"][0]["units"] == 6.0


def test_extracts_object_when_surrounded_by_prose():
    raw = (
        "Here you go: {\"Physics\": [{\"min_score\": 4, \"max_score\": 5, "
        "\"units\": 8.0, \"courses\": [\"PHYS 4A\"], \"notes\": []}]} thanks!"
    )
    out = _coerce_to_json(raw)
    assert "Physics" in out


def test_invalid_raises():
    with pytest.raises(ValueError):
        _coerce_to_json("totally not json")
