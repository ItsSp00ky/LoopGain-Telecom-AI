"""Entry point: `python -m cvm.synthesis.run`  (step 2 of 3)

Fits CTGAN / TVAE / Copula, samples the population, applies quantile mapping
and business overlays, generates labels from the hazard function, and runs the
quality gate. A gate failure exits non-zero -- the pipeline must not produce a
population that a discriminator can spot.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("TODO(E1)")


if __name__ == "__main__":
    main()