"""
Test suite for the /players/ API endpoints.

Covers:
- GET    /health/
- GET    /players/
- GET    /players/{player_id}
- GET    /players/squadnumber/{squad_number}
- POST   /players/
- PUT    /players/squadnumber/{squad_number}
- DELETE /players/squadnumber/{squad_number}

Validates:
- Status codes, response bodies, headers (e.g., X-Cache)
- Handling of existing, nonexistent, and malformed requests
- Conflict and edge case behaviors
"""

from uuid import UUID

from tests.player_fake import (
    existing_player,
    nonexistent_player,
    unknown_player,
)

PATH = "/players/"


def _is_valid_uuid(value: str) -> bool:
    """Return True if value is a well-formed UUID string, False otherwise."""
    try:
        UUID(value)
        return True
    except ValueError:
        return False


# GET /health/ -----------------------------------------------------------------


def test_request_get_health_response_status_ok(client):
    """GET /health/ returns 200 OK"""
    # Act
    response = client.get("/health/")
    # Assert
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


# GET /players/ ----------------------------------------------------------------


def test_request_get_players_response_header_cache_miss(client):
    """GET /players/ initial request returns X-Cache: MISS"""
    # Act
    response = client.get(PATH)
    # Assert
    assert "X-Cache" in response.headers
    assert response.headers.get("X-Cache") == "MISS"


def test_request_get_players_response_header_cache_hit(client):
    """GET /players/ subsequent request returns X-Cache: HIT"""
    # Act
    client.get(PATH)  # initial
    response = client.get(PATH)  # subsequent (cached)
    # Assert
    assert "X-Cache" in response.headers
    assert response.headers.get("X-Cache") == "HIT"


def test_request_get_players_response_status_ok(client):
    """GET /players/ returns 200 OK"""
    # Act
    response = client.get(PATH)
    # Assert
    assert response.status_code == 200


def test_request_get_players_response_body_each_player_has_uuid(client):
    """GET /players/ returns players each containing a UUID id field"""
    # Act
    response = client.get(PATH)
    # Assert
    players = response.get_json()
    assert all(
        _is_valid_uuid(player["id"]) for player in players
    )  # UUID v5 (migration-seeded)


# GET /players/{player_id} -----------------------------------------------------


def test_request_get_player_id_unknown_response_status_not_found(client):
    """GET /players/{player_id} with unknown UUID returns 404 Not Found"""
    # Arrange
    player_id = unknown_player().id
    # Act
    response = client.get(PATH + str(player_id))
    # Assert
    assert response.status_code == 404


def test_request_get_player_id_existing_response_status_ok(client):
    """GET /players/{player_id} with existing ID returns 200 OK"""
    # Arrange
    player_id = existing_player().id
    # Act
    response = client.get(PATH + str(player_id))
    # Assert
    assert response.status_code == 200


def test_request_get_player_id_existing_response_body_player_match(client):
    """GET /players/{player_id} with existing ID returns matching player"""
    # Arrange
    player_id = existing_player().id
    # Act
    response = client.get(PATH + str(player_id))
    # Assert
    player = response.get_json()
    assert player["id"] == str(player_id)


# GET /players/squadnumber/{squad_number} --------------------------------------


def test_request_get_player_squadnumber_nonexistent_response_status_not_found(client):
    """GET /players/squadnumber/{squad_number} with nonexistent number returns 404 Not Found"""
    # Arrange
    squad_number = nonexistent_player().squad_number
    # Act
    response = client.get(PATH + "squadnumber" + "/" + str(squad_number))
    # Assert
    assert response.status_code == 404


def test_request_get_player_squadnumber_existing_response_status_ok(client):
    """GET /players/squadnumber/{squad_number} with existing number returns 200 OK"""
    # Arrange
    squad_number = existing_player().squad_number
    # Act
    response = client.get(PATH + "squadnumber" + "/" + str(squad_number))
    # Assert
    assert response.status_code == 200


def test_request_get_player_squadnumber_existing_response_body_player_match(client):
    """GET /players/squadnumber/{squad_number} with existing number returns matching player"""
    # Arrange
    squad_number = existing_player().squad_number
    # Act
    response = client.get(PATH + "squadnumber" + "/" + str(squad_number))
    # Assert
    player = response.get_json()
    assert player["squadNumber"] == squad_number


# POST /players/ ---------------------------------------------------------------


def test_request_post_player_body_empty_response_status_unprocessable(client):
    """POST /players/ with empty body returns 422 Unprocessable Entity"""
    # Act
    response = client.post(PATH, json={})
    # Assert
    assert response.status_code == 422


def test_request_post_player_body_existing_response_status_conflict(client):
    """POST /players/ with existing player returns 409 Conflict"""
    # Arrange
    player = existing_player()
    # Act
    response = client.post(PATH, json=player.__dict__)
    # Assert
    assert response.status_code == 409


def test_request_post_player_body_existing_response_body_detail(client):
    """POST /players/ with existing player returns 409 with detail message"""
    # Arrange
    player = existing_player()
    # Act
    response = client.post(PATH, json=player.__dict__)
    # Assert
    assert (
        response.get_json()["detail"]
        == "A Player with this squad number already exists."
    )


def test_request_post_player_body_nonexistent_response_status_created(client):
    """POST /players/ with nonexistent player returns 201 Created with a valid UUID"""
    # Arrange
    player = nonexistent_player()
    try:
        # Act
        response = client.post(PATH, json=player.__dict__)
        # Assert
        assert response.status_code == 201
        body = response.get_json()
        assert "id" in body
        assert UUID(body["id"]).version == 4  # UUID v4 (API-created)
    finally:
        # Teardown — remove the created player
        client.delete(PATH + "squadnumber/" + str(player.squad_number))


# PUT /players/squadnumber/{squad_number} --------------------------------------


def test_request_put_player_squadnumber_existing_body_empty_response_status_unprocessable(
    client,
):
    """PUT /players/squadnumber/{squad_number} with empty body returns 422 Unprocessable Entity"""
    # Arrange
    squad_number = existing_player().squad_number
    # Act
    response = client.put(PATH + "squadnumber/" + str(squad_number), json={})
    # Assert
    assert response.status_code == 422


def test_request_put_player_squadnumber_unknown_response_status_not_found(client):
    """PUT /players/squadnumber/{squad_number} with unknown number returns 404 Not Found"""
    # Arrange
    squad_number = unknown_player().squad_number
    player = unknown_player()
    # Act
    response = client.put(
        PATH + "squadnumber/" + str(squad_number), json=player.__dict__
    )
    # Assert
    assert response.status_code == 404


def test_request_put_player_squadnumber_existing_response_status_no_content(client):
    """PUT /players/squadnumber/{squad_number} with existing number returns 204 No Content"""
    # Arrange
    squad_number = existing_player().squad_number
    player = existing_player()
    player.first_name = "Emiliano"
    player.middle_name = None
    try:
        # Act
        response = client.put(
            PATH + "squadnumber/" + str(squad_number), json=player.__dict__
        )
        # Assert
        assert response.status_code == 204
    finally:
        # Teardown — restore Damián Martínez to its seeded state
        seed = existing_player()
        client.put(PATH + "squadnumber/" + str(seed.squad_number), json=seed.__dict__)


def test_request_put_player_squadnumber_mismatch_response_status_bad_request(client):
    """PUT /players/squadnumber/{squad_number} with mismatched squad number in body returns 400 Bad Request"""
    # Arrange
    squad_number = existing_player().squad_number
    player = existing_player()
    player.squad_number = unknown_player().squad_number
    # Act
    response = client.put(
        PATH + "squadnumber/" + str(squad_number), json=player.__dict__
    )
    # Assert
    assert response.status_code == 400


# DELETE /players/squadnumber/{squad_number} -----------------------------------


def test_request_delete_player_squadnumber_unknown_response_status_not_found(client):
    """DELETE /players/squadnumber/{squad_number} with unknown number returns 404 Not Found"""
    # Arrange
    squad_number = unknown_player().squad_number
    # Act
    response = client.delete(PATH + "squadnumber/" + str(squad_number))
    # Assert
    assert response.status_code == 404


def test_request_delete_player_squadnumber_existing_response_status_no_content(
    client, nonexistent_player_in_db
):
    """DELETE /players/squadnumber/{squad_number} with existing number returns 204 No Content"""
    # Arrange
    player = nonexistent_player_in_db
    # Act
    response = client.delete(PATH + "squadnumber/" + str(player.squad_number))
    # Assert
    assert response.status_code == 204


def test_request_post_player_body_nonexistent_response_header_location(client):
    """POST /players/ with nonexistent player returns 201 with Location header"""
    # Arrange
    player = nonexistent_player()
    try:
        # Act
        response = client.post(PATH, json=player.__dict__)
        # Assert
        assert response.status_code == 201
        assert "Location" in response.headers
        assert (
            response.headers["Location"]
            == f"/players/squadnumber/{player.squad_number}"
        )
    finally:
        client.delete(PATH + "squadnumber/" + str(player.squad_number))


# Request validation ------------------------------------------------------------
# These paths replace validation FastAPI performed before a handler was reached.


def test_request_get_player_id_malformed_response_status_unprocessable(client):
    """GET /players/{player_id} with a malformed UUID returns 422 Unprocessable Entity"""
    # Act
    response = client.get(PATH + "not-a-uuid")
    # Assert
    assert response.status_code == 422
    detail = response.get_json()["detail"]
    assert detail[0]["type"] == "uuid_parsing"
    assert detail[0]["loc"] == ["path", "player_id"]


def test_request_get_player_squadnumber_malformed_response_status_unprocessable(client):
    """GET /players/squadnumber/{squad_number} with a non-integer returns 422 Unprocessable Entity"""
    # Act
    response = client.get(PATH + "squadnumber/abc")
    # Assert
    assert response.status_code == 422
    detail = response.get_json()["detail"]
    assert detail[0]["type"] == "int_parsing"
    assert detail[0]["loc"] == ["path", "squad_number"]


def test_request_post_player_body_absent_response_status_unprocessable(client):
    """POST /players/ with no body returns 422 Unprocessable Entity"""
    # Act
    response = client.post(PATH, content_type="application/json")
    # Assert
    assert response.status_code == 422
    detail = response.get_json()["detail"]
    assert detail[0]["type"] == "missing"
    assert detail[0]["loc"] == ["body"]


def test_request_post_player_body_malformed_json_response_status_unprocessable(client):
    """POST /players/ with unparsable JSON returns 422 Unprocessable Entity"""
    # Act
    response = client.post(PATH, data="{oops", content_type="application/json")
    # Assert
    assert response.status_code == 422
    detail = response.get_json()["detail"]
    assert detail[0]["type"] == "json_invalid"
    assert detail[0]["msg"] == "JSON decode error"


def test_request_post_player_body_not_json_media_type_response_status_unprocessable(
    client,
):
    """POST /players/ with a non-JSON media type returns 422 Unprocessable Entity"""
    # Act
    response = client.post(PATH, data='{"firstName": "A"}', content_type="text/plain")
    # Assert
    assert response.status_code == 422
    detail = response.get_json()["detail"]
    assert detail[0]["loc"] == ["body"]


def test_request_post_player_body_missing_fields_response_body_locations(client):
    """POST /players/ reports each missing required field under the body location"""
    # Act
    response = client.post(PATH, json={})
    # Assert
    detail = response.get_json()["detail"]
    locations = {tuple(error["loc"]) for error in detail}
    assert ("body", "firstName") in locations
    assert ("body", "squadNumber") in locations


def test_request_delete_player_squadnumber_malformed_response_status_unprocessable(
    client,
):
    """DELETE /players/squadnumber/{squad_number} with a non-integer returns 422 Unprocessable Entity"""
    # Act
    response = client.delete(PATH + "squadnumber/abc")
    # Assert
    assert response.status_code == 422


def test_request_get_unknown_route_response_status_not_found(client):
    """GET an unmapped path returns 404 Not Found as JSON"""
    # Act
    response = client.get("/nope")
    # Assert
    assert response.status_code == 404
    assert response.get_json()["detail"] == "Not Found"


def test_request_patch_player_squadnumber_response_status_method_not_allowed(client):
    """PATCH /players/squadnumber/{squad_number} returns 405 Method Not Allowed as JSON"""
    # Arrange
    squad_number = existing_player().squad_number
    # Act
    response = client.patch(PATH + "squadnumber/" + str(squad_number))
    # Assert
    assert response.status_code == 405
    assert response.get_json()["detail"] == "Method Not Allowed"
    assert "Allow" in response.headers
