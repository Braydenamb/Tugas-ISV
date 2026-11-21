"""Rebuild report without remeasuring photos or recalibrating."""
from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, help="Folder yang berisi refinement_summary.json")
    args = parser.parse_args()
    try:
        path = args.results
        if path is None:
            pointer = json.loads((ROOT / "reports/refinement_run.json").read_text(encoding="utf-8"))
            path = ROOT / pointer["output"]
        from isv_calibration.evolution_report import build_evolution_report
        print(build_evolution_report(path))
    except (OSError, ValueError, KeyError, ModuleNotFoundError) as exc:
        parser.exit(1, f"Gagal membuat laporan: {exc}. Jalankan initialize.py dan eksperimen refinement terlebih dulu.\n")
