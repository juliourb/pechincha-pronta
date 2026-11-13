import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


@pytest.fixture(autouse=True)
def sem_token(monkeypatch):
    """Os testes nunca usam o token real nem a rede."""
    monkeypatch.delenv("ECONOMIZA_AL_TOKEN", raising=False)
