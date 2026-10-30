import json
from pathlib import Path
from unittest.mock import patch

import pytest

from container import invoke
from runner.model_catalog import pinned_model_catalog

FIXTURE = Path(__file__).parent / "fixtures" / "models-catalog.json"


def test_explicit_catalog_is_snapshotted_and_validated(tmp_path):
    source = tmp_path / "catalog.json"
    source.write_bytes(FIXTURE.read_bytes())

    with pinned_model_catalog(source) as snapshot:
        expected = snapshot.read_bytes()
        source.write_text("{}", encoding="utf-8")
        assert snapshot.read_bytes() == expected
        assert snapshot.stat().st_mode & 0o222 == 0


def test_explicit_path_takes_precedence_over_environment_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCODE_EVAL_RUNNER_MODELS", str(tmp_path / "missing.json"))

    with pinned_model_catalog(FIXTURE) as snapshot:
        assert snapshot.read_bytes() == FIXTURE.read_bytes()


def test_default_download_is_one_bounded_request_and_keeps_original_bytes(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, _size):
            nonlocal sent
            if sent:
                return b""
            sent = True
            return FIXTURE.read_bytes()

    sent = False
    opener = patch("runner.model_catalog.urllib.request.urlopen", return_value=Response())
    with (
        patch.dict("os.environ", {"OPENCODE_EVAL_RUNNER_MODELS": ""}),
        opener as mocked,
        pinned_model_catalog() as snapshot,
    ):
        assert snapshot.read_bytes() == FIXTURE.read_bytes()
    mocked.assert_called_once()
    assert mocked.call_args.kwargs["timeout"] == 10
    assert mocked.call_args.args[0].get_header("User-agent") == "opencode-eval-runner/1"


def test_invalid_catalog_is_rejected_before_snapshot_yield(tmp_path):
    source = tmp_path / "bad.json"
    source.write_text(json.dumps({"provider": {
        "id": "provider", "name": "P", "env": [], "npm": "provider/pkg", "models": [],
    }}))

    with pytest.raises(TypeError, match="models object"), pinned_model_catalog(source):
        pytest.fail("invalid catalog was yielded")


def test_current_discriminated_reasoning_options_are_accepted(tmp_path):
    source = tmp_path / "catalog.json"
    source.write_bytes(FIXTURE.read_bytes())

    with pinned_model_catalog(source) as snapshot:
        catalog = json.loads(snapshot.read_text(encoding="utf-8"))
    options = catalog["fixture"]["models"]["fixture/model"]["reasoning_options"]
    assert options == [
        {"type": "effort", "values": ["low", "high"]},
        {"type": "toggle"},
        {"type": "budget_tokens", "min": 0, "max": 262144},
    ]


def test_malformed_discriminated_reasoning_option_is_rejected(tmp_path):
    source = tmp_path / "catalog.json"
    source.write_text(json.dumps({"provider": {
        "id": "provider", "name": "P", "env": [], "npm": "provider/pkg", "models": {
            "model": {"id": "model", "name": "M", "release_date": "2026-01-01",
                      "limit": {"context": 10, "output": 2},
                      "reasoning_options": [{"type": "effort", "values": [3]}]},
        },
    }}))

    with pytest.raises(ValueError, match="reasoning options"), pinned_model_catalog(source):
        pytest.fail("invalid reasoning option was yielded")


def test_catalog_missing_222_native_model_fields_is_rejected(tmp_path):
    source = tmp_path / "catalog.json"
    source.write_text(json.dumps({"provider": {
        "id": "provider", "name": "P", "env": [], "npm": "provider/pkg", "models": {
            "model": {"id": "model", "limit": {"context": 10, "output": 2}},
        },
    }}))

    with pytest.raises(TypeError, match="name, release_date"), pinned_model_catalog(source):
        pytest.fail("catalog missing native 2.2.2 fields was yielded")


def test_effort_values_accept_native_null_and_preserve_source_bytes(tmp_path):
    source = tmp_path / "catalog.json"
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["fixture"]["models"]["fixture/model"]["reasoning_options"] = [
        {"type": "effort", "values": ["low", None, "high"]}
    ]
    raw = json.dumps(value).encode("utf-8")
    source.write_bytes(raw)

    with pinned_model_catalog(source) as snapshot:
        assert snapshot.read_bytes() == raw
        assert json.loads(snapshot.read_bytes())["fixture"]["models"]["fixture/model"]["reasoning_options"][0]["values"] == ["low", None, "high"]


def test_effort_option_requires_values_array(tmp_path):
    source = tmp_path / "catalog.json"
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["fixture"]["models"]["fixture/model"]["reasoning_options"] = [{"type": "effort"}]
    source.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="reasoning options"), pinned_model_catalog(source):
        pytest.fail("effort option without values was yielded")


def test_runtime_environment_selects_readonly_catalog_and_disables_fetch(tmp_path, monkeypatch):
    real_path = Path

    def mapped_path(value):
        if str(value) == "/seed/models.json":
            return FIXTURE
        if str(value) == "/tmp/runtime":
            return tmp_path / "runtime"
        return real_path(value)

    monkeypatch.setattr(invoke, "Path", mapped_path)
    monkeypatch.setenv("OPENCODE_MODELS_PATH", "/host/override.json")
    monkeypatch.setenv("OPENCODE_DISABLE_MODELS_FETCH", "0")

    env = invoke.prepare_opencode_env()

    assert env["OPENCODE_MODELS_PATH"] == "/seed/models.json"
    assert env["OPENCODE_DISABLE_MODELS_FETCH"] == "1"
    assert not (tmp_path / "runtime" / "cache" / "opencode" / "models.json").exists()
