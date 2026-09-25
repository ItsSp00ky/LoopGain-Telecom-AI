# Prepaid module end-to-end readiness check

Date: 2026-09-22.
Branch: `Ali_Branch`, starting from `d83fc9a`.
Environment: Windows, Python 3.12, the locked runtime and the optional `experiments` dependency group.

## Result

All 22 tickets, T0 through T21, are marked Done.
The prepaid module runs from the committed raw exports through scoring, value tiers, retention proposals, the HTTP service and the dashboard.
It is ready for a local demonstration and consumer integration testing with the existing data.
This check does not establish performance on Almadar subscribers or the effect of actually sending a retention offer.

## Pipeline reproduced

The following commands ran successfully from `prepaid_churn/` in the locked environment:

```bash
uv run churn build-dataset
uv run churn train
uv run churn evaluate --chosen-at 2026-09-19
uv run churn bundle
uv run churn score
uv run churn almadar-view
uv run churn fit-tiers
uv run churn tiers
uv run churn advance
uv run churn decide --output-dir artifacts/campaigns/e2e-20260922
```

The frozen rebuild produced bundle `lightgbm-2026-09-19-ef9430fb` and tier artifact `tiers-v1-cd15525cb3ef`, matching the recorded release.
The model passed all four release checks.
No model, feature, calibration method or threshold was changed, and rebuilding left every existing tracked report unchanged.

| Output | Result |
|---|---|
| Scored subscribers | 30,000 |
| Low / medium / high risk | 22,779 / 3,594 / 1,209 |
| Already silent | 2,418, with no churn probability |
| Value tiers | One for every subscriber |
| Subscribers with 12-month revenue scenarios | 27,582 |
| Emergency credit advice | 30,000 rows; no credit granted |
| Current catalogue | 37 packages; the 20 retired Mix packages remain excluded |
| Retention proposals | 2,911; no approvals in the original campaign |

The proposal report is local at `artifacts/campaigns/e2e-20260922/decisions.md`.
The existing default `artifacts/campaigns/retention` campaign was preserved, so select the new directory explicitly when opening the demo or starting the service.

## Running service and screens

The API ran on a real loopback socket with the rebuilt model, all 30,000 subscribers and a separate QA copy of the campaign.
Temporary API keys were generated in memory.
Only the QA copy was reviewed, using a reviewer and note explicitly identifying it as automated QA.

- `/health` reported `ok`, the expected model version, 30,000 subscribers and the one QA approval present at startup.
- The catalogue returned 37 packages, the copilot received risk and value, and the chatbot received the approved offer without internal risk, tier or reviewer fields.
- Rejected, pending and unknown subscribers received the same no-offer response.
- All five refusals in `churn check-integration` passed, and the actual CLI command completed with its Arabic output intact.
- The Streamlit server answered its HTTP health endpoint and served the application shell.
- Streamlit's `AppTest` executed Home, Overview, Subscriber, Campaign builder and Message preview without page exceptions.
- Subscriber lookup, the phone-number refusal, a zero-budget preview, empty-selection refusal, individual approval and Arabic/English message previews passed.
- Budget preview and empty-selection approval left the authoritative campaign byte-for-byte unchanged.
- Approving one selected QA subscriber refreshed the dashboard and added exactly one customer to the message selector.
- The running API retained its startup snapshot, as documented; a dashboard review does not silently change an API release.
- The original campaign remained byte-for-byte unchanged and had no approved offers when the check ended.

The temporary API and Streamlit processes were stopped after testing.
Screen execution and widget behavior were tested with `AppTest`; this was not a browser screenshot or mobile layout review.

## Problems found and corrected

| Problem | Correction and regression evidence |
|---|---|
| CSV parsing treated the literal subscriber ID `NA` as missing | ID converters preserve literal text in the API portfolio and dashboard view; the API lookup and recharge card now survive the round trip |
| Duplicate or empty portfolio IDs could reach serving | Startup rejects ambiguous identifiers and reports degraded health before a subscriber lookup |
| A non-ASCII API key header could raise a server error | Malformed credentials receive 401; configured keys must be distinct printable ASCII strings without spaces |
| A reviewed package removed from the current catalogue could still be exposed with empty details | Unavailable packages are withheld and reported in health; a new campaign must be created and reviewed |
| The integration checker could say every check passed despite degraded health, missing risk or a failed release gate | Those states now fail the check and the CLI exits 1; unavailable LYD at risk is printed as unavailable |
| Redirected CLI output crashed on Arabic under Windows code pages | The integration report uses UTF-8, with a subprocess regression starting from `cp1252` |
| Chart rendering emitted a deprecated Streamlit width warning | The three chart calls now use the existing `width="stretch"` convention |

All changes follow the existing pure service/client functions, thin CLI and page scripts, and shared hand-made fixtures.
Page-render and review-to-message regression tests now exercise the actual scripts as well as their pure helpers.

## Validation and limits

`ruff check`, `ruff format --check` and the complete prepaid test suite pass: **420 passed, none skipped**.
The optional LSTM test ran after installing the locked `experiments` group.
Third-party deprecation warnings remain in the FastAPI test adapter and Keras/Torch array conversion; they did not cause a failure.
The longer T12, T13 and T17 research experiments were not rerun or retuned; their existing reports and negative findings remain unchanged.

The remaining limits are the ones already recorded in the model card and decisions: another market's prepaid behavior, assumed LYD conversion and retention effects, no operator-side sending or provisioning, and no measured Almadar campaign outcome.
The source links for the Almadar files still need to be supplied.
The example HTTP consumer was tested here; deployment of the other teams' chatbot, copilot and network/GIS applications was outside this prepaid acceptance run.

## Open this checkout

In PowerShell, from `prepaid_churn/`:

```powershell
$env:PREPAID_CHURN_CAMPAIGN_DIR = "artifacts/campaigns/e2e-20260922"
uv run streamlit run app/Home.py
```

This opens the original, unreviewed campaign, so an empty message preview is the expected initial state.
Select and review a proposal on the campaign screen to preview its message.
Do not point a demo or consumer at the isolated QA campaign.

For consumer integration, set two different random API keys of at least 24 printable ASCII characters without spaces and run:

```powershell
uv run churn serve --campaign-dir artifacts/campaigns/e2e-20260922
```

The variable names and consumer commands are in [the integration guide](../docs/integration.md).
Restart the service after reviewing a campaign to publish that new local snapshot to its consumers.
