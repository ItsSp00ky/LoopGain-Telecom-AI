# Datasets Used — Customer Churn Prediction Project

Four candidate datasets were profiled in `churn_datasets/`. One was selected as the champion training set; the other three were evaluated and excluded. This document lists all four with their columns, for use in the presentation.

---

## Summary comparison

| Dataset | File(s) | Shape (rows × cols) | Domain | Test ROC-AUC | Status |
|---|---|---|---|---|---|
| **Maven Telecom Churn** | `Maven_telecom/telecom_customer_churn.csv` | 7,043 × 38 | Broadband & Cellular, with tracked marketing offers | **0.9280** | ✅ **Primary Champion** |
| **Telecom_data (Client + Record)** | `Telecom_data/Client.csv` + `Record.csv` | 100,000 × 100 (joined) | Wireless mobile carrier, high call telemetry | 0.6952 | Evaluated, not used |
| **Cell2Cell** | `cell2celltrain.csv/` (train + holdout) | 71,047 × 58 | Wireless mobile carrier, demographic + usage | not reported | Evaluated, not used |
| **Generic Subscription Churn** | `customer_churn_dataset-testing-master.csv/` (train + test) | 505,209 × 12 | Generic SaaS/subscription app | N/A | Excluded (not telecom-specific) |

**Why Maven Telecom Churn won:** it's the only dataset that tracks real marketing offers (`Offer A`–`Offer E`) alongside churn outcomes, letting the model connect *why* a customer churned to a specific retention action — e.g. Offer E customers churn at 67.6% vs. Offer A at 6.7%. It also has billing telemetry (`Total Extra Data Charges`, `Avg Monthly GB Download`) that directly supports the project's retention-discount engine, which the other three datasets lack.

---

## 1. Maven Telecom Churn (Champion — used for training)

`Maven_telecom/telecom_customer_churn.csv` — 7,043 customers, 38 columns:
```
Customer ID, Gender, Age, Married, Number of Dependents, City, Zip Code, Latitude, Longitude,
Number of Referrals, Tenure in Months, Offer, Phone Service, Avg Monthly Long Distance Charges,
Multiple Lines, Internet Service, Internet Type, Avg Monthly GB Download, Online Security,
Online Backup, Device Protection Plan, Premium Tech Support, Streaming TV, Streaming Movies,
Streaming Music, Unlimited Data, Contract, Paperless Billing, Payment Method, Monthly Charge,
Total Charges, Total Refunds, Total Extra Data Charges, Total Long Distance Charges,
Total Revenue, Customer Status, Churn Category, Churn Reason
```
Key fields for the presentation: `Offer` (the marketing package the customer is on — the unique differentiator of this dataset), `Churn Category`/`Churn Reason` (labelled root cause), billing/usage fields for the retention-discount engine.

---

## 2. Telecom_data (Client + Record) — evaluated, not used

Two files joined on `Customer_ID`, ~100,000 rows, ~100 combined columns.

`Telecom_data/Client.csv` — customer/account attributes:
```
uniqsubs, actvsubs, new_cell, crclscod, asl_flag, totcalls, totmou, totrev, adjrev, adjmou,
adjqty, avgrev, avgmou, avgqty, avg3mou, avg3qty, avg3rev, avg6mou, avg6qty, avg6rev,
prizm_social_one, area, dualband, refurb_new, hnd_price, phones, models, hnd_webcap,
truck, rv, ownrent, lor, dwlltype, marital, adults, infobase, income, numbcars, HHstatin,
dwllsize, forgntvl, ethnic, kid0_2, kid3_5, kid6_10, kid11_15, kid16_17, creditcd,
eqpdays, Customer_ID
```
`Telecom_data/Record.csv` — call/usage telemetry:
```
rev_Mean, mou_Mean, totmrc_Mean, da_Mean, ovrmou_Mean, ovrrev_Mean, vceovr_Mean, datovr_Mean,
roam_Mean, change_mou, change_rev, drop_vce_Mean, drop_dat_Mean, blck_vce_Mean, blck_dat_Mean,
unan_vce_Mean, unan_dat_Mean, plcd_vce_Mean, plcd_dat_Mean, recv_vce_Mean, recv_sms_Mean,
comp_vce_Mean, comp_dat_Mean, custcare_Mean, ccrndmou_Mean, cc_mou_Mean, inonemin_Mean,
threeway_Mean, mou_cvce_Mean, mou_cdat_Mean, mou_rvce_Mean, owylis_vce_Mean, mouowylisv_Mean,
iwylis_vce_Mean, mouiwylisv_Mean, peak_vce_Mean, peak_dat_Mean, mou_peav_Mean, mou_pead_Mean,
opk_vce_Mean, opk_dat_Mean, mou_opkv_Mean, mou_opkd_Mean, drop_blk_Mean, attempt_Mean,
complete_Mean, callfwdv_Mean, callwait_Mean, churn, months, Customer_ID
```
Heaviest telemetry of all four (100 columns), but no package/offer information — scored lowest (0.6952 ROC-AUC) since it can't connect churn to an actionable retention lever.

---

## 3. Cell2Cell — evaluated, not used

`cell2celltrain.csv/cell2celltrain.csv` (51,047 rows) + `cell2cellholdout.csv` (20,000 rows), 58 columns each:
```
CustomerID, Churn, MonthlyRevenue, MonthlyMinutes, TotalRecurringCharge, DirectorAssistedCalls,
OverageMinutes, RoamingCalls, PercChangeMinutes, PercChangeRevenues, DroppedCalls, BlockedCalls,
UnansweredCalls, CustomerCareCalls, ThreewayCalls, ReceivedCalls, OutboundCalls, InboundCalls,
PeakCallsInOut, OffPeakCallsInOut, DroppedBlockedCalls, CallForwardingCalls, CallWaitingCalls,
MonthsInService, UniqueSubs, ActiveSubs, ServiceArea, Handsets, HandsetModels,
CurrentEquipmentDays, AgeHH1, AgeHH2, ChildrenInHH, HandsetRefurbished, HandsetWebCapable,
TruckOwner, RVOwner, Homeownership, BuysViaMailOrder, RespondsToMailOffers, OptOutMailings,
NonUSTravel, OwnsComputer, HasCreditCard, RetentionCalls, RetentionOffersAccepted,
NewCellphoneUser, NotNewCellphoneUser, ReferralsMadeBySubscriber, IncomeGroup, OwnsMotorcycle,
AdjustmentsToCreditRating, HandsetPrice, MadeCallToRetentionTeam, CreditRating, PrizmCode,
Occupation, MaritalStatus
```
Rich demographic + call-quality data (dropped/blocked/unanswered calls, retention call history), but again no specific marketing-offer tracking like Maven Telecom has.

---

## 4. Generic Subscription Churn — excluded

`customer_churn_dataset-testing-master.csv/` — training file (440,833 rows) + testing file (64,374 rows), 12 columns each:
```
CustomerID, Age, Gender, Tenure, Usage Frequency, Support Calls, Payment Delay,
Subscription Type, Contract Length, Total Spend, Last Interaction, Churn
```
Largest by row count (505K+ rows) but generic SaaS-style fields (no calls, handsets, or telecom-specific billing) — excluded for not being domain-specific to telecom.
