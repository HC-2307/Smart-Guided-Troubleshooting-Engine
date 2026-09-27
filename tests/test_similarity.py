from backend.services.text_similarity import (
    canonical_tokens,
    catalog_idf,
    facets,
    facets_conflict,
    fingerprint,
    similarity,
)


def test_synonyms_collapse_to_one_concept():
    assert "drain" in canonical_tokens("battery draining")
    assert "drain" in canonical_tokens("phone loses charge")
    assert "drain" in canonical_tokens("battery dies quickly")


def test_charge_failure_is_a_distinct_concept_from_drain():
    tokens = canonical_tokens("my phone won't charge")
    assert "chargefail" in tokens
    assert "drain" not in tokens


def test_device_models_and_filler_words_are_dropped():
    tokens = canonical_tokens("1. My Samsung Galaxy S22 Ultra screen flickers")
    assert tokens == ["screen", "flicker"]


def test_typos_are_corrected_against_domain_vocabulary():
    assert "battery" in canonical_tokens("battry drains")
    assert "bluetooth" in canonical_tokens("bluetoth wont connect")


def test_facets_detect_camera_side_and_radio():
    assert facets("front camera blurry")["camera_side"] == {"front"}
    assert facets("rear camera blurry")["camera_side"] == {"rear"}
    assert facets("mobile data drops")["radio"] == {"mobiledata"}
    assert facets("turn off the floating button")["polarity"] == {"off"}


def test_facet_conflict_only_when_both_sides_specify_the_group():
    assert facets_conflict({"camera_side": {"front"}}, {"camera_side": {"rear"}})
    assert not facets_conflict({"camera_side": {"front"}}, {})
    assert not facets_conflict({"power_issue": {"drain", "chargefail"}}, {"power_issue": {"drain"}})


def test_identical_text_scores_one_and_similarity_is_symmetric():
    a, b = fingerprint("wifi keeps disconnecting"), fingerprint("wi-fi drops all the time")
    assert abs(similarity(a, a) - 1.0) < 1e-9
    assert abs(similarity(a, b) - similarity(b, a)) < 1e-9


def test_paraphrase_scores_higher_than_unrelated_query():
    seed = fingerprint("My phone battery drains really fast")
    paraphrase = fingerprint("battery dying so quickly")
    unrelated = fingerprint("camera photos are blurry")
    assert similarity(seed, paraphrase) > similarity(seed, unrelated)


def test_empty_text_has_zero_similarity():
    assert similarity(fingerprint(""), fingerprint("battery drain")) == 0.0


def test_catalog_idf_is_built_from_trusted_catalog():
    idf = catalog_idf()
    assert len(idf) > 100
    assert all(v > 0 for v in idf.values())
