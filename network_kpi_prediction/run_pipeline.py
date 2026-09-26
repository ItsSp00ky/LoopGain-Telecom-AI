"""
run_pipeline.py (Root Launcher)
Unified repository-level CLI orchestrator for Network-ML.
Delegates commands to either the 3GPP cellular multi-band pipeline (cellular_kpi_forecast)
or the 4G traffic volume pipeline (traffic_volume_forecast).
"""

import os
import sys
import subprocess

_ROOT = os.path.abspath(os.path.dirname(__file__))
_CELLULAR_PKG = os.path.join(_ROOT, "cellular_kpi_forecast")
_TRAFFIC_PKG = os.path.join(_ROOT, "traffic_volume_forecast")


def main() -> int:
    args = sys.argv[1:]
    target_pkg = _CELLULAR_PKG
    target_script = "run_cellular.py"

    # Support optional pipeline selector
    if "--pipeline" in args:
        idx = args.index("--pipeline")
        if idx + 1 < len(args):
            p_val = args[idx + 1].lower()
            if p_val in ["traffic", "data"]:
                target_pkg = _TRAFFIC_PKG
                target_script = "run_traffic.py"
            elif p_val in ["cellular", "ran", "kpi"]:
                target_pkg = _CELLULAR_PKG
                target_script = "run_cellular.py"
            else:
                print(f"[!] Unknown pipeline '{p_val}'. Choose from: 'cellular' (default) or 'traffic'.", file=sys.stderr)
                return 1
            # Remove --pipeline <val> from delegated arguments
            args = args[:idx] + args[idx + 2:]
        else:
            print("[!] Flag --pipeline requires an argument ('cellular' or 'traffic').", file=sys.stderr)
            return 1

    entry_point = os.path.join(target_pkg, target_script)
    cmd = [sys.executable, entry_point] + args

    try:
        res = subprocess.run(cmd, cwd=target_pkg)
        return res.returncode
    except KeyboardInterrupt:
        print("\n[!] Execution interrupted by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
