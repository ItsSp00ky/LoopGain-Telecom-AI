"""M4 -- Smart Advance: the repayment PD heads.  Owner: E2 / E4

These are not new products. Almadar already runs two emergency-credit
services; what they lack is a risk model.

    رصيد في وقته  airtime advance, 1/3/5 LYD, via *140#
                  gate: basic balance <= 0.5 LYD
                  allocated "according to the subscriber's consumption"

    نت في وقته    emergency data, flat 5 LYD for 2 GB / 3 days, via *000#
                  gate: balance <= 1 LYD AND remaining quota < 250 MB
                  no tiering at all

Both gate on the subscriber being nearly out of money, which is the inverse of
a risk filter: the eligible population is by construction the one least able to
repay. Consumption is not repayment probability, and a flat 5 LYD debt against
a 3 LYD smallest recharge card cannot be cleared in one top-up.

The PD models are SECOND PREDICTION HEADS sharing M1's feature pipeline -- not
separate models with their own infrastructure. That is why M4 is cheap to build
despite being the most differentiated idea in the project.

Targets: settled by the next recharge, censored at 14 days. There is no
published grace period for either product, so the horizon is behavioural rather
than contractual.

The LIMIT logic -- min(f(PD), g(tier), h(CLV), affordability) and all the safety
guards -- lives in cvm.decision.advance_limit, not here. This module only
predicts.

Product facts: conf/catalogue.yaml#emergency_credit
Decision logic: conf/advance.yaml
"""
