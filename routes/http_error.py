"""
JSON error responses for the API.

FastAPI rendered errors as a JSON body with a single "detail" key; Flask renders
an aborted request as HTML. The helpers below keep the previous error contract
unchanged:

- `{"detail": "<message>"}` for aborted requests, including the ones Flask
  raises on its own (an unmatched route, a disallowed method).
- `{"detail": [<errors>]}`, HTTP 422 Unprocessable Entity, for path parameters
  and request bodies that could not be read or validated. The three `*_detail()`
  builders reproduce, entry for entry, the payloads FastAPI reported for an
  absent body, an unparsable body, and a body that failed Pydantic validation.

`abort_with()` is the direct counterpart of `raise HTTPException(...)`: when no
detail is supplied, the standard reason phrase for the status code is used, just
as FastAPI did.
"""

import json
from http import HTTPStatus
from typing import Any, Dict, List, NoReturn, Optional, Sequence

from flask import Response, abort, jsonify, make_response
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

# Headers that belong to the discarded HTML body rather than to the error itself
_BODY_HEADERS = ("content-type", "content-length")


def abort_with(status_code: int, detail: Optional[str] = None) -> NoReturn:
    """
    Aborts the current request with a JSON error body.

    Args:
        status_code (int): The HTTP status code of the response.
        detail (Optional[str]): The message for the "detail" key. Defaults to
        the standard reason phrase of the status code.

    Raises:
        HTTPException: Always; Flask turns it into the error response.
    """
    abort(status_code, description=detail or HTTPStatus(status_code).phrase)


def abort_unprocessable(detail: List[Dict[str, Any]]) -> NoReturn:
    """
    Aborts the current request with HTTP 422 Unprocessable Entity.

    Args:
        detail (List[Dict[str, Any]]): The error entries, as built by one of the
        `*_detail()` functions below.

    Raises:
        HTTPException: Always; Flask turns it into the error response.
    """
    abort(make_response(jsonify(detail=detail), HTTPStatus.UNPROCESSABLE_ENTITY))


def validation_error_detail(
    error: ValidationError, location: Sequence[str] = ()
) -> List[Dict[str, Any]]:
    """
    Renders Pydantic validation errors as the "detail" of a 422 response.

    Args:
        error (ValidationError): The exception raised by Pydantic.
        location (Sequence[str]): The path prefixed to the "loc" of every error,
        e.g. "body", or "path" and the name of the offending path parameter.

    Returns:
        List[Dict[str, Any]]: One entry per validation error.
    """
    # ValidationError.json() serializes error inputs that json.dumps cannot.
    errors: List[Dict[str, Any]] = json.loads(error.json(include_url=False))
    for reported in errors:
        reported["loc"] = list(location) + list(reported.get("loc", []))
    return errors


def missing_body_detail() -> List[Dict[str, Any]]:
    """
    Renders an absent request body as the "detail" of a 422 response.

    Returns:
        List[Dict[str, Any]]: A single "missing" entry located at the body.
    """
    return [
        {
            "type": "missing",
            "loc": ["body"],
            "msg": "Field required",
            "input": None,
        }
    ]


def invalid_json_detail(error: json.JSONDecodeError) -> List[Dict[str, Any]]:
    """
    Renders an unparsable request body as the "detail" of a 422 response.

    Args:
        error (json.JSONDecodeError): The exception raised while decoding.

    Returns:
        List[Dict[str, Any]]: A single "json_invalid" entry carrying the offset
        at which decoding failed and the decoder's own message.
    """
    return [
        {
            "type": "json_invalid",
            "loc": ["body", error.pos],
            "msg": "JSON decode error",
            "input": {},
            "ctx": {"error": error.msg},
        }
    ]


def handle_http_exception(error: HTTPException) -> Response:
    """
    Renders an aborted request as `{"detail": ...}`.

    Args:
        error (HTTPException): The exception raised by `abort_with()` or by
        Flask itself (e.g. an unmatched route, a disallowed method).

    Returns:
        Response: The JSON error response, keeping any header the exception
        carries (e.g. "Allow" on HTTP 405 Method Not Allowed).
    """
    status_code = error.code or HTTPStatus.INTERNAL_SERVER_ERROR
    detail = error.description
    if detail == type(error).description:
        # Werkzeug's own prose; FastAPI used the standard reason phrase.
        detail = HTTPStatus(status_code).phrase
    response = jsonify(detail=detail)
    response.status_code = status_code
    for name, value in error.get_response().headers.items():
        if name.lower() not in _BODY_HEADERS:
            response.headers[name] = value
    return response
