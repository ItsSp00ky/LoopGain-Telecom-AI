"""Layer 5 -- the decision engine.  Owner: E4

Step four of the pipeline:

    predict churn -> understand value -> estimate treatment effect -> DECIDE

Consumes M1 (churn probability, time-to-churn), M2 (segment, CLV), M3 (uplift)
and M4 (repayment PD), and answers two questions in order:

    1. Is intervening economically worthwhile?
           E[gain] = uplift x CLV - offer_cost
       "No" is a first-class answer. Most subscribers should get no action.

    2. If yes, which action? Selected from the operator's real catalogue, so
       the recommendation is executable and its cost is real rather than
       invented.

Emits:

    { offer_id, price_lyd, bonus_mb, valid_hours, advance_limit_lyd,
      stage, reason_codes[], expected_margin_lyd }

Everything passes through guardrails.py before it leaves this package. Nothing
here calls an LLM: an LLM is not permitted anywhere in a path that moves money.
"""