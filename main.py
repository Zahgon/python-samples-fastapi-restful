"""
Main application module for the Flask RESTful API.

- Sets up the Flask app and its JSON serialization settings.
- Logs application startup.
- Registers API blueprints for player, health and documentation endpoints.
- Registers the JSON error handlers and the database session teardown.

Database migrations are applied by entrypoint.sh before the process starts
(Docker). For local development, run `alembic upgrade head` once before
starting the server.

This serves as the entry point for running the API server.
"""

import logging

from flask import Flask
from werkzeug.exceptions import HTTPException

from databases.player_database import close_async_session
from routes import docs_route, health_route, http_error, player_route

# https://docs.gunicorn.org/en/stable/settings.html#logger-class
GUNICORN_LOGGER = "gunicorn.error"
logger = logging.getLogger(GUNICORN_LOGGER)


def create_app() -> Flask:
    """
    Creates and configures the Flask application.

    Returns:
        Flask: The configured application instance.
    """
    # `static_folder=None`: the service has no static assets, so Flask's default
    # "/static/<filename>" route is not registered.
    flask_app = Flask(__name__, static_folder=None)

    # Preserve the JSON rendering FastAPI produced: fields in declaration order
    # and non-ASCII characters (e.g. "Martínez") emitted verbatim.
    flask_app.json.sort_keys = False
    flask_app.json.ensure_ascii = False

    flask_app.register_blueprint(player_route.api_blueprint)
    flask_app.register_blueprint(health_route.api_blueprint)
    flask_app.register_blueprint(docs_route.api_blueprint)

    # Only HTTPException is handled application-wide: a Pydantic failure is
    # turned into HTTP 422 at the point where the request is parsed, so that a
    # validation error raised anywhere else still surfaces as HTTP 500.
    flask_app.register_error_handler(HTTPException, http_error.handle_http_exception)

    flask_app.teardown_appcontext(close_async_session)

    logger.info("Application startup complete.")
    return flask_app


app = create_app()
