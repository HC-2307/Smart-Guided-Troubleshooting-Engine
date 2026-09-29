import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from backend.services import catalog_index, config_planner
from backend.services.catalog_index import DenseIndex

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = [{"message": "Dark"}, {"message": "Wifi"}, {"message": "Sound"}]
VOCAB = ["dark", "wifi", "sound"]


def fake_encoder(texts):
    return np.array([[1.0 if word in t.lower() else 0.0 for word in VOCAB] for t in texts], dtype=np.float32)


def test_search_ranks_entries_by_cosine_similarity():
    index = DenseIndex()
    assert index.build(ENTRIES, ["dark theme", "wifi network", "sound volume"], encoder=fake_encoder)
    results = index.search("make it dark")
    assert results[0][1]["message"] == "Dark"
    assert results[0][0] == pytest.approx(1.0)


def test_model_load_failure_marks_index_unavailable(monkeypatch):
    index = DenseIndex()
    monkeypatch.setattr(index, "_load_encoder", lambda: (_ for _ in ()).throw(OSError("no network")))
    assert not index.build(ENTRIES, ["a", "b", "c"])
    assert index.status == "unavailable"
    assert index.search("dark") == []


def test_query_encoding_failure_returns_no_results():
    calls = {"n": 0}

    def flaky(texts):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("onnx session crashed")
        return fake_encoder(texts)

    index = DenseIndex()
    index.build(ENTRIES, ["dark", "wifi", "sound"], encoder=flaky)
    assert index.search("dark") == []


def test_disabled_embeddings_do_not_load_a_model(monkeypatch):
    monkeypatch.setattr(catalog_index, "settings", replace(catalog_index.settings, embeddings_enabled=False))
    index = DenseIndex()
    assert not index.build(ENTRIES, ["a", "b", "c"], encoder=fake_encoder)
    assert index.status == "disabled"


def test_catalog_vectors_are_persisted_and_reused(monkeypatch, tmp_path):
    monkeypatch.setattr(catalog_index, "settings", replace(catalog_index.settings, embedding_cache_dir=tmp_path))
    calls = {"n": 0}

    def counting(texts):
        calls["n"] += 1
        return fake_encoder(texts)

    index = DenseIndex()
    index._encoder = counting
    first = index._catalog_matrix(["dark", "wifi"], persist=True)
    second = index._catalog_matrix(["dark", "wifi"], persist=True)
    assert calls["n"] == 1
    assert np.allclose(first, second)
    assert len(list(tmp_path.glob("catalog_vectors_*.npy"))) == 1


def test_planner_falls_back_to_keywords_when_index_is_unavailable(monkeypatch):
    monkeypatch.setattr(config_planner.dense_index, "status", "unavailable")
    assert config_planner.match("change to light mode") is None
    assert config_planner.match("my phone time is in 24 hrs").source == "keyword"


def _dense_ready() -> bool:
    return config_planner.ensure_dense_index()


needs_model = pytest.mark.skipif(not _dense_ready(), reason="embedding model not available offline")


@needs_model
def test_light_mode_maps_to_dark_mode_settings_through_meaning():
    found = config_planner.match("change to light mode")
    assert found is not None and found.source == "dense"
    assert config_planner._key(found.entry) == "Dark mode settings"


@needs_model
def test_settings_evaluation_set_has_no_wrong_plans_and_no_false_plans():
    data = json.loads((ROOT / "evaluation" / "m3_settings_set.json").read_text(encoding="utf-8"))
    wrong, correct = [], 0
    for item in data["settings"]:
        found = config_planner.match(item["query"])
        if found is None:
            continue
        if config_planner._key(found.entry).lower() == item["expect"]:
            correct += 1
        else:
            wrong.append((item["query"], config_planner._key(found.entry)))
    assert wrong == []
    assert correct >= 31
    assert [q for q in data["no_plan"] if config_planner.match(q)] == []
