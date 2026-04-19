"""Convenience launcher: `python run.py` to start the Compass dev server."""
from backend.app import app
from backend.config import config

if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
