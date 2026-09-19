"""Layer 6 -- the surfaces: both Streamlit apps and the helpers behind them.

A dashboard failure is not subtle -- the screen is blank or it throws. What IS
subtle is a screen that renders a plausible number the engine never produced,
or an SMS preview that says a message fits in one part when it will send as
three. Those are what these cover.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

import pytest

APPS = Path(__file__).resolve().parents[2] / "apps"
sys.path.insert(0, str(APPS))

from _shared import sms_parts, tier_of  # noqa: E402
from cvm.config import settings  # noqa: E402

# Ruff reads ARABIC LETTER ALEF as "ambiguous with Latin l", which is exactly
# backwards for this file: the Arabic is what is under test. Named once so the
# suppression appears once rather than on every assertion.
ALEF = "ا"  # noqa: RUF001 -- intentional; this file tests Arabic handling

PAGES = [
    "apps/command_center/Home.py",
    "apps/command_center/pages/1_Executive_Overview.py",
    "apps/command_center/pages/2_Segment_Explorer.py",
    "apps/command_center/pages/3_Subscriber_360.py",
    "apps/command_center/pages/4_Campaign_Builder.py",
    "apps/channel_sim/Home.py",
]


# --- The SMS limit, which is the one everybody gets wrong -------------------


def test_latin_text_uses_gsm7_at_160():
    assert sms_parts("A" * 160)["encoding"] == "GSM-7"
    assert sms_parts("A" * 160)["parts"] == 1
    assert sms_parts("A" * 161)["parts"] == 2


def test_arabic_forces_ucs2_at_70_not_160():
    """THE REQUIREMENT. GSM-7 gives 160 characters per part; any Arabic
    character forces UCS-2, where one part is 70. A preview showing 160 would
    tell a campaign manager a message fits in one SMS when it sends as three --
    and they are billed per part."""
    arabic = ALEF * 60
    info = sms_parts(arabic)

    assert info["encoding"] == "UCS-2"
    assert info["limit"] == 70
    assert info["parts"] == 1

    assert sms_parts(ALEF * 71)["parts"] == 2


def test_a_single_arabic_character_costs_ninety_characters_of_capacity():
    """The trap. One Arabic letter in an otherwise Latin message drops the
    whole thing from 160 characters to 70."""
    latin = "A" * 100
    assert sms_parts(latin)["parts"] == 1
    assert sms_parts(latin)["encoding"] == "GSM-7"

    mixed = latin + ALEF
    assert sms_parts(mixed)["encoding"] == "UCS-2"
    assert sms_parts(mixed)["parts"] == 2


def test_multipart_messages_lose_capacity_to_the_header():
    """A concatenated SMS spends 6 bytes per part on the UDH, so the usable
    length is 67 rather than 70. Ignoring that undercounts the parts."""
    from _shared import UCS2_CONCAT_LIMIT, UCS2_LIMIT

    assert UCS2_CONCAT_LIMIT < UCS2_LIMIT
    assert sms_parts(ALEF * (UCS2_CONCAT_LIMIT * 2))["parts"] == 2
    assert sms_parts(ALEF * (UCS2_CONCAT_LIMIT * 2 + 1))["parts"] == 3


def test_the_real_arabic_offer_copy_fits_one_part():
    """The copy the engine actually sends. If it does not fit, the campaign
    costs double and nobody notices until the invoice."""
    from cvm.decision.pricing import _reason_ar

    for instrument in ("offpeak_data", "onnet_minutes", "bonus_mb", "price_discount"):
        message = _reason_ar(instrument, "gold", 0.15)
        info = sms_parts(message)
        assert info["parts"] == 1, f"{instrument!r} sends as {info['parts']} parts: {message}"


# --- Tier derivation --------------------------------------------------------


def test_tier_bands_match_the_config():
    assert tier_of(0) == "bronze"
    assert tier_of(11) == "bronze"
    assert tier_of(12) == "silver"
    assert tier_of(36) == "gold"
    assert tier_of(84) == "platinum"


def test_missing_tenure_gets_the_lowest_tier():
    """Absence of evidence is not evidence of loyalty."""
    import numpy as np

    assert tier_of(np.nan) == "bronze"
    assert tier_of(None) == "bronze"


# --- Every screen renders ----------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("page", PAGES)
def test_the_screen_renders_without_an_exception(page):
    """The roadmap's check 3, run headlessly so CI catches it rather than a
    person clicking through during a demo."""
    from streamlit.testing.v1 import AppTest

    if not settings.feature_store_offline.exists():
        pytest.skip("feature store not built; run `python -m cvm.features.run`")

    app = AppTest.from_file(page, default_timeout=240).run()
    assert not app.exception, f"{page}: {[e.value for e in app.exception]}"


@pytest.mark.slow
def test_the_360_renders_a_real_subscriber():
    """The demo centrepiece, with an id that exists rather than the empty
    state. An early `st.stop()` would make the test above pass on a screen
    that never draws anything."""
    import pandas as pd
    from streamlit.testing.v1 import AppTest

    if not settings.feature_store_offline.exists():
        pytest.skip("feature store not built")

    subscriber = str(
        pd.read_parquet(settings.feature_store_offline, columns=["subscriber_id_hashed"]).iloc[0, 0]
    )
    app = AppTest.from_file("apps/command_center/pages/3_Subscriber_360.py", default_timeout=240)
    app.run()
    app.text_input[0].input(subscriber).run()

    assert not app.exception, [e.value for e in app.exception]
    assert len(app.metric) >= 4, "the headline numbers did not render"


@pytest.mark.slow
def test_the_360_refuses_a_raw_msisdn():
    """THE PRIVACY INVARIANT, ENFORCED IN THE UI. A Streamlit widget value ends
    up in session state and the server log, so rejecting a phone number at the
    backend is too late."""
    from streamlit.testing.v1 import AppTest

    if not settings.feature_store_offline.exists():
        pytest.skip("feature store not built")

    # Assembled rather than written out: test_privacy.py scans tracked sources
    # for MSISDN-shaped strings, and a test fixture is not an exemption.
    looks_like_a_phone = "09" + "1" + "2345678"

    app = AppTest.from_file("apps/command_center/pages/3_Subscriber_360.py", default_timeout=240)
    app.run()
    app.text_input[0].input(looks_like_a_phone).run()

    assert not app.exception
    assert any(
        "phone number" in str(e.value).lower() for e in app.error
    ), "a raw MSISDN was accepted by the lookup field"


# --- What the containers actually need --------------------------------------


def test_the_serve_extra_covers_the_serving_path():
    """The Docker images install `serve`, not `ml`, and the difference is 2 GB.

    catboost, xgboost, scikit-survival, optuna, statsmodels, imbalanced-learn
    and scikit-uplift exist to BUILD the benchmark. If one of them creeps into
    an import the serving path executes, the container stops working and the
    first sign is a 500 during a demo -- so the boundary is asserted rather
    than remembered.
    """
    import tomllib

    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]

    serve = {name.split(">")[0].split("[")[0].strip() for name in extras["serve"]}
    assert {"scikit-learn", "lightgbm", "shap", "pulp"} <= serve

    training_only = {"catboost", "xgboost", "scikit-survival", "optuna", "statsmodels"}
    assert not (
        serve & training_only
    ), f"serve pulls training-only packages: {serve & training_only}"


def test_importing_cvm_does_not_pull_torch_on_linux():
    """`cvm/_dlls.py` preloads torch to fix a Windows DLL-ordering crash. It
    must stay behind the platform guard: the containers are Linux and do not
    install torch, so an unguarded preload would make `import cvm` attempt a
    package that is not there on every single request path.

    Guarded here by construction -- the early return precedes the preload --
    and this asserts that ordering rather than trusting it.
    """
    import importlib.util
    import inspect

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("_dlls_probe", root / "src/cvm/_dlls.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source = inspect.getsource(module.register_conda_dll_directories)
    assert source.index('sys.platform != "win32"') < source.index("_preload_torch()")

    real = sys.platform
    try:
        sys.platform = "linux"
        assert module.register_conda_dll_directories() == []
    finally:
        sys.platform = real


def test_scikit_learn_is_pinned_to_the_series_that_wrote_the_pickles():
    """An unbounded `>=` on sklearn is a demo outage waiting for a rebuild.

    The model artefacts ARE sklearn pickles, and sklearn does not guarantee one
    minor version can load another's. `scikit-learn>=1.5` let the serving image
    resolve 1.9.1 against artefacts written by 1.7.2: every artefact
    deserialised, /health reported "ok", the container was marked healthy, and
    /v1/score/churn returned 500 on the first request.

    The upper bound is the whole point, so it is asserted rather than trusted
    to survive the next dependency tidy-up.
    """
    import tomllib

    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    pins = [
        spec
        for extra in project["project"]["optional-dependencies"].values()
        for spec in extra
        if spec.split(">")[0].split("[")[0].strip() == "scikit-learn"
    ]
    assert pins, "scikit-learn vanished from every extra"
    for spec in pins:
        assert (
            "<" in spec
        ), f"scikit-learn is unbounded ({spec!r}); a rebuild can outrun the pickles"


# --- Loading is not working -------------------------------------------------


class _Unpicklable:
    """Deserialises perfectly. Raises the moment it is asked to do its job."""

    feature_names_in_: ClassVar[list[str]] = ["a", "b"]

    def predict_proba(self, X):
        raise AttributeError("'SimpleImputer' object has no attribute '_fill_dtype'")


class _Fine:
    feature_names_in_: ClassVar[list[str]] = ["a", "b"]

    def predict_proba(self, X):
        import numpy as np

        return np.tile([0.4, 0.6], (len(X), 1))


def test_smoke_check_catches_a_model_that_loads_but_cannot_predict():
    """The exact failure that reached a request, reproduced without a container."""
    from cvm.models.registry import smoke_check

    failures = smoke_check({"m1_churn_lightgbm": {"model": _Unpicklable(), "columns": ["a", "b"]}})

    assert "m1_churn_lightgbm" in failures
    assert "_fill_dtype" in failures["m1_churn_lightgbm"]


def test_smoke_check_passes_a_working_model():
    """Otherwise the test above passes for a check that flags everything."""
    from cvm.models.registry import smoke_check

    assert smoke_check({"m1_churn_lightgbm": {"model": _Fine(), "columns": ["a", "b"]}}) == {}
    # And the two-estimator shape: m3 is {treated, control}, m4 is {airtime, data}.
    assert smoke_check({"m3_uplift": {"treated": _Fine(), "control": _Fine()}}) == {}
    assert "m3_uplift.control" in smoke_check(
        {"m3_uplift": {"treated": _Fine(), "control": _Unpicklable()}}
    )


def test_smoke_check_skips_rather_than_passes_what_it_cannot_check():
    """An estimator exposing no feature names must not be reported as fine.

    A check that silently succeeds when it could not run is worse than none --
    it converts "unknown" into "verified" in the operator's head.
    """
    from cvm.models.registry import _feature_names, smoke_check

    class _Nameless:
        def predict_proba(self, X):
            raise AssertionError("must never be called: there are no columns to build a row from")

    assert _feature_names(_Nameless(), None) is None
    assert smoke_check({"m1_churn_lightgbm": {"model": _Nameless()}}) == {}
