from assistants import measurements, sources


def _service(copilot_data, **arguments):
    return measurements.measured_service(
        measurements.areas(measurements.load(sources.MEASURED_AREAS)),
        measurements.load(sources.MEASUREMENT_MANIFEST),
        measurements.load(sources.MEASUREMENT_PILOT),
        **arguments,
    )


def test_networks_are_codes_and_areas_have_a_centre(copilot_data):
    rows = measurements.areas(measurements.load(sources.MEASURED_AREAS))
    assert rows[0]["network"] == "606-01" and rows[3]["network"] == "606-00"
    assert (rows[0]["latitude"], rows[0]["longitude"]) == (32.81, 13.01)


def test_the_review_totals_by_network_and_technology(copilot_data):
    result = _service(copilot_data)
    assert result["eligible_readings"] == 45
    assert result["collection_days"] == ["2026-09-23", "2026-09-26"]
    assert result["by_network_and_technology"] == [
        {
            "network": "606-00",
            "technology": "UMTS",
            "areas": 1,
            "readings": 12,
            "median_of_area_medians_dbm": -90.0,
        },
        {
            "network": "606-01",
            "technology": "LTE",
            "areas": 3,
            "readings": 33,
            "median_of_area_medians_dbm": -95.0,
        },
    ]
    assert result["priorities_with_readings_within_5km"] == 0
    assert any("cannot compare networks" in caveat for caveat in result["caveats"])


def test_the_weakest_areas_need_enough_readings(copilot_data):
    weakest = _service(copilot_data)["weakest_areas"]
    # The -120 dBm area has only 3 readings, too few to be shown.
    assert [area["median_dbm"] for area in weakest] == [-95.0, -90.0, -80.0]
    assert [a["median_dbm"] for a in _service(copilot_data, count=1)["weakest_areas"]] == [-95.0]


def test_the_review_filters_by_network_and_technology(copilot_data):
    assert _service(copilot_data, network="606-00")["areas_matched"] == 1
    assert _service(copilot_data, technology="lte")["areas_matched"] == 3
    assert _service(copilot_data, network="606-09")["weakest_areas"] == []


def test_each_ranked_site_gets_its_distance_to_a_reading(copilot_data):
    support = measurements.support_by_site(measurements.load(sources.MEASUREMENT_MANIFEST))
    assert support == {
        "candidate-aaa111": {"nearest_measurement_m": 8035, "readings_within_5km": 0}
    }
