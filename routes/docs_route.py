"""
OpenAPI schema and interactive documentation routes.

FastAPI served an OpenAPI document plus Swagger UI and ReDoc out of the box.
Flask does not, so the same three endpoints are declared here to keep the public
surface of the service unchanged:

- GET /openapi.json : the OpenAPI 3.1 document.
- GET /docs         : Swagger UI.
- GET /redoc        : ReDoc.

The component schemas are derived from the very Pydantic models used to validate
requests and serialize responses, so the document cannot drift from the
implementation.
"""

import inspect
from http import HTTPStatus
from typing import Any, Callable, Dict

from flask import Blueprint, Response, jsonify

from models.player_model import PlayerRequestModel, PlayerResponseModel
from routes import health_route, player_route

api_blueprint = Blueprint("docs", __name__)

TITLE = "python-samples-flask-restful"
DESCRIPTION = "🧪 Proof of Concept for a RESTful API made with Python 3 and Flask"
VERSION = "1.0.0"

OPENAPI_VERSION = "3.1.0"
OPENAPI_PATH = "/openapi.json"
REF_TEMPLATE = "#/components/schemas/{model}"

SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5"
REDOC_URL = "https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js"

PLAYER_ID_TITLE = "The UUID of the Player"
SQUAD_NUMBER_TITLE = "The Squad Number of the Player"
SUCCESSFUL_RESPONSE = "Successful Response"
UNPROCESSABLE_BODY = "Unprocessable Entity - request body validation failed"

_PLAYER_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {"$ref": REF_TEMPLATE.format(model="PlayerRequestModel")}
        }
    },
}

_PLAYER_RESPONSE = {
    "description": SUCCESSFUL_RESPONSE,
    "content": {
        "application/json": {
            "schema": {"$ref": REF_TEMPLATE.format(model="PlayerResponseModel")}
        }
    },
}

_PLAYER_COLLECTION_RESPONSE = {
    "description": SUCCESSFUL_RESPONSE,
    "content": {
        "application/json": {
            "schema": {
                "type": "array",
                "items": {"$ref": REF_TEMPLATE.format(model="PlayerResponseModel")},
                "title": "Response Retrieves A Collection Of Players",
            }
        }
    },
}

_VALIDATION_ERROR_RESPONSE = {
    "description": "Validation Error",
    "content": {
        "application/json": {
            "schema": {"$ref": REF_TEMPLATE.format(model="HTTPValidationError")}
        }
    },
}

_NO_CONTENT_RESPONSE = {"description": SUCCESSFUL_RESPONSE}

_UNTYPED_RESPONSE = {
    "description": SUCCESSFUL_RESPONSE,
    "content": {"application/json": {"schema": {}}},
}


def _description(view: Callable[..., Any]) -> str:
    """Returns the docstring of a view function, as FastAPI did for descriptions."""
    return inspect.cleandoc(view.__doc__ or "")


def _path_parameter(name: str, title: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Builds the OpenAPI description of a required path parameter."""
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": dict(schema, title=title),
    }


_PLAYER_ID_PARAMETER = _path_parameter(
    "player_id", PLAYER_ID_TITLE, {"type": "string", "format": "uuid"}
)
_SQUAD_NUMBER_PARAMETER = _path_parameter(
    "squad_number", SQUAD_NUMBER_TITLE, {"type": "integer"}
)


def _paths() -> Dict[str, Any]:
    """Builds the "paths" section of the OpenAPI document."""
    return {
        "/players/": {
            "post": {
                "tags": ["Players"],
                "summary": "Creates a new Player",
                "description": _description(player_route.post_player),
                "operationId": "post_player",
                "requestBody": _PLAYER_REQUEST_BODY,
                "responses": {
                    "201": _PLAYER_RESPONSE,
                    "422": {"description": UNPROCESSABLE_BODY},
                },
            },
            "get": {
                "tags": ["Players"],
                "summary": "Retrieves a collection of Players",
                "description": _description(player_route.get_all_players),
                "operationId": "get_all_players",
                "responses": {"200": _PLAYER_COLLECTION_RESPONSE},
            },
        },
        "/players/{player_id}": {
            "get": {
                "tags": ["Players"],
                "summary": "Retrieves a Player by its UUID",
                "description": _description(player_route.get_player_by_id),
                "operationId": "get_player_by_id",
                "parameters": [_PLAYER_ID_PARAMETER],
                "responses": {
                    "200": _PLAYER_RESPONSE,
                    "422": _VALIDATION_ERROR_RESPONSE,
                },
            }
        },
        "/players/squadnumber/{squad_number}": {
            "get": {
                "tags": ["Players"],
                "summary": "Retrieves a Player by its Squad Number",
                "description": _description(player_route.get_player_by_squad_number),
                "operationId": "get_player_by_squad_number",
                "parameters": [_SQUAD_NUMBER_PARAMETER],
                "responses": {
                    "200": _PLAYER_RESPONSE,
                    "422": _VALIDATION_ERROR_RESPONSE,
                },
            },
            "put": {
                "tags": ["Players"],
                "summary": "Updates an existing Player",
                "description": _description(player_route.put_player),
                "operationId": "put_player",
                "parameters": [_SQUAD_NUMBER_PARAMETER],
                "requestBody": _PLAYER_REQUEST_BODY,
                "responses": {
                    "204": _NO_CONTENT_RESPONSE,
                    "422": {"description": UNPROCESSABLE_BODY},
                },
            },
            "delete": {
                "tags": ["Players"],
                "summary": "Deletes an existing Player",
                "description": _description(player_route.delete_player),
                "operationId": "delete_player",
                "parameters": [_SQUAD_NUMBER_PARAMETER],
                "responses": {
                    "204": _NO_CONTENT_RESPONSE,
                    "422": _VALIDATION_ERROR_RESPONSE,
                },
            },
        },
        "/health": {
            "get": {
                "tags": ["Health"],
                "summary": "Health Check",
                "description": _description(health_route.health_check),
                "operationId": "health_check",
                "responses": {"200": _UNTYPED_RESPONSE},
            }
        },
    }


def _component_schemas() -> Dict[str, Any]:
    """Builds the "components.schemas" section of the OpenAPI document."""
    schemas: Dict[str, Any] = {
        model.__name__: model.model_json_schema(ref_template=REF_TEMPLATE)
        for model in (PlayerRequestModel, PlayerResponseModel)
    }
    schemas["ValidationError"] = {
        "title": "ValidationError",
        "type": "object",
        "required": ["loc", "msg", "type"],
        "properties": {
            "loc": {
                "title": "Location",
                "type": "array",
                "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            },
            "msg": {"title": "Message", "type": "string"},
            "type": {"title": "Error Type", "type": "string"},
            "input": {"title": "Input"},
            "ctx": {"title": "Context", "type": "object"},
        },
    }
    schemas["HTTPValidationError"] = {
        "title": "HTTPValidationError",
        "type": "object",
        "properties": {
            "detail": {
                "title": "Detail",
                "type": "array",
                "items": {"$ref": REF_TEMPLATE.format(model="ValidationError")},
            }
        },
    }
    return schemas


def build_openapi_document() -> Dict[str, Any]:
    """
    Builds the OpenAPI document describing the API.

    Returns:
        Dict[str, Any]: The OpenAPI 3.1 document.
    """
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": TITLE,
            "description": DESCRIPTION,
            "version": VERSION,
        },
        "paths": _paths(),
        "components": {"schemas": _component_schemas()},
    }


@api_blueprint.get(OPENAPI_PATH)
def openapi() -> Response:
    """
    Endpoint serving the OpenAPI document of the API.

    Returns:
        Response: The OpenAPI 3.1 document as JSON.
    """
    return jsonify(build_openapi_document())


@api_blueprint.get("/docs")
def swagger_ui() -> Response:
    """
    Endpoint serving the Swagger UI documentation page.

    Returns:
        Response: An HTML page rendering the OpenAPI document.
    """
    html = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{TITLE} - Swagger UI</title>
    <link rel="stylesheet" href="{SWAGGER_UI_URL}/swagger-ui.css" />
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="{SWAGGER_UI_URL}/swagger-ui-bundle.js"></script>
    <script>
      window.onload = () => {{
        window.ui = SwaggerUIBundle({{
          url: "{OPENAPI_PATH}",
          dom_id: "#swagger-ui",
        }});
      }};
    </script>
  </body>
</html>
"""
    return Response(html, status=HTTPStatus.OK, mimetype="text/html")


@api_blueprint.get("/redoc")
def redoc() -> Response:
    """
    Endpoint serving the ReDoc documentation page.

    Returns:
        Response: An HTML page rendering the OpenAPI document.
    """
    html = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{TITLE} - ReDoc</title>
  </head>
  <body>
    <redoc spec-url="{OPENAPI_PATH}"></redoc>
    <script src="{REDOC_URL}"></script>
  </body>
</html>
"""
    return Response(html, status=HTTPStatus.OK, mimetype="text/html")
