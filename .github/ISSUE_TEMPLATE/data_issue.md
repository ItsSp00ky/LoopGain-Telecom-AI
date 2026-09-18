---
name: Data or synthesis issue
about: Schema break, quality-gate failure, suspicious distribution, licence question
title: "[data] "
labels: data
assignees: ''
---

**Layer:** <!-- 1 Ingestion / 2 GAN synthesis / 3 Feature store -->
**Dataset:** <!-- A UCI Iranian / B Cell2Cell / C IBM Telco / synthetic / F Criteo / G Hillstrom / H KKBox / J Online Retail II -->
**Field(s):**

## What is wrong

## Evidence

<!-- Row counts, distribution plot, failing Pandera check, SDMetrics score. -->

## If this is a synthesis quality-gate failure

| Gate | Threshold | Observed |
|---|---|---|
| KS-complement (continuous marginals) | >= 0.85 | |
| Pairwise correlation delta | <= 0.10 | |
| Discriminator detection AUC | <= 0.65 | |

<!-- Above 0.65 detection AUC the generator is rejected and retrained. That is the
     rule, not a suggestion — the whole point is that we evaluate the GAN with an
     adversarial test, the same principle that trains it. -->

## Does this affect a documented field?

- [ ] `docs/data_dictionary.md` needs updating
- [ ] A Pandera contract in `src/cvm/ingest/schemas.py` needs updating
- [ ] A licence or attribution note in `data/README.md` needs updating
