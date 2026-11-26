import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    # Used as a context manager so the app's startup/shutdown code runs, and
    # one event loop is shared by every test (the database pool needs this).
    with TestClient(app) as c:
        yield c