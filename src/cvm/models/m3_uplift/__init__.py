"""M3 -- Uplift Engine: who can actually be influenced?  Owner: E4

Step three of the pipeline:

    predict churn -> understand value -> ESTIMATE TREATMENT EFFECT -> decide

This is the module that stops the system spending money on people who were
never going to leave, and on people nothing would have saved. A churn score
ranks who is *at risk*; an uplift score ranks who is *movable*, and those are
different populations. Targeting on churn probability alone systematically
funds the wrong subscribers.

Four quadrants, and only one of them should receive budget:

    persuadable   stays only if treated          <- the entire target
    sure thing    stays either way               <- pure waste
    lost cause    leaves either way              <- pure waste
    sleeping dog  leaves BECAUSE treated         <- actively harmful

The sleeping-dog quadrant is why this cannot be skipped. Contacting a
dormant-but-not-departing subscriber can remind them to leave, so a system
without an uplift model does not merely waste budget -- it causes churn it
would otherwise not have caused.

Method: a two-model difference, trained and validated on Criteo's real
randomised treatment and control arms before being applied to the generated
population. See docs/adr/0003 for why not a causal-inference library.

Output feeds cvm.decision, which decides whether intervening is economically
worthwhile and which action to take.
"""
