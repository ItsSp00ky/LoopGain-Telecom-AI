import json

import numpy as np
import pytest

from prepaid_churn.bundle import (
    MANIFEST_FILE,
    MODEL_FILE,
    BundleError,
    build_bundle,
    load_bundle,
    save_bundle,
)


def _edit_manifest(directory, **changes):
    path = directory / MANIFEST_FILE
    manifest = json.loads(path.read_text("utf-8"))
    manifest.update(changes)
    path.write_text(json.dumps(manifest), "utf-8")


def test_bundle_round_trip(bundle, trained, tmp_path):
    loaded = load_bundle(save_bundle(bundle, tmp_path))
    assert loaded.version == bundle.version
    assert loaded.version.startswith(f"{bundle.champion.name}-2026-09-19-")
    assert loaded.features == bundle.features
    validation = trained["datasets"]["validation"]
    np.testing.assert_array_equal(
        loaded.champion.predict(validation), bundle.champion.predict(validation)
    )


def test_manifest_records_what_a_reader_needs(bundle):
    manifest = bundle.manifest
    for key in ("libraries", "contract_version", "release_gate", "risk_thresholds", "features"):
        assert manifest[key]
    assert set(manifest["libraries"]) == {"scikit-learn", "lightgbm", "numpy", "pandas"}
    json.dumps(manifest)  # plain JSON, readable without unpickling anything


def test_a_failed_gate_is_refused(trained, passing_gate):
    passing_gate["thresholds"]["capture"]["passed"] = False
    passing_gate["passed"] = False
    with pytest.raises(BundleError, match="failed its release gate \\(capture\\)"):
        build_bundle(trained["champion"], passing_gate, trained["datasets"]["validation"], "now")


def test_the_gate_of_another_champion_is_refused(trained, passing_gate):
    passing_gate["chosen_at"] = "2020-01-01"
    with pytest.raises(BundleError, match="another champion"):
        build_bundle(trained["champion"], passing_gate, trained["datasets"]["validation"], "now")


def test_other_library_versions_stop_before_unpickling(bundle, tmp_path):
    save_bundle(bundle, tmp_path)
    _edit_manifest(tmp_path, libraries={"lightgbm": "0.0.1"})
    (tmp_path / MODEL_FILE).unlink()  # proves the manifest is checked before the pickle is read
    with pytest.raises(BundleError, match="lightgbm 0.0.1"):
        load_bundle(tmp_path)


def test_another_data_contract_is_refused(bundle, tmp_path):
    save_bundle(bundle, tmp_path)
    _edit_manifest(tmp_path, contract_version="000000000000")
    with pytest.raises(BundleError, match="another data contract"):
        load_bundle(tmp_path)


def test_a_changed_answer_is_refused(bundle, tmp_path):
    save_bundle(bundle, tmp_path)
    _edit_manifest(tmp_path, sample_probability=bundle.manifest["sample_probability"] + 0.1)
    with pytest.raises(BundleError, match="for its sample row instead of"):
        load_bundle(tmp_path)


def test_a_bundle_that_cannot_predict_is_refused(bundle, tmp_path):
    bundle.sample = bundle.sample.iloc[:, :-1]  # a feature is missing
    save_bundle(bundle, tmp_path)
    with pytest.raises(BundleError, match="loads but cannot predict"):
        load_bundle(tmp_path)


def test_missing_bundle_names_the_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="churn bundle"):
        load_bundle(tmp_path)
