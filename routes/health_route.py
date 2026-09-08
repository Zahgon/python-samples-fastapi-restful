"""
Health check API route.

Defines a simple endpoint to verify that the service is up and running.
Returns a JSON response with a "status" key set to "ok".
"""

from typing import Dict

from flask import Blueprint

api_blueprint = Blueprint("health", __name__)


# `strict_slashes=False` accepts both "/health" and "/health/", matching the
# redirect FastAPI performed for the trailing-slash variant.
@api_blueprint.get("/health", strict_slashes=False)
def health_check() -> Dict[str, str]:
    """
    Simple health check endpoint.
    Returns a JSON response with a single key "status" and value "ok".
    """
    return {"status": "ok"}
