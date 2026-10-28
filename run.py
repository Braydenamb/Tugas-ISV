"""Run from any working directory: python /path/to/project/run.py."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
sys.path.insert(0, str(ROOT / "src"))

if __name__ == "__main__":
    try:
        from isv_calibration.cli import main
    except ModuleNotFoundError as exc:
        print(f"Dependensi belum tersedia: {exc.name}. Jalankan: python initialize.py", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(main())
