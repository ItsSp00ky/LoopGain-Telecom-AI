# Talking points for mentoring sessions and the final presentation

Prepared for the Samsung mentoring session on 2026-09-23, and kept because the final presentation needs the same words.
Every number here comes from a committed report; the report is named beside it.
The results chart is `churn_results.png` in this folder; `make_chart.py` redraws it.

## The short script (about 90 seconds)

**The data**

"We are working on prepaid customer churn.
Our dataset is the upGrad telecom dataset: about 70,000 prepaid customers, four months of behaviour, around 170 measurements per customer per month.
Calls, data usage, recharges, and how each of those moves from one month to the next.

We define churn the way a prepaid operator has to define it.
There is no contract to cancel, so a customer churns when they go silent: no incoming calls, no outgoing calls, and no data in a whole month.
On this data that is about four percent of customers in a month, which means the interesting problem is not accuracy, it is finding that four percent.

The data is from another market and it is educational, so we treat it as behaviour to learn from, not as evidence about Libya.
To make it local we collected a real Libyan mobile operator's catalogue ourselves: 37 packages on sale across 12 families, with their real prices, plus the pay as you go tariffs and the emergency credit rules.
Everything we show is in Libyan dinar and in packages a Libyan customer would recognise."

**What we want to do**

"The goal is not a churn score. It is a retention loop.

First, predict who is about to go silent next month.
The riskiest ten percent of customers contain about sixty percent of next month's churners, so a campaign can be small instead of blanket.

Second, say what each customer is worth, in dinar.

Third, propose a retention offer from the real catalogue, inside a budget, with rules about what not to do.

And the part we care most about: a person approves every offer before it reaches a customer.
The system proposes, a named employee decides, and every decision is logged.
No AI sends anything to a customer by itself.

Then our module plugs into the team platform, so the chatbot and the employee assistant read our outputs instead of guessing."

**The chatbot**

"The chatbot is the customer facing part of our platform, and it is the next thing we build.
It is not built yet, so here is what it will do and what we have already prepared for it.

A customer asks it two kinds of question: what packages can I get, and is there anything for me today.
Our module already serves exactly those two answers: the operator's full catalogue, and the one retention offer that a named employee has approved for that customer.
If nobody approved an offer, the chatbot gets nothing, and it says nothing.

The chatbot never sets a price, never chooses an offer and never invents a number.
It reads what our engine decided and explains it in Arabic.
If it has no answer it says so instead of guessing.
And it never sees a customer's churn probability, because a customer should not be told how likely the company thinks they are to leave.

So the language model is the mouth, not the brain."

## Is it RAG?

Say it about the copilot, not the chatbot.

- The chatbot is grounded on live tool calls: it asks our service for the catalogue and the approved offer (`docs/integration.md`).
  That is tool use, not retrieval, and saying RAG invites questions about a vector store we do not have.
- The employee copilot is retrieval based over our own documents: the model card, the decision log and the reports, with citations.
  The list of what it may index, and what it may never touch, is section 7 of `docs/integration.md`.

The sentence to use:

"Both of our assistants are grounded, in two different ways.
The customer chatbot is grounded on live tool calls, so every number it says came from our engine.
The employee copilot is retrieval based over our own documentation, and answers with citations.
Neither of them generates a price or an offer, and both refuse instead of guessing."

If asked directly: "The copilot yes, over our documents. The chatbot no, on purpose: an offer changes every campaign and needs a budget check and a human approval, so it is read live from the service, never from an indexed document that could be stale."

## Describing the results chart (`churn_results.png`)

Numbers from `reports/evaluation_all.md`, measured once on the frozen test month (9,677 customers, 4.35% churn).

**Left panel, the cumulative gain curve**

"The horizontal axis is how many customers we contact, sorted from the riskiest first.
The vertical axis is how many of next month's real churners we caught.
The grey dashed line is contacting people at random: call 20% at random, reach 20% of the leavers.
The blue line is our model, and the steep bend at the start is its whole value.
Contact the riskiest 5% and we catch 42% of the churners; 10% catches 61.5%; 20% catches 80%.
So with one customer in ten we find six churners in ten."

Why it matters: every offer costs money, so reaching most of the risk inside a tenth of the base is what makes a campaign affordable.
After about 20% the curve flattens, so contacting more people adds cost and finds few extra churners.

**Right panel, the risk bands**

"We split customers into three bands and checked what really happened in a month the model had never seen.
In the high band 38% went silent, in the medium band 12%, in the low band 1.3%, against a base rate of 4.4%."

**Two honest lines to close on**

"This is measured on a later month, with customers the model never trained on, and we scored it once after freezing everything."
"The model is calibrated: when it says 30%, about 30 in 100 such customers really do go silent, which matters because the retention budget is computed from those probabilities."

## Likely questions

- **Why not let the AI decide the offer?** "Because an offer is money, and a language model cannot be held to a budget or a rule. Ours is chosen by a model with guardrails, checked against a budget, and approved by a named employee; the chatbot only repeats that decision, and every step is logged."
- **What do you need help with?** The ARPU anchor of 70 LYD a month rests on the operator's bundle prices and a published market study (decision 42), and a real operator figure should replace it; proving an offer changes behaviour needs a campaign with a control group; and how best to present a model trained on foreign data but applied to a Libyan operator.
- **Did the deep learning model win?** No, and that is a result: the LSTM reached PR-AUC 0.233 against LightGBM's 0.348, because two monthly steps are not a history (the model card's model selection note, decision 44).
- **Can the operator share synthetic data instead?** Not at this budget: the best synthetic copy keeps 45% of the real model's PR-AUC and is told apart from real rows perfectly (the model card's model selection note, decision 44).
- **Does targeting the riskiest customers save the most?** Not necessarily: on 1.4 million randomised Criteo rows, targeting by risk was worse than random while targeting by uplift worked; it needs a randomised campaign, which the permanent holdout will provide (decisions 43 and 44).

## Simple explanation in Arabic (شرح مبسط)

**المشكلة:** في خطوط الدفع المسبق ما فيش عقد يتلغى، الزبون ببساطة يسكت: يبطل يتصل، يبطل يستعمل النت، وما يعبيش رصيد.
عرفنا المغادرة إنها شهر كامل بدون مكالمات داخلة ولا خارجة ولا استهلاك بيانات.

**البيانات:** حوالي 70 ألف زبون دفع مسبق، أربعة أشهر، وحوالي 170 قياس لكل زبون في الشهر.
نسبة المغادرة حوالي 4% في الشهر، فالمشكلة إننا نلقوا هذه الـ 4%.
البيانات تعليمية ومن سوق ثاني، فنتعاملوا معاها كسلوك نتعلموا منه مش كدليل على السوق الليبي.

**الجزء الليبي:** جمعنا باقات حقيقية لمشغل ليبي: 37 باقة معروضة في 12 عائلة بأسعارها، مع تعرفة الدفع المسبق وخدمتَي الرصيد والنت في وقته، فكل شيء بالدينار الليبي.

**النتيجة:** لو نتواصلوا مع أخطر 10% من الزباين نلقوا فيهم حوالي 61% من اللي فعلاً حيغادروا، ولو عشوائي ما نلقوش غير 10%.
مقاس على شهر النموذج ما شافوش، وحسبناه مرة وحدة بعد التجميد.

**بعد التوقع:** قيمة كل زبون بالدينار، اقتراح عرض من الباقات الحقيقية داخل ميزانية، و**موظف باسمه** يوافق على كل عرض قبل ما يوصل الزبون، وكل قرار يتسجل.

**الربط:** الشات بوت ولوحة الموظف يقروا من خدمة صغيرة؛ الشات بوت ما يختارش عرض وما يخترعش رقم، وما يعرفش احتمال مغادرة الزبون.

**اللي باقي:** نستبدلوا الافتراضات بأرقام المشغل (خصوصاً متوسط الإنفاق)، ونحتاجوا حملة حقيقية فيها مجموعة ضابطة باش نعرفوا هل العرض فعلاً غيّر سلوك الزبون.
