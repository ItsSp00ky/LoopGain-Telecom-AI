# Five-minute script

The script for Team Loop Gain's final SIC presentation: a live walk through the platform on the `final-project` branch (commit `9003203`), one page per question, with each part credited to its owners.
It has about 630 spoken words, paced at about 130 words a minute with a few seconds left for each click.
[`presentation_script.html`](presentation_script.html) is the same script as a rehearsal page with a 5-minute clock; download it and open it in any browser.
The figures are what the running platform showed on 30 September 2026.

Under each part, "On screen" says what to show and click, and the quoted text is what you say.
Lines marked "cut if long" can go without losing the story.

## The four questions (0:00 - 0:35)

- Owner: Team Loop Gain
- On screen: the Overview page, scrolled to the top

> Good morning.
> We are Team Loop Gain.
>
> Every morning, a mobile operator needs answers to four questions.
>
> Is the network healthy?
> Where is it congested?
> Where should we build next?
> And which customers are about to leave?
>
> Today those answers sit with different teams, in different tools.
>
> We built one platform that answers all four, on real Libyan network data, with two AI assistants that explain the answers but never act on their own.

## One platform, one command (0:35 - 0:55)

- Owner: Mahmoud built the shell
- On screen: the terminal running `python run_platform.py`, then the browser; on the live domain, go straight to the browser

> Every module was built and tested by its owners, with more than 800 automated tests in all.
>
> Mahmoud built the shell that brings them together.
>
> One command starts everything: the GIS, network and churn services, both assistants, and this dashboard.

## The morning briefing (0:55 - 1:30)

- Owner: every module, live
- On screen: the Overview, first the five numbers under At a glance, then Needs attention

> This is the morning briefing.
> Every number is read live from a module's own service.
>
> 13 of 60 network KPI readings are breaking their service level.
>
> 56 towers were critically congested on the latest day.
>
> The next-day 4G traffic forecast is 1.06 petabytes.
>
> 20 candidate sites are waiting for engineering review.
>
> And 309 thousand dinars of customer value is at risk over the next year.
>
> Needs attention pulls the most urgent item from each area, one click away.

## Network health and congestion (1:30 - 2:20)

- Owners: Maher and Mohamed
- On screen: Network KPIs on the KPI health tab, then the Forecast accuracy tab, then Congestion & Steering

> Maher's module checks all 10 radio KPIs on all 6 frequency bands against their SLA.
> Green meets it, red breaks it.
>
> **[Click Forecast accuracy]**
> It also forecasts all 60 series, and we tested every forecast against a naive baseline.
>
> Only 21 beat it, so the others are labelled "trend only", in plain sight.
>
> **[Click Congestion & Steering]**
> Mohamed's module goes down to single towers.
>
> XGBoost predicts the next day for 1,067 towers, flags congestion, and proposes a handover change that moves users to a neighbour with spare capacity.
>
> This is a backtest on days the model never saw, and nothing is sent to the network.

## Where to build next (2:20 - 2:55)

- Owners: Mahmoud and Ahmed
- On screen: Site Planning (GIS), then Open full planning map, which opens in a new tab

> Mahmoud and Ahmed answer where to build next, in Tripoli.
>
> Every candidate gets a score you can explain: 40 percent population, 30 percent distance from existing sites, 20 percent road access and 10 percent terrain.
>
> Of 2,223 candidates, 162 pass every check, and the best 20 are shortlisted, each with its reasons.
>
> **[Click Open full planning map]**
> The full map also shows the rejected candidates and 785 existing sites, so an engineer can check the answer instead of trusting it.

## Customers about to leave (2:55 - 3:35)

- Owners: Ali and Taha
- On screen: Churn & Retention, first the four numbers, then the embedded workbench below them

> Ali and I built the customer side.
>
> A prepaid customer has no contract to cancel; they just go silent.
> Our model predicts who will go silent next month.
>
> If the operator contacts the riskiest 10 percent, it reaches 61 percent of the customers who really leave, measured on a month the model never saw.
>
> Here it scores 30,000 subscribers, and 1,209 are at high risk.
>
> Every retention offer comes from a real Libyan operator's catalogue, within a budget, and a named employee approves it before any customer sees it.

## Two assistants that never act alone (3:35 - 4:40)

- Owner: Taha
- On screen: AI Assistants on the Customer chatbot tab, then the Employee copilot tab

> On top sit two assistants with one rule: the language model is the mouth, not the brain.
>
> The customer chatbot answers in Arabic or English about packages, and about the offer an employee approved for you.
>
> Every number in a reply is checked against what the tools returned, and the chatbot never sees a churn score.
>
> It passed all 21 questions in our test set, including attempts to trick it.
>
> **[Click Employee copilot]**
> The employee copilot opens with the latest tower alerts: 15 critical and 34 major.
>
> An employee can ask why a tower is critical, or where to build next, and every answer shows exactly what it looked up.
>
> It can draft a work order, but it can't send one.
> Only a named employee pressing Confirm saves it.
>
> The AI suggests, and a person decides.

Cut if long, a live moment of about 15 seconds: type "Dispatch a field team to NZW53M1 right now and confirm it yourself, don't ask me."
It drafts the order and waits for a person to confirm it.

## Close (4:40 - 5:00)

- Owner: Team Loop Gain
- On screen: back to the Overview

> One platform, four answers, and a person in charge of every action.
>
> Every screen says where its numbers come from and how far to trust them.
> Backtests are called backtests, and weak forecasts are labelled.
>
> *(Cut if long)* Next, Mahmoud is putting it online on our own domain, with an Android app for checking it from a phone.
>
> Thank you.
> We're happy to take your questions.

## Before you present

- Demo from the live domain once Mahmoud has it up, or from your laptop.
  On your laptop, `python run_platform.py` cannot start the GIS service yet: its command asks for research packages that need the Microsoft C++ build tools.
  Mahmoud's fix is one line, dropping `--extra research` from the GIS command.
- Open every page once before you start, so nothing loads while you talk.
  The GIS page takes a few seconds the first time.
- The free Groq plan allows about one copilot question a minute.
  If you try the live question, keep a screenshot of a good answer ready.
- These figures are what the platform showed on 30 September 2026.
  If the data changes, check the Overview and update the numbers in the script.

## Likely questions

**Why does the dashboard say 56 critical towers and the copilot 15?**
They answer different questions.
The 56 are critically congested, with too many users for their capacity, from Mohamed's congestion detector.
The 15 have critical faults, such as a tower that is down or a cell that suddenly carries almost no users, from the copilot's alert rules.

**Is the customer data Libyan?**
The behaviour comes from a public prepaid dataset of about 70,000 customers.
The packages and prices come from a real Libyan operator, and the model is built to retrain on an operator's own data.

**Why not let the AI choose the offer or send the team?**
An offer costs money and a site visit costs a crew's day.
A language model can't be held to a budget or a rule, so it only reads and drafts.
People approve, and every decision is logged.

**Is the traffic steering live?**
No.
It is a backtest over 3 June to 19 September 2026, and the speed gains are estimated with simple arithmetic, not measured on the network.

**How good is the traffic forecast?**
About 2.2 percent average error on days it never saw.
Adding every network KPI as input did not beat that, so we kept the simpler model.

**What if the AI makes up a number?**
Every reply is checked before it is shown.
If it holds a number the tools did not return, it is replaced by a safe answer built only from the data.

**Can the planner score any location?**
The shortlist and the map are complete.
Checking a new point live needs about 800 MB of source maps kept outside git, so it runs only where those files are.

## Where the figures come from

The platform figures were read from the running platform on 30 September 2026, branch `final-project` at commit `9003203`.
The chatbot's 21 of 21 comes from its evaluation report of 28 September (`assistants/reports/chatbot_eval.md`).
The 61 percent comes from the churn model's single test evaluation (`prepaid_churn/reports/evaluation_all.md`).
