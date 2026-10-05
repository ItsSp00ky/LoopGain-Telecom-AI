import json

from assistants import planning, sources


def _priorities(copilot_data, **arguments):
    candidates = planning.load(sources.CANDIDATES)
    return planning.expansion_priorities(
        planning.load(sources.SHORTLIST),
        planning.load_manifest(sources.MANIFEST),
        int(len(candidates)),
        int(candidates["eligible"].sum()),
        **arguments,
    )


def test_the_shortlist_comes_best_first_with_its_reasons(copilot_data):
    result = _priorities(copilot_data, top_n=2)
    assert result["scope"] == "Tripoli"
    assert result["candidates_checked"] == 4 and result["candidates_eligible"] == 3
    assert result["matched"] == 3 and result["shown"] == 2
    first = result["sites"][0]
    assert first["rank"] == 1 and first["score"] == 66.7
    assert first["components"] == {
        "population": 0.97,
        "gap_to_known_sites": 0.02,
        "road_access": 0.99,
        "terrain": 0.76,
    }
    assert first["reason_codes"] == ["high_population_catchment", "good_road_access"]
    assert first["population_within_5km"] == 68900
    assert "new site or more capacity" in result["limits"]
    assert result["shown_ranges"]["population_within_5km"] == {
        "lowest": 41936,
        "highest": 68900,
    }
    assert result["shown_ranges"]["score"] == {"lowest": 66.4, "highest": 66.7}


def test_a_municipality_narrows_the_list(copilot_data):
    result = _priorities(copilot_data, municipality="aljfara")
    assert [s["rank"] for s in result["sites"]] == [2]


def test_no_operator_named_column_reaches_the_model(copilot_data):
    text = json.dumps(_priorities(copilot_data))
    assert "almadar" not in text.casefold() and "3300" not in text


def test_a_site_is_explained_by_rank_or_by_id_including_a_rejected_one(copilot_data):
    candidates = planning.load(sources.CANDIDATES)
    shortlist = planning.load(sources.SHORTLIST)
    assert planning.explain_location(candidates, shortlist, "2")["municipality"] == "Aljfara"
    rejected = planning.explain_location(candidates, shortlist, "candidate-ddd444")
    assert rejected["eligible"] is False
    assert rejected["rejection_reasons"] == ["too_close_to_known_site"]
    assert planning.explain_location(candidates, shortlist, "candidate-zzz") is None
    assert planning.explain_location(candidates, shortlist, "") is None
