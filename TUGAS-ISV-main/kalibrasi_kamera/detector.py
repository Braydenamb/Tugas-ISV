"""Deteksi sudut papan catur lipat 8x8 (7x7 sudut dalam) yang tahan terhadap garis lipatan.

Strategi bertingkat:
 1. Deteksi langsung 7x7 pada citra diperkecil (cepat, presisi) -> find_full().
 2. Bila gagal: temukan SEBAGIAN kisi (mis. 4x3, 7x4) dengan findChessboardCornersSB, lalu
    tentukan posisi blok itu di dalam papan 8x8 dengan mencocokkan pola terang/gelap
    kotak-kotak hasil ekstrapolasi homografi (place_block) dan perhalus -> find_by_block().
"""
import cv2
import numpy as np

N = 7  # sudut dalam per sisi
CRIT = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.0005)
GRID = np.mgrid[0:N, 0:N].T.reshape(-1, 2).astype(np.float32)  # (x,y) indeks sudut, x paling cepat
PATS = [(7, 7), (7, 6), (6, 7), (6, 6), (7, 5), (5, 7), (6, 5), (5, 6), (5, 5), (7, 4), (4, 7),
        (6, 4), (4, 6), (5, 4), (4, 5), (4, 4), (7, 3), (3, 7), (6, 3), (3, 6), (5, 3), (3, 5),
        (4, 3), (3, 4), (3, 3)]


def _refine_subpix(gray, pts):
    d = np.median(np.linalg.norm(np.diff(pts.reshape(-1, 2)[:N], axis=0), axis=1))
    w = int(np.clip(d * 0.25, 5, 25))
    return cv2.cornerSubPix(gray, pts.reshape(-1, 1, 2).astype(np.float32), (w, w), (-1, -1), CRIT)


def find_full(gray):
    """Deteksi 7x7 langsung (multi-skala). Mengembalikan (49,1,2) atau None."""
    for s in (0.4, 0.33, 0.28, 0.25, 0.2):
        small = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        for im in (small, cv2.createCLAHE(3, (8, 8)).apply(small), cv2.GaussianBlur(small, (0, 0), 1.2)):
            ok, c = cv2.findChessboardCorners(
                im, (N, N), cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE)
            if not ok:
                ok, c = cv2.findChessboardCornersSB(
                    im, (N, N), cv2.CALIB_CB_EXHAUSTIVE + cv2.CALIB_CB_NORMALIZE_IMAGE)
            if ok:
                return _refine_subpix(gray, (c.reshape(-1, 2) / s).astype(np.float32))
    return None


def _find_blocks(gray, maxn=8):
    out = []
    for s in (0.4, 0.3, 0.22):
        small = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        for im in (small, cv2.GaussianBlur(small, (0, 0), 1.2), cv2.createCLAHE(3, (8, 8)).apply(small)):
            for p in PATS:
                ok, c = cv2.findChessboardCornersSB(im, p, cv2.CALIB_CB_NORMALIZE_IMAGE)
                if ok:
                    out.append((p, (c.reshape(-1, 2) / s).astype(np.float32)))
                    break
            if len(out) >= maxn:
                return out
    return out


def _local_grid(a, b, tr, fi, fj):
    ii, jj = np.meshgrid(np.arange(a), np.arange(b))
    X = ii.ravel().astype(np.float32); Y = jj.ravel().astype(np.float32)
    if fi: X = (a - 1) - X
    if fj: Y = (b - 1) - Y
    if tr: X, Y = Y, X
    return X, Y


def _sample(gb, H, pts, partial=False):
    p = cv2.perspectiveTransform(np.array(pts, np.float32).reshape(-1, 1, 2), H).reshape(-1, 2)
    h, w = gb.shape
    ok = (p[:, 0] >= 2) & (p[:, 0] <= w - 3) & (p[:, 1] >= 2) & (p[:, 1] <= h - 3)
    if not partial:
        return gb[p[:, 1].astype(int), p[:, 0].astype(int)].astype(np.float32) if ok.all() else None
    v = np.full(len(p), np.nan, np.float32)
    v[ok] = gb[p[ok, 1].astype(int), p[ok, 0].astype(int)]
    return v


_CENT = [(i - .5, j - .5) for i in range(8) for j in range(8)]
_S_IN = np.array([(-1) ** (i + j) for i in range(8) for j in range(8)], np.float32)
_RING = [(i - .5, j - .5) for i in range(-1, 9) for j in range(-1, 9) if i in (-1, 8) or j in (-1, 8)]
_S_RING = np.array([(-1) ** (i + j) for i in range(-1, 9) for j in range(-1, 9)
                    if i in (-1, 8) or j in (-1, 8)], np.float32)


def place_block(gray_blur, p, c):
    """Cari letak/orientasi blok (a x b sudut) di dalam kisi 7x7 yang membuat pola
    papan 8x8 hasil ekstrapolasi paling cocok dengan citra. Mengembalikan daftar (skor, H)."""
    a, b = p; cands = []
    for tr in (0, 1):
        for fi in (0, 1):
            for fj in (0, 1):
                X, Y = _local_grid(a, b, tr, fi, fj)
                wa, wb = (b, a) if tr else (a, b)
                for ox in range(N - wa + 1):
                    for oy in range(N - wb + 1):
                        H, _ = cv2.findHomography(np.stack([X + ox, Y + oy], 1), c, 0)
                        if H is None: continue
                        I = _sample(gray_blur, H, _CENT)
                        if I is None: continue
                        R = _sample(gray_blur, H, _RING, True)
                        m = I.mean(); cin = abs(np.sum(_S_IN * (I - m))) / 64
                        vr = ~np.isnan(R)
                        if vr.sum() >= 8:
                            cr = abs(np.sum(_S_RING[vr] * (R[vr] - m))) / vr.sum()
                            pen = 0.5 * max(0, R[vr].mean() - I.mean())
                        else:
                            cr = pen = 0
                        sc = cin - 2 * cr - pen
                        cands.append((sc, H))
    return cands


def _refine_from_H(gray, H):
    pts = cv2.perspectiveTransform(GRID.reshape(-1, 1, 2), H).astype(np.float32)
    for _ in range(4):  # perhalus bertahap: subpix -> refit homografi -> prediksi ulang
        pts = _refine_subpix(gray, pts)
        H2, _ = cv2.findHomography(GRID, pts.reshape(-1, 2), 0)
        pts = cv2.perspectiveTransform(GRID.reshape(-1, 1, 2), H2).astype(np.float32)
    pts = _refine_subpix(gray, pts)
    # validasi: 49 titik hasil perhalusan harus tetap membentuk kisi (homografi) yang rapi
    H3, _ = cv2.findHomography(GRID, pts.reshape(-1, 2), 0)
    pr = cv2.perspectiveTransform(GRID.reshape(-1, 1, 2), H3).reshape(-1, 2)
    resid = float(np.sqrt(np.mean(np.sum((pr - pts.reshape(-1, 2)) ** 2, 1))))
    return pts, resid


def find_by_block(gray, min_score=20.0, max_resid=1.5, top=6):
    gb = cv2.GaussianBlur(gray, (0, 0), 3)
    cands = []
    for p, c in _find_blocks(gray):
        cands += place_block(gb, p, c)
    cands = sorted([x for x in cands if x[0] >= min_score], key=lambda x: -x[0])
    tried = []
    for sc, H in cands:
        # lewati kandidat yang hampir identik dengan yang sudah dicoba
        P = cv2.perspectiveTransform(GRID.reshape(-1, 1, 2), H).reshape(-1, 2)
        if any(np.abs(P - Q).max() < 3 for Q in tried):
            continue
        tried.append(P)
        pts, resid = _refine_from_H(gray, H)
        if resid <= max_resid:
            return pts
        if len(tried) >= top:
            break
    return None


def detect(gray):
    """Kembalikan (corners (49,1,2), metode) atau (None, None)."""
    c = find_full(gray)
    if c is not None: return c, "langsung"
    c = find_by_block(gray)
    if c is not None: return c, "blok+ekstrapolasi"
    return None, None


def board_outline(corners):
    """Empat titik tepi luar papan 8x8 (garis kuning), dari homografi kisi -> citra."""
    H, _ = cv2.findHomography(GRID, corners.reshape(-1, 2), 0)
    q = np.array([[-1, -1], [N, -1], [N, N], [-1, N]], np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(q, H).reshape(-1, 2)