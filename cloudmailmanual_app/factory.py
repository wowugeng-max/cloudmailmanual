from __future__ import annotations

import os
import secrets

from flask import Flask

from auth import init_auth_db

from .config import BASE_DIR
from .database import init_db
from .routes import register_routes


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
    )
    app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

    init_db()
    init_auth_db()
    register_routes(app)

    return app
