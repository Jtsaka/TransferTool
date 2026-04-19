"""Firestore-backed cache for AP scores and transfer deadlines.

If Firebase credentials aren't configured, the store transparently falls back
to a local JSON file so the rest of the app still works during development.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any

from ..config import config

logger = logging.getLogger(__name__)

_LOCAL_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "local_cache.json",
)


def _slugify(value: str) -> str:
    """Make a deterministic, Firestore-safe document id from free-form text."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "unknown"


class FirestoreStore:
    """Thin wrapper around Firestore with a local-file fallback."""

    AP_COLLECTION = "ap_scores"
    DEADLINE_COLLECTION = "deadlines"
    OVERLAP_COLLECTION = "course_overlaps"

    def __init__(self) -> None:
        self._client = None
        self._lock = threading.Lock()
        self._init_client()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def _init_client(self) -> None:
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except Exception as exc:  # pragma: no cover - import guard
            logger.warning("firebase-admin not available (%s); using local cache", exc)
            return

        try:
            if not firebase_admin._apps:
                cred = self._build_credentials(credentials)
                if cred is None:
                    logger.warning(
                        "No Firebase credentials configured; falling back to local cache."
                    )
                    return
                options: dict[str, Any] = {}
                if config.FIREBASE_PROJECT_ID:
                    options["projectId"] = config.FIREBASE_PROJECT_ID
                firebase_admin.initialize_app(cred, options or None)
            self._client = firestore.client()
            logger.info("Firestore client initialized.")
        except Exception as exc:
            logger.exception("Failed to initialize Firestore client: %s", exc)
            self._client = None

    def _build_credentials(self, credentials_module):
        if config.FIREBASE_CREDENTIALS_JSON:
            try:
                data = json.loads(config.FIREBASE_CREDENTIALS_JSON)
                return credentials_module.Certificate(data)
            except Exception as exc:
                logger.error("Invalid FIREBASE_CREDENTIALS_JSON: %s", exc)
                return None
        if config.FIREBASE_CREDENTIALS and os.path.isfile(config.FIREBASE_CREDENTIALS):
            return credentials_module.Certificate(config.FIREBASE_CREDENTIALS)
        return None

    @property
    def is_remote(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Local file fallback
    # ------------------------------------------------------------------
    def _load_local(self) -> dict[str, Any]:
        if not os.path.isfile(_LOCAL_CACHE_PATH):
            return {}
        try:
            with open(_LOCAL_CACHE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.error("Local cache read failed: %s", exc)
            return {}

    def _write_local(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(_LOCAL_CACHE_PATH), exist_ok=True)
        with open(_LOCAL_CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)

    # ------------------------------------------------------------------
    # AP Scores
    # ------------------------------------------------------------------
    def ap_doc_id(self, institution: str, major: str) -> str:
        return f"{_slugify(institution)}__{_slugify(major)}"

    def get_ap_scores(self, institution: str, major: str) -> dict | None:
        doc_id = self.ap_doc_id(institution, major)
        return self._get(self.AP_COLLECTION, doc_id)

    def save_ap_scores(
        self, institution: str, major: str, payload: dict
    ) -> None:
        doc_id = self.ap_doc_id(institution, major)
        wrapper = {
            "institution": institution,
            "major": major,
            "data": payload,
        }
        self._set(self.AP_COLLECTION, doc_id, wrapper)

    # ------------------------------------------------------------------
    # Deadlines
    # ------------------------------------------------------------------
    def deadline_doc_id(self, institution: str, major: str, term: str) -> str:
        return f"{_slugify(institution)}__{_slugify(major)}__{_slugify(term)}"

    def get_deadline(
        self, institution: str, major: str, term: str
    ) -> dict | None:
        doc_id = self.deadline_doc_id(institution, major, term)
        return self._get(self.DEADLINE_COLLECTION, doc_id)

    def save_deadline(
        self,
        institution: str,
        major: str,
        term: str,
        deadline: str,
        raw: str | None = None,
    ) -> None:
        doc_id = self.deadline_doc_id(institution, major, term)
        wrapper = {
            "institution": institution,
            "major": major,
            "term": term,
            "deadline": deadline,
            "raw_response": raw,
        }
        self._set(self.DEADLINE_COLLECTION, doc_id, wrapper)

    # ------------------------------------------------------------------
    # Course overlap
    # ------------------------------------------------------------------
    def overlap_doc_id(self, from_inst: str, target_inst: str, major: str) -> str:
        return (
            f"{_slugify(from_inst)}__{_slugify(target_inst)}__{_slugify(major)}"
        )

    def get_overlap(
        self, from_inst: str, target_inst: str, major: str
    ) -> dict | None:
        doc_id = self.overlap_doc_id(from_inst, target_inst, major)
        return self._get(self.OVERLAP_COLLECTION, doc_id)

    def save_overlap(
        self, from_inst: str, target_inst: str, major: str, payload: dict
    ) -> None:
        doc_id = self.overlap_doc_id(from_inst, target_inst, major)
        wrapper = {
            "from_institution": from_inst,
            "target_institution": target_inst,
            "major": major,
            "data": payload,
        }
        self._set(self.OVERLAP_COLLECTION, doc_id, wrapper)

    # ------------------------------------------------------------------
    # Shared low-level get/set
    # ------------------------------------------------------------------
    def _get(self, collection: str, doc_id: str) -> dict | None:
        if self._client is not None:
            try:
                snap = self._client.collection(collection).document(doc_id).get()
                if snap.exists:
                    return snap.to_dict()
                return None
            except Exception as exc:
                logger.exception("Firestore read failed: %s", exc)
        with self._lock:
            data = self._load_local()
            return data.get(collection, {}).get(doc_id)

    def _set(self, collection: str, doc_id: str, value: dict) -> None:
        if self._client is not None:
            try:
                self._client.collection(collection).document(doc_id).set(value)
                return
            except Exception as exc:
                logger.exception("Firestore write failed: %s", exc)
        with self._lock:
            data = self._load_local()
            data.setdefault(collection, {})[doc_id] = value
            self._write_local(data)


_store: FirestoreStore | None = None


def get_store() -> FirestoreStore:
    global _store
    if _store is None:
        _store = FirestoreStore()
    return _store
