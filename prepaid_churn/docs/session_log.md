# Session log (Taha + Claude)

The long working sessions, written down so the next session can start without the chat; the newest comes first.
The sources of truth stay where they were: [../CLAUDE.md](../CLAUDE.md), the Handoff at the top of [../TICKETS.md](../TICKETS.md), and [decisions.md](decisions.md).
This file is the narrative that connects them: what happened, in what order, what went wrong, and what is still open.

# Session 2: 2026-09-26 to 2026-09-28

## Where things stand on 2026-09-28

- `tahaDev` holds Ali's work through `bf498d4`, the teammates' GIS and network ML branches (decision 53) and the customer chatbot in `assistants/` (decision 54).
- 37 local commits are not pushed; the last push was `fbc3ac3` on 2026-09-26. Taha pushes only on request.
- The churn module: 475 tests, lint and format green, the frozen champion unchanged.
- The chatbot (T24) is closed: 64 tests green, 21 of 21 evaluation questions on the real model (`../../assistants/reports/chatbot_eval.md`).
- The final report's chatbot part is written; the copilot (T25) is next and planned in its ticket.
- [study_guide.md](study_guide.md) explains the module and the chatbot for Taha.

## Timeline

### 1. Ali's first merge, and the teammates' branches (2026-09-25 and 26)

- `Ali_Branch` through `f0156e2` merged into `tahaDev` (decisions 35 and 36, the recap to T4).
- Taha asked for every teammate branch to be read and merged: Mahmoud's final GIS `integration/antenna-planning-v2`, Maher's `maher_kpi_prediction` and Mohamed's `MNK_forecasting` went in, one merge commit each (decision 53).
  `ahmed_cell_placement` was not merged, because the GIS integration already carries his audited work.
- Two conflicts, where Ali's GIS fix met Mahmoud's rewrite; the owner's version won, and Ali's superseded optimizer test was removed with its guarantees kept by the GIS tests.
- Findings for the owners, in decision 53: Maher's MASE claim (17 of 60, not all), Mohamed's early stopping on the test set, and more.

### 2. The customer chatbot (2026-09-26)

- Taha chose Groq's free Llama 3.3 70B, but Groq had retired it on 2026-08-16; he then chose `openai/gpt-oss-120b`.
- `assistants/` replaced the empty `customer_support_chatbot/` placeholder: one project for the chatbot and the future copilot, with the tool loop, the reply checks and one look taken from the GIS demo page.
- First push of the session: `f2cc724..fbc3ac3`, on Taha's request.

### 3. Real runs, and what they found (2026-09-26 and 27)

- Taha holds the Groq key; he put it in the git-ignored `assistants/.env`, which the chatbot and the evaluation read, so Claude never handles it.
- Every real run found something the tests on a scripted model could not; each fix went into code, not the prompt (the table in [study_guide.md](study_guide.md), Part 6).
- Six evaluation rounds, from a first run that failed every call to 21 of 21.

### 4. Ali's review merged, the chatbot aligned (2026-09-27)

- `Ali_Branch` through `fa1fa21`: decisions 37 to 52, among them the 70 LYD anchor, the removed experiments, the operator no longer named and the customer message for offers.
- Colliding numbers were renumbered on our side: decisions 37 and 38 became 53 and 54, tickets T22 and T23 became T24 and T25.
- The chatbot followed decisions 45, 51 and 52: no operator name, the service's customer message, volumes only as the operator states them. T24 was closed.

### 5. Ali's last commit, the report and the study guide (2026-09-28)

- `Ali_Branch` through `bf498d4` (the credit advice on the Subscriber screen): no conflicts, no chatbot change needed, 21 of 21 again.
- The final report: Ali and Taha's prepaid part was in `SIC_AI_Capstone_Project_Final_Report_Prepaid_Churn_short,_credit.docx` on Taha's Desktop; the chatbot's part was added under every section as a "Customer chatbot" block, cloned from the report's own XML so nothing is restyled, with Tables 3 and 4 and Figures 7 and 8.
  The result is the `_with_chatbot.docx` beside it; the original is unchanged.
- Figures 7 and 8 come from `../../assistants/report_figures/`.
- Ali's own final report ("the brief") is not in the repository; Taha will share it from Telegram.

## Mistakes caught this session, and the lesson from each

- **The chosen model no longer existed.** Check a provider's current models and free limits before building on one.
- **Every call failed silently at first.** GPT-OSS rejects `parallel_tool_calls`, and the error was swallowed; errors now show and the evaluation stops at the first one.
- **Groq validates tool calls against the schema.** The model filled unused arguments with null and the call was refused; every optional argument now accepts null.
- **A cached client outlived a code reload** and raised the old error class; nothing is cached across reloads now.
- **21 of 21 checks passed while answers were wrong** (English answered in Arabic, "no data" for unstated volumes). Always read the answers, not only the checks.
- **Rules in the prompt were followed in one run and not the next.** When code can decide something (language, sign-in, another account's number), code decides it.
- **The heredoc trap struck twice more**: `\n` inside Python written through a bash heredoc becomes a real newline. Write Python files with the Write tool.
- **A report image overwrote the footer logo** (`image7.png` already existed), which also made Word hang. Give new media unique names and check before copying.
- **A test passed for the wrong reason**, monkeypatching a module attribute that a default argument had already bound; the fake is now passed in, and the test asserts it was used.
- **A watcher was pointed at the wrong task output**; check task IDs before arming one.

## Working on this machine (additions to session 1's list)

- The keys live in `assistants/.env` (git-ignored): `GROQ_API_KEY` (Taha's), and the two service keys.
- Start the service from `prepaid_churn/` with the service keys from that file, never reading the Groq line:
  `export $(grep '^PREPAID_CHURN_.*_KEY=' ../assistants/.env | xargs)` then `uv run churn serve --campaign-dir artifacts/campaigns/ui-2026-09-22-200`.
- Start the chatbot from `assistants/`: `uv run streamlit run chatbot_app.py --server.port 8501 --server.headless true`; it listens on 127.0.0.1 only.
- In campaign `ui-2026-09-22-200`, subscriber 70016 has an approved offer (the morning pass) and 70017 has none.
- Word 16 is installed and scriptable: export a `.docx` to PDF through the Word COM object, inside a PowerShell job with a timeout, because a hidden dialog can hang it.
  Then render pages with `uv run --no-project --python 3.12 --with pymupdf`.
- Screenshots of a Streamlit app: headless Edge through the DevTools protocol, with `suppress_origin=True` in `websocket-client` (`../../assistants/report_figures/chatbot_screenshot.py`).
- The GIS research extra cannot install here (`pyrosm` needs the Microsoft C++ build tools); run the GIS tests with the planning environment plus `--with joblib --with lightgbm --with scikit-learn --with rasterstats --with xgboost --with matplotlib --with seaborn --with openpyxl`.
- Maher's tests: `uv run --no-project --python 3.12 --with-requirements requirements.txt --with xgboost`, retrying once if uv reports a path error after building the environment.

## What is on disk but not in git (additions)

- `assistants/.env`, with the keys.
- On Taha's Desktop: the final report as received, and the `_with_chatbot.docx` version.
- `artifacts/scores/` still holds the scored export from before the 70 LYD anchor; T25's first step rebuilds it.

## Branches as last merged into `tahaDev` (2026-09-28)

Anything on these branches after the commit shown is new since this session.

| Branch | Owner | Last merged | Notes |
|---|---|---|---|
| `Ali_Branch` | Ali | `bf498d4` | the prepaid module |
| `integration/antenna-planning-v2` | Mahmoud, with Ahmed | `2eca2dd` | the team's final GIS; the copilot reads `antenna_cell_placement/integrated_release/` |
| `mahalm_antenna_cell_placement` | Mahmoud | `8a2be6c` | contained in the GIS integration |
| `maher_kpi_prediction` | Maher | `732e88c` | `network_kpi_prediction/`: KPI and traffic forecasts |
| `MNK_forecasting` | Mohamed | `2425707` | `KPI_forecasting/`: next-day KPI predictions |
| `ahmed_cell_placement` | Ahmed | not merged (`15dc13a`) | superseded by the GIS integration (decision 53) |
| `main` | team | `a4368a0` | arrived inside the teammates' branches; never merge `main` itself |

## Starting the next session (the copilot)

The plan: compact, then read everything new on the other branches, then build the copilot the same way as the chatbot.
Open Claude Code in `D:\capstone project (SIC)\LoopGain-Telecom-AI` and paste:

> I am Taha. Read `prepaid_churn/CLAUDE.md`, the Handoff at the top of `prepaid_churn/TICKETS.md`, session 2 of `prepaid_churn/docs/session_log.md` (including "Branches as last merged") and ticket T25. Run `git fetch origin` for every branch, and for each teammate branch show me what is new since the commit it was last merged at, and whether any new branch appeared. Read what changed in the GIS and network ML work, because the copilot reads their outputs, and tell me how it affects the T25 plan. Confirm the tests in `prepaid_churn/` and `assistants/` pass. Then walk me through the T25 plan for the employee copilot, built the same way as the chatbot, with its open questions, and wait for my answers before merging or writing any code.

# Session 1: 2026-09-19 to 2026-09-25

## Where things stand on 2026-09-25

- Branch `tahaDev`, pushed; the only branch anyone works on (decision 24).
  `Ali_Branch` was meant to stay a record, but Ali kept working on it through 2026-09-25; it was merged into `tahaDev` through `f0156e2` (see the Handoff).
- Every ticket in TICKETS.md is closed, T0 to T21.
- 435 prepaid tests after merging `Ali_Branch` (401 before it), `ruff check` and `ruff format --check` pass (with `uv sync --group experiments`; without it the one Keras test is skipped).
- A fresh rebuild reproduces the frozen champion byte for byte: bundle `lightgbm-2026-09-19-ef9430fb`, tiers `tiers-v1-cd15525cb3ef`, and no committed report changes.
- Decisions run from 1 to 36; this session wrote 15 to 17, 24 to 30 and 34, and Ali wrote 18 to 23, 31 to 33, 35 and 36.
  Both sessions first numbered a decision 31; Ali's merge `5483f50` kept his Mix catalogue decision as 31 and renumbered the demo app decision to 34.
- **Open, and the first thing to pick up:** Taha tried the reworked demo app and said it is "still somehow heavy and somehow random, I didn't understand it" (see "Feedback not yet acted on" below).
- **Also open:** the one question for Ali left in the TICKETS open questions (the source links for the operator's files, answered on 2026-09-26: the operator's own website), and three checks on the final report draft (section "The final report draft").

## Timeline

### 1. Review of Ali's branch and the re-plan (2026-09-19)

- `Ali_Branch` at `06890f6` was an orphan branch: a separate "CVM suite" project whose churn labels came from Ali's own hazard formula on a generated population.
- Taha's direction: take the best of both into one module, built around a real Libyan mobile operator, and keep the team platform (chatbot, copilot, network ML, GIS) as the real goal.
- Decisions 15 (one module from two efforts, ported by hand), 16 (a real Libyan mobile operator's catalogue; real customers shown in its terms, and since decision 45 the operator is not named) and 17 (customer MVP first, built to plug into the platform).
- Commit `3942926`; every step of combining the two efforts is logged in [ali_branch_merge.md](ali_branch_merge.md).

### 2. T16, T8, T18 and the first handover (2026-09-19)

- T16 `729a896`: all 57 of the operator's packages (Ali had dropped the five Mix families) and `market.toml` with a status on every figure.
- T8 `42926d0`: the model bundle with version checks and a smoke prediction, `churn score`, and the output contract.
- T18 `6f3d606`: customers shown in LYD and the operator's packages. Taha chose the 40 LYD ARPU anchor; the rate is 40 over the measured mean recharge of 537.17.
- Handover `bfb28ab`, pushed on Taha's request, with rebuild instructions for Ali.

### 3. Ali's delivery taken in (2026-09-21)

- Ali had rebuilt his branch on top of `tahaDev` `bfb28ab` (his decision 18, merge commit `22aefc8` whose tree equals ours) and added 13 commits: the T21 code review with fixes (including fixes to Ahmed's antenna module and a root `CODE_REVIEW.md`), T10, T11, T15, T14, T9 and T19.
- Verified here before taking it: 379 tests, lint, and a byte-identical rebuild.
- `tahaDev` was fast-forwarded to `ae38840` rather than re-typing 9,000 verified lines (decision 24). The fast-forward also brought his old CVM history into the log; no old files are in the tree.
- His commit `62040af` answered part of an open question: he removed the Mix packages deliberately, though it does not say whether the operator still sells them (`e10a334`).

### 4. T20, the integration with the team platform (2026-09-21 and 22)

- `d968d17`: `docs/integration.md` for the chatbot, copilot, network ML and antenna owners; `src/prepaid_churn/client.py`, a standard-library example client the other teams copy rather than import (decision 25); `churn check-integration`, which calls a live service and checks the refusals.
- Taha asked for the remaining work to be done by us rather than waiting on other owners, so the walkthrough was run from the consumer side.
  It found the copilot could not look up one subscriber, so `ac8ce04` added `GET /subscribers/{id}/risk` for the copilot only (decision 26).
  Four questions stay unserved on purpose, each with its reason in the guide.

### 5. The three graded experiments (2026-09-22)

- Claimed first in `86452a4` so Ali's session would not start the same work.
- T12 `8f6e246`: a Keras LSTM on the torch backend. PR-AUC 0.2326 against LightGBM 0.3477; fails two of the four release checks. Kept as it came out (decisions 27 and 28).
- T13 `468ad8e`: CTGAN and a Gaussian copula on real training customers. The best copy keeps 45% of the real model's PR-AUC and both are detected perfectly; a synthetic copy is a demo, not a way to share data (decision 29). Runs as a standalone script because SDV caps pandas below 3.
- T17 `73762df`: two-model uplift and Qini (ported by hand from Ali, checked against scikit-uplift). On Criteo, uplift targeting reaches a Qini of 0.0698 while risk targeting reaches -0.1138, worse than random; Orange Belgium is too small to answer (decision 30).
  Taha authorised the downloads; the datasets are in the git-ignored `data/external/`.

### 6. The demo app, after Taha used it (2026-09-22)

- Taha's first test: the app was slow at everything, there was no way to create an offer, and after approving 15 offers he could not find them.
- `d38377d` (decision 34): the campaign snapshot is parsed once instead of twice; a campaign picker in the sidebar; the Campaign builder can propose a campaign (customers, budget, name) and the Subscriber screen can propose for one customer, both through the same path as `churn decide`; a new Released screen; a "Pick a high-risk one" button; and a fix for a real hazard, where an empty selection in the approval box approved every pending proposal.
- Checked end to end in the browser: propose, approve one, see it on Released.

### 7. Mentoring session preparation (2026-09-23)

- Taha had a Samsung mentoring session and wanted to talk about the data and the plan, not claim the project was finished.
- The script, the chatbot and RAG wording, how to describe the results chart, likely questions and an Arabic summary are in [presentation/talking_points.md](presentation/talking_points.md); the chart is [presentation/churn_results.png](presentation/churn_results.png).

### 8. The final report draft (2026-09-23)

- The Samsung template `SIC_AI_Capstone Project_Final Report.docx` was filled into `SIC_AI_Capstone Project_Final Report - Loop Gain.docx`, both at the repository root and kept out of git like the action plan files.
- It covers the cover page, sections 1 to 4 and all six members; sections 5 and 6 are left for the team's comments and the instructor.
- Three checks before anyone sends it:
  1. The roles of Mahmoud Almabrouk, Maher Alqadhi and Mohamed Khalaf are copied from the root README only; nobody here knows what they built.
  2. It deliberately does not repeat the old `customer_churn_prediction/` claims (0.928 ROC-AUC, $917k saved), because the code review found them selected on the test set.
  3. It was never rendered here (no LibreOffice or pandoc on this machine); open it in Word and check the layout.
- The script that filled it is not in the repo; regenerating it means editing the docx again.

## Feedback not yet acted on

Taha, 2026-09-23, after trying the reworked app: "do not open it again, it is still somehow heavy and somehow random, I didn't understand it".

What the disk shows about that session:
- He proposed a campaign over all 30,000 customers from the Campaign builder (`artifacts/campaigns/ui-2026-09-22-30000`, 78 MB), which brings back exactly the slowness decision 34 fixed, because the slider offers 30,000.
- He also proposed a 200-customer campaign and approved one offer in it (`ui-2026-09-22-200`: subscriber 70016, reviewer "taha", note "offer"), so the propose, approve and release path did work for him; the problem is understanding, not a broken flow.

What "random" means is not known; candidates are the "Pick one at random" button, the random holdout group, or campaigns built from "the first N customers", which looks arbitrary.
Do not change the app before asking Taha what felt random and what he expected to see.
Likely directions, to propose rather than build:
- take 30,000 off the slider (the whole base stays a `churn decide` job) or warn before it;
- one guided path through the screens (propose, review, see what was released) instead of five independent screens;
- say on screen why a customer gets "no offer" and what the holdout is.

## Mistakes caught this session, and how

- Adding SDV to the `experiments` group downgraded pandas from 3.0.5 to 2.3.3 for the whole project and the frozen bundle refused to load. Reverted; SDV runs in its own environment (decision 27).
- The first synthetic fidelity check counted negative amounts and called the real data 58% impossible, because difference columns are negative for half the customers. Replaced with a check against columns never negative in the real data (decision 29).
- The first uplift report read a winner out of Orange Belgium, where every ranking sat inside the noise band. A band from twenty random rankings is now measured and printed (decision 30).
- `churn decide` overwrites the committed `reports/decisions.md`; every run here restored it with `git checkout`. Still unfixed, listed for Ali.
- The docs said the Mix packages were removed "without a recorded reason"; Ali's commit `62040af` recorded the removal, so the wording was corrected.
- Two test counts in the tickets were written before the suite ran and were wrong; both were corrected after running it. Count from the test output, never from arithmetic.

## Working on this machine

- `uv` is at `C:\Users\LOQ\AppData\Roaming\Python\Python314\Scripts\uv.exe` and may not be on PATH; prefix commands with `export PATH="$PATH:/c/Users/LOQ/AppData/Roaming/Python/Python314/Scripts"`.
- Push with `GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c "credential.helper=!gh auth git-credential" -c push.negotiate=true push origin tahaDev`. Without `push.negotiate` git re-uploads the whole history and GitHub times out.
- In auto mode the permission classifier refuses `git merge` and `git push` until Taha asks for them in the chat.
- Never pull or merge `main`.
- In bash heredocs that generate Python, `\n` inside a string becomes a real newline and breaks the file; build it with `chr(92) + "n"` or edit with a file-based script.
- pandoc and LibreOffice are not installed; read a `.docx` by unzipping `word/document.xml` with Python.
- The desktop app's preview tool looks for `D:\.claude\launch.json`, not the repository's; start servers from bash and open the browser pane with a URL instead.
- Demo app: `PREPAID_CHURN_CAMPAIGN_DIR="<repo>/prepaid_churn/artifacts/campaigns/retention-500" ./.venv/Scripts/streamlit.exe run app/Home.py` from `prepaid_churn/`. The small campaign is what keeps it fast.
- Service: set `PREPAID_CHURN_CHATBOT_KEY` and `PREPAID_CHURN_COPILOT_KEY` (24 characters or more, different), then `uv run churn serve --campaign-dir artifacts/campaigns/retention-500`. It reads the campaign once at start, so restart it after approving.

## What is on disk but not in git

- `prepaid_churn/data/external/`: the Criteo archive (311 MB) and the Orange Belgium cache, for T17.
- `prepaid_churn/artifacts/campaigns/`: `full-base-30000` holds Taha's 15 approvals from 2026-09-22 (reviewer "Taha", note "testingNO01") and 2 from the T20 walkthrough; `retention-500` is the small demo campaign; `ui-2026-09-22-200` and `ui-2026-09-22-30000` are Taha's from the app.
- The two final report `.docx` files and the two action plan `.docx` files at the repository root, excluded through `.git/info/exclude`.
- Claude's memory for sessions started in `D:\` is `C:\Users\LOQ\.claude\projects\D--\memory\sic-capstone-churn.md`.

## Starting the next session

Open Claude Code in `D:\capstone project (SIC)\LoopGain-Telecom-AI` and paste:

> I am Taha. Read `prepaid_churn/CLAUDE.md`, the Handoff at the top of `prepaid_churn/TICKETS.md`, and `prepaid_churn/docs/session_log.md`, which is the log of the last session. Then run `git fetch origin tahaDev` and tell me whether anything arrived on `origin/tahaDev` after this log was written, confirm the test suite still passes, and summarise where the project stands and what is open. Do not change any code until I say what we work on next.
