# Tickets

Work plan for the prepaid churn module.
Pick a ticket by writing your name in its **Owner** field.
A ticket is done only when its acceptance criteria pass and `ruff check`, `ruff format --check` and `pytest` are green.
The reasons behind every decision are in [docs/decisions.md](docs/decisions.md).

## Handoff

Update this section at the end of every working session.

**Last updated:** 2026-09-26 by Ali (step-by-step recap of the module, now at T10; prior notes retained).

**Ali's step-by-step recap, 2026-09-25 and 2026-09-26**

- Ali is walking through the module from T1, confirming or changing each step; every change goes to `Ali_Branch` only.
- Steps 1 to 3 changed wording, not results: T1 now leads with the finding that shapes the product, decision 1 leads with the dataset mismatch, and decision 5 states the four-month trade-off.
- Step 4 (T4) added error bars on the frozen test numbers with `churn uncertainty` (decision 35), which changes no model and reproduces `evaluation_all.md` exactly.
  The champion's lead over the baseline held in all 2,000 resamples, and all four release checks pass at the unfavourable end of their intervals.
- Step 4 also settled `--high-value`: it stays as a comparison with the upGrad case study, the product never uses it, and it must not be evaluated on the spent test window (decision 36).
  T4 now says 107 window features, with the 126 of `dataset_all.md` explained by T5's 19.
- Step 5 (T5) changed text only: the two share descriptions in `features.py` now say what the data shows, and T5 answers its own open question (the four share features carry 3.0% of the gain).
- Step 6 (T6) found that the model's top signal is partly temporary absence: roamers are 52% of the churners, and 26% of customers silent in month 8 were active again in month 9.
  That is now a model card limitation, and the early-stopping change T6 made without a decision entry is recorded as decision 37.
- Step 7 (T7) found that the calibration check only sees the average, where two errors cancel; the largest miss is in the low band, which holds 24% of the leavers and gets no offer.
  The model card no longer claims more than the average shows, and decision 38 sets a fifth check, on the high and medium bands, for the next model before it is tested.
- Step 8 (T8) found that the contract and the scorer only accept June to August exports, so an operator's current base cannot be scored as it is.
  That is now a model card limitation, a T8 finding and the open ticket T22.
  Low-band customers no longer get "reasons for churn" that read as warning signs: only high and medium ones do, and a low one gets one plain line (decision 40).
- Step 9 (T9): CLAUDE.md still told every session to work on `tahaDev`; it now says Ali works on `Ali_Branch` only and Taha's work arrives by merge (decision 39).
  Taha's `f2cc724` on `tahaDev` (a session log and presentation material) is not merged yet.
  The README rebuild now writes every committed report except the three research ones, and a fresh clone ran it on 2026-09-26 with `git status` empty.
  The model card, T9 and the brief say exactly what was reproduced, and a test checks the uncertainty ranges the card quotes.
- Step 10 (T10) found, on the validation customers, that the 12-month value's constant-risk and no-comeback assumptions do not hold, which undervalues high-risk customers in T11 (decision 41).
  That is written into the tiers report, the model card and T10, and T23 is open for the fix; no number changed.
- Validation: 436 tests pass with 1 skipped (T12's LSTM, which needs the `experiments` group); lint and formatting green.
- Next: step 11, T11 retention decisions.

**Ali's branch sync, 2026-09-22**

- Merged `origin/tahaDev` through `d38377d`, preserving its commit history and all of the Ali readiness fixes.
- Taha's campaign picker, single-load snapshots, campaign and subscriber proposal controls, and Released screen are included.
  The approval controls retain an explicit review-all checkbox and refuse an empty selection.
- Both branches added decision 31 independently; the Mix catalogue decision stays 31 and Taha's dashboard decision is now 34, with its references updated.
- The page tests use only the hand-made campaign directory and select widgets by label where the new controls changed their order.
  The Released screen is included in the render checks.
- Validation: 426 tests passed, none skipped; lint and formatting pass.
  `tahaDev` is read as the source branch and is not committed or pushed to.

**Ali's end-to-end readiness check, 2026-09-22**

- All 22 tickets remain Done; this was the explicitly requested T21 acceptance review, not a new model experiment.
- The full README rebuild reproduced the frozen bundle and tiers, scored 30,000 subscribers and proposed 2,911 offers from the current 37-package catalogue.
  Existing tracked model and research reports reproduced unchanged.
- The live API, CLI consumer and all five Streamlit pages passed, including individual approval and Arabic/English message preview on an isolated QA campaign.
  The original new campaign is unreviewed at `artifacts/campaigns/e2e-20260922`; all temporary servers were stopped.
- Fixed identifier parsing and ambiguous IDs, malformed API credentials, serving retired approvals, false-positive integration checks and redirected Arabic CLI output (decision 33).
  Dashboard regressions now execute the page scripts and approval-to-preview flow on the shared hand-made fixtures.
- Validation: 420 tests pass with none skipped, including the optional LSTM test; lint and formatting pass.
  Third-party test adapter and Keras/Torch deprecation warnings remain.
- Ready for a local demo and HTTP consumer testing with the available data; operator performance and campaign effectiveness remain unvalidated.
  The Almadar source links remain open, and no new operator data is required for the completed fixes.
- [The acceptance report](reports/end_to_end.md) records evidence, limitations and exact startup commands for this checkout.
- Delivery stays on `Ali_Branch` under Ali's explicit instruction in this task; no commit or push targets `tahaDev`.
  Earlier branch directions below are historical and do not supersede that instruction.

**Ali's session, 2026-09-22**

- Ali is working on `Ali_Branch`, which was fast-forwarded onto Taha's `73762df`; `tahaDev` is not written to from this checkout.
  Every commit of both branches is in this history, so nothing diverges yet, but the two branch tips will drift if both are pushed. Agree one branch before the next session.
- **Ali's answers:** he agrees with decisions 15 to 17, 24 and 25; the folder keeps the name `prepaid_churn/`; the Mix families are no longer sold.
- **The Mix packages are out.** The catalogue is 37 packages in 12 families, matching Ali's own, and the 20 retired ones are recorded in `data/almadar/excluded.csv` with a reason, a name and a date (decision 31).
  `check_against_source` now requires every operator row to be in the catalogue exactly once or recorded as excluded, so a package can never leave silently again.
- **Consequence worth knowing:** Mix held the only metered data-and-voice packages, so a voice-only customer above the base monthly rung now has no eligible offer.
  That is pinned as the expected answer in `tests/test_retention.py`, not treated as a bug.
- **`churn decide` no longer dirties a tracked file** (decision 32): `--report` defaults beside the campaign, and a test runs the documented command and asserts the committed report is untouched.
- **The duplicated fixtures are gone.** The four subscribers lived in four test files; Taha's version is now the single one in `tests/conftest.py`.
  `test_demo.py` keeps one documented override, because its campaign screens need a customer the `low_risk` guard actually excludes.
- `reports/decisions.md` was regenerated and lost only its 20 Mix rows; every headline number is unchanged, because the readiness run proposes nothing.
- Validation: 400 prepaid tests pass with 1 skipped (T12's LSTM, which needs the `experiments` group), lint and formatting green.
- **Still open for Ali:** the source links for the Almadar files, the only question of his that remains.

**Where the module is now**

- **One branch.** Ali built his delivery on top of `tahaDev` `bfb28ab`, so `tahaDev` was fast-forwarded to `Ali_Branch` `ae38840` instead of porting 9,000 lines by hand (decision 24).
  Both of us work on `tahaDev` from here; `Ali_Branch` stays as the record and is not worked on.
  Superseded on 2026-09-22: Ali works on `Ali_Branch` only and Taha on `tahaDev`, and Taha's work reaches `Ali_Branch` by merge (decision 39).
- **Ali's delivery was checked here before it was taken**: 379 tests, lint and formatting green, and a full rebuild that reproduced bundle `lightgbm-2026-09-19-ef9430fb` and tier artifact `tiers-v1-cd15525cb3ef` with no committed report changed.
  His review of our files (identifiers read as text, stricter export and bundle checks, one calibration prediction instead of three) moves no model, feature or threshold, which that rebuild proves.
- **The MVP is complete end to end**: T16, T8, T18, T10, T11, T15, T14, T9, T19 and now T20.
- **T20 is done.**
  [docs/integration.md](docs/integration.md) is the guide for the chatbot, copilot, network ML and antenna owners; `src/prepaid_churn/client.py` is the example client they copy; `churn check-integration` runs it against a live service and checks five refusals.
  Its walkthrough found one real gap and closed it: the copilot can now look up one subscriber (`GET /subscribers/{id}/risk`, decision 26), which it needs to help an employee with a customer on the phone.
  Four questions are deliberately not served, each written in the guide with its reason.
- **Validation of T20 here**: 390 prepaid tests, lint and formatting pass; 11 of them are T20's, and no dependency was added.
  The check ran clean against a real service holding the 30,000-subscriber base and a campaign with two approved offers and one rejected.
- **T12 and T13 are done**, so every graded syllabus chapter is now covered on real data (decision 8).
  T12: the LSTM loses to LightGBM by a third of its PR-AUC and fails two of the four release checks, which is the expected answer for a two-step window and is kept as it came out (decision 28).
  T13: a synthetic copy of the customers is a demo and a pipeline test, not a way to share data; the best copy keeps 45% of the real model's PR-AUC and both copies are told from real rows at a detection ROC-AUC of 1.000 (decision 29).
- **T17 is done, so every ticket in this file is closed.**
  It measured the assumption behind T11 on two public randomised trials: targeting by uplift and targeting by risk are not the same ranking, and on Criteo the risk ranking is worse than random (decision 30).
  The telecom dataset the action plan names, Orange Belgium, is too small to answer, and the report says so rather than picking a winner.
- **The demo app was reworked after Taha used it (decision 34):** a campaign picker in the sidebar, proposing a campaign or a single offer from the screens, a Released screen that shows what was approved and where it lives, and a fix for the approval box, where an empty selection used to approve every pending proposal.
  Keep demo campaigns small: 500 customers is a 1.7 MB snapshot that loads instantly, the whole base is 80 MB and is what made the app feel heavy.
- **What is left:** nothing in this file.
  Since 2026-09-26 two tickets are open again: T22, scoring and retraining on any calendar months, and T23, a 12-month value built on measured risk and comebacks.
  The open questions below still stand, and the next real work is whatever the team needs for the presentation and the demo.

**For Ali: what changed on our side**

1. Your branch is now our branch.
   Taha reviewed your thirteen commits, checked them on his machine, and fast-forwarded `tahaDev` to `ae38840`; decision 24 says why that replaces the hand-porting rule of decision 15.
   Work on `tahaDev` from now on: `git pull --rebase` before you start, claim a ticket by writing your name in its Owner field, push when it is done.
   Nothing of yours was dropped, rewritten or renamed.
2. We took T20, the last MVP item, because the action plan gives Taha the chatbot, the copilot and the integration.
   New files: `docs/integration.md`, `src/prepaid_churn/client.py`, `tests/test_client.py`, and the `churn check-integration` command.
   Your `docs/INTEGRATION.md` at `06890f6` is where the shape came from, and your six grounding rules are kept nearly word for word; step 14 of [docs/ali_branch_merge.md](docs/ali_branch_merge.md) lists what was adapted and what was not.
3. Two things we found while using your work, neither of them a bug in it:
   - `churn decide` overwrites the committed `reports/decisions.md`, so running the documented command dirties a tracked file that records your readiness run.
     We restored it with `git checkout` rather than committing the new one.
     Worth a `--report` flag or a campaign-local path.
   - `test_api.py` and `test_demo.py` each build their own copy of the same four subscribers, and `tests/test_client.py` now makes three.
     If you touch those fixtures, moving them into `conftest.py` would be a good small cleanup; we left them alone rather than editing your tests.
4. T12, T13 and T17 are done too, so every ticket in TICKETS.md is closed.
   The results are negative and stay that way: the LSTM loses to LightGBM, a synthetic copy is a demo rather than a way to share data, and targeting by risk is not targeting by uplift (decisions 28, 29 and 30).
   T17 ports your Qini and your two-model difference by hand, and our Criteo Qini of 0.0698 on a 10% sample is close to the 0.0771 your branch reports, which is the first of your numbers this module has reproduced independently.
   Your Criteo sourcing notes saved real time: scikit-uplift's fetcher and Criteo's own link are both dead, and the HuggingFace copy you found is what the script uses.
5. Please still answer the open questions below that name you; the Mix packages and the source links for the Almadar files are the two that block nothing but weaken the report.
6. Your Claude can start from this, in the repo:

   > I am Ali. Taha took my `Ali_Branch` work into `tahaDev` and then finished T20, T12, T13 and T17, so every ticket is closed. Read `prepaid_churn/CLAUDE.md`, the Handoff at the top of `prepaid_churn/TICKETS.md`, decisions 24 to 30 in `prepaid_churn/docs/decisions.md`, and steps 13 to 17 of `prepaid_churn/docs/ali_branch_merge.md`. Then rebuild the artifacts with the commands in the README, confirm the bundle is `lightgbm-2026-09-19-ef9430fb`, and tell me which ticket is next and what Taha still needs from me, before writing any code.

**Ali's delivery log (2026-09-20 and 2026-09-21)**

- Delivered on `Ali_Branch` under decision 18; that delivery is finished and decision 24 supersedes its branch instruction.
- T21 fixes export validation, identifier preservation, bundle consistency and repeated inference.
- T21 validation: 170 prepaid tests and 21 geospatial tests passed.
- T10 adds frozen value tiers, an explicit 12-month revenue scenario, and a training-only clustering comparison.
- T10 validation: 202 prepaid tests, lint, formatting and the locked offline environment check pass.
- Fitted tiers on 45,858 active training customers; assigned one tier to each of 30,000 unlabeled customers.
- The clustering result is weak (best silhouette 0.2766 at k=2); five value tiers remain a reporting convention.
- Run `uv run churn fit-tiers`, then `uv run churn tiers --tiers-only` without a churn bundle, or `uv run churn tiers` with the existing gated bundle.
- This checkout has no real churn bundle: the 30,000-row run contains tiers and explicitly unavailable risk-based values; the full bundle-to-scenario path is covered by hand-made integration tests.
- Both raw exports pass validation, and their model features are unchanged in both windows.
- The frozen model and the spent test window are unchanged.
- Rebuild old bundles with `uv run churn bundle` using the existing champion and gate, because the input contract fingerprint and bundle integrity checks changed.
- Findings and remaining work are in [../CODE_REVIEW.md](../CODE_REVIEW.md).
- T11 is implemented: catalogue bonuses, spend and cannibalisation guards, deterministic holdout, equal-spend comparisons and named approve/reject commands.
- T11 validation: 247 prepaid tests, lint and formatting pass; the 30,000-row readiness run creates no offers without a gated churn bundle.
- The readiness report records 27,582 active rows with unavailable risk, 2,418 silent rows and 2,965 holdout assignments; all proposals and releases remain empty.
- Positive recommendations, partial/all reviews, rejected-row exclusion, review locking and interrupted-write recovery are covered by hand-made tests.
- Run `churn decide` with the existing gated bundle for risk-based proposals, or `churn decide --tiers-only` for readiness; choose a new campaign output directory on each run.
- T15 is implemented: a read-only FastAPI service with four endpoints, one API key per consumer and a phone-number check on subscriber IDs.
  T20's walkthrough added a fifth, `GET /subscribers/{id}/risk` for the copilot (decision 26).
- T15 validation: 299 prepaid tests, lint and formatting pass; 52 of those tests are new.
- `fastapi`, `uvicorn` and `httpx` are the first dependencies added since the module was built; decision 21 records why.
- Start it with `uv run churn serve` after setting `PREPAID_CHURN_CHATBOT_KEY` and `PREPAID_CHURN_COPILOT_KEY`; neither has a default and the service refuses to start without both.
- The OpenAPI page at `/docs` is generated from the response models, so it is the integration documentation for the chatbot and copilot owners.
- Run against this checkout on 2026-09-21: `/health` reports degraded with no bundle, `/catalogue` serves all 57 packages, `/portfolio/summary` summarises 30,000 subscribers with `risk_available` false, and no offer is released because none was approved.
- Outputs are read once at startup, so restart the service after a new `churn approve` release; `/health` shows which campaign is being served.
- T14 is implemented: five Streamlit screens over the released outputs, with the named approval step on the campaign screen.
  Taha used it on 2026-09-22 and it grew a campaign picker, a way to propose a campaign or a single offer from the screen, and a Released screen (decision 34).
- T14 validation: 325 prepaid tests, lint and formatting pass; 26 of those tests are new.
- Start it with `uv run streamlit run app/Home.py`; set `PREPAID_CHURN_CAMPAIGN_DIR` and `PREPAID_CHURN_PORTFOLIO` to show a campaign other than the first.
- `streamlit` is the fourth dependency added on this delivery; decision 22 records why, and charts use the Altair that Streamlit already installs.
- Every screen was opened in a browser against the 30,000-row export, a five-customer campaign and a one-customer campaign; that found five defects the unit tests had missed, all fixed.
- Approving on screen writes through the same locked, audited path as `churn approve`, and only approved rows reach `released.csv`.
- **For T11 to consider:** the approved Arabic message is 102 characters, so it sends and bills as two SMS parts; one part is 70 characters once any Arabic is present.
- T10, T11, T14 and T15 are complete; the next product work is T20 integration checks, which needs Taha and the chatbot and copilot owners rather than code alone.
- T9 is done: [docs/model_card.md](docs/model_card.md) covers intended and out-of-scope use, the data, the frozen metrics and thresholds, calibration, explanations, the approval step, the Almadar assumptions, limitations, ethics, selection bias and maintenance.
- T9 validation: 341 prepaid tests, lint and formatting pass; 16 of those tests compare the card's figures against the reports they cite.
- **The fresh-clone check was rerun on 2026-09-21 and passed:** the README pipeline rebuilt bundle `lightgbm-2026-09-19-ef9430fb` and tier artifact `tiers-v1-cd15525cb3ef`, and `git status` showed no changed report.
- That confirms T21, T15, T14 and the four new dependencies did not move the frozen champion or any committed number.
- With a real bundle the 30,000 unlabeled customers score high 1,209, medium 3,594, low 22,779 and already silent 2,418.
- T19 is done, the first experiment after the MVP: `churn advance` advises an emergency credit limit from recharge behaviour alone.
- T19 validation: 379 prepaid tests, lint and formatting pass; 38 of those tests are new, and no dependency was added.
- **The T19 result is a finding about the product, not about the rule.** This base tops up often in very small amounts, median typical top-up 1.89 LYD.
- So 46.1% of customers cannot carry even the 1 LYD advance and still have balance left, and the flat 5 LYD data advance suits only 4.65%, though the operator offers it to anyone with a low balance.
- The zero-residual finding is computed, not asserted: the smallest card, the data advance and the top airtime rung are all 5 LYD.
- The "typical top-up" basis is an assumption that moves the headline by twenty points, so `reports/emergency_credit.md` carries a sensitivity table instead of hiding it.
- T9, T10, T11, T14, T15 and T19 are complete.
- T20 is the last MVP item and needs Taha and the chatbot and copilot owners rather than code alone.
- **T12 and T13 are graded:** decision 8 says SIC grades syllabus coverage, and Ch 8, Ch 9 RNN (T12) and Ch 9 GAN (T13) are the two chapters still uncovered. T17 covers no chapter.

The rebuild commands and the fresh-clone check that used to sit here are in [README.md](README.md); the branch instructions above replace the 2026-09-19 ones.

**Status**
- T0 to T7 are done: the churn model is trained, calibrated and evaluated once on the test month (`reports/evaluation_all.md`).
  LightGBM test ROC-AUC 0.891, PR-AUC 0.348; the riskiest 10% of customers hold 61.5% of next month's churners.
- The data is committed in `data/raw/` (`train.csv`, `test.csv`, `data_dictionary.csv`), so a fresh clone can run everything (decision 9).
- `reports/profile.md` holds the real-data profile; the T1 Findings below summarise it.
- `docs/data_contract.md` is the input contract (generated by `uv run churn contract`); the real `train.csv` and `test.csv` both pass `uv run churn validate`.
- Integration with the team's chatbot and copilot is designed in decisions 10 and 17; the tickets T8, T11, T15, T16 and T20 follow it.
- The instructor reviewed the SIC action plan on 2026-09-19: success thresholds (decision 13) and a human approval step for retention actions (decision 14) are now part of the plan (T7 result, T8, T9, T11, T14, T15).
  The current champion passes all four thresholds.
- Ali's parallel work on `Ali_Branch` was reviewed and is being combined into this module (decisions 15, 16 and 17).
  Every step is logged in [docs/ali_branch_merge.md](docs/ali_branch_merge.md).
- Almadar Aljadid is now the operator (decision 16), and the customer MVP comes first, built to plug into the team platform (decision 17).
- T16 is done: `data/almadar/` holds the 37 Almadar packages still sold and the market facts, each with a status; the 20 Mix packages the operator retired are recorded in `excluded.csv` (`docs/almadar.md`).
- T8 is done: `churn score` writes the subscriber output contract (`docs/output_contract.md`) from the gated bundle `lightgbm-2026-09-19-ef9430fb`; it is the integration point for the chatbot, the copilot and T11.
- T18 is done: `churn almadar-view` shows every customer in LYD and Almadar packages, at the 40 LYD ARPU Taha chose (`reports/almadar_view.md`).
- A fresh clone rebuilds everything and reproduces the champion byte for byte, checked on 2026-09-19, again on 2026-09-21 by Ali, and again on 2026-09-21 here after his branch was taken in.
- T20 is done: the guide, the example client, `churn check-integration` and the copilot's subscriber lookup that the walkthrough found missing.
- T12, T13 and T17 are done: `reports/sequence_benchmark.md`, `reports/synthetic.md` and `reports/uplift.md`, with decisions 27 to 30.
  No experiment changed a model, a feature or a threshold, and the frozen champion is untouched.
- T17's external datasets are downloaded on demand into the git-ignored `data/external/`; they are under non-commercial licences and are never committed.
- `tahaDev` now also carries Ali's fixes to Ahmed's `antenna_cell_placement/` and the root `CODE_REVIEW.md`; they are Ali's work, and the team has to see them before anything reaches `main`.

**Blocked on**
- Nothing.
  T20 is accepted from the consumer side by its owner (decision 26 and the T20 Findings); reopen it if a response shape turns out to be wrong when the chatbot and the copilot are built.

**Next steps, in order (the MVP path from decision 17)**
1. T16 Almadar catalogue and market facts (done).
2. T8 model bundle, batch scoring and the output contract (done).
3. T18 Almadar view of the real customers (done).
4. T10 value tiers and T11 offers with human approval (done).
5. T15 integration service (done, Ali), then T20 integration check (done, Taha + Claude).
   The suggested split had Taha taking T15 and T20; Ali took T15 on 2026-09-21 because T11 was finished and the endpoints were the next thing blocking the platform.
6. T14 demo app (done, Ali) and T9 documentation with the model card (done, Ali).
7. The MVP now works end to end: T19 (done, Ali), T12, T13 and T17 (done, Taha + Claude).
   Every ticket in this file is closed.
   The test window is spent: T12 compares against the frozen T7 numbers and must not change any T7 choice.

**Open questions**
- **Ali's agreement: answered on 2026-09-22.**
  Ali agrees with decisions 15 to 17 and with 24 and 25, and disagrees with nothing taken or left out.
- **Folder name: answered on 2026-09-22.**
  Ali chose to keep `prepaid_churn/`; the rename is not happening, so every path in the docs and the action plan stays as it is.
- **Almadar sources:** Ali's Almadar files have no source links; ask him where each came from (website page, app screenshot or shop) so T16 rows can cite them.
- **Mix packages: answered on 2026-09-22.**
  Ali confirmed the operator no longer sells the five Mix families, so the 20 packages are out of the catalogue and recorded in `data/almadar/excluded.csv` with the reason (decision 31).
  The catalogue is now 37 packages in 12 families, matching his.
- **Almadar ARPU:** Taha chose 40 LYD per month for T18 on 2026-09-19; it is still an assumption, so replace it if an operator figure appears (one number in `data/almadar/market.toml`).
- **`churn decide` overwrites a committed report: fixed on 2026-09-22.**
  `--report` now defaults to `decisions.md` inside `--output-dir`, so the documented command leaves the committed report alone (decision 32).
- **Action plan dataset:** the team's SIC action plan lists `telco_customer_churn` (the IBM data) for churn.
  We use the upGrad prepaid data instead (decisions 1 and 5), because the IBM data is fictional and postpaid.
  Taha should tell the team leader so the action plan matches the work.

## Decisions already made

These are settled and every ticket must respect them.
Reasons are in [docs/decisions.md](docs/decisions.md).

- **Dataset:** upGrad "Telecom Churn Case Study" prepaid data, Kaggle `train.csv` (69,999 customers, months 6, 7, 8 plus a month 9 churn label in `churn_probability`).
  Kaggle's `test.csv` has no labels and is not used for evaluation.
- **Churn definition:** usage-based.
  A customer churns in month `m` when incoming calls, outgoing calls, 2G data and 3G data are all zero in month `m`.
  The rule lives in `src/prepaid_churn/labels.py`.
- **Two windows with relative month names.**
  Features always come from "previous month" and "current month", and the label from "next month".
  - Window A: features from months 6 and 7, label = churn in month 8, computed by us.
  - Window B: features from months 7 and 8, label = Kaggle's month 9 label.
- **Customer split:** customers are split 70/15/15 into train, validation and test, stratified by the window A label.
  - Train customers: fit models on window A.
  - Validation customers: calibration and threshold choice on window A; LightGBM's early stopping uses 10% of the train customers instead (decision 37).
  - Test customers: final evaluation on window B, run once after everything is frozen.
- **No leakage:** a feature may only use months up to and including "current month".
  Month 9 information never enters features.
- **Eligibility:** only customers active in the current month are trained on, validated and scored (decision 12).
- **High-value filter:** optional flag, off by default.
  When on, it keeps customers whose average recharge amount over the two feature months is at or above the 70th percentile (the top 30%).
  It is for comparison with the upGrad case study only; the product never uses it (decision 36).
- **Models:** logistic regression baseline and LightGBM, with probability calibration.
  PCA is never a model input, because it destroys per-customer explanations.
  PCA is allowed only for the T10 segment plot.
- **Success thresholds** (decision 13), measured on an out-of-time test (a later month, unseen customers, active customers only).
  A model is fit for use only if it passes all four:
  1. Capture: the riskiest 10% of customers contain at least 50% of the churners.
  2. Better than chance: PR-AUC is at least 3 times the churn rate.
  3. Better than the baseline: the champion's PR-AUC is higher than logistic regression's on the same test.
  4. Calibration: the mean predicted churn rate is within 1 percentage point of the observed rate.

  From the next model on, a fifth check is set in advance (decision 38): in the high and medium bands separately, actual leavers must be within 20% of the predicted number, or within two standard deviations of chance if that is wider.
  It does not apply to the current champion, whose gate was recorded with the four checks above.
- **Human approval** (decision 14): the system only proposes retention offers.
  A named person approves or rejects them before any offer is sent or shown by the chatbot, and every approval is logged.
- **Operator** (decision 16): Almadar Aljadid.
  The churn model trains on real upGrad customers in their original units; the business layer shows them in Almadar terms (T18).
- **MVP first** (decision 17): one customer use case, integrated with the chatbot and copilot, before any extra experiment.
  No LLM in any path that sets an offer, price or credit limit; pseudonymous IDs; separate API keys for the chatbot and the copilot.
- **Ali's work** (decision 15): ported by hand from `Ali_Branch`, never merged with git, and every port logged in `docs/ali_branch_merge.md`.
- **Syllabus experiments** (T12, T13) use a separate `experiments` dependency group, so the core package stays small.
- **Data in git:** the raw Kaggle files in `data/raw/` are committed (decision 9).
  `data/processed/` and `artifacts/` are git-ignored and rebuilt by the pipeline.
  Reports with aggregate numbers (`reports/`) are committed.

## Conventions

- Code lives in `src/prepaid_churn/`, tests in `tests/`.
- Every pipeline stage is a set of pure functions that can be tested without files, plus a thin CLI subcommand in `cli.py`.
- Unit tests use small hand-made DataFrames (see `tests/conftest.py`), never the real dataset.
- Run everything through `uv run`.

## T0 - Scaffold

**Owner:** Claude
**Status:** Done
**Depends on:** nothing

Scope:
- `uv` project with pinned lockfile, ruff and pytest.
- Git-ignored `data/processed/` and `artifacts/` folders.
- Empty `churn` CLI.

Acceptance:
- `uv run churn --help` works.
- Lint, format check and tests pass.

## T1 - Data profiling

**Owner:** Claude
**Status:** Done
**Depends on:** T0

Scope:
- Group the columns by month: `split_month` and `monthly_columns` in `data.py` (handles `_6` suffixes and `jun_vbc_3g`-style prefixes).
- Missing-value share per column and month, and whether columns go missing together (minute columns with `onnet_mou`, data recharge columns with `date_of_last_rech_data`).
- Whether total minutes are zero when minute columns are missing, which tests the "missing means zero" hypothesis.
- Constant columns, duplicate IDs and rows, negative values.
- Usage-based inactivity (the label rule) and recharge-based inactivity (no recharge at all) per month, and how much they overlap.
- Kaggle's month 9 label rate, how many month 9 churners were already inactive in month 8, and the label rate for active vs inactive customers in month 8.
- `churn profile` command that writes `reports/profile.md`.

Acceptance:
- `reports/profile.md` exists, built from the real `train.csv`.
- The "Findings" subsection below states, with numbers, what the report confirms or changes for T2, T3 and T4.

Findings (from `reports/profile.md`, 69,999 customers, 172 columns):
- **The finding that shapes the whole product: most churn has already happened.**
  59.9% of month 9 churners were already usage-inactive in month 8.
  Customers inactive in month 8 churn at 77.9%; customers active in month 8 churn at 4.4%.
  So the raw label rate of 10.19% is mostly people who had already stopped, and predicting them is not a retention opportunity.
  Scoring only the customers still active in the current month is what turns this into a useful question, and it is why the evaluated churn rate is 4.35% rather than 10.19% (decision 12).
  This drives the eligibility question in the Handoff section.
- Missing values come in exactly two blocks, and both mean "nothing happened", so they become 0:
  - Voice block: 29 minute columns always go missing together (agreement 1.0 with `onnet_mou`), for 3.9%, 3.8% and 5.3% of customers in months 6, 7 and 8.
    For 100% of those customers, total incoming and outgoing minutes are 0.
  - Data block: 10 data recharge columns always go missing together with `date_of_last_rech_data` (agreement 1.0), for 74.9%, 74.5% and 73.7% of customers: no data recharge that month.
    `fb_user` and `night_pck_user` are 0/1 flags in this block, so missing means 0.
- `date_of_last_rech` is missing exactly when `total_rech_num` is 0 (100% agreement; 1,101, 1,234 and 2,461 customers).
  So missing means "no recharge this month", which T3 must encode as its own recency value, not as 0.
- 13 columns carry no information (one value, sometimes plus missing values): `circle_id`, `loc_og_t2o_mou`, `std_og_t2o_mou`, `loc_ic_t2o_mou`, `last_date_of_month_6/7/8`, `std_og_t2c_mou_6/7/8`, `std_ic_t2o_mou_6/7/8`.
  The month end dates are fixed (2014-06-30, 2014-07-31, 2014-08-31).
- No duplicate IDs and no duplicate rows.
- Negative ARPU: 292, 341 and 352 customers in months 6, 7 and 8 (minimum -2,258.7); small negatives in `arpu_2g` and `arpu_3g`.
  75% of the customers with negative `arpu_8` made no recharge in month 8, so these look like billing adjustments, not errors.
- Label: 10.19% of customers churn in month 9 (7,132 of 69,999).
- Usage-based inactivity is 6.8%, 6.4% and 7.8% in months 6, 7 and 8; recharge-based inactivity is only 1.6%, 1.8% and 3.5%.
  Most usage-inactive customers still recharged (5.8% of all customers in month 8), so the two definitions disagree.
  We keep the usage-based definition, because Kaggle's month 9 label uses it.

## T2 - Input data contract

**Owner:** Claude
**Status:** Done
**Depends on:** T1

Scope:
- The contract is written once as column groups in `src/prepaid_churn/schema.py` (`GROUPS`).
  The pandera schema, the T3 cleaning rules and `docs/data_contract.md` are all built from it, so they cannot drift apart.
- Column checks: types, non-negative amounts, 0/1 flags, dates inside their month, unique IDs.
- Row rules from the T1 Findings: the voice block and the data block are complete or entirely missing, the recharge date is missing exactly when there was no recharge, and every month has a month-end date.
- The 13 no-information columns are not part of the contract; extra columns are allowed and ignored.
- `validate` collects every problem and raises one readable error; `churn validate` checks a file, `churn contract` regenerates the document.
- Dates are accepted as month/day/year (Kaggle) or year-month-day (ISO), so an operator export can use either.

Acceptance:
- The real `train.csv` and `test.csv` pass `uv run churn validate`.
- Tests show that missing columns, wrong types, out-of-range values and broken row rules fail with clear errors, all reported at once.
- A test fails when `docs/data_contract.md` is out of date.

## T3 - Cleaning

**Owner:** Claude
**Status:** Done
**Depends on:** T2

Scope (rules confirmed by the T1 Findings), in `src/prepaid_churn/clean.py`:
- Keep only contract columns, which drops the 13 no-information columns and any extra operator columns.
- Voice block and data block missing values become 0.
- `no_voice_record_<month>` flag: 1 when the whole voice block of the month was missing.
- `date_of_last_rech` and `date_of_last_rech_data` become `days_since_last_rech_<month>` and `days_since_last_rech_data_<month>`: days from the date to the month end.
  No recharge in the month gets the number of days in the month (for example 31 for August), one more than any real value, so larger always means staler.
  Recency across months (for example "no recharge this month, last one 12 days before it") is a T5 feature.
- Negative ARPU values stay as they are (billing adjustments).
- `id` stays in the cleaned data as the key; T4 keeps it out of the features.

Acceptance:
- One unit test per rule on the hand-made frame in `tests/conftest.py`.
- Cleaning twice gives the same result as cleaning once.

Result on the real data: 69,999 rows, 172 columns in, 162 columns out, no missing values left.

## T4 - Windows, labels and split

**Owner:** Claude
**Status:** Done
**Depends on:** T3

Scope, in `src/prepaid_churn/windows.py`:
- `window_features`: every monthly column becomes `prev_<base>` and `cur_<base>`, plus `tenure_days` from `aon`.
  `aon` is a snapshot from data extraction; the one-month difference between windows is small against its 180 to 4,337 day range.
- `window_label`: window A uses our usage rule on month 8; window B uses Kaggle's month 9 label.
- Eligibility: only customers active in the current month (decision 12).
- Optional high-value filter: average airtime plus data recharge amount over the two window months in the top 30%, computed among eligible customers of that window.
  It exists to compare with the upGrad case study's population; nothing downstream reads its output (decision 36).
- Customer split 70/15/15, stratified by the window A label, seed 42.
- `churn build-dataset [--high-value]` writes `train`, `validation` and `test` Parquet files to `data/processed/all/` (or `high_value/`) and a summary to `reports/dataset_all.md` (or `dataset_high_value.md`).

Acceptance:
- Tests prove that changing later months, or the Kaggle label, does not change any feature.
- Tests prove no customer appears in more than one split.
- Window A and window B have identical feature columns.

Result on the real data: 107 window features.
`reports/dataset_all.md` shows 126, because `build-dataset` now also adds the 19 features of T5.
Train 45,858 rows (4.65% churn), validation 9,812 (4.61%), test 9,677 (4.35%).
Our computed month 8 label and Kaggle's month 9 label give almost the same churn rate, which supports that our rule matches Kaggle's definition.
High-value only (`reports/dataset_high_value.md`): 13,708, 3,024 and 2,942 rows, with 4.2%, 4.4% and 3.0% churn.
It must not be carried through `churn evaluate`, because the test window is spent; the T7 high-value slice answers how the model does on these customers (decision 36).

## T5 - Features

**Owner:** Claude
**Status:** Done
**Depends on:** T4

Scope, in `src/prepaid_churn/features.py` (`FEATURES` holds a one-line description of each; `build_datasets` applies `add_features`):
- Recency across the window: `days_since_last_rech_window` and `days_since_last_rech_data_window`.
  Without a recharge in the current month, they add the current month's days to the previous month's value (T3 encodes "none" as the number of days in the month).
- `diff_<measure>` (current minus previous) for ARPU, outgoing, incoming and total minutes, data MB, recharge amount and recharge count.
- `trend_<measure>`: the current month's share of both months (0.5 = stable, 0 = dropped to zero); not for ARPU, which can be negative.
- `cur_onnet_share`, `cur_incoming_share` and their changes from the previous month, as dual-SIM signals from the proposal.
  Shares fall back to a neutral 0.5 when there are no minutes; the `no_voice_record` flag keeps that case visible.
- Night-pack and social-pack use were already columns (`night_pck_user`, `fb_user`), so they need no new feature.

Acceptance:
- Each feature has a unit test.
- No feature uses the label month (features only read `prev_` and `cur_` columns).

Result: 19 new features, 126 in total.
Medians in the train set, churners vs non-churners: 6 vs 3 days since the last recharge, `trend_total_og_mou` 0.35 vs 0.50, `diff_arpu` -89.5 vs +2.8.
The "receiving SIM" idea did not hold here: churners have a lower incoming share (0.30 vs 0.47), not a higher one; T7's feature importance will show whether the shares help at all.

Answered on 2026-09-25 from the trained LightGBM's gain and the train customers, not the test window:
- The 19 features are 15% of the columns and carry 25.1% of the gain; `trend_total_mou` ranks 2nd of 126 (8.4%).
- The four share features carry 3.0% of the gain, and the best, `cur_incoming_share`, ranks 21st, so they help a little.
- Churn by fifths of incoming share, lowest to highest: 8.6%, 4.9%, 4.0%, 2.2% and 3.6%.
  A low share goes with churn; a likely reading is that incoming calls tie people to their number.
- The second-SIM idea behind the on-net share has weak support among customers with call minutes: churn is 5.3% in the lowest fifth, 6.7% in the highest and 3.1% to 3.6% in between.
  Those whose on-net share fell by more than 0.1 churn at 5.2%, against 4.2% for a stable share.
- The descriptions in `FEATURES` now say what the data shows instead of the two hypotheses.

## T6 - Training

**Owner:** Claude
**Status:** Done
**Depends on:** T5

Scope, in `src/prepaid_churn/training.py`:
- Logistic regression baseline: signed log transform (heavy-tailed amounts), scaling, no class weights.
  It uses scikit-learn's default L2 penalty and converged in 87 of the 5,000 iterations it is allowed.
- LightGBM, no class weights, deterministic mode, seed 42.
  The tree count comes from early stopping on 10% of the train customers, then LightGBM is refit on all train customers.
  This keeps the validation customers untouched for T7 (a change from the first plan, which early-stopped on validation; decision 37).
  The other settings were set by hand and never searched: learning rate 0.03, 31 leaves, at least 50 customers per leaf, 80% row and column sampling and an L2 penalty of 1.0.
- `churn train [--data-dir data/processed/all]` writes `artifacts/models/all/*.joblib` and `reports/training_all.md`.

Acceptance:
- Running `churn train` twice gives the same models (tested).
- Validation metrics for both models are in `reports/training_all.md`.

Result on the validation customers (uncalibrated), 12 seconds on a laptop CPU:

| Model | ROC-AUC | PR-AUC | Log loss | Brier |
|---|---|---|---|---|
| Logistic regression | 0.881 | 0.336 | 0.134 | 0.036 |
| LightGBM (288 trees) | 0.928 | 0.458 | 0.114 | 0.032 |

The churn rate is 4.6%, so a PR-AUC of 0.458 is about 10 times better than random.
The top feature is roaming outgoing minutes in the current month (13% of gain), then `trend_total_mou` and days since the last recharge.
Roaming is plausible (travel, moving away, or a local SIM abroad), and it is not leakage: it is measured in the month before the label month.

Checked on 2026-09-25 with the train and validation customers only; no model was saved or changed:
- Customers roaming in the current month are 14.0% of the train customers and 52.2% of the churners, and they churn at 17.3% against 2.6%.
- The four roaming columns carry 18.9% of the gain.
  The same recipe without them scores a validation PR-AUC of 0.401 instead of 0.458 (logistic regression: 0.318 instead of 0.336).
- Of 2,131 train customers silent in month 8, 561 (26.3%) were active again in month 9 by Kaggle's label: 35.2% of those who had been roaming and 16.7% of the others.
  So part of this signal is temporary absence, which the one-month label counts as churn.
- Every customer in the data has the same home circle (`circle_id` 109), so roaming here mostly means being away from that region, which is unlikely to mean the same in Libya (model card, Limitations).

## T7 - Calibration and evaluation

**Owner:** Claude
**Status:** Done
**Depends on:** T6

Scope, in `src/prepaid_churn/evaluation.py`:
- For each model, choose none, sigmoid or isotonic calibration by 5-fold cross-validated log loss on validation customers (not by in-sample loss, which favours isotonic), then refit it on all validation customers.
- Champion: highest validation PR-AUC after calibration.
- Risk bands from validation only: `high` from the best-F1 threshold, `medium` above the validation churn rate, `low` below.
- `freeze` saves everything to `artifacts/models/all/champion.joblib` before the test window is scored.
- `churn evaluate` then scores test customers in window B once and writes `reports/evaluation_all.md`: metrics for both models, precision and recall at the top 5%, 10% and 20%, risk bands, a reliability table (instead of an image, so it reads in Markdown), and the high-value slice.
- Added on 2026-09-25 (decision 35): `churn uncertainty` resamples the frozen test predictions to put 95% intervals on the published numbers and writes `reports/uncertainty.md`; it trains and chooses nothing.

Acceptance:
- `reports/evaluation_all.md` compares logistic regression and LightGBM on window B.
- The report states the frozen thresholds and the date they were chosen (2026-09-19).

Result on the test window (months 7 and 8, Kaggle's month 9 label, unseen customers, 4.35% churn):

| Model | ROC-AUC | PR-AUC | Log loss | Brier |
|---|---|---|---|---|
| Logistic regression | 0.870 | 0.277 | 0.134 | 0.036 |
| LightGBM (champion) | 0.891 | 0.348 | 0.126 | 0.034 |

- Contacting the riskiest 10% catches 61.5% of churners at 26.8% precision; the riskiest 20% catches 79.8%.
- Risk bands: `high` 450 customers with 38.4% churn, `medium` 1,238 with 11.9%, `low` 7,989 with 1.3%.
  The low band still holds 100 of the 421 leavers (24%), and T11 makes it no offer.
- Calibration: LightGBM without class weights was already well calibrated on average (sigmoid and none tie at 0.1142 log loss).
  On test, the mean prediction is 4.22% against 4.35% observed, and the top tenth predicts 29.2% against 26.8% observed.
  Added on 2026-09-26 from the frozen predictions, read only: the average hides two errors that cancel.
  Tenths 7 to 9 (predicted 1.1% to 10.9%) expected 98 leavers and had 134, while the riskiest tenth expected 283 and had 259.
  By band, the high band had 173 leavers against 199 predicted (-13%), the medium band 148 against 135 (+10%) and the low band 100 against 75 (+34%), so the largest miss is where T11 spends nothing (model card, Calibration).
  Decision 38 adds a check on the high and medium bands for the next model.
- High-value slice: ROC-AUC 0.906, PR-AUC 0.383 at 2.9% churn.
- Test is lower than validation (ROC-AUC 0.928, PR-AUC 0.458): it is a later month, Kaggle's label instead of ours, and unseen customers.
  This gap is the honest estimate of production performance.
- After the first run, the report was regenerated once only to print customer counts as whole numbers; the choices are frozen and deterministic, so no number changed.

Success thresholds (decision 13), checked against these test results:

| Threshold | Required | Result | Pass |
|---|---|---|---|
| Churners in the riskiest 10% | at least 50% | 61.5% | yes |
| PR-AUC vs churn rate | at least 3 times (0.131) | 0.348 (8.0 times) | yes |
| PR-AUC vs logistic regression | higher than 0.277 | 0.348 | yes |
| Mean predicted vs observed churn | within 1 point | 4.22% vs 4.35% (0.13 points) | yes |

The thresholds were written down after this test run, at the instructor's request, so this pass is reported honestly as a check, not as a pre-registered result.
From now on they are a gate for every new model (retraining, a new month or an operator's own data), checked before the model is used (T8).

How sure these numbers are (decision 35, `reports/uncertainty.md`, 2,000 paired resamples of the frozen predictions, nothing changed):
- LightGBM PR-AUC 0.348, 95% interval 0.301 to 0.400; logistic regression 0.277, 0.238 to 0.324.
- LightGBM scored higher than the baseline in all 2,000 resamples; the difference is 0.071, interval 0.040 to 0.102.
- All four thresholds still pass at the unfavourable end of their intervals; the closest to its bar is capture, at 57.3% against 50%.

## T8 - Model bundle and batch scoring

**Owner:** Claude
**Status:** Done
**Depends on:** T7

Scope:
- One versioned bundle in `artifacts/`: cleaning and feature pipeline, model, calibrator, threshold, data contract version, training metadata and metrics.
- Everything a scoring run needs travels inside the bundle: the feature list, fill values, the SHAP background sample and one stored sample row.
  Nothing is computed from the batch being scored, so one customer scored alone gets the same answer as inside a batch of ten thousand (a lesson from `Ali_Branch`, where three serving bugs only appeared on one-row batches).
- The bundle records the scikit-learn and LightGBM versions it was built with; loading it under other versions stops with a clear error.
- Loading runs a smoke prediction on the stored sample row; a bundle that loads but cannot predict is refused.
- `churn score --input <csv> --output <file>` validates the input against the data contract, scores every customer and writes the **subscriber output contract** from decision 10:
  subscriber ID (pseudonymous, decision 17), calibrated churn probability, risk band, top three reasons in plain language (from SHAP values), model version and scoring time.
  Customers already silent in the current month are not scored by the model; they get the risk band `already_silent` (decision 12).
  T10 and T11 later add the value tier and the recommended offer to the same rows.
- A Python function `score(df)` returns the same rows, so a teammate's service can call the model without files.
- The output contract is documented in `docs/output_contract.md`, generated from code like the data contract.
- Release gate: T7's evaluation computes the four success thresholds (decision 13) and stores the result with the champion.
  The bundle is only built from a champion that passes all four; otherwise the command stops and names the failed thresholds.

Acceptance:
- End-to-end test: a small valid CSV scores successfully.
- An invalid CSV is rejected by the schema before scoring.
- A test checks every output row against the output contract.
- A test shows the bundle is refused for a champion that fails a threshold.
- A one-row batch gives the same probability and reasons as the same row inside a larger batch, and its reasons are not all zero.
- A bundle whose smoke prediction fails is refused.

Findings:
- Commands: `churn evaluate` now also stores the release gate (`artifacts/models/all/gate.json`) and adds the four thresholds to `reports/evaluation_all.md`; `churn bundle` packages the champion; `churn score` writes `artifacts/scores/scores.csv`; `churn output-contract` writes `docs/output_contract.md`.
- `churn evaluate` was rerun once, only to store the gate: `champion.joblib` is byte-identical (same SHA-256) and every T7 number is unchanged; the report only gained the thresholds section.
- The bundle `lightgbm-2026-09-19-ef9430fb` is `artifacts/bundle/manifest.json` (plain JSON: library versions, data contract fingerprint, gate, thresholds, features) plus `model.joblib`.
  Loading checks the versions before unpickling anything, then predicts a stored sample row and refuses a bundle whose answer changed.
- `churn score` defaults to Kaggle's `test.csv`: 30,000 customers never used for training or evaluation, which stand in for "this month's base".
  In 10 seconds: 1,209 high, 3,594 medium, 22,779 low and 2,418 already silent; the mean prediction among active customers is 4.14% (test churn rate 4.35%).
- Reasons are exact SHAP values from LightGBM's own `pred_contrib`, which needs no background sample, so `Ali_Branch`'s "every reason is zero" bug cannot happen here.
  Computing them on all cores gives identical numbers 9 times faster (55 to 10 seconds for 30,000 customers).
  The most frequent top reasons are days since the last recharge, the amount on the last recharge day and outgoing roaming minutes.
- A one-row bug was found and fixed: pandas 3 gives an all-empty text column the type `object` in a one-row batch and `str` in a larger one; text columns now have an explicit type, and a test compares each customer alone with the full batch.
- Nothing is computed from the scored batch except the month end date, which the data contract already requires on at least one row.
- Data contract: `id` may now be a number or text, so an operator can export a salted hash of the phone number (decision 17); `docs/data_contract.md` was regenerated.
- `shap` was removed from the dependencies (LightGBM computes SHAP itself), and with it numba, llvmlite, slicer and tqdm.
- Found in the 2026-09-26 recap: the contract and the scorer only accept June to August.
  Column names carry the month number, every date must fall in the month its column names, the `vbc_3g` names cover only June to September, and the scorer always reads months 7 and 8.
  On the hand-made fixture, the same export with its dates three months later was refused ("date in month 6 failed"), and one with honest names for months 9 to 11 was refused for missing June to August columns.
  So an operator's current base cannot be scored without rewriting its dates; T22 is the fix.
- Changed on 2026-09-26 (decision 40): only `high` and `medium` subscribers get the model's reasons, and a `low` one gets "Low risk: nothing stands out".
  Before, all 22,779 low-band customers of the unlabelled base got three "reasons for churn" that read as warning signs; probabilities and bands are unchanged.

## T9 - Documentation

**Owner:** Ali
**Status:** Done
**Depends on:** T8

Scope:
- README with setup, data, every command and the full pipeline run.
- Model card, starting from `Ali_Branch`'s `docs/model_cards/TEMPLATE.md`: data, churn definition, windows, metrics, success thresholds and their results, the human approval step, the Almadar view and its assumptions (decision 16), and limitations (single 4-month window, undocumented data provenance, behaviour from another market, educational license).
- The employee copilot indexes these documents (decision 17), so every fact in them names its source and date.

Acceptance:
- A teammate reproduces the evaluation report from a fresh clone by following the README only.

Findings (2026-09-21):
- [docs/model_card.md](docs/model_card.md) is written, adapted from `Ali_Branch`'s template (port log step 11).
- Every figure in it is copied from a committed report and names that report, because the copilot indexes the document (decision 17).
- It states what the model may not be used for first: no pricing, no credit or limits, no decision without a named reviewer, nothing sellable, and no language model in any path that sets an offer or a price.
- Limitations are explicit: another market, undocumented provenance, four months of history, an educational licence, a spent test window, no causal claim and no network-quality features.
- Ethics, selection bias and maintenance are covered; `circle_id` is the only region field and it is dropped before training, checked on 2026-09-21.
- No naive-versus-honest table is invented. Instead the card shows validation PR-AUC 0.4582 against test 0.3477 and names the four traps the design avoids.
- **Acceptance met.** A fresh clone of `Ali_Branch` on 2026-09-21 ran the README pipeline and reproduced every committed report byte for byte, with `git status` clean.
  Corrected on 2026-09-26: that pipeline did not write every report, so `git status` could not show the others changing.
  The T1 profile, the high-value dataset report, the readiness decisions report and the uncertainty report are now in the README rebuild, and on 2026-09-26 a fresh clone ran it with `git status` clean.
  The three research reports (T12, T13, T17) need their own environments and long runs and have never been rerun.
- The same run rebuilt bundle `lightgbm-2026-09-19-ef9430fb` and tier artifact `tiers-v1-cd15525cb3ef`, which confirms the T21, T15, T14 and dependency changes did not move the frozen champion.
- The README already listed every command; the full-pipeline block now also runs `fit-tiers` and `tiers`, which the service and the app need, and links the model card.
- `tests/test_model_card.py` compares the card's figures against the reports, so a stale number fails the suite instead of reaching the copilot.
- 16 new tests; 341 prepaid tests, lint and formatting pass.
- Scoring the 30,000 unlabeled customers with the real bundle gives high 1,209, medium 3,594, low 22,779 and already silent 2,418 (fresh clone, 2026-09-21).

## T10 - Value tiers (syllabus Ch 6)

**Owner:** Ali (implementation with Codex)
**Status:** Done
**Depends on:** T8, T18

Scope:
- Prepaid value scores per customer, from the two feature months only, adapted from `Ali_Branch`'s prepaid RFM (`src/cvm/features/rfm_le.py`):
  recency (days since last recharge), frequency (recharge count), monetary (recharge amount in LYD, from T18), tenure (age on network) and engagement (how many of voice, data, packs and roaming a customer uses).
- Rule-based tiers from score quintiles, readable by a business user; this is `value_tier` in the output contract.
- 12-month value in LYD: monthly value times the expected months kept, from the calibrated churn probability, capped at 12 months.
  T11 uses it.
- K-Means on the scaled scores with k chosen by silhouette score, a dendrogram (hierarchical clustering) on a sample, and a PCA 2-D plot of the clusters, adapted from `Ali_Branch`'s `src/cvm/models/m2_value/segmentation.py`.
- A short, honest comparison of rule-based tiers vs clusters.
  If the silhouette shows no clear structure, the report says the tiers are a reporting convention, not a discovered structure (as `Ali_Branch` found on its data).
- `churn tiers` command.

Acceptance:
- Every customer gets exactly one tier.
- Tiers are computed without the label month.
- Plots and the comparison are in `reports/tiers.md`.

Findings (2026-09-20):
- Adapted Ali's five-dimension prepaid RFM and exploratory clustering design to the existing two-month windows (decision 19; port log step 7).
- Training-frozen dimension and composite cutoffs, the T18 LYD rate and a version fingerprint are saved in `artifacts/tiers/tiers.json`.
- Ties are preserved, constant dimensions stay neutral, and a subscriber receives the same output alone, reordered or in a batch.
- The full `churn tiers` path extends the T8 output using the same export and a gated bundle; `--tiers-only` explicitly leaves risk-dependent scenarios unavailable.
- Already-silent customers receive a tier but no invented probability or value estimate.
- The 12-month revenue scenarios and hazard sensitivities are documented assumptions, not validated CLV or measured offer savings.
- The training fit uses 45,858 customers; every one of the 30,000 unlabeled export customers receives one of the five tiers.
- K-Means selects k=2 with silhouette 0.2766, showing weak separation; adjusted Rand agreement with tiers is 0.2702.
- `reports/tiers.md` contains the comparison, training cutoffs, illustrative value scenarios, PCA plot and sampled Ward dendrogram.
- Tests cover absent/invalid inputs, ties, missing activity, silent customers, ID preservation, artifact corruption, future-field exclusion, single-customer consistency and CLI integration.
- 202 prepaid tests pass; lint, format and locked offline sync pass.
- No churn model was retrained, no real-data test evaluation was repeated, and no raw or customer-level artifact was added to Git.
- Checked on 2026-09-26 on the validation customers (decision 41): the scenario's constant-risk and no-comeback assumptions do not hold.
  High-band customers who stayed active in month 8 churned at 11.0% in month 9, not the 43.2% predicted, and low-band ones at 3.6% instead of 0.9%.
  28.1% of those silent in month 8 were active again in month 9.
  So the 12-month value of high-risk customers is understated, and T11's ranking inherits it; T23 is the fix.

## T11 - Retention decision layer

**Owner:** Ali (implementation with Codex)
**Status:** Done
**Depends on:** T8, T10, T16, T18

Scope:
- Action space: the real Almadar catalogue (T16) plus "no offer".
  "No offer" wins whenever no offer has a positive expected value, and the report says how often that happens.
- Expected value per customer and offer: churn probability x share of churners the offer saves x 12-month value (T10) - offer cost.
  The share saved and every cost are assumptions in one config file and are printed in the report; none is presented as a measured fact.
  Costs use the delivery cost estimates from T16 and are labelled as estimates.
- Offers prefer Almadar's own off-peak and bonus-data products (for example the 1 LYD morning pass, 06:00 to 11:00) over price discounts.
- Guardrails, adapted from `Ali_Branch` (`src/cvm/decision/`):
  - a per-customer spend cap relative to the customer's value;
  - a total budget filled greedily by expected net value;
  - no offers to low-risk customers;
  - a cannibalisation guard keyed on the bundle a customer holds (T18): a cheap unlimited offer is never proposed to a customer on a monthly bundle above the base rung (نت 20, 35 LYD), because it can pull them down to a cheaper package.
- The report compares the targeted campaign with treating everyone **at the same spend**, and with targeting by churn risk alone.
  (Lesson from `Ali_Branch`: comparing campaigns with different budgets measures the budget, not the targeting.)
- A random holdout group (default 10%) that gets no offer, so a real campaign can measure the true effect later.
- Each subscriber row gets `value_tier`, `recommended_offer_id` and a plain-language `offer_reason` in Arabic and English, extending the T8 output contract.
- A decision log with the reason for every offer.
- Human approval step (decision 14):
  - `churn decide` only writes **proposals** (status `proposed`), each with customer ID, offer, reason, expected cost and expected value.
  - A named reviewer approves or rejects proposals, one by one or the whole list, with `churn approve --proposals <file> --reviewer <name>` (and later from the T14 app).
  - Only approved rows go into the released campaign file that the chatbot and any sending system read; rejected and unreviewed rows never leave.
  - The decision log records the reviewer, the time, the decision and an optional note for every proposal.
- `churn decide` and `churn approve` commands.

Acceptance:
- Tests for each guardrail, including the cannibalisation guard.
- Holdout assignment is random, reproducible with a seed, and never receives an offer.
- Tests show that unapproved or rejected proposals never appear in the released campaign file, and that every approval is logged with a reviewer name.
- `reports/decisions.md` states every assumption next to the results, including the equal-spend comparison.

Findings (2026-09-20):
- `retention.py` follows the existing pure-function and thin-CLI patterns, adapting Ali's guardrails, budget comparison and decision-log design (decision 20; port log step 8).
- `data/almadar/retention.toml` declares the budget, per-customer campaign cap, holdout, saved-share assumptions and delivery-cost estimates in one file.
- Decisions use the same raw export for gated risk, frozen value and the mapped held bundle; no model is trained or reevaluated.
- Only positive-value catalogue bonuses can be proposed; no offer is explicit for low risk, inactivity, unavailable risk, holdout, guard failures, nonpositive value and budget exhaustion.
- Cheap unlimited products are blocked above the 35 LYD base monthly rung; unknown 5G and family eligibility also excludes a product.
- Costs and budgets use integer dirhams, with conservative rounding; allocation is deterministic greedy net-value ordering.
- The report compares untargeted and risk-only allocation at the exact targeted spend in expectation, with fractional counts only in diagnostic baselines.
- Seeded hash holdouts are stable across ordering and batches; 2,965 of the 30,000 real export rows were assigned to holdout.
- `campaign.py` stores input, catalogue, policy and proposal snapshots with a fingerprint, plus named review events.
- `churn approve` reviews selected IDs or all pending proposals, supports rejection and notes, and releases only approved rows without internal risk/value fields.
- CSV edits cannot approve offers, reviews are serialized with a lock, JSON writes are atomic, and `--refresh` recovers derived files without approving pending rows.
- All 30,000 real-export rows received a decision; the report is explicitly a no-bundle readiness run with zero offers and no effectiveness claim.
- 247 prepaid tests, lint and formatting pass; tests use hand-made data, including the full bundle-to-decision path and positive approval/rejection scenarios.
- No real customer campaign was approved, sent or released; no customer-level artifacts were committed.
- Local reviewer names are not authentication, and caps are per campaign rather than annual; T15 and a future spending ledger must address those boundaries before shared operational use.

## T12 - Sequence benchmark (syllabus Ch 8, Ch 9 RNN)

**Owner:** Taha + Claude
**Status:** Done
**Depends on:** T7

Scope:
- A Keras LSTM over the monthly steps of each window, with dropout and early stopping on validation customers.
- Calibrate it the same way as T7 and compare it with LightGBM on the same frozen test.
- Explain the result honestly: with only two monthly steps per window, LightGBM is expected to win.
- TensorFlow goes in the `experiments` dependency group.

Acceptance:
- `reports/sequence_benchmark.md` with the comparison table and a written verdict.

Findings (2026-09-22, `reports/sequence_benchmark.md`):
- `uv run churn sequence-benchmark` trains the LSTM, calibrates it on validation customers and scores the frozen test window once; it takes about 20 seconds on a laptop CPU.
- The LSTM reads the two monthly steps as a sequence of 53 measures plus tenure, and the T5 features are deliberately withheld from it: they are the movement between the months, which is what the sequence model is supposed to derive.
- Result: PR-AUC 0.2326 against LightGBM's 0.3477 and logistic regression's 0.2770; capture at 10% 0.4941 against the champion's 0.6152; calibration is fine (0.0016 off).
  It fails two of the four release checks and would not be released (decision 28).
- Keras runs on the torch backend rather than TensorFlow, because T13's CTGAN needs torch anyway; `uv sync --group experiments` installs both (decision 27).
- SDV is deliberately not in that group: it caps pandas below 3 and downgraded the whole project, which broke the frozen bundle's version check.
- The run reproduces: seeded through `keras.utils.set_random_seed`, and two runs wrote a byte-identical report on this machine.
- 6 new tests, one of which is skipped when the experiments group is not installed; 396 prepaid tests pass.
  The Keras and torch deprecation warnings in the test output come from those libraries, not from this module.

## T13 - Synthetic data experiment (syllabus Ch 9 GAN)

**Owner:** Taha + Claude
**Status:** Done
**Depends on:** T4, T18

Question: can an operator share a synthetic copy of its customer data (real data cannot leave the operator) and still get a useful model?

Scope:
- Reuse `Ali_Branch`'s synthesis engine (`src/cvm/synthesis/ctgan_engine.py`) and quality gate (`quality_gate.py`), refit on window A train customers only instead of Cell2Cell.
  So the synthetic customers' churn is learnt from real behaviour, not drawn from a formula.
- CTGAN, with a Gaussian copula as a simple baseline.
- Train on synthetic, test on real validation customers; compare with train on real.
- Detection test: a classifier that tries to tell real from synthetic rows (lower ROC-AUC means more realistic).
- SDMetrics quality report.
- The synthetic copy can be shown in Almadar terms through T18, which makes it a shareable "synthetic Almadar customer base" for demos.
- SDV goes in the `experiments` dependency group; its Business Source License allows non-production use.

Acceptance:
- `reports/synthetic.md` with the train-on-synthetic vs train-on-real table and the detection ROC-AUC.
- The synthetic data is never used to train the production model.

Findings (2026-09-22, `reports/synthetic.md`):
- `uv run --script experiments/synthetic.py` runs the whole experiment in about 90 seconds and writes the report.
  It is a standalone script with its own environment because SDV caps pandas below 3, which would downgrade the module and break the frozen bundle (decision 27); it imports this package for the Almadar rules and the LightGBM settings, so nothing is duplicated.
- Setup: 6,000 real training customers, 28 features (the 18 strongest by gain plus the columns T18 needs), CTGAN at 60 epochs on a CPU, and a Gaussian copula as the baseline.
- Utility, scored on the same 9,812 real validation customers: real training 0.3238 PR-AUC, copula copy 0.1456 (45%), CTGAN copy 0.0491 (15%).
- Detection ROC-AUC is 1.000 for both copies, so neither is realistic enough to pass for real data.
- CTGAN lost the churn rate: 16.8% churners against 4.7% real. The copula kept it (5.1%).
- In Almadar terms (T18) the copies are visibly wrong: real customers are 72% pay-as-you-go, 14% monthly, 14% daily; the copula copy is 86% daily and 0% pay-as-you-go, CTGAN is 44% monthly.
  Every column is inside its real range, and the customers are still on the wrong packages.
- Verdict: a synthetic copy here is a demo, a schema and a pipeline test, not a way to share customer data (decision 29).
  That is the measured version of decisions 7 and 15, which cut generated populations and formula labels on the same argument.
- Honest note: the first fidelity check counted negative amounts and reported 54% for both copies; it was wrong, because `diff_*` columns are negative for half the real customers too, so the same check called the real data 58% impossible. The corrected check is 0% for both.
- Not measured: privacy. A copy can pass every fidelity test and still memorise a rare customer; membership inference is the test for that, and it is not in this experiment.
- The script is linted by `ruff check` with the rest of the module, and it has no unit tests: it lives in its own environment, so the module's suite cannot import it, and its evidence is the committed report.

## T14 - Demo app

**Owner:** Ali
**Status:** Done
**Depends on:** T8, T11

Scope:
- One Streamlit app, adapted from `Ali_Branch`'s Command Center (`apps/`):
  - Overview: customers and LYD at risk by risk band and value tier, the model version and its test results.
  - Subscriber view: churn probability, top reasons, value tier, the Almadar bundle held and the proposed offer for one customer.
  - Campaign builder: set a budget, see the proposed customers, holdout size, expected cost and value, and the equal-spend comparison, then approve or reject proposals under a reviewer name (the T11 approval step).
  - Customer message preview: the Arabic text of an approved offer as the customer would see it by SMS or in the chatbot.
- It reads the model bundle and decision output; it contains no model logic of its own.

Acceptance:
- `uv run streamlit run ...` starts the app from the README instructions.
- Every screen is opened in a browser and checked, including with a single customer.
  (Lesson from `Ali_Branch`: two of its late bugs were only visible on screen.)

Findings (2026-09-22, after Taha used it):
- It was slow at everything, because a campaign over the whole base is an 80 MB snapshot that was parsed twice per load and again after every review.
  It is parsed once now, and the app can propose a campaign over as few customers as it likes: 500 customers is a 1.7 MB snapshot that loads instantly.
- A campaign picker in the sidebar names the campaign every screen is reading, its size and how many offers are approved in it.
- The Campaign builder proposes a new campaign (customers considered, budget, name) through the same path as `churn decide`, and the Subscriber screen proposes for one customer.
  Neither picks a package and neither approves anything (decision 34).
- A new Released screen answers "I approved it, where did it go": the approved rows, the package beside each one, the reviewer, the three files and the chatbot endpoint that serves them.
- Fixed a real hazard: an empty selection in the approval box used to mean "approve every pending proposal". It is an error now, and reviewing them all is a separate checkbox that says how many.
- Taha's own 15 approvals from that session are intact in `artifacts/campaigns/full-base-30000`, which is still in the picker.
- The Subscriber screen also gained a "Pick a high-risk one" button, because a random customer on this base is almost always a "no offer" and finding one to look at took several tries.
- 5 new tests; 401 prepaid tests, lint and formatting pass.

Findings (2026-09-21):
- Four screens in `app/`, over the pure `src/prepaid_churn/demo.py`; loading goes through `service.load_state`, so the app and the T15 endpoints answer from one state.
- Start it with `uv run streamlit run app/Home.py`; `PREPAID_CHURN_CAMPAIGN_DIR` and `PREPAID_CHURN_PORTFOLIO` choose which campaign and export to show.
- The app recomputes nothing. Its only write is a review, through `campaign.review_file`, with the same lock, atomic replacement and named audit event as `churn approve`.
- The budget control is an explicit preview over the campaign's own stored inputs; it is never written and nothing in it can be approved (decision 22).
- Every screen was opened in a browser on 2026-09-21: against the real 30,000-row export, a five-customer campaign and a one-customer campaign.
- The browser check found five defects the unit tests had not, all now fixed: an alphabetically sorted axis that put the value tiers in a meaningless order, a typed ID silently overriding the random-pick button, fractional tick marks for whole customers, "1 customers", and "reviewed by nan" on an unreviewed proposal.
- Approving on screen was verified end to end: the reviewer name is required, `review_log.jsonl` records subscriber, reviewer, decision, UTC time and campaign fingerprint, and only the approved row reaches `released.csv`.
- The SMS preview reports parts rather than characters alone. The approved message on the checked campaign is 102 characters and sends as **two** UCS-2 parts, so T11's reason text does not fit one SMS in Arabic; that is a real finding for T11 to consider, not a display detail.
- The customer message carries no churn probability, risk band, value figure or reviewer name.
- The subscriber screen refuses an ID shaped like a Libyan mobile number before any lookup, which was checked in the browser.
- 26 new tests; 325 prepaid tests, lint and formatting pass.
- `streamlit` is added as a dependency; charts use Altair, which Streamlit already installs.
- Limitations: outputs are cached per session and reread after a review or a restart, and the app is a local development server, not a deployed one.

Readiness follow-up (Ali, 2026-09-22):
- All five page scripts passed `AppTest` on the rebuilt 30,000-subscriber export, and the Streamlit server passed HTTP startup.
- Literal `NA` IDs now retain their Almadar view, and chart widths use the current Streamlit argument.
- Permanent hand-made regressions cover rendering, empty-selection refusal, individual approval, refreshed message selection and Arabic/English previews.

## T15 - Integration service for the chatbot and copilot

**Owner:** Ali
**Status:** Done
**Depends on:** T8, T11

Part of the MVP (decision 17): the chatbot and copilot call this service; they never import the package or read its files.

Scope:
- A small FastAPI app that only reads the latest released outputs; it has no model logic, and nothing can be created, changed or approved through it.
- Endpoints:
  - `GET /health`: bundle loaded, smoke prediction passed, date of the latest outputs.
  - `GET /catalogue`: the Almadar packages (T16), for the chatbot.
  - `GET /subscribers/{id}/retention`, for the chatbot: the offer and its reason only if a reviewer approved it (T11), never the churn probability; 404 when there is no approved offer.
  - `GET /portfolio/summary`, for the copilot: customers and LYD at risk by risk band and value tier, plus the model version, its test metrics and the success-threshold results.
- Access control: separate API keys for the chatbot and the copilot, each accepted only on its own endpoints.
- De-identification: IDs are pseudonymous.
  The API rejects IDs shaped like a Libyan phone number (pattern from `Ali_Branch`'s privacy check), and a `pseudonymize` helper (salted SHA-256, from `Ali_Branch`'s `src/cvm/ingest/hashing.py`) is provided for operators to hash phone numbers before export.
- Response models match the output contract, so the OpenAPI page at `/docs` doubles as the integration documentation.

Acceptance:
- Tests call every endpoint with FastAPI's test client, including with a wrong key and with a phone-number ID.
- A test shows the chatbot endpoint never returns a churn probability or an unapproved offer.

Findings (2026-09-21):
- `service.py` holds the pure read-only state and the payload builders; `api.py` is the thin FastAPI layer; `privacy.py` is the ported identifier check.
- T20 later added a fifth endpoint to this service, `GET /subscribers/{id}/risk` for the copilot, for the reason in decision 26.
- Every route is a GET, and a test asserts the generated OpenAPI document contains no other method, so the service has no write path.
- Approved offers are read from the authoritative `proposals.json` through `released_campaign`, never from the derived `released.csv`, so a hand-edited CSV still cannot publish an offer.
- One key per consumer in the `X-API-Key` header, compared in constant time; the copilot key is refused on chatbot endpoints and the chatbot key on `/portfolio/summary`.
- Both keys come from the environment with no default, must be at least 24 characters and must differ; the service refuses to start otherwise (decision 21).
- `/health` needs no key, reports bundle loaded and smoke prediction separately, and is `ok` only when the bundle predicts and a portfolio exists.
- The chatbot response model forbids undeclared fields, and omits the churn probability, the risk band, every value figure and the reviewer's name.
- Rejected, unreviewed, unproposed and unknown subscribers all return the same 404 message, so no one can infer that an offer was considered and refused.
- An ID shaped like a Libyan mobile number is refused with 422; a salted SHA-256 digest is looked up normally, checked over 500 generated digests.
- `lyd_at_risk` is value weighted by churn probability, and is null rather than zero when an export carries no risk estimate.
- 52 new tests; 299 prepaid tests, lint and formatting pass.
- Run against this checkout on 2026-09-21: degraded with no bundle, all 57 packages served, 30,000 subscribers summarised with `risk_available` false, zero approved offers.
- Limitations: outputs are loaded once, so a new release is served after a restart; the keys are service-to-service access control, not per-user authorization, and assume the service is not exposed publicly.
- T20 still owns `docs/integration.md`, the example client and the walkthrough with the chatbot and copilot owners.

Readiness follow-up (Ali, 2026-09-22):
- The real API served the frozen bundle, 30,000 subscribers and 37 current packages with health `ok`.
- Portfolio IDs preserve literal text and reject empty or duplicate identifiers; malformed non-ASCII credentials return 401.
- Approvals for packages absent from the current catalogue are withheld and explained in health (decision 33).

## T16 - Almadar catalogue and market facts

**Owner:** Claude
**Status:** Done
**Depends on:** nothing

Why: the retention offers (T11) and the team's customer chatbot both need the real prepaid packages, and Ali collected Almadar's (decision 16).

Scope:
- Keep Ali's Almadar source files unchanged in `data/almadar/source/`.
- `data/almadar/offers.csv`, one row per package: offer ID, operator, family, Arabic and English name, price in LYD, validity, data volume or unlimited, minutes, speed caps, time window, where the volume comes from, source row and collection date.
  It holds only what the operator sells, so the chatbot can read it as is.
- `data/almadar/market.toml`: recharge cards, pay-as-you-go tariffs, the two emergency credit products, the ARPU assumption and the delivery cost estimate, each with its status (confirmed, reported, assumption or estimate) and source.
  TOML instead of YAML, because Python reads it without a new dependency.
- A loader and validation in `src/prepaid_churn/almadar.py`, and `docs/almadar.md` explaining the files and how to refresh them (prices change, so every row keeps its collection date).
- Libyana can be added later as rows with its own operator value.
- Share `offers.csv` with the chatbot owners: it is the action plan's "Offer / Package Catalogue".

Acceptance:
- Every row has a source and a collection date.
- A test validates the files: required columns, positive prices, known operator, unique IDs, and a status on every market value.
- The package count matches `Ali_Branch`'s catalogue (37 packages in 12 families), or the difference is explained.

Findings (details in `docs/almadar.md`):
- 37 packages in 12 families, all from the operator's own file; `check_against_source` proves every family, name, price and stated value still matches it, row by row.
- The operator file lists 57; the 20 Mix packages Ali confirmed retired on 2026-09-22 are in `excluded.csv` with a reason, a name and a date, and the check requires every source row to be in one place or the other (decision 31).
- The 20 extra packages against `Ali_Branch` are the five Mix families (data and voice), which Ali removed in commit `62040af` without saying why; they stay until he says the operator no longer sells them (a test pins the difference).
- Data volumes: 31 packages state them, 17 are read from the name ("نت 20" is 20 GB), 6 are reported as unlimited by `Ali_Branch` (Silver and hourly 5G), and 3 are unknown (Social).
- Only one package has a time window: the 1 LYD morning pass, unlimited data and voice from 06:00 to 11:00.
- The recharge cards are `reported` (no operator document yet); ARPU (40 LYD) is an assumption and delivery costs are estimates.

## T17 - Uplift experiment on real data

**Owner:** Taha + Claude
**Status:** Done
**Depends on:** nothing

Why: the SIC action plan lists the Orange Belgium Churn-Uplift dataset, and a retention offer only pays when it changes behaviour (decision 4).

Scope:
- Reuse `Ali_Branch`'s two-model uplift and Qini code (`src/cvm/models/m3_uplift/`), whose Qini was checked against scikit-uplift.
- Orange Belgium, from OpenML (dataset 45580): 11,896 customers, 178 anonymized features, a phone retention campaign with a random control group (about 76% treated, 24% control), churn about 3.5%.
- Criteo Uplift, as in `Ali_Branch` (a 10% sample; held-out Qini 0.0771 there): a large randomized trial, but advertising, not telecom.
- Compare targeting by churn risk with targeting by uplift, using Qini curves on held-out customers.
- Write the lesson for T11's "share saved" assumption in `reports/uplift.md`.
- Limits to state: Orange is postpaid with anonymized features that cannot be combined with our model; Criteo is advertising; both licenses are non-commercial.

Acceptance:
- `reports/uplift.md` with the Qini comparison for both datasets and a written verdict.

Findings (2026-09-22, `reports/uplift.md`):
- `uv run --script experiments/uplift.py` fetches both datasets into the git-ignored `data/external/` and writes the report; the Criteo archive is 311 MB and is downloaded once.
- Criteo (1,397,959 rows, a real randomised advertising test): ranking by uplift reaches a Qini of 0.0698, ranking by predicted response reaches -0.1138, and twenty random rankings span plus or minus 0.0110.
  Realised uplift in the top 30%: +2.89% against +0.02%.
  The response ranking, which is the one T11 uses, is worse than random here.
- Orange Belgium (11,896 customers, a real telecom retention call): every ranking sits inside the noise band, because the held-out 30% holds 3,569 customers and 120 churners.
  The dataset is the right industry and too small to settle anything, and the report says so instead of picking a winner.
- Ali's Qini is ported by hand, including the control-arm rescaling and the perfect-ranking normalisation, and checked at runtime against `sklift.metrics.qini_auc_score`: agreement 8.14e-06 on Criteo, 1.46e-03 on the small Orange holdout.
- Orange's outcome is flipped to retention on purpose; fitting on churn would rank the customers a call *loses* (decision 30).
- The lesson for T11: the riskiest decile is not the persuadable decile, so "share saved" stays an assumption and every LYD figure downstream of it stays a scenario.
  T11's random holdout is the only instrument in this module that can turn it into a measurement, and this is the reason to keep it.
- Neither dataset is committed: both are non-commercial licences, and `data/external/` is git-ignored.

## T18 - Almadar view of the real customers

**Owner:** Claude
**Status:** Done
**Depends on:** T4, T16

Why: decision 16; value, offers, emergency credit and the app speak Almadar's money and packages, while the churn model stays on real behaviour.

Scope, in `src/prepaid_churn/almadar.py`:
- One scale factor from the source currency to LYD, anchored on Almadar's ARPU assumption in `data/almadar/market.toml`, so the shape of real spending is kept.
- Monthly value in LYD from the current month's recharges.
- Usual recharge card: each customer's typical recharge mapped to the nearest Almadar card (5, 10, 20, 40 or 100 LYD).
- Bundle held in the current month: customers with a monthly data pack (upGrad `monthly_2g`, `monthly_3g`) get the Almadar monthly bundle their data spend in LYD would buy; customers with only short packs (`sachet_2g`, `sachet_3g`) get a daily pack; the rest are pay-as-you-go.
- Uses only the feature months of a window, never the label month.
- `churn almadar-view` writes the view for a dataset and `reports/almadar_view.md` with the distributions, the share on each bundle and every assumption.

Acceptance:
- Unit tests for each mapping rule on hand-made frames.
- The report lists every assumption with its status.
- The view never changes a churn feature or the model.

Findings (`reports/almadar_view.md`, rules in `docs/almadar.md`):
- Taha chose the 40 LYD ARPU on 2026-09-19.
  The rate is 40 LYD over 537.17, the mean monthly recharge of the 64,509 customers active in month 8 of `train.csv` (stored in `market.toml` as a measured fact), so 1 unit of the source currency is 0.074464 LYD.
- On the scoring base (Kaggle's `test.csv`, 27,582 active customers): mean spend 39.39 LYD a month, median 22.08, 10th percentile 5.21, 90th percentile 82.13.
- For 88.9% of active customers the nearest card to their usual airtime recharge is the smallest, 5 LYD, and for 9.1% it is 10 LYD; small top-ups dominate, as `Ali_Branch` argued.
- Bundles held: 71.3% pay-as-you-go, 14.4% a monthly bundle (mostly Net 6, the floor for small data spend) and 14.3% a daily pack.
- A test changes month 8 and checks that a window A view does not move; breaking the code to read month 8 makes it fail.

## T19 - Emergency credit advice

**Owner:** Ali
**Status:** Done
**Depends on:** T16, T18

Why: Almadar's two emergency credit products (an airtime advance of 1, 3 or 5 LYD and a 5 LYD data advance) are the most Libyan part of Ali's work, and a safe limit can be set from real recharge behaviour.

Scope:
- Rule-based advice, adapted from `Ali_Branch`'s `conf/advance.yaml` and `src/cvm/decision/advance_limit.py`: never advance more than the customer's usual recharge card can clear (affordability ceiling).
- State the zero-residual finding from `Ali_Branch`: the 5 LYD data advance equals the smallest 5 LYD card, so clearing it leaves the customer at zero balance; the smaller airtime advances avoid this.
- No repayment model: no real repayment data exists (decision 15).
- Advice is a proposal for a person, like offers (decision 14).

Acceptance:
- Tests for the ceiling and the denominations.
- `reports/emergency_credit.md` with the share of customers per advised limit and every assumption.

Findings (2026-09-21):
- `src/prepaid_churn/advance.py` advises a limit and grants nothing; `churn advance` writes the advice and the report.
- One rule: never advise a debt above 0.6 of the customer's typical top-up, ported with Ali's reason, and the code refuses any fraction at or above 1.
- Only denominations the operator sells are advised, so a 2.9 LYD ceiling advises 1 LYD rather than inventing a 2 LYD advance.
- The zero-residual finding is computed from `market.toml`, not hardcoded: the smallest card, the data advance and the top airtime rung are all 5 LYD, so clearing either leaves 0 LYD.
- A test shows the finding would retire itself if the operator ever sold a larger smallest card.
- The basis is an adaptation. Ali asks for the modal top-up; this data has only monthly totals and counts, so the quieter month's average per recharge is used, which is never larger and so cannot widen the advice.
- That choice moves the result by more than twenty points, so the report carries a sensitivity table across the quieter month, the mean and the busier month, and both months travel beside each verdict.
- **The result is a finding about the product.** This base tops up often in very small amounts, with a median typical top-up of 1.89 LYD against five to six recharges a month.
- The smallest advance needs 1.67 LYD to clear while leaving balance, so 46.1% of customers are advised nothing; the flat 5 LYD data advance needs 8.33 LYD and is advised for 4.65%, though the operator offers it to anyone with a low balance.
- Advised airtime limits: 1 LYD for 37.51%, 3 LYD for 11.70%, 5 LYD for 4.65%, declined for 46.14%; 0.90% had no recharge at all.
- Not ported, each for a stated reason: the repayment model, tier ceiling, CLV cap, cooling-off, chronic distress, lockout step-down, reject inference and fee structure.
- 38 new tests; 379 prepaid tests, lint and formatting pass. No new dependency.

## T20 - Integration check with the team platform

**Owner:** Taha + Claude; Ali for the 2026-09-22 readiness follow-up
**Status:** Done
**Depends on:** T15

Why: the final goal is one platform (decision 17), and `Ali_Branch` noted that nobody had ever called its API from the other side.

Scope:
- `docs/integration.md` for the chatbot, copilot, network ML and GIS owners, adapted from `Ali_Branch`'s `docs/INTEGRATION.md`:
  - endpoints with request and response examples, API keys and pseudonymous IDs;
  - the grounding rules for LLM consumers: never set a price, offer or limit; never invent a number; cite the response field; refuse rather than guess; never cache an offer;
  - which documents the copilot may index;
  - the future field contract for per-subscriber network quality from network ML.
- A small example client (a chatbot lookup and a copilot summary).
- A contract test that runs the example client against the app.
- Walk through it with the chatbot and copilot owners (Taha and Ali) and record what they still need.

Acceptance:
- The example client works against a running service, following the README.
- The chatbot and copilot owners confirm in this ticket's Findings that the responses give them what they need.

Findings (2026-09-21):
- [docs/integration.md](docs/integration.md) is written for four owners at once: it says why the seam is HTTP rather than an import, how to start the service, what each endpoint answers with real captured responses, the six grounding rules for components that use a language model, which files a retriever may index and which it may never touch, and what this module would need from network ML.
- Every example in it was captured from a running service, not written by hand; the guide is checked against the live OpenAPI document by a test, so a route or a key it misses fails the suite.
- `src/prepaid_churn/client.py` is the example, written to be copied rather than imported: standard library only, keys and base URL as arguments, no dependency added on either side (decision 25).
- `churn check-integration --url <url> --subscriber-id <id>` runs it and prints what each consumer sees, including the four refusals: the copilot's endpoint with the chatbot key (403), a chatbot endpoint with the copilot key (403), no key at all (401) and an ID shaped like a Libyan phone number (422).
  It exits 1 when a refusal did not happen.
- Run on 2026-09-21 against a service holding the 30,000-subscriber base, the gated bundle and a campaign with two approved offers and one rejected: status ok, 57 packages, `SABAH_1` returned for subscriber 70008 with its Arabic reason, 176,494 LYD at risk across the bands, 4 of 4 success thresholds passed, and every refusal correct.
- The contract test starts the real app on a real port and calls it over a socket, rather than in process as `test_api.py` does, because the seam is the thing this ticket proves.
- 9 new tests; 388 prepaid tests, lint and formatting pass.
- The network ML contract is keyed by the pseudonymous subscriber ID rather than by `cell_id` as `Ali_Branch` had it, because this module never sees a cell; it also states that adding any such field means a new frozen champion, so it is a version 2 change.
- For the antenna and cell placement owners the honest answer is that we have nothing per cell to give; the guide says so rather than implying a join that nobody can make.
Walkthrough (2026-09-22), which is the acceptance:
- Taha asked for the remaining work to be finished by us rather than waiting on other owners, and he owns the chatbot and the copilot in the action plan, so the walkthrough was run from the consumer side here.
- The method: ask the questions each consumer really gets, rather than checking that the documented calls answer. The chatbot passed. The copilot did not.
- **The gap:** an employee with a customer on the phone asks what we know about them, and the service could answer only with portfolio totals. `GET /subscribers/{id}/risk` was added for the copilot, with the probability, risk band, the model's own reasons, the value tier and the 12-month scenarios (decision 26).
  Both subscriber lookups share a path prefix, so each key is refused on the other's, and a test proves it over a real socket.
- Four questions are deliberately not served, each written in the guide with its reason: the package a customer holds, the emergency credit advice, a bulk list of risky customers, and the review queue.
- The check now covers five refusals and ran clean against a live service (its timestamps are UTC, so they read 2026-09-21): status ok, 57 packages, the approved offer, 176,494 LYD at risk, subscriber 70008 high risk at 0.52 with three reasons, and every refusal correct.
- 390 prepaid tests, lint and formatting pass; 11 of them are T20's.
- Reopen this ticket if a response shape turns out to be wrong when the chatbot and the copilot are actually built; the network ML and antenna owners have not read the guide yet, and neither consumes this module today.

Readiness follow-up (Ali, 2026-09-22):
- The real consumer and CLI passed all five refusals over the rebuilt artifacts and an isolated reviewed campaign.
- Degraded health, unavailable portfolio risk and a failed release gate now fail the check; unavailable LYD at risk stays unavailable.
- Redirected Arabic output now uses UTF-8, with a subprocess regression for a Western Windows code page.

## T21 - Code and logic review

**Owner:** Ali (review requested and implemented with Codex)
**Status:** Done
**Depends on:** T2, T3, T7, T8

Scope:
- Review `tahaDev` and deliver fixes only on `Ali_Branch`, preserving the source coding style and methodology (decision 18).
- Fix invalid input acceptance, identifier corruption, stale derived flags and bundle consistency checks.
- Remove redundant prediction work without changing calibrated outputs or frozen choices.
- Review GIS and the legacy modules, implement independent correctness/performance fixes and document modelling follow-ups.

Acceptance:
- Synthetic regressions reproduce the original defects and pass after the fixes.
- Lint, format checks and the full prepaid test suite pass.
- GIS tests pass, and batched density queries match the original counts.
- Valid real exports retain the same model features in both windows.
- Findings, benchmark limits and bundle migration steps are documented in [../CODE_REVIEW.md](../CODE_REVIEW.md).

Findings:
- 170 prepaid tests and 21 GIS tests pass; lint and formatting are green.
- The stricter schema accepts both committed raw exports, with identical model features.
- Calibration uses two model prediction calls instead of five; the focused density benchmark is 4.00 times faster.
- The frozen champion choices and real-data test results are unchanged.
- No new infrastructure, dependencies or business logic were introduced.
- The 2026-09-22 serving and dashboard acceptance review fixed the issues in decision 33 and added the live-run evidence in [reports/end_to_end.md](reports/end_to_end.md).
  Validation now passes 420 tests with none skipped; the frozen model and prior research results are unchanged.

## T22 - Score and retrain on any calendar months

**Owner:** unclaimed
**Status:** Open
**Depends on:** T2, T4, T8

Why: decision 11 says what can be sold is the pipeline retrained on an operator's own export, but the input edge only accepts June to August (T8 findings, 2026-09-26).
Inside, the pipeline already uses relative months (T4's `prev_` and `cur_`), so the fix is at the edge.

Scope:
- The data contract and `validate` accept any consecutive calendar months, including a window that crosses a year end.
- The `vbc_3g` column names cover all twelve months.
- `churn score` takes the export's two latest months as previous and current, instead of the fixed months 7 and 8.
- `churn build-dataset` builds its windows from the export's own months and label month, instead of 6 to 9.
- The Kaggle files keep working unchanged.

Acceptance:
- The hand-made fixture relabelled to November, December and January, which have the same month lengths as June, July and August, validates and scores to exactly the same probabilities, bands and reasons.
- An export whose dates do not fall in the months its columns name is still refused.
- The contract's text changes, so its fingerprint changes: the bundle is rebuilt from the existing champion and gate with `churn bundle`, keeps version `lightgbm-2026-09-19-ef9430fb`, and the README rebuild still leaves every committed report unchanged.

## T23 - A 12-month value built on measured risk and comebacks

**Owner:** unclaimed
**Status:** Open
**Depends on:** T10, T11

Why: the 12-month value assumes a customer keeps this month's risk for a year and never comes back after going silent, and both assumptions fail on the validation customers (decision 41).
Under them, risk times value peaks near 20% risk, so T11 gives its riskiest customers less reason for an offer than medium-risk ones.

Scope:
- The value an offer protects is the value if the customer stays this month: this month's spend, then later months at risks measured on validation customers who stayed active, by risk band.
- A customer who goes silent can come back, at the rate measured on validation customers.
- The low, base and high scenarios stay, as sensitivities around the measured rates.
- T11, the service's "LYD at risk" and the demo use the new value; the tiers report, decision 19, the model card, the integration guide and the brief get the new numbers.

Acceptance:
- At the same spend, a customer at 43% risk carries a larger expected loss than one at 20%, and one at 90% the largest.
- The measured rates are fitted on validation customers only and stored in the versioned tier artifact, so nothing is fitted on the batch being scored.
- The churn model, its thresholds and the spent test window are unchanged, and the README rebuild still reproduces every report the change does not touch.
- The campaign numbers that change are reported next to the old ones, not silently replaced.

## Future work (needs real operator data)

- Airtime advance limits learnt from repayment history (T19 is the rule-based first step).
- Network-quality features (dropped calls, outages) from the network ML team, through the T20 field contract.
- Uplift models on our own customers, once a campaign with a holdout group has run.
- Retraining on Almadar's own export, which is what a commercial deployment requires (decisions 11 and 16); T22 has to come first.
