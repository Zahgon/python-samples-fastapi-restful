"""
API routes for managing Player resources.

Provides CRUD endpoints to create, read, update, and delete Player entities.

Features:
- Caching with in-memory cache to optimize retrieval performance.
- Request-scoped async database session.
- Standard HTTP status codes and error handling.

Endpoints:
- POST /players/                          : Create a new Player.
- GET /players/                           : Retrieve all Players.
- GET /players/<player_id>                : Retrieve Player by UUID
                                            (surrogate key, internal).
- GET /players/squadnumber/<squad_number> : Retrieve Player by Squad Number
                                            (natural key, domain).
- PUT /players/squadnumber/<squad_number> : Update an existing Player.
- DELETE /players/squadnumber/<squad_number> : Delete an existing Player.

The view functions are synchronous, as Flask's WSGI request model requires; the
asynchronous service calls they make are run through `run_async()`.
"""

import json
from http import HTTPStatus
from typing import Any, Dict, Tuple, Union
from uuid import UUID

from aiocache import SimpleMemoryCache
from flask import Blueprint, Response, jsonify, request
from pydantic import TypeAdapter, ValidationError

from async_runner import run_async
from databases.player_database import generate_async_session
from models.player_model import PlayerRequestModel, PlayerResponseModel
from routes.http_error import (
    abort_unprocessable,
    abort_with,
    invalid_json_detail,
    missing_body_detail,
    validation_error_detail,
)
from schemas.player_schema import Player
from services import player_service

api_blueprint = Blueprint("players", __name__)
simple_memory_cache = SimpleMemoryCache()

CACHE_KEY = "players"
CACHE_TTL = 600  # 10 minutes

# Path parameters are validated with the same Pydantic machinery FastAPI used,
# so a malformed value still yields HTTP 422 with the very same error payload.
PLAYER_ID_ADAPTER: TypeAdapter[UUID] = TypeAdapter(UUID)
SQUAD_NUMBER_ADAPTER: TypeAdapter[int] = TypeAdapter(int)

# Helpers ----------------------------------------------------------------------


def no_content() -> Response:
    """
    Builds an empty HTTP 204 No Content response.

    Returns:
        Response: A body-less response; the media type is kept for parity with
        the previous implementation.
    """
    return Response("", status=HTTPStatus.NO_CONTENT, mimetype="application/json")


def read_request_body() -> Union[Any, bytes]:
    """
    Reads the request body the way FastAPI did before validating it.

    The body is decoded as JSON when the request carries no media type, or one
    of "application/json" and "application/<something>+json". Any other media
    type is handed to the model as raw bytes, so that the reported error names
    the body itself rather than a decoding failure.

    Returns:
        Union[Any, bytes]: The decoded JSON payload, or the raw request body.

    Raises:
        HTTPException: HTTP 422 Unprocessable Entity if the body is absent or
        cannot be decoded as JSON.
    """
    body = request.get_data()
    if not body:
        abort_unprocessable(missing_body_detail())
    subtype = request.mimetype.partition("/")[2] if request.mimetype else ""
    # A request that declares no media type is NOT treated as JSON. Starlette
    # parsed a body only when the request said it was JSON, and handing the raw
    # bytes to the model here reproduces the same 422 the source returned -
    # exactly as an explicitly wrong media type (text/plain, form-encoded)
    # already does below.
    is_json = bool(request.mimetype) and (
        request.mimetype.startswith("application/")
        and (subtype == "json" or subtype.endswith("+json"))
    )
    if not is_json:
        return body
    try:
        return json.loads(body)
    except json.JSONDecodeError as error:
        abort_unprocessable(invalid_json_detail(error))


def parse_player_request() -> PlayerRequestModel:
    """
    Validates the JSON request body against the Player request model.

    Returns:
        PlayerRequestModel: The Pydantic model built from the request body.

    Raises:
        HTTPException: HTTP 422 Unprocessable Entity if the body is missing,
        malformed, or fails Pydantic validation.
    """
    try:
        return PlayerRequestModel.model_validate(read_request_body())
    except ValidationError as error:
        abort_unprocessable(validation_error_detail(error, ("body",)))


def parse_uuid(value: str) -> UUID:
    """
    Parses a path parameter as a UUID.

    Args:
        value (str): The raw path parameter.

    Returns:
        UUID: The parsed UUID.

    Raises:
        HTTPException: HTTP 422 Unprocessable Entity if the value is not a
        well-formed UUID.
    """
    try:
        return PLAYER_ID_ADAPTER.validate_python(value)
    except ValidationError as error:
        abort_unprocessable(validation_error_detail(error, ("path", "player_id")))


def parse_squad_number(value: str) -> int:
    """
    Parses a path parameter as a Squad Number.

    Args:
        value (str): The raw path parameter.

    Returns:
        int: The parsed Squad Number.

    Raises:
        HTTPException: HTTP 422 Unprocessable Entity if the value is not a
        well-formed integer.
    """
    try:
        return SQUAD_NUMBER_ADAPTER.validate_python(value)
    except ValidationError as error:
        abort_unprocessable(validation_error_detail(error, ("path", "squad_number")))


def to_response_model(player: Player) -> Dict[str, Any]:
    """
    Serializes a Player ORM object into its camelCase JSON representation.

    Args:
        player (Player): The Player ORM object to serialize.

    Returns:
        Dict[str, Any]: The Player as a JSON-ready dictionary.
    """
    response_model = PlayerResponseModel.model_validate(player)
    return response_model.model_dump(mode="json", by_alias=True)


# POST -------------------------------------------------------------------------


@api_blueprint.post("/players/")
def post_player() -> Tuple[Response, int, Dict[str, str]]:
    """
    Endpoint to create a new player.

    Returns:
        The created Player with its generated UUID, HTTP 201 Created, and a
        Location header pointing at its Squad Number resource.

    Raises:
        HTTPException: HTTP 409 Conflict error if the Player already exists.
        ValidationError: HTTP 422 Unprocessable Entity if request body fails
        Pydantic validation (missing or invalid required fields).
    """
    player_model = parse_player_request()
    async_session = generate_async_session()
    existing = run_async(
        player_service.retrieve_by_squad_number_async(
            async_session, player_model.squad_number
        )
    )
    if existing:
        abort_with(
            HTTPStatus.CONFLICT,
            "A Player with this squad number already exists.",
        )
    player = run_async(player_service.create_async(async_session, player_model))
    if player is None:  # pragma: no cover
        abort_with(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Failed to create the Player due to a database error.",
        )
    run_async(simple_memory_cache.clear(CACHE_KEY))
    location = {"Location": f"/players/squadnumber/{player.squad_number}"}
    return jsonify(to_response_model(player)), HTTPStatus.CREATED, location


# GET --------------------------------------------------------------------------


@api_blueprint.get("/players/")
def get_all_players() -> Tuple[Response, int]:
    """
    Endpoint to retrieve all players.

    Returns:
        A collection of all players, HTTP 200 OK, and an X-Cache header set to
        HIT when the collection was served from the in-memory cache and to MISS
        when it was read from the database.
    """
    players = run_async(simple_memory_cache.get(CACHE_KEY))
    cache_status = "HIT"
    if players is None:
        async_session = generate_async_session()
        players = run_async(player_service.retrieve_all_async(async_session))
        run_async(simple_memory_cache.set(CACHE_KEY, players, ttl=CACHE_TTL))
        cache_status = "MISS"
    response = jsonify([to_response_model(player) for player in players])
    response.headers["X-Cache"] = cache_status
    return response, HTTPStatus.OK


@api_blueprint.get("/players/<player_id>")
def get_player_by_id(player_id: str) -> Tuple[Response, int]:
    """
    Endpoint to retrieve a Player by its UUID.

    Args:
        player_id (str): The UUID of the Player to retrieve.

    Returns:
        The matching Player and HTTP 200 OK.

    Raises:
        HTTPException: HTTP 404 Not Found error if the Player with the specified
        UUID does not exist.
        HTTPException: HTTP 422 Unprocessable Entity if the UUID is malformed.
    """
    identifier = parse_uuid(player_id)
    async_session = generate_async_session()
    player = run_async(player_service.retrieve_by_id_async(async_session, identifier))
    if not player:
        abort_with(HTTPStatus.NOT_FOUND)
    return jsonify(to_response_model(player)), HTTPStatus.OK


@api_blueprint.get("/players/squadnumber/<squad_number>")
def get_player_by_squad_number(squad_number: str) -> Tuple[Response, int]:
    """
    Endpoint to retrieve a Player by its Squad Number.

    Args:
        squad_number (str): The Squad Number of the Player to retrieve.

    Returns:
        The matching Player and HTTP 200 OK.

    Raises:
        HTTPException: HTTP 404 Not Found error if the Player with the specified
        Squad Number does not exist.
        HTTPException: HTTP 422 Unprocessable Entity if the Squad Number is
        malformed.
    """
    number = parse_squad_number(squad_number)
    async_session = generate_async_session()
    player = run_async(
        player_service.retrieve_by_squad_number_async(async_session, number)
    )
    if not player:
        abort_with(HTTPStatus.NOT_FOUND)
    return jsonify(to_response_model(player)), HTTPStatus.OK


# PUT --------------------------------------------------------------------------


@api_blueprint.put("/players/squadnumber/<squad_number>")
def put_player(squad_number: str) -> Response:
    """
    Endpoint to entirely update an existing Player.

    Args:
        squad_number (str): The Squad Number of the Player to update.

    Returns:
        Response: An empty body and HTTP 204 No Content.

    Raises:
        HTTPException: HTTP 400 Bad Request if squad_number in the request body
        does not match the path parameter. The path parameter is the
        authoritative source of identity on PUT; a mismatch makes the request
        semantically ambiguous (not a validation failure).
        HTTPException: HTTP 404 Not Found error if the Player with the specified
        Squad Number does not exist.
        ValidationError: HTTP 422 Unprocessable Entity if request body fails
        Pydantic validation (missing or invalid required fields).
    """
    number = parse_squad_number(squad_number)
    player_model = parse_player_request()
    if player_model.squad_number != number:
        abort_with(HTTPStatus.BAD_REQUEST)
    async_session = generate_async_session()
    player = run_async(
        player_service.retrieve_by_squad_number_async(async_session, number)
    )
    if not player:
        abort_with(HTTPStatus.NOT_FOUND)
    updated = run_async(
        player_service.update_by_squad_number_async(async_session, number, player_model)
    )
    if not updated:  # pragma: no cover
        abort_with(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Failed to update the Player due to a database error.",
        )
    run_async(simple_memory_cache.clear(CACHE_KEY))
    return no_content()


# DELETE -----------------------------------------------------------------------


@api_blueprint.delete("/players/squadnumber/<squad_number>")
def delete_player(squad_number: str) -> Response:
    """
    Endpoint to delete an existing Player.

    Args:
        squad_number (str): The Squad Number of the Player to delete.

    Returns:
        Response: An empty body and HTTP 204 No Content.

    Raises:
        HTTPException: HTTP 404 Not Found error if the Player with the specified
        Squad Number does not exist.
        HTTPException: HTTP 422 Unprocessable Entity if the Squad Number is
        malformed.
    """
    number = parse_squad_number(squad_number)
    async_session = generate_async_session()
    player = run_async(
        player_service.retrieve_by_squad_number_async(async_session, number)
    )
    if not player:
        abort_with(HTTPStatus.NOT_FOUND)
    deleted = run_async(
        player_service.delete_by_squad_number_async(async_session, number)
    )
    if not deleted:  # pragma: no cover
        abort_with(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Failed to delete the Player due to a database error.",
        )
    run_async(simple_memory_cache.clear(CACHE_KEY))
    return no_content()
