"""Entry point: `python -m cvm.ingest.run`  (step 1 of 3 in the pipeline)

Downloads nothing. Assumes `python scripts/download_data.py` has already run,
so that a network failure is a separate, obvious failure mode from a schema
break.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def main() -> None:
    """Validate, deduplicate, hash, and land every source as Parquet."""
    raise NotImplementedError("TODO(E1)")


if __name__ == "__main__":
    main()
