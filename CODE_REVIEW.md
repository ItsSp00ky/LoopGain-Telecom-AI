# Code and logic review

Date: 2026-09-20.
Source: `tahaDev` at `bfb28ab`.
Delivery: `Ali_Branch`, replacing its previous tracked CVM tree at the owner's explicit request while preserving history.

## Scope and approach

Reviewed the active prepaid pipeline from CSV ingestion through cleaning, feature windows, training, calibration, release gating, bundle loading, scoring and the operator mapping.
Also reviewed geospatial cleaning, feature extraction, model training, candidate ranking and supplementary demand/cell evidence, plus the legacy churn module and chatbot scaffold.
Changes keep the source branch's pure functions and thin CLI in prepaid, and its existing extractor class, pandas/scipy approach and unittest style in GIS.
No dependencies, model families, feature definitions, business assumptions or frozen thresholds were changed.

## Implemented findings

| Priority | Area | Problem | Change |
|---|---|---|---|
| High | Prepaid ingestion | CSV inference changed `001` into `1` and interpreted text IDs such as `NA` as missing. | Preserve identifier tokens and reject blank subscriber IDs. |
| High | Export contract | Integer coercion truncated fractional tenure/counts/labels; infinities passed numeric checks. | Validate whole numbers before conversion and reject non-finite inputs. |
| High | Recharge recency | Different month ends or recharge years passed validation; the batch mode then produced misleading recency features. | Require a shared calendar month end, matching recharge years and one year across the fixed feature months. |
| High | Cleaning | An extra `no_voice_record` column could override the flag derived from the raw export. | Recompute flags when raw month-end columns are present, retaining cleaning idempotence. |
| High | Bundle integrity | A partial release gate, reordered manifest features or changed thresholds could survive loading; a sample prediction alone did not detect these cases. | Require all four gate checks and all library versions, verify the model checksum before unpickling, then match sample columns, thresholds, calibration and champion identity. |
| Medium | Release metrics | A no-churn evaluation divided by zero; a one-class sample cannot establish discrimination. | Reject a release check without both classes with a clear error. |
| Medium | Calibration | Each candidate was predicted twice and the winner a third time. | Reuse probabilities, reducing five model prediction calls to two for the current benchmark. |
| Medium | Scoring | The active feature matrix and plain-language feature labels were rebuilt repeatedly. | Reuse the active matrix and precompute labels once per scoring call, preserving stable reason order. |
| High | GIS operator distances | Existing sites always skipped the nearest operator site, even when the customer site belonged only to the other operator. | Skip the first neighbor only at the queried location. |
| Medium | GIS cache/input | Replacing the site population retained an absent operator's old tree; invalid coordinates triggered layer loading first. | Clear operator trees on replacement and validate coordinates before loading layers. |
| Medium | GIS density queries | Four per-row loops allocated neighbor lists only to count them. | Use four batched `return_length` queries with identical density counts. |
| High | Site consolidation | KD-tree positions were treated as DataFrame labels, breaking filtered frames; reported distances used the first tower instead of the centroid. | Map positions to index labels, use the projected cluster centroid and replace the shifting list queue with `deque`. |
| Medium | Regional demand | The join discarded the caller's row index; infinite demand was ranked as usable evidence. | Preserve the index and reject non-finite demand values. |
| High | Candidate filtering | An empty strict search relaxed caller limits and could still send an empty frame to estimators. | Respect the requested minimums, validate limits, skip inference for empty results and overwrite stale CSV/GeoJSON outputs with an empty result. |
| Medium | Operator inputs | Invalid conversion scales, card ladders and missing offer families reached arithmetic or array indexing. | Reject invalid market values and missing families with the existing catalogue error type. |
| Medium | GIS artifact paths | Training ignored caller-supplied output directories. | Save models and metrics in the requested directories and create the equipment directory when needed. |

## Validation

- Prepaid: `uv run ruff check`, `uv run ruff format --check` and **170 tests passed** under the locked Python 3.12 environment.
- GIS: `uv run python -m unittest discover -s tests -v`, **21 tests passed** under its separate locked environment.
- The new prepaid regressions produced **21 failures** against the original source, then passed after the fixes.
- GIS regressions reproduced the wrong operator distance, stale tree, lost row index, non-finite demand, filtered-index failure and wrong centroid distance against the original source.
- `churn validate` accepted all **69,999** training-export rows and **30,000** unlabeled-export rows.
- Compared original and reviewed preprocessing on both real exports: all model features are exactly equal in both window A and window B; subscriber IDs agree after text conversion.
- No real-data model was retrained or selected, and the held-out test evaluation was not rerun.
- `git diff --check` passed.

Density microbenchmark: NumPy `default_rng(42)`, 2,500 sites and 20,000 query points uniformly distributed over a 100 km square, radii 1/3/5/10 km, best of three runs on this workstation.
The original per-point loop took **0.551 s**; the batched count queries took **0.138 s**, or **4.00 times faster**, with exact equality of every count.
This measures the neighbor-counting step, not total pipeline speed.

Windows validation redirected pytest's temporary directory into the workspace because the shared system pytest directory was inaccessible in the sandbox.
The GIS suite emits existing affine multiplication deprecation warnings; these do not fail the tests.
Large-scale GIS retraining and a complete map regeneration were not run.

## Compatibility

The input contract now rejects previously accepted malformed exports.
Its fingerprint changed, and saved bundles now need `model_sha256` in their manifest.
Rebuild an older bundle with `uv run churn bundle` from the existing frozen `champion.joblib` and `gate.json`; do not rerun `evaluate` just to upgrade the bundle.
If those artifacts are absent, follow the existing fresh-clone reconstruction procedure without tuning any choice from the spent test window.
The checksum detects corrupt or mismatched local artifacts; it does not authenticate an untrusted pickle.
GIS operator distances and reported collocation distances change where the old values were incorrect.
The optimizer now treats requested minima as hard limits and writes empty exports when no candidate qualifies; it does not relax them automatically.
Model-input density counts and valid prepaid features remain unchanged.

## Remaining findings and recommended next work

These are documented separately because they require a modelling or product decision, a larger contract change, or concern an explicitly retired component.

1. **High: legacy churn metrics and revenue claims are not deployment evidence.**
   `customer_churn_prediction/model_trainer.py` selects the champion by test ROC-AUC, `evaluate.py` tunes its threshold on the test predictions, and the discount engine uses uncalibrated risk with an assumed acceptance rate.
   The branch already rejects this module in prepaid decision 1; its code and historical reports remain untouched.
   Retire the root README's production-ready claims when publishing a platform-level presentation.
2. **High: GIS evaluation needs a spatially separated validation design.**
   The suitability model distinguishes observed sites from synthetic negatives with random stratified folds and a site-reference tree built from the complete population.
   That does not establish generalisation to genuinely unserved locations or RF coverage.
   The final LightGBM also uses different hyperparameters from the cross-validated models.
   Define a held-out geographic evaluation and train/deploy the evaluated configuration before claiming deployment quality.
3. **Medium: GIS raster sampling uses rounded pixel coordinates and square pixel windows as approximate kilometre radii.**
   Verify cell containment, raster CRS and physical window areas before changing this: it alters model inputs and requires rebuilding the committed features/models and their evidence.
4. **Product gap: the chatbot remains a scaffold and the integration API/approval workflow are future tickets.**
   Complete T10/T11/T15/T20 rather than treating this CLI review as an end-to-end deployed retention service.

## Status on 2026-09-27

- The fourth finding is done in the prepaid module: named approvals (T11), the read-only integration service (T15) and the integration guide and check for the chatbot and copilot (T20) exist.
  No chatbot or copilot has called the service yet.
- Findings 1 to 3 concern the legacy churn module and the GIS module, which belong to the team's other parts; they are unchanged and stay with their owners.
- The prepaid figures above are those of 2026-09-20; the module now has 456 tests, and every later change is recorded in `prepaid_churn/docs/decisions.md`.
- The operator's name was removed from this file on 2026-09-27, so that the prepaid module's operator stays unnamed (decision 45).
