#!/usr/bin/env python3
"""Main entry point for Network KPI Prediction.

Forwards all calls directly to run_pipeline.py CLI orchestrator.
"""
import sys
from run_pipeline import main

if __name__ == "__main__":
    sys.exit(main())
