"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the model adapters NOTED as
they called. Before a request is answered the pill shows ``generator_model`` from ``/healthz``,
so that value must be the model the bound adapter calls, never one a configuration flag names
while the adapter calls another.

This service binds no model port, so its deterministic engine notes nothing and a surveillance
response carries neither header. The route is still proved to carry them the day an adapter
notes something, by standing a noting engine in for the real one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from trade_comms_surveillance import config
from trade_comms_surveillance.api import app as app_module
from trade_comms_surveillance.domain.alert_intake_service import AlertIntakeService
from trade_comms_surveillance.domain.models import AlertInput, SurveillanceCase

from tests import REPO_ROOT
from tests.conftest import local_settings

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"


def _surveil(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    # CI targets run the suite with no profile exported; the served app must still be `local`.
    monkeypatch.setenv("TRADECOMMS_PROFILE", "local")
    client = TestClient(app_module.app, client=("127.0.0.1", 50000))
    response = client.post(
        "/v1/surveil",
        json={"subject": "Acme Holdings (FICTIONAL)", "text": "routine note"},
        headers={"X-Dev-Persona": "analyst"},
    )
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_a_deterministic_answer_names_no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing noted, nothing sent: the pill never invents a model the engine did not call."""
    headers = _surveil(monkeypatch)
    assert ANSWERED_BY not in headers
    assert SEARCH_USED not in headers
    assert local_settings().generator_model == "no-model"


class _AnsweringService(AlertIntakeService):
    """The real engine, plus what a model adapter that searched would note while it called."""

    def assess(self, alert: AlertInput, *, actor: str) -> SurveillanceCase:
        provenance.note_model("fake-answering-model")
        provenance.note_search()
        return super().assess(alert, actor=actor)


def test_the_route_names_the_model_that_answered_and_that_it_searched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "AlertIntakeService", _AnsweringService)
    headers = _surveil(monkeypatch)
    assert headers[ANSWERED_BY] == "fake-answering-model"
    assert headers[SEARCH_USED] == "true"
    # The next request is a fresh record: an answer never leaks into a later response.
    monkeypatch.setattr(app_module, "AlertIntakeService", AlertIntakeService)
    assert ANSWERED_BY not in _surveil(monkeypatch)


def test_generator_model_is_the_setting_the_adapter_reads_and_no_flag_swaps_it() -> None:
    """The latent false banner: a flag that moved the pill but not the model that answered."""
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
