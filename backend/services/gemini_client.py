"""Wrapper around the Gemini API with the prompts described in the spec."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..config import config

logger = logging.getLogger(__name__)


class GeminiUnavailableError(RuntimeError):
    """Raised when no Gemini API key is configured."""


class GeminiClient:
    def __init__(self) -> None:
        self._model = None
        self._init_model()

    def _init_model(self) -> None:
        if not config.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set; Gemini calls will be disabled.")
            return
        try:
            import google.generativeai as genai

            genai.configure(api_key=config.GEMINI_API_KEY)
            self._model = genai.GenerativeModel(config.GEMINI_MODEL)
        except Exception as exc:
            logger.exception("Failed to initialize Gemini model: %s", exc)
            self._model = None

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    # ------------------------------------------------------------------
    # AP scores
    # ------------------------------------------------------------------
    @staticmethod
    def build_ap_prompt(institution: str, major: str) -> str:
        return (
            f"Find the most relevant {institution}'s page for the major "
            f"{major}, regarding \"Exams\" or \"Accepted Ap scores.\" Once "
            "located, extract the AP credit policy from their provided table "
            "and format the retrieved information as a structured JSON format. "
            "Follow these strict rules to ensure data consistency:\n\n"
            "Key Normalization: The primary keys must be the standard subject "
            "name only (e.g., use 'Chemistry', not 'AP Chemistry' or "
            "'Chemistry with score of 3').\n"
            "Range Logic: Use min_score and max_score for requirements.\n"
            "- If the table says '3 or 4', min_score is 3 and max_score is 4.\n"
            "- If the table says '3 or higher', min_score is 3 and max_score is 5.\n"
            "Course List: Always return 'courses' as an array of strings, "
            "even if there is only one course. If there is not an explicit "
            "course/course number listed and there is instead a requirement "
            "it fulfills, use that instead.\n"
            "Units: Store units as a float. Do not round any numbers.\n\n"
            "After creating primary keys for all the ap scores listed, create "
            "one more primary key called \"SiteNotes\".\n"
            "Notes (one new primary key after storing all the ap scores): "
            "stores unique scenarios and rules about specific majors/ap scores\n"
            "- the website mentions a specific AP score not able to fulfill "
            "an elective or class requirement\n"
            "- there exists a comment about a specific AP scores that if not "
            "above a certain threshold, would would need additional classes "
            "to meet pre-requisites\n"
            "- maximum allowances of specific AP scores towards a specific "
            "requirement\n"
            "- important footnotes\n"
            "- other important notices\n"
            "After every unique comment within \"Notes,\" use a '. '.\n"
            "If there are no comments on the website regarding \"Exams\" or "
            "\"Accepted Ap scores,\" then the key shall contain the comment "
            "\"No other relevant comments found from the institution page.\"\n"
            "Output Format:\n"
            "{\n"
            "'SubjectName': [\n"
            "{ 'min_score': int, 'max_score': int, 'units': float, "
            "'courses': [string], 'notes': [string]}\n"
            "]\n"
            "}\n"
            "{\n"
            "'SiteNotes:'[\n"
            "{ 'notes:' string\n"
            "]\n"
            "}\n\n"
            "The response should be just be the output of the JSON formatting "
            "and nothing else."
        )

    def fetch_ap_scores(self, institution: str, major: str) -> dict:
        prompt = self.build_ap_prompt(institution, major)
        text = self._generate(prompt)
        return _coerce_to_json(text)

    # ------------------------------------------------------------------
    # Deadlines
    # ------------------------------------------------------------------
    @staticmethod
    def build_deadline_prompt(institution: str, major: str, term: str) -> str:
        return (
            f"{institution} {major} major transfer deadline for {term}. "
            "The response should be just the exact date."
        )

    def fetch_deadline(self, institution: str, major: str, term: str) -> str:
        prompt = self.build_deadline_prompt(institution, major, term)
        text = self._generate(prompt)
        return text.strip().strip("`").strip()

    # ------------------------------------------------------------------
    # Course overlap
    # ------------------------------------------------------------------
    @staticmethod
    def build_overlap_prompt(
        from_institution: str, target_institution: str, major: str
    ) -> str:
        return (
            f"List the {from_institution} courses that are articulated as "
            f"transferable and required for the {major} major at "
            f"{target_institution}. Use ASSIST.org or the institution's "
            "official articulation agreement when possible. Respond as JSON "
            "in this exact shape and nothing else:\n"
            "{\n"
            "  \"courses\": [\n"
            "    { \"course\": string, \"title\": string, \"required\": boolean }\n"
            "  ]\n"
            "}\n"
            "The 'course' field must use the source-institution course code "
            f"(e.g. a {from_institution} course code such as MATH 251). If no "
            "data can be found, return {\"courses\": []}."
        )

    def fetch_overlap(
        self, from_institution: str, target_institution: str, major: str
    ) -> dict:
        prompt = self.build_overlap_prompt(
            from_institution, target_institution, major
        )
        text = self._generate(prompt)
        return _coerce_to_json(text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _generate(self, prompt: str) -> str:
        if self._model is None:
            raise GeminiUnavailableError(
                "Gemini API key not configured. Set GEMINI_API_KEY in .env"
            )
        response = self._model.generate_content(prompt)
        text = getattr(response, "text", None)
        if not text:
            try:
                text = response.candidates[0].content.parts[0].text  # type: ignore[attr-defined]
            except Exception as exc:
                raise RuntimeError(f"Empty Gemini response: {exc}") from exc
        return text


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _coerce_to_json(raw: str) -> dict:
    """Best-effort conversion of Gemini's text into a dict.

    Gemini sometimes wraps the JSON in code fences and the spec uses single
    quotes. We normalize before parsing.
    """
    if not raw:
        raise ValueError("Empty response from Gemini")

    text = raw.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    candidates = [text]
    candidates.append(text.replace("\u201c", '"').replace("\u201d", '"'))
    candidates.append(_single_to_double_quotes(candidates[-1]))

    last_err: Exception | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception as exc:
            last_err = exc
            continue

    extracted = _extract_json_object(text)
    if extracted is not None:
        try:
            return json.loads(extracted)
        except Exception as exc:
            last_err = exc

    raise ValueError(f"Could not parse Gemini response as JSON: {last_err}")


def _single_to_double_quotes(text: str) -> str:
    """Convert single-quoted JSON-ish content to double-quoted JSON.

    This is a heuristic that handles the spec's example output (which uses
    single quotes). It only swaps quotes when there are no embedded double
    quotes already, to avoid corrupting strings that contain apostrophes.
    """
    if '"' in text:
        return text
    return text.replace("'", '"')


def _extract_json_object(text: str) -> str | None:
    """Extract the first balanced { ... } substring from text."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


_client: GeminiClient | None = None


def get_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
