# Ahmed's September 29 update: value for the current integration

Reviewed 2026-09-29. This is an assessment and implementation proposal, not a completed merge.

## Decision

There is substantial useful new work. Prioritize the Libya measurement/pilot workflow, source-location reconciliation, and official-statistics audit. Keep the current GIS-v2 terrain implementation. Retain FABDEM and foreign RF work as separate experiments with their actual negative/incomplete results.

The most important additional finding is geographic: **none of the current 20 selected planning points has an eligible supplied handset measurement within 5 km**. Adding these observations gives the project a measured-service review capability, but cannot directly validate or justify reranking this existing shortlist.

## 1. Exact branch state

GitHub branch hashes were checked during this review:

| Branch | Commit | Meaning |
|---|---|---|
| `integration/antenna-planning-v2` | `2eca2dd45c1e8ac0dba496f5825d350dba088368` | Current combined implementation |
| `mahalm_antenna_cell_placement` | `8a2be6c928945ce8c52dba93e975e72aea0123d2` | Original submission branch |
| `ahmed_cell_placement` | `2c48a27494545988561acc4782e6b23530d33af0` | New reviewed Ahmed snapshot |

No local or remote branch named `mah-dev` was found in this repository. If that name refers to a different checkout or repository, its state is not established by this review. The original submission commit is an ancestor of the integration commit, so bringing that exact original branch up to the existing integration is eligible for a fast-forward at the checked state.

Ahmed's earlier integration source was `15dc13a021f12f259319d611dc291ab6de9e4bbe`. His new commit was not part of `2eca2dd`.

No branch was switched, merged, committed or pushed during this review. No work on `tahaDev` or a combined web interface was performed.

## 2. What to take, retain or defer

| Capability | Current situation | Recommendation |
|---|---|---|
| `collected_data.py` | No equivalent measured-service ingestion in the active integrated planner | Port adapters with declared sources, row rejection, deduplication, explicit signal metrics and separate handset/site tables. |
| `pilot.py` | Existing diagnostic hides known sites; it does not evaluate measured service | Add chronological measured-service review as a separate command/output. Keep its source-pinned training/holdout split. |
| `reconciliation.py` and cleaning changes | Current scoped inventory still takes coordinate medians; active planning uses the previously frozen cleaned physical sites | Add conflict groups and alternatives before rebuilding a new inventory. Preserve old-to-new IDs and attribution provenance. |
| `public_evidence.py` | WorldPop units and completeness are checked; no official-population comparison is integrated | Add a source-quality report with unmatched regions and year differences visible. Do not rescale local population automatically. |
| `terrain.py` | Active `gis_v2.GeographicRaster.terrain()` already uses geodesic pixel spacing | Retain current implementation. Ahmed's extra projected-CRS support is potentially useful if a future input needs it; port useful tests, not a wholesale replacement. |
| `fabdem.py` | No integrated terrain-source comparison | Preserve as an optional controlled experiment. Do not replace SRTM based on this report. |
| `foreign_rf.py` | No measurement-based foreign benchmark | Keep as research-method evidence. Its tested distance model was worse than baseline and must not become a Libya predictor. |
| `operator_assets.py` | No authorized sector engineering export is available | Add the schema and aggregate audit when convenient; actual engineering capability remains data-dependent. |

## 3. Libya observations: independently reproduced results

The committed Libya inputs were extracted into an isolated review directory. Collection validation was executed locally:

| Source | Finding |
|---|---|
| Handset logs | 11,335 input rows; 3,622 duplicates; 7,713 retained observations; **4,874 review-eligible observations** |
| CellMapper export | 2,528 input rows; 34 rejected; **2,494 retained sector/cell rows**, representing **538 explicit site identities** |
| BeaconDB | 534 input rows; 531 retained; context only |

Of the 538 CellMapper identities, **202 match the existing scoped inventory and 336 are absent**. This uses normalized network/RAT/region/site identity, not spatial mast confirmation. The 336 must not be advertised as 336 new physical towers. Different identities can share a mast, and source coordinates can conflict.

Using WGS84 geodesic distances:

- Current shortlist with an eligible handset observation within 1 km: **0/20**.
- Current shortlist with an eligible handset observation within 5 km: **0/20**.
- Current shortlist with a retained collected CellMapper reference closer than the existing 3 km gap threshold: **0/20**.

These checks use the existing shortlist only. They do not prove that a full candidate rerun after inventory reconciliation would return the same shortlist.

### Operator and technology imbalance

Eligible LTE observations include **1,938 for MNC 1 (Al-Madar)** and only **28 for MNC 0 (Libyana)**. Al-Madar also has 964 eligible UMTS observations; Libyana has 1,896. The LTE observations cover four days/two device labels for Al-Madar and two days/one device label for Libyana.

This supports separate operator/technology service summaries. It does not support a balanced operator comparison, national coverage estimates, or mixing generic `dbm` with explicit LTE RSRP as one target.

### Pilot reproduction

After the Windows path-only adaptation described below, the existing frozen pilot reproduced:

- Training: September 23-24, 2,975 observations.
- Holdout: September 26 and 28, 1,899 observations.
- Later-day baseline: **74/258 blocks matched (28.68% support)**.
- Matched-block mean absolute error: **7.676 dB**.
- Service summaries: 209 operator/technology/area groups.
- Exact measurement-to-collected-sector identity matches: **0/449**.
- Complete engineering sectors: **0**.
- Conflicting tower identities: **8**; one provisional source-based preference; **zero independently surveyed resolutions**.

The error measures temporal repeatability of an observed-area median. It is not the error of our planning score, our ML classifier, or a calibrated propagation model. The held-out dates are now inspected historical evidence; reserve a genuinely new collection period before claiming a new blind evaluation.

## 4. Corrections to the proposed description

### Terrain spacing is already corrected in our active mix

`planning_features.py` uses `FeatureExtractorV2`, whose `gis_v2.py` calculates slope from ellipsoidal distances between pixel centres. Its 3 km prominence uses geodesic distances, area weights, a full-extent check and at least 99% valid sampled support.

The old fixed-spacing calculation remains in legacy `feature_engineering.py`; it is not the current public planner. Replacing the active sampler would duplicate a fix and could weaken missing-data handling.

### FABDEM is an evaluated alternative, not an established improvement here

Ahmed's committed Step 14 report says `status: remove` and explicitly declines production replacement. It supports 46/50 of his frozen shortlist candidates (92%) and 90.91% of its municipalities, below the declared 95% gates. It has no independent elevation checkpoints or RF reference, and no full candidate rerank.

Its elevation differences do not establish which source is more accurate. The 13 terrain tiles are absent from both the current integration and isolated review folders, so this review inspected the code/report and manifest tests, not a fresh terrain-data experiment.

### Foreign measurements do not establish Libya generalization

Ahmed's committed Chongqing report gives:

| Method | MAE |
|---|---:|
| Per-cell measured median baseline | **7.101 dB** |
| Fitted per-cell distance curve | **7.793 dB** |

The distance curve is **9.75% worse**, with only 436/1,126 held-out blocks scored (38.72%). Its explicit decision is `do_not_use`. This is valuable negative evidence and a useful spatial-holdout method. It does not validate the integrated heuristic, existing-site classifier, Libya RF accuracy, or site placement.

The four manifest-listed foreign source files are absent from the current integration/review folders. These benchmark numbers are Ahmed's committed results, not independently rerun in this review.

## 5. Integration issues found

### A. Frozen pilot fails on Windows with unchanged source bytes — reproduced

`pilot._pilot_split()` builds source keys with `str(path.relative_to(MODULE_DIR))`, while `pilot_snapshot.json` stores forward-slash paths. On Windows, the comparison rejects the snapshot even when every source hash matches.

Fix: canonicalize relative manifest paths with `.as_posix()` wherever they are constructed. Add a cross-platform snapshot regression check. For this review, every original hash was verified before adapting only the keys in a scratch config; source code and original snapshot were not modified.

### B. Ahmed's terrain sampler accepts largely missing neighbourhoods — reproduced

A 101-by-101 synthetic raster was set to nodata except its centre and four slope neighbours. Ahmed's sampler returned `terrain_data_available=True` and `window_complete=True`, even with `require_full_window=True`. The flag checks raster extent, not valid support inside the circle. Our current sampler returned unavailable prominence, causing current strict eligibility to reject it.

Keep the current valid-support requirement in any future shared terrain abstraction. A centre-only/nodata-edge test does not cover this case.

### C. New spatial code reuses a single national UTM zone — source inspection

Collected measurement proximity, pilot nearby-reference checks and conflict grouping call Ahmed's `opencellid.projected()`, which uses `EPSG:32633` for all Libya. The current mix has already moved critical national distances to geodesic calculations/local zones. Port the functionality using our distance policy; do not reintroduce the old national projection assumption.

### D. Protect the 645 owner-confirmed Al-Madar observations

Ahmed's loader/attribution does not include our source-fingerprinted `owner_confirmed_almadar` rule. A wholesale replacement can lose that evidence and alter operator-scoped results. Preserve the 645 source records and their attribution through normalization, conflict grouping and deduplication.

After adding other sources, the number of resulting radio groups is an output to audit, not necessarily an eternal invariant of 645. Keep the immutable source-record invariant, and verify attribution through an explicit record-to-radio-to-site crosswalk.

### E. New data do not automatically enter the active inventory

Our public planner reads locked cleaned inventory files; `inventory_audit_v2.py` is an audit, not a full rebuild of the active physical-site inventory. Adding an adapter or copying Ahmed's `data_cleaning.py` is insufficient.

Build a separate versioned inventory, resolve/flag alternatives, retain a crosswalk to existing IDs, then update the source lock after reviewing differences. Recompute all network distances and operator-specific features for comparison. Keep historical release/model inputs reproducible.

### F. Preserve the integrated runtime contract

Do not replace our CLI, optimizer, source checks or offline map wholesale. Integrate the new commands around them. Extend source locks to the collected inputs and pilot snapshot, record the validation date, and keep optional-source absence distinct from zero evidence.

Use the pilot's equal day/device/spatial-block weighting consistently: `annotate_measurements()` currently uses ordinary per-row medians and can over-weight repeated stationary samples compared with `service_summary()`.

## 6. Official-statistics audit: useful now

The audit was rerun with the existing WorldPop raster and the committed official tables. It matched **19/22 regions**, with approximately **6.276 million** WorldPop 2020 people versus **6.446 million** reported 2022 people in those matched regions (ratio **0.9737**).

This is a useful aggregate consistency check, not proof of local catchment accuracy. Years differ; three regions lack a safe crosswalk; municipality boundaries use pixel-centre assignment. Missing raster support is currently filled with zero in this audit: add valid-area reporting before using regional deficits to diagnose population errors. Keep national technology totals as context only.

## 7. Recommended implementation sequence

### Step 1 — Reconcile the working branch and preserve the release

Use the existing integrated commit as the baseline. If the target is `mahalm_antenna_cell_placement`, it can fast-forward at the reviewed state. If `mah-dev` is a different checkout, identify it first. Preserve the unrelated untracked `INTEGRATION_HANDOFF.md` in the original checkout.

### Step 2 — Add measured-service review independently of ranking

Port collected-data validation, chronological pilot, service summaries and data-request outputs. Fix portable snapshot paths and geodesic proximity. Add operator/RAT filters, sample/day/device/block support and explicit signal type to an offline map overlay. Handset coordinates remain measurement locations.

Acceptance: reproduce the frozen counts/split, reject changed source bytes, preserve training/holdout separation, display no-data areas honestly, and demonstrate that adding the context layer alone does not change primary scores.

### Step 3 — Upgrade inventory reconciliation

Port conflict grouping and the review ledger using network-scoped identities, source fingerprints and geodesic distances. Preserve owner attribution and source verification as separate concepts. Review uncertain alternatives; do not silently use a midpoint as a real mast or treat every alternative as independently confirmed.

Acceptance: source-to-site crosswalk, retained conflict alternatives, attributable changes in inventory/eligibility/shortlist, 645 historical records preserved, and same-candidate population/gap/heuristic comparisons after rebuilding network features. Compare inclusion/exclusion of uncertain references to expose ranking sensitivity.

### Step 4 — Add evidence audits and conditional engineering inputs

Add the official-statistics report and operator export templates/readiness audit. Keep authorized engineering rows out of public map exports. Keep FABDEM and foreign RF commands under an optional research workflow with reproducible dependencies and verified source manifests.

### Step 5 — Collect the evidence our actual shortlist lacks

Plan field routes around shortlisted areas, recording comparable serving-cell identities and explicit metrics for both operators over additional days/devices. Freeze the next test period before developing a measured-service model. Use the pilot data request for surveyed coordinates and sector engineering parameters.

For ML, these observations support a future service-measurement prediction task. They are not new positive/negative labels for antenna placement, and should not simply be appended to the existing-site classifier. New inventory changes also require a newly documented model evaluation; the historical AUC remains tied to its original snapshot.

## 8. Validation scope and evidence

This review exercised **30 focused Ahmed test cases**. Initially, 27 passed and three encountered missing inputs. After supplying the already-available WorldPop raster in the isolated folder, the official-source test passed: **28 distinct tests passed; two foreign-RF tests remain unexecuted successfully because their source files are absent**. This is not a claim that Ahmed's entire branch or a future combined build passes.

Additional local checks reproduced source hashes, collection counts, the chronological pilot (with the documented path-only adaptation), official statistics, the terrain missing-support issue, current-shortlist measurement proximity, and CellMapper identity overlap.

Local review evidence (outside the repository):

- `C:/Users/LED/Desktop/GIS/ahmed_latest_review/reproduced/review_results.json`
- `C:/Users/LED/Desktop/GIS/ahmed_latest_review/reproduced/inventory_overlap.json`
- `C:/Users/LED/Desktop/GIS/ahmed_latest_review/reproduced/collections.json`
- `C:/Users/LED/Desktop/GIS/ahmed_latest_review/reproduced/pilot_windows_paths/`
- `C:/Users/LED/Desktop/GIS/ahmed_latest_review/reproduced/public_evidence.json`
- Reproduction scripts: `ahmed_latest_review/reproduce_review.py` and `compare_inventory.py`.

Source references:

- [Current integrated GIS](../src/antenna_cell_placement/gis_v2.py), [inventory audit](../src/antenna_cell_placement/inventory_audit_v2.py), [pipeline](../src/antenna_cell_placement/planning_pipeline.py).
- [Ahmed's reviewed commit](https://github.com/ItsSp00ky/LoopGain-Telecom-AI/commit/2c48a27494545988561acc4782e6b23530d33af0).
- At that commit: `src/antenna_cell_placement/{terrain,collected_data,reconciliation,pilot,public_evidence,fabdem,foreign_rf,operator_assets}.py`, their tests, `pilot_snapshot.json`, and the matching `eval_reports` artifacts.

The implementation adds genuinely useful evidence workflows. The immediate gain is more reliable source handling and measured service review; demonstrated improvement in recommended deployment outcomes remains a separate, unfulfilled evaluation goal.
