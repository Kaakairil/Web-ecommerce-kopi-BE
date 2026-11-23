"""Shared fixtures: mocked Supabase layer for unit tests."""
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def mock_db(monkeypatch):
    """Replace app.supabase_client.db with a MagicMock; returns the mock."""
    m = MagicMock()
    import app.supabase_client as sc

    monkeypatch.setattr(sc, "db", m)
    # routes/models import `db` directly; patch there too as modules register
    return m


@pytest.fixture()
def app(mock_db):
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
