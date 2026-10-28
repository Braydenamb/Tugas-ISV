"""Portable first-run setup. Uses only the Python standard library."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parent


def environment_python():
    return ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def check_dataset():
    config = json.loads((ROOT / "config/calibration.json").read_text(encoding="utf-8"))
    size = config["square_size_mm"]
    if not isinstance(size, (int, float)) or not math.isfinite(size) or size <= 0:
        raise ValueError("Ukuran kotak harus positif dan finite")
    photos = ROOT / config["photos"]
    files = sorted(p for p in photos.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"})
    if len(files) < config["minimum_photos"]:
        raise ValueError(f"Hanya ada {len(files)} foto di {photos}; perlu {config['minimum_photos']}")
    if len({p.name for p in files}) != len(files):
        raise ValueError("Nama foto harus unik")
    manifest_path = ROOT / config["dataset_manifest"]
    verified = 0
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        known = {row["file"]: row["sha256"] for row in manifest["images"]}
        verified = sum(known.get(p.name) == hashlib.sha256(p.read_bytes()).hexdigest() for p in files)
    print(f"Dataset: {len(files)} foto; {verified} cocok dengan hash dataset acuan; kotak {size:g} mm.", flush=True)
    if verified < len(files):
        print("Foto baru/berubah akan dideteksi ulang; koordinat cache dan pengecualian lama tidak diterapkan.", flush=True)
    return config


def check_dependencies(python):
    probe = (
        "import json,sys,cv2,numpy,matplotlib; "
        "print(json.dumps({'python':sys.version.split()[0],'opencv':cv2.__version__,"
        "'numpy':numpy.__version__,'matplotlib':matplotlib.__version__}))"
    )
    with tempfile.TemporaryDirectory(prefix="isv-check-") as temporary:
        environment = dict(os.environ, MPLCONFIGDIR=temporary)
        process = subprocess.run([str(python), "-c", probe], cwd=ROOT, text=True, capture_output=True, env=environment)
    if process.returncode:
        raise RuntimeError("Dependensi belum lengkap. Jalankan kembali python initialize.py.\n" + process.stderr[-1800:])
    versions = json.loads(process.stdout.strip().splitlines()[-1])
    cv_version = tuple(int(x) for x in versions["opencv"].split(".")[:2])
    if not (4, 11) <= cv_version < (6, 0):
        raise RuntimeError(f"Versi OpenCV di luar rentang yang didukung: {versions['opencv']}")
    print("Dependensi siap: " + ", ".join(f"{k} {v}" for k, v in versions.items()), flush=True)
    return versions


def main(argv=None):
    parser = argparse.ArgumentParser(description="Siapkan proyek kalibrasi setelah clone/download Git")
    parser.add_argument("--check", action="store_true", help="Periksa lingkungan dan data tanpa memasang/mengubah apa pun")
    parser.add_argument("--skip-install", action="store_true", help="Lewati pip; hanya untuk lingkungan yang sudah memiliki dependensi")
    parser.add_argument("--run", action="store_true", help="Jalankan kalibrasi setelah penyiapan berhasil")
    parser.add_argument("--compare", action="store_true", help="Setelah penyiapan, bandingkan baseline dan mild")
    parser.add_argument("--experiment", choices=("panels",), help="Setelah penyiapan, uji metode dua panel dengan validasi silang")
    args = parser.parse_args(argv)
    if args.check and (args.run or args.compare or args.skip_install or args.experiment):
        parser.error("--check dipakai sendiri agar tidak mengubah atau menjalankan proyek")
    if args.compare and args.experiment:
        parser.error("--compare dan --experiment dijalankan terpisah")
    try:
        if sys.version_info < (3, 10):
            raise RuntimeError("Gunakan Python 3.10 atau lebih baru")
        check_dataset()
        python = environment_python()
        if args.check:
            if not python.is_file():
                raise RuntimeError("Lingkungan .venv belum tersedia. Jalankan: python initialize.py")
            check_dependencies(python)
            return 0
        env = ROOT / ".venv"
        if env.exists() and not (env / "pyvenv.cfg").is_file():
            raise RuntimeError("Folder .venv sudah ada tetapi bukan virtual environment. Tidak akan ditimpa.")
        if not python.is_file():
            print("Membuat lingkungan Python lokal .venv...", flush=True)
            venv.EnvBuilder(with_pip=True).create(env)
        (ROOT / "outputs").mkdir(exist_ok=True)
        (ROOT / ".cache/matplotlib").mkdir(parents=True, exist_ok=True)
        if not args.skip_install:
            print("Memasang dependensi dari requirements.txt (memerlukan internet)...", flush=True)
            subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--timeout", "30", "--retries", "1", "-r", str(ROOT / "requirements.txt")], cwd=ROOT, check=True)
        check_dependencies(python)
        print("Penyiapan selesai. Jalankan: python run.py memakai Python di .venv, atau python initialize.py --run.", flush=True)
        if args.run or args.compare or args.experiment:
            command = [str(python), str(ROOT / "run.py")]
            if args.compare:
                command.append("--compare")
            if args.experiment:
                command.extend(["--experiment", args.experiment])
            subprocess.run(command, cwd=ROOT, check=True)
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Penyiapan gagal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
    raise SystemExit(main())
