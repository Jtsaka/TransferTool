"""Flask application factory.

Serves the existing static HTML (ap-scores.html, deadlines.html, courses.html,
index.html) plus the JSON API under /api/*.
"""
from __future__ import annotations

import logging
import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from .config import config
from .routes import api

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def create_app() -> Flask:
    logging.basicConfig(level=logging.INFO)
    app = Flask(
        __name__,
        static_folder=PROJECT_ROOT,
        static_url_path="",
    )
    CORS(app)
    app.register_blueprint(api)

    @app.get("/")
    def root():
        return send_from_directory(PROJECT_ROOT, "index.html")

    @app.get("/<path:path>")
    def static_proxy(path: str):
        full_path = os.path.join(PROJECT_ROOT, path)
        if os.path.isfile(full_path):
            return send_from_directory(PROJECT_ROOT, path)
        if os.path.isfile(full_path + ".html"):
            return send_from_directory(PROJECT_ROOT, path + ".html")
        return send_from_directory(PROJECT_ROOT, "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
