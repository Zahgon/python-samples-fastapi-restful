from pathlib import Path
from typing import Any, Generator

import pytest
from alembic import command
from alembic.config import Config
from flask.testing import FlaskClient
from main import app
from tests.player_fake import Player, nonexistent_player

ALEMBIC_CONFIG = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Apply Alembic migrations once before the test session starts."""
    command.upgrade(ALEMBIC_CONFIG, "head")


@pytest.fixture(scope="function")
def client() -> Generator[FlaskClient, None, None]:
    """
    Creates a test client for the Flask app.

    This fixture provides a fresh instance of FlaskClient for each test function,
    ensuring test isolation and a clean request context.

    Yields:
        FlaskClient: A client instance for sending HTTP requests to the Flask app.
    """
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture(scope="function")
def nonexistent_player_in_db(client: Any) -> Generator[Player, None, None]:
    """
    Creates the nonexistent player in the database and removes it on teardown.

    Yields:
        Player: The fake player created in the database.
    """
    player: Player = nonexistent_player()
    client.post("/players/", json=player.__dict__)
    yield player
    client.delete(f"/players/squadnumber/{player.squad_number}")
