# Session log: 2026-09-19 to 2026-09-25 (Taha + Claude)

One long working session, written down so the next session can start without the chat.
The sources of truth stay where they were: [../CLAUDE.md](../CLAUDE.md), the Handoff at the top of [../TICKETS.md](../TICKETS.md), and [decisions.md](decisions.md).
This file is the narrative that connects them: what happened, in what order, what went wrong, and what is still open.

## Where things stand on 2026-09-25

- Branch `tahaDev`, pushed; the only branch anyone works on (decision 24).
  `Ali_Branch` was meant to stay a record, but Ali kept working on it through 2026-09-25; it was merged into `tahaDev` through `f0156e2` (see the Handoff).
- Every ticket in TICKETS.md is closed, T0 to T21.
- 435 prepaid tests after merging `Ali_Branch` (401 before it), `ruff check` and `ruff format --check` pass (with `uv sync --group experiments`; without it the one Keras test is skipped).
- A fresh rebuild reproduces the frozen champion byte for byte: bundle `lightgbm-2026-09-19-ef9430fb`, tiers `tiers-v1-cd15525cb3ef`, and no committed report changes.
- Decisions run from 1 to 36; this session wrote 15 to 17, 24 to 30 and 34, and Ali wrote 18 to 23, 31 to 33, 35 and 36.
  Both sessions first numbered a decision 31; Ali's merge `5483f50` kept his Mix catalogue decision as 31 and renumbered the demo app decision to 34.
- **Open, and the first thing to pick up:** Taha tried the reworked demo app and said it is "still somehow heavy and somehow random, I didn't understand it" (see "Feedback not yet acted on" below).
- **Also open:** the one question for Ali left in the TICKETS open questions (the Almadar source links), and three checks on the final report draft (section "The final report draft").

## Timeline

### 1. Review of Ali's branch and the re-plan (2026-09-19)

- `Ali_Branch` at `06890f6` was an orphan branch: a separate "CVM suite" project whose churn labels came from Ali's own hazard formula on a generated population.
- Taha's direction: take the best of both into one module, built around Almadar, and keep the team platform (chatbot, copilot, network ML, GIS) as the real goal.
- Decisions 15 (one module from two efforts, ported by hand), 16 (Almadar Aljadid is the operator; real customers shown in Almadar terms) and 17 (customer MVP first, built to plug into the platform).
- Commit `3942926`; every step of combining the two efforts is logged in [ali_branch_merge.md](ali_branch_merge.md).

### 2. T16, T8, T18 and the first handover (2026-09-19)

- T16 `729a896`: all 57 Almadar packages (Ali had dropped the five Mix families) and `market.toml` with a status on every figure.
- T8 `42926d0`: the model bundle with version checks and a smoke prediction, `churn score`, and the output contract.
- T18 `6f3d606`: customers shown in LYD and Almadar packages. Taha chose the 40 LYD ARPU anchor; the rate is 40 over the measured mean recharge of 537.17.
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
