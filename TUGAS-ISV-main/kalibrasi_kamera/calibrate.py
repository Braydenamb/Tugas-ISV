"""Kalibrasi kamera smartphone dengan papan catur (metode Zhang, OpenCV).

Keluaran: matriks intrinsik K, koefisien distorsi D, Mean Reprojection Error (MRE),
plot koefisien distorsi, dan gambar pendukung di folder reports/.

Pemakaian:  python calibrate.py [--square-mm 25] [--outlier-px 1.5] [--fix-k3]
Papan catur 8x8 kotak -> 7x7 sudut dalam. Deteksi sudut ada di detector.py.
"""
import argparse, glob, json, os, shutil
import cv2
import numpy as np
import detector
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CRIT = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.0005)


def draw_board_scan(img, corners, pattern, dim=0.55):
    """Hasil 'scan' papan: garis kuning mengikuti tepi area permainan (8x8 kotak),
    latar di luar papan digelapkan. Tepi luar diekstrapolasi dari sudut dalam
    lewat homografi (grid -> citra), bukan dari deteksi kontur."""
    quad = detector.board_outline(corners)
    mask = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(mask, [np.round(quad).astype(np.int32)], 255)
    out = (img * dim).astype(np.uint8)
    out[mask > 0] = img[mask > 0]
    t = max(2, img.shape[1] // 400)
    cv2.polylines(out, [np.round(quad).astype(np.int32)], True, (0, 255, 255), t, cv2.LINE_AA)
    return out


def per_image_rmse(objp, imgp, rvec, tvec, K, D):
    proj, _ = cv2.projectPoints(objp, rvec, tvec, K, D)
    return float(np.sqrt(np.mean(np.sum((imgp.reshape(-1, 2) - proj.reshape(-1, 2)) ** 2, axis=1))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default="data/raw/*.jpg")
    ap.add_argument("--square-mm", type=float, default=25.0)
    ap.add_argument("--outlier-px", type=float, default=1.5,
                    help="buang citra dengan RMSE > nilai ini lalu kalibrasi ulang (0 = nonaktif)")
    ap.add_argument("--fix-k3", action="store_true",
                    help="kunci k3=0 (lebih stabil bila variasi pose/jarak terbatas)")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args()
    pattern = (detector.N, detector.N)  # papan 8x8 kotak -> 7x7 sudut dalam
    for sub in ("detected", "scan"):  # buang sisa hasil jalan sebelumnya
        shutil.rmtree(f"{a.out}/{sub}", ignore_errors=True)
    os.makedirs(f"{a.out}/figures", exist_ok=True); os.makedirs(f"{a.out}/detected", exist_ok=True); os.makedirs(f"{a.out}/scan", exist_ok=True)

    objp = np.zeros((detector.N ** 2, 3), np.float32)
    objp[:, :2] = detector.GRID * a.square_mm

    names, imgpoints, size = [], [], None
    for f in sorted(glob.glob(a.images)):
        img = cv2.imread(f)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        size = gray.shape[::-1]
        c, how = detector.detect(gray)
        ok = c is not None
        print(f"{os.path.basename(f)}: {how if ok else 'gagal'}")
        if ok:
            names.append(os.path.basename(f)); imgpoints.append(c)
            vis = img.copy(); cv2.drawChessboardCorners(vis, pattern, c, True)
            cv2.imwrite(f"{a.out}/detected/{os.path.basename(f)}", cv2.resize(vis, None, fx=0.5, fy=0.5))
            cv2.imwrite(f"{a.out}/scan/{os.path.basename(f)}", draw_board_scan(img, c, pattern))
    total = len(glob.glob(a.images))
    print(f"\nTerdeteksi: {len(names)}/{total} citra, ukuran {size}")
    if len(names) < 12:
        raise SystemExit("Kurang dari 12 citra valid.")

    def calibrate(idx):
        op = [objp] * len(idx); ip = [imgpoints[i] for i in idx]
        flags = cv2.CALIB_FIX_K3 if a.fix_k3 else 0
        rms, K, D, rv, tv = cv2.calibrateCamera(op, ip, size, None, None, flags=flags)
        errs = [per_image_rmse(objp, ip[j], rv[j], tv[j], K, D) for j in range(len(idx))]
        return rms, K, D, rv, tv, errs

    idx = list(range(len(names)))
    rms, K, D, rv, tv, errs = calibrate(idx)
    dropped = []
    if a.outlier_px > 0:
        # buang outlier satu per satu (yang terburuk dulu) selama masih > 12 citra
        while max(errs) > a.outlier_px and len(idx) > 12:
            w = int(np.argmax(errs)); dropped.append((names[idx[w]], errs[w])); idx.pop(w)
            rms, K, D, rv, tv, errs = calibrate(idx)
    used = [names[i] for i in idx]
    mre = float(np.mean(errs))  # rata-rata RMSE per-citra

    # Validasi silang: kalibrasi dengan setengah citra, uji error pada setengah lain
    rng = np.random.default_rng(0); perm = rng.permutation(len(idx)); h = len(idx) // 2
    A, B = [idx[i] for i in perm[:h]], [idx[i] for i in perm[h:]]
    _, Ka, Da, _, _, _ = calibrate(A)
    test = []
    for i in B:
        ok, r, t = cv2.solvePnP(objp, imgpoints[i], Ka, Da)
        test.append(per_image_rmse(objp, imgpoints[i], r, t, Ka, Da))
    cv_err = float(np.mean(test))

    print("\n=== HASIL ===")
    print("Matriks Intrinsik K:\n", K)
    print("Koefisien Distorsi D [k1 k2 p1 p2 k3]:\n", D)
    print(f"RMS reprojection error (ret calibrateCamera): {rms:.4f} px")
    print(f"Mean Reprojection Error (rata-rata per citra): {mre:.4f} px")
    print(f"Validasi silang (kalibrasi {len(A)} citra, uji {len(B)} citra): {cv_err:.4f} px")
    print(f"Citra dipakai: {len(used)}; dibuang sbg outlier: {dropped}")

    res = dict(image_size=size, pattern_inner_corners=pattern, square_mm=a.square_mm,
               n_detected=len(names), n_total=total, n_used=len(used), images_used=used,
               dropped_outliers=[{"file": n, "rmse_px": e} for n, e in dropped],
               K=K.tolist(), fx=K[0, 0], fy=K[1, 1], cx=K[0, 2], cy=K[1, 2],
               dist_k1_k2_p1_p2_k3=D.ravel().tolist(),
               rms_calibrateCamera_px=rms, mean_reprojection_error_px=mre,
               per_image_rmse_px=dict(zip(used, errs)), cross_validation_error_px=cv_err)
    json.dump(res, open(f"{a.out}/hasil_kalibrasi.json", "w"), indent=2)
    np.savez(f"{a.out}/kalibrasi.npz", K=K, D=D)

    # ---- Plot 1: koefisien distorsi
    labels = ["k1", "k2", "p1", "p2", "k3"]; d = D.ravel()[:5]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    bars = ax.bar(labels, d, color=["#2a6fdb" if v >= 0 else "#d9534f" for v in d])
    for b, v in zip(bars, d):
        ax.annotate(f"{v:.4f}", (b.get_x() + b.get_width() / 2, v), ha="center",
                    va="bottom" if v >= 0 else "top", fontsize=9)
    ax.axhline(0, color="k", lw=.8); ax.set_ylabel("Nilai koefisien")
    ax.set_title("Koefisien distorsi lensa D = [k1, k2, p1, p2, k3]"); ax.margins(y=.2)
    fig.tight_layout(); fig.savefig(f"{a.out}/figures/koefisien_distorsi.png", dpi=150); plt.close(fig)

    # ---- Plot 2: error reproyeksi per citra
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(range(len(used)), errs, color="#2a6fdb")
    ax.axhline(mre, color="#d9534f", ls="--", label=f"Rata-rata (MRE) = {mre:.3f} px")
    ax.set_xticks(range(len(used))); ax.set_xticklabels([u[6:8] for u in used])
    ax.set_xlabel("Nomor foto (papan_XX)"); ax.set_ylabel("RMSE reproyeksi (px)")
    ax.set_title("Error reproyeksi per citra"); ax.legend()
    fig.tight_layout(); fig.savefig(f"{a.out}/figures/error_reproyeksi.png", dpi=150); plt.close(fig)

    # ---- Plot 3: profil distorsi radial & peta perpindahan piksel
    w, h_ = size; fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    rmax = np.hypot(max(cx, w - cx) / fx, max(cy, h_ - cy) / fy)
    r = np.linspace(0, rmax, 200); k1, k2, _, _, k3 = d
    factor = 1 + k1 * r**2 + k2 * r**4 + k3 * r**6
    gx, gy = np.meshgrid(np.linspace(0, w, 25), np.linspace(0, h_, 33))
    pts = np.stack([gx.ravel(), gy.ravel()], 1).astype(np.float32).reshape(-1, 1, 2)
    und = cv2.undistortPoints(pts, K, D, P=K).reshape(-1, 2)
    disp = und - pts.reshape(-1, 2); mag = np.hypot(disp[:, 0], disp[:, 1])
    fig, axs = plt.subplots(1, 2, figsize=(11, 5))
    axs[0].plot(r, (factor - 1) * 100); axs[0].axhline(0, color="k", lw=.7)
    axs[0].set_xlabel("Jarak radial ternormalisasi r"); axs[0].set_ylabel("Faktor radial − 1 (%)")
    axs[0].set_title("Profil distorsi radial"); axs[0].grid(alpha=.3)
    q = axs[1].quiver(pts[:, 0, 0], pts[:, 0, 1], disp[:, 0], -disp[:, 1], mag, angles="xy",
                      scale_units="xy", scale=1, cmap="viridis")
    axs[1].invert_yaxis(); axs[1].set_aspect("equal"); fig.colorbar(q, ax=axs[1], label="px")
    axs[1].set_title("Perpindahan piksel saat undistort (vektor 1:1)")
    fig.tight_layout(); fig.savefig(f"{a.out}/figures/distorsi_radial.png", dpi=150); plt.close(fig)

    # ---- Plot 3b: sebaran sudut terdeteksi di bingkai (cakupan data)
    fig, ax = plt.subplots(figsize=(4.5, 6))
    allp = np.concatenate([imgpoints[i].reshape(-1, 2) for i in idx])
    ax.scatter(allp[:, 0], allp[:, 1], s=3, alpha=.5)
    ax.add_patch(plt.Rectangle((0, 0), w, h_, fill=False, color="k"))
    ax.set_xlim(-20, w + 20); ax.set_ylim(h_ + 20, -20); ax.set_aspect("equal")
    ax.set_title("Cakupan sudut papan pada bingkai"); fig.tight_layout()
    fig.savefig(f"{a.out}/figures/cakupan_sudut.png", dpi=150); plt.close(fig)

    # ---- Plot 4: sebelum/sesudah undistort pada satu foto
    pick = used[int(np.argmax(errs))] if False else used[0]
    img = cv2.imread(f"data/raw/{pick}") if os.path.exists(f"data/raw/{pick}") else cv2.imread(glob.glob(a.images)[0])
    newK, roi = cv2.getOptimalNewCameraMatrix(K, D, size, 1, size)
    dst = cv2.undistort(img, K, D, None, newK)
    both = np.hstack([cv2.resize(img, None, fx=.4, fy=.4), cv2.resize(dst, None, fx=.4, fy=.4)])
    cv2.imwrite(f"{a.out}/figures/sebelum_sesudah_undistort.jpg", both)


if __name__ == "__main__":
    main()