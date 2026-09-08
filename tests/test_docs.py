"""
Tests for the OpenAPI document and the documentation endpoints.

Covers:
- GET /openapi.json
- GET /docs
- GET /redoc

The OpenAPI document is assembled by hand in `routes/docs_route.py`, because
Flask does not derive one from the route signatures the way FastAPI did. These
tests pin it to the application it describes: every registered route must appear
in the document with the same methods, every documented operation must be
registered, and every `$ref` must resolve.
"""

from main import app

# Endpoints that describe the API rather than being part of it
DOCUMENTATION_ENDPOINTS = {"/openapi.json", "/docs", "/redoc"}

# Methods Flask adds to every rule on its own
IMPLICIT_METHODS = {"HEAD", "OPTIONS"}


def _registered_operations() -> set:
    """Return the (path, method) pairs of the API, in OpenAPI path syntax."""
    operations = set()
    for rule in app.url_map.iter_rules():
        path = str(rule).replace("<", "{").replace(">", "}")
        if path in DOCUMENTATION_ENDPOINTS:
            continue
        for method in rule.methods - IMPLICIT_METHODS:
            operations.add((path, method.lower()))
    return operations


def _documented_operations(document: dict) -> set:
    """Return the (path, method) pairs declared by the OpenAPI document."""
    return {
        (path, method)
        for path, operations in document["paths"].items()
        for method in operations
    }


def _references(node) -> set:
    """Return every schema name referenced by a `$ref` anywhere in the document."""
    if isinstance(node, dict):
        found = set()
        for key, value in node.items():
            if key == "$ref":
                found.add(value.rsplit("/", 1)[-1])
            else:
                found |= _references(value)
        return found
    if isinstance(node, list):
        return {name for item in node for name in _references(item)}
    return set()


# GET /openapi.json ------------------------------------------------------------


def test_request_get_openapi_response_status_ok(client):
    """GET /openapi.json returns 200 OK"""
    # Act
    response = client.get("/openapi.json")
    # Assert
    assert response.status_code == 200


def test_request_get_openapi_response_body_documents_every_registered_route(client):
    """GET /openapi.json documents every registered route and no phantom ones"""
    # Act
    document = client.get("/openapi.json").get_json()
    # Assert
    assert _documented_operations(document) == _registered_operations()


def test_request_get_openapi_response_body_every_reference_resolves(client):
    """GET /openapi.json only references schemas it defines"""
    # Act
    document = client.get("/openapi.json").get_json()
    # Assert
    defined = set(document["components"]["schemas"])
    assert _references(document) <= defined


def test_request_get_openapi_response_body_player_schemas_use_camel_case(client):
    """GET /openapi.json describes the Player models with camelCase properties"""
    # Act
    document = client.get("/openapi.json").get_json()
    # Assert
    properties = document["components"]["schemas"]["PlayerResponseModel"]["properties"]
    assert "squadNumber" in properties
    assert "squad_number" not in properties


# GET /docs, GET /redoc --------------------------------------------------------


def test_request_get_docs_response_status_ok(client):
    """GET /docs returns 200 OK with an HTML page"""
    # Act
    response = client.get("/docs")
    # Assert
    assert response.status_code == 200
    assert response.mimetype == "text/html"


def test_request_get_redoc_response_status_ok(client):
    """GET /redoc returns 200 OK with an HTML page"""
    # Act
    response = client.get("/redoc")
    # Assert
    assert response.status_code == 200
    assert response.mimetype == "text/html"
