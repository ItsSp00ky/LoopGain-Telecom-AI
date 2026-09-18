"""Layer 5 -- the decision engine. The commercial core.  Owner: E4

Consumes churn_prob, time-to-churn, CLV, loyalty_idx, repay_PD and network
quality; emits:

    { offer_id, price_lyd, bonus_mb, valid_hours, advance_limit_lyd,
      stage, reason_codes[], expected_margin_lyd }

Everything passes through guardrails.py before it leaves this package. Nothing
here calls an LLM: an LLM is not permitted anywhere in a path that moves money.
"""