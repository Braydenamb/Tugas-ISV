from pathlib import Path
import argparse
from datetime import datetime
import json
import os
import sys

from .calibration import ROOT, calibrate, load_config
from .preprocessing import PROFILES
from .reporting import write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kalibrasi papan catur berdasarkan materi ISV")
    parser.add_argument("--config", type=Path, default=ROOT / "config/calibration.json")
    parser.add_argument("--photos", type=Path, help="Folder foto lain (ditelusuri rekursif)")
    parser.add_argument("--output", type=Path, help="Folder run baru; tidak menimpa run yang sudah ada")
    parser.add_argument("--preprocessing", choices=PROFILES)
    parser.add_argument("--compare", action="store_true", help="Hitung baseline dan mild pada dataset yang sama")
    parser.add_argument("--experiment", choices=("panels", "refinement"), help="Uji dua panel atau metode lanjutan dengan validasi silang")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        profile = args.preprocessing or config["preprocessing"]
        if profile not in PROFILES:
            raise ValueError(f"Profil tidak valid: {profile}")
        photos = args.photos.resolve() if args.photos else ROOT / config["photos"]
        output = args.output.resolve() if args.output else ROOT / "outputs" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        if output.exists() and any(output.iterdir()):
            raise ValueError(f"Folder hasil tidak kosong: {output}. Pilih folder baru agar hasil lama tetap tersimpan.")
        output.mkdir(parents=True, exist_ok=True)
        if args.experiment:
            if args.compare or args.preprocessing:
                raise ValueError("--experiment dipakai terpisah dari --compare/--preprocessing")
            if args.experiment == "panels":
                from .alternatives import run_panel_study
                run_panel_study(config, photos, output)
                report = ROOT / "reports/alternatives.md"
            else:
                from .refinement import run_refinement_study
                run_refinement_study(config, photos, output)
                report = ROOT / "reports/refinement.md"
            print(f"\nEksperimen selesai. Hasil: {output}\nLaporan: {report}")
            return 0
        if args.compare:
            results = {}
            for name in PROFILES:
                print(f"\nMemproses profil {name}...", flush=True)
                results[name] = calibrate(config, photos, output / name, name)
            baseline, mild = results["baseline"], results["mild"]
            # Same names, hashes, point identities, and exclusions are required for a fair comparison.
            a = [(r["file"], r["sha256"], r["points_used"]) for r in baseline["inputs"] if r["status"] == "used"]
            b = [(r["file"], r["sha256"], r["points_used"]) for r in mild["inputs"] if r["status"] == "used"]
            comparable = a == b and baseline["excluded_points"] == mild["excluded_points"]
            comparison = {"same_observations": comparable, "results": results}
            (output / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
            text = "# Perbandingan pemrosesan\n\n| Profil | Foto | Titik | Mean (px) | RMS (px) |\n|---|---:|---:|---:|---:|\n"
            for name in PROFILES:
                r = results[name]
                text += f"| {name} | {r['images_used']} | {r['observations_used']} | {r['mean_reprojection_error_px']:.6f} | {r['rms_reprojection_error_px']:.6f} |\n"
            text += "\n" + ("Kedua run memakai foto, hash, dan identitas titik yang sama." if comparable else "PERINGATAN: foto/titik yang digunakan berbeda, sehingga penurunan error tidak boleh dibandingkan langsung.")
            text += "\n\nProfil mild menambahkan Gaussian 3x3 sigma 0,8 dan CLAHE clipLimit 1,5 grid 8x8. Ini perbandingan kecocokan pada data kalibrasi, bukan validasi independen atau bukti bahwa posisi sudut lebih akurat.\n"
            (output / "comparison.md").write_text(text, encoding="utf-8")
            relative = Path(os.path.relpath(output, ROOT / "reports")).as_posix()
            (ROOT / "reports/comparison.md").write_text(text + f"\n[Detail hasil]({relative}/comparison.json)\n", encoding="utf-8")
            selected = results[profile]
            selected_output = output / profile
            for name in PROFILES:
                r = results[name]
                print(f"{name}: mean {r['mean_reprojection_error_px']:.6f} px; RMS {r['rms_reprojection_error_px']:.6f} px")
        else:
            selected = calibrate(config, photos, output, profile)
            selected_output = output
        write_report(selected, selected_output, ROOT / "reports/latest.md")
        (ROOT / "reports/latest_run.json").write_text(json.dumps({"output": Path(os.path.relpath(selected_output, ROOT)).as_posix(), "profile": profile}, indent=2), encoding="utf-8")
        print(f"\nSelesai: {selected['images_used']} foto, {selected['observations_used']} titik.")
        print(f"Mean {selected['mean_reprojection_error_px']:.6f} px; RMS {selected['rms_reprojection_error_px']:.6f} px.")
        print(f"Hasil: {selected_output}\nLaporan: {ROOT / 'reports/latest.md'}")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 1
