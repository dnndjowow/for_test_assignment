import json

import pytest
from fastapi.testclient import TestClient

from app.config import BASE_DIR
from app.main import app
from app.schemas.product import CardDraft, ProductInput


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch):
    for name in ['OPENROUTER_API_KEY', 'OPENROUTER_MODEL', 'OPENROUTER_TIMEOUT', 'OPENROUTER_REASONING']:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def product():
    path = BASE_DIR / 'examples' / 'manometer.json'
    return ProductInput.model_validate_json(path.read_text(encoding='utf-8'))


@pytest.fixture
def draft():
    path = BASE_DIR / 'examples' / 'results' / 'manometer.json'
    card = json.loads(path.read_text(encoding='utf-8'))['card']
    card.pop('characteristics')
    return CardDraft(**card, conflicts=[])
