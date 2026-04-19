"""HTTP API routes for the Compass backend.

Endpoints
---------
GET  /api/catalog                         - school/major/term/from lists
GET  /api/ap-scores                       - cached or freshly fetched AP scores
GET  /api/deadlines                       - cached or freshly fetched deadline
POST /api/course-overlap                  - overlap of CSM courses with target lists
GET  /api/health                          - liveness probe
"""
from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict, defaultdict
from typing import Any

from flask import Blueprint, jsonify, request

from .config import config
from .services.firestore_store import get_store
from .services.gemini_client import GeminiUnavailableError, get_client

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__, url_prefix="/api")

_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "catalog.json"
)


def _load_catalog() -> dict[str, Any]:
    with open(_CATALOG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


@api.get("/health")
def health():
    store = get_store()
    client = get_client()
    return jsonify(
        {
            "status": "ok",
            "firestore_remote": store.is_remote,
            "gemini_ready": client.is_ready,
            "default_from_institution": config.DEFAULT_FROM_INSTITUTION,
        }
    )


@api.get("/catalog")
def catalog():
    data = _load_catalog()
    data.setdefault("default_from_institution", config.DEFAULT_FROM_INSTITUTION)
    return jsonify(data)


# ---------------------------------------------------------------------------
# AP Scores
# ---------------------------------------------------------------------------
@api.get("/ap-scores")
def ap_scores():
    institution = (request.args.get("institution") or "").strip()
    major = (request.args.get("major") or "").strip()
    refresh = request.args.get("refresh") in {"1", "true", "True"}

    if not institution or not major:
        return (
            jsonify({"error": "institution and major query params are required"}),
            400,
        )

    store = get_store()
    if not refresh:
        cached = store.get_ap_scores(institution, major)
        if cached:
            return jsonify(
                {
                    "institution": institution,
                    "major": major,
                    "data": cached.get("data", {}),
                    "source": "cache",
                }
            )

    try:
        payload = get_client().fetch_ap_scores(institution, major)
    except GeminiUnavailableError as exc:
        return jsonify({"error": str(exc), "source": "gemini"}), 503
    except Exception as exc:
        logger.exception("AP scores fetch failed")
        return jsonify({"error": f"Gemini lookup failed: {exc}"}), 502

    try:
        store.save_ap_scores(institution, major, payload)
    except Exception as exc:
        logger.exception("AP scores save failed: %s", exc)

    return jsonify(
        {
            "institution": institution,
            "major": major,
            "data": payload,
            "source": "gemini",
        }
    )


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------
@api.get("/deadlines")
def deadlines():
    institution = (request.args.get("institution") or "").strip()
    major = (request.args.get("major") or "").strip()
    term = (request.args.get("term") or "").strip()
    refresh = request.args.get("refresh") in {"1", "true", "True"}

    if not institution or not major or not term:
        return (
            jsonify(
                {"error": "institution, major and term query params are required"}
            ),
            400,
        )

    store = get_store()
    if not refresh:
        cached = store.get_deadline(institution, major, term)
        if cached:
            return jsonify(
                {
                    "institution": institution,
                    "major": major,
                    "term": term,
                    "deadline": cached.get("deadline"),
                    "source": "cache",
                }
            )

    try:
        deadline_text = get_client().fetch_deadline(institution, major, term)
    except GeminiUnavailableError as exc:
        return jsonify({"error": str(exc), "source": "gemini"}), 503
    except Exception as exc:
        logger.exception("Deadline fetch failed")
        return jsonify({"error": f"Gemini lookup failed: {exc}"}), 502

    try:
        store.save_deadline(institution, major, term, deadline_text, raw=deadline_text)
    except Exception as exc:
        logger.exception("Deadline save failed: %s", exc)

    return jsonify(
        {
            "institution": institution,
            "major": major,
            "term": term,
            "deadline": deadline_text,
            "source": "gemini",
        }
    )


# ---------------------------------------------------------------------------
# Course overlap
# ---------------------------------------------------------------------------
@api.post("/course-overlap")
def course_overlap():
    body = request.get_json(silent=True) or {}
    from_institution = (
        body.get("from_institution") or config.DEFAULT_FROM_INSTITUTION
    ).strip()
    selections = body.get("selections") or []
    refresh = bool(body.get("refresh"))

    if not isinstance(selections, list) or not selections:
        return (
            jsonify(
                {
                    "error": "Provide a non-empty 'selections' list of "
                    "{institution, major} objects (typically the user's "
                    "deadline list)."
                }
            ),
            400,
        )

    store = get_store()
    client = get_client()

    per_target: list[dict[str, Any]] = []
    course_map: dict[str, dict[str, Any]] = OrderedDict()
    school_set_per_course: dict[str, set[str]] = defaultdict(set)
    major_set_per_course: dict[str, set[str]] = defaultdict(set)

    errors: list[dict[str, Any]] = []

    for sel in selections:
        institution = (sel.get("institution") or "").strip()
        major = (sel.get("major") or "").strip()
        if not institution or not major:
            continue

        cached = None if refresh else store.get_overlap(
            from_institution, institution, major
        )
        if cached:
            payload = cached.get("data") or {}
            source = "cache"
        else:
            try:
                payload = client.fetch_overlap(from_institution, institution, major)
                source = "gemini"
                try:
                    store.save_overlap(
                        from_institution, institution, major, payload
                    )
                except Exception as exc:
                    logger.exception("overlap save failed: %s", exc)
            except GeminiUnavailableError as exc:
                errors.append(
                    {
                        "institution": institution,
                        "major": major,
                        "error": str(exc),
                    }
                )
                continue
            except Exception as exc:
                logger.exception("overlap fetch failed for %s / %s", institution, major)
                errors.append(
                    {
                        "institution": institution,
                        "major": major,
                        "error": f"Gemini lookup failed: {exc}",
                    }
                )
                continue

        courses = payload.get("courses") if isinstance(payload, dict) else None
        if not isinstance(courses, list):
            courses = []

        per_target.append(
            {
                "institution": institution,
                "major": major,
                "courses": courses,
                "source": source,
            }
        )

        for course in courses:
            if not isinstance(course, dict):
                continue
            code = (course.get("course") or "").strip()
            if not code:
                continue
            key = code.upper()
            entry = course_map.get(key)
            if entry is None:
                entry = {
                    "course": code,
                    "title": course.get("title") or "",
                    "schools": [],
                    "majors": [],
                    "school_count": 0,
                }
                course_map[key] = entry
            elif not entry["title"] and course.get("title"):
                entry["title"] = course["title"]
            school_set_per_course[key].add(institution)
            if major:
                major_set_per_course[key].add(major)

    overlap_rows: list[dict[str, Any]] = []
    for key, entry in course_map.items():
        schools = sorted(school_set_per_course[key])
        majors = sorted(major_set_per_course[key])
        entry["schools"] = schools
        entry["majors"] = majors
        entry["school_count"] = len(schools)
        overlap_rows.append(entry)

    overlap_rows.sort(key=lambda row: (-row["school_count"], row["course"]))

    total_schools = len({s["institution"] for s in per_target})

    return jsonify(
        {
            "from_institution": from_institution,
            "selections": selections,
            "per_target": per_target,
            "overlap": overlap_rows,
            "total_schools": total_schools,
            "errors": errors,
        }
    )
