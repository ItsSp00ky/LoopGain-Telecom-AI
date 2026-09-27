"""
predict.py
Forwarding alias to run_inference.py to maintain backward compatibility with legacy scripts and tests.
"""

import sys
from run_inference import query_predictions, main

if __name__ == "__main__":
    sys.exit(main())
