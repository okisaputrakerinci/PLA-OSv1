#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leaf Area Estimation – Research-Grade Pipeline (OpenCV)
Schema: 1.8  (deteksi koin robust + debug steps)

Subcommands:
  - process  : Proses 1 gambar atau 1 folder → kalibrasi, segmentasi, area,
               JSON/CSV/overlay/mask (+ debug steps), summary.csv (batch).
  - evaluate : Evaluasi terhadap GT (mask &/atau area) → IoU/Dice/P/R/F1,
               MAE/RMSE/MAPE (+ Bland–Altman, CI bootstrap).

Summary.csv (batch) memuat:
  filename, area_cm2, area_mm2, pixels_per_mm, mask_pixels, perimeter_mm,
  convex_area_cm2, bbox_coverage, scale_mode, runtime_ms, runtime_ms_pre,
  runtime_ms_calib, runtime_ms_seg, warnings, radius_px, diameter_px,
  calib_method, calib_circularity, calib_eccentricity, segmentation_method,
  camera_model, lighting_condition, background_color, manual_area_cm2,
  error_percent, orig_h, orig_w, proc_h, proc_w

Contoh:
  python leaf_area_research.py process --image data/daun1.jpg --save-prefix hasil/daun1 --coin-mm 25 --debug --save-steps
  python leaf_area_research.py process --data-folder data --out-folder output_batch --coin-mm 25 --resize-long 1200 --threads 4 --log-hw --save-steps
  python leaf_area_research.py evaluate --results-folder output_batch --gt-area-csv gt/area_gt.csv --gt-mask-dir gt/masks --summary-out eval_summary.csv

Format gt/area_gt.csv:
  filename,area_gt_cm2
  daun1.jpg,3.95
"""
import argparse
import csv
import glob
import json
import math
import os
import time
from datetime import datetime, timezone

import platform, random
import cv2
import numpy as np


# -------------------------- Utilitas dasar --------------------------
def ensure_dir_for_prefix(pathprefix: str):
    d = os.path.dirname(pathprefix)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def ensure_dir(path: str):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def read_image(path: str):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return img


def write_json(path: str, obj: dict):
    ensure_dir_for_prefix(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ------------------------- Preprocessing ops ------------------------
def apply_gamma(img_bgr: np.ndarray, gamma: float) -> np.ndarray:
    if abs(gamma - 1.0) < 1e-3:
        return img_bgr
    lut = np.array([((i / 255.0) ** (1.0 / gamma)) * 255 for i in range(256)]).astype("uint8")
    return cv2.LUT(img_bgr, lut)


def gray_world_wb(img_bgr: np.ndarray) -> np.ndarray:
    b, g, r = cv2.split(img_bgr.astype(np.float32))
    mb, mg, mr = b.mean() + 1e-6, g.mean() + 1e-6, r.mean() + 1e-6
    mgray = (mb + mg + mr) / 3.0
    b *= (mgray / mb); g *= (mgray / mg); r *= (mgray / mr)
    out = cv2.merge([b, g, r])
    return np.clip(out, 0, 255).astype(np.uint8)


# ----------------------- Visual util ----------------
def draw_coin(img: np.ndarray, coin_info) -> np.ndarray:
    """
    Gambar lingkar & center pada img.
    coin_info bisa (x,y,r) atau dict {"center_xy":[x,y], "radius_px":r}.
    """
    out = img.copy()
    if isinstance(coin_info, (tuple, list)) and len(coin_info) >= 3:
        x, y, r = coin_info[:3]
    elif isinstance(coin_info, dict):
        cx, cy = coin_info.get("center_xy", [0, 0])
        r = coin_info.get("radius_px", 0)
        x, y = cx, cy
    else:
        return out
    cv2.circle(out, (int(x), int(y)), int(r), (0, 255, 0), 2)     # outline
    cv2.circle(out, (int(x), int(y)), 2, (0, 0, 255), -1)         # center
    return out


# ------------- Deteksi lingkar kalibrasi (versi robust 1.8) -------------
def _coin_candidate_masks(bgr: np.ndarray):
    """
    Kembalikan tiga mask:
      - mas_adp : adaptive threshold (gelap = 1)
      - mas_hsv : gate piksel sangat gelap pada HSV
      - mas_comb: gabungan yang sudah dibersihkan (open/close)
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    mas_adp = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 5
    )
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    S, V = hsv[:, :, 1], hsv[:, :, 2]
    mas_hsv = cv2.inRange(V, 0, 90) & cv2.inRange(S, 0, 150)

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mas_comb = cv2.morphologyEx(cv2.bitwise_or(mas_adp, mas_hsv), cv2.MORPH_OPEN, k, 1)
    mas_comb = cv2.morphologyEx(mas_comb, cv2.MORPH_CLOSE, k, 2)
    return mas_adp, mas_hsv, mas_comb


def _score_circle_contour(c, gray: np.ndarray, r_min: float, r_max: float):
    """Skor 1 kontur sebagai kandidat disk solid berwarna gelap."""
    area = cv2.contourArea(c)
    if area < 50:
        return None

    peri = cv2.arcLength(c, True) + 1e-9
    circ = (4.0 * math.pi * area) / (peri * peri)  # → 1 kalau sangat bulat
    (cx, cy), r = cv2.minEnclosingCircle(c)
    r = float(r)
    if r < r_min or r > r_max:
        return None

    # extent terhadap disk penutup (semakin mendekati 1 semakin solid)
    extent = area / (math.pi * r * r + 1e-9)

    # solidity (tolak bentuk berlubang/bergerigi)
    hull = cv2.convexHull(c)
    solidity = area / (cv2.contourArea(hull) + 1e-9)

    # kehomogenan & kegelapan di dalam lingkar
    msk = np.zeros_like(gray)
    cv2.circle(msk, (int(cx), int(cy)), int(r), 255, -1)
    vals = gray[msk > 0]
    if vals.size == 0:
        return None
    mean = float(np.mean(vals))
    stdd = float(np.std(vals))

    # skor gabungan
    score = (
        0.45 * circ
        + 0.25 * extent
        + 0.15 * solidity
        + 0.10 * (1.0 / (1.0 + stdd / 30.0))
        + 0.05 * (1.0 / (1.0 + mean / 50.0))  # makin gelap makin baik
    )
    diag = dict(circularity=circ, extent=extent, solidity=solidity, std=stdd, mean=mean)
    return score, (cx, cy, r), diag


def detect_coin_pixels_per_mm(
    bgr: np.ndarray,
    coin_diameter_mm: float,
    warnings: list,
    coin_is_dark: bool = True,   # tetap disediakan untuk kompatibilitas (unused untuk sementara)
    debug_prefix: str = None,
):
    """
    Deteksi marker lingkar (koin/print bulat hitam) di mana pun posisinya.
    Strategi: adaptive+HSV → kontur → skoring → (fallback) HoughCircles.
    Return: (px_per_mm, (x,y,r), calib_dict) atau (None, None, None).
    """
    if coin_diameter_mm <= 0:
        raise ValueError("--coin-mm must be > 0")

    H, W = bgr.shape[:2]
    mn = min(H, W)
    r_min = max(4, int(0.01 * mn))
    r_max = int(0.20 * mn)  # batasi agar pot rim besar tidak lolos

    # --- kandidat via threshold ---
    mas_adp, mas_hsv, mas_comb = _coin_candidate_masks(bgr)
    cnts, _ = cv2.findContours(mas_comb, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    best = None
    best_score = -1.0
    best_diag = None
    for c in cnts:
        res = _score_circle_contour(c, gray, r_min, r_max)
        if res is None:
            continue
        sc, (cx, cy, r), diag = res
        if sc > best_score:
            best_score = sc
            best = (cx, cy, r)
            best_diag = diag

    # simpan debug step bila diminta
    if debug_prefix:
        cv2.imwrite(f"{debug_prefix}_coin_mask_adaptive.png", mas_adp)
        cv2.imwrite(f"{debug_prefix}_coin_mask_hsv.png", mas_hsv)
        cv2.imwrite(f"{debug_prefix}_coin_mask_combined.png", mas_comb)
        cand_vis = bgr.copy()
        for c in cnts:
            (cx, cy), rr = cv2.minEnclosingCircle(c)
            cv2.circle(cand_vis, (int(cx), int(cy)), int(rr), (0, 200, 255), 2)
        cv2.imwrite(f"{debug_prefix}_coin_candidates.jpg", cand_vis)

    if best is not None:
        cx, cy, r = best
        circ = float(best_diag["circularity"])
        if circ < 0.88:
            warnings.append(f"calib_low_circularity={circ:.2f}")
        if debug_prefix:
            cv2.imwrite(f"{debug_prefix}_coin_detect.jpg", draw_coin(bgr, (cx, cy, r)))
        px_per_mm = (2.0 * float(r)) / float(coin_diameter_mm)
        calib = {
            "method": "adaptive_dark_circularity",
            "radius_px": float(r),
            "diameter_px": float(2 * r),
            "circularity": float(circ),
            "eccentricity": None,
            "center_xy": [float(cx), float(cy)],
            "score": float(best_score),
            "extent": float(best_diag["extent"]),
            "solidity": float(best_diag["solidity"]),
            "int_mean": float(best_diag["mean"]),
            "int_std": float(best_diag["std"]),
        }
        return px_per_mm, (int(round(cx)), int(round(cy)), int(round(r))), calib

    # --- Fallback: Hough (lebih permisif) ---
    gray_c = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g = clahe.apply(gray_c)
    g_blur = cv2.GaussianBlur(g, (0, 0), 1.0)
    g_sharp = cv2.addWeighted(g, 1.5, g_blur, -0.5, 0)
    circles = cv2.HoughCircles(
        g_sharp,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(18, mn // 6),
        param1=120,
        param2=28,
        minRadius=r_min,
        maxRadius=r_max,
    )
    if circles is None:
        return None, None, None

    x, y, r = circles[0][0]
    px_per_mm = (2.0 * float(r)) / float(coin_diameter_mm)
    calib = {
        "method": "hough_fallback",
        "radius_px": float(r),
        "diameter_px": float(2 * r),
        "circularity": None,
        "eccentricity": None,
        "center_xy": [float(x), float(y)],
    }
    if debug_prefix:
        cv2.imwrite(f"{debug_prefix}_coin_detect.jpg", draw_coin(bgr, (x, y, r)))
    return px_per_mm, (int(x), int(y), int(r)), calib


# ------------------------ Segmentasi daun ---------------------------
def segment_leaf_mask(bgr: np.ndarray, use_clahe=False, adaptive_fallback=True, debug_prefix: str=None):
    """
    LAB; invert A → Otsu; fallback adaptif bila Otsu jelek; morphology; largest component; hole filling
    Return: (mask_uint8, debug_dict)
    """
    dbg = {}
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    if use_clahe:
        clahe = cv2.createCLAHE(2.0,(8,8)); L = clahe.apply(L); lab = cv2.merge([L,A,B])

    A_inv = 255 - lab[:,:,1]
    _, th = cv2.threshold(A_inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    nz = np.count_nonzero(th)
    if adaptive_fallback and (nz < 50 or nz > 0.95*th.size):
        th = cv2.adaptiveThreshold(A_inv,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,2)

    k1 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
    k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9))
    mask = cv2.morphologyEx(th, cv2.MORPH_OPEN, k1, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k2, iterations=2)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if num_labels <= 1:
        largest = mask; areas_sorted = []
    else:
        areas = stats[1:, cv2.CC_STAT_AREA]
        max_idx = 1 + np.argmax(areas)
        largest = np.zeros_like(mask); largest[labels==max_idx] = 255
        areas_sorted = sorted(areas.tolist(), reverse=True)

    ff = largest.copy(); h,w = ff.shape; mask_ff = np.zeros((h+2,w+2),np.uint8)
    cv2.floodFill(ff, mask_ff, (0,0), 255); holes = cv2.bitwise_not(ff)
    filled = cv2.bitwise_or(largest, holes)

    if debug_prefix:
        cv2.imwrite(f"{debug_prefix}_Ainv.png", A_inv)
        cv2.imwrite(f"{debug_prefix}_thresh.png", th)
        cv2.imwrite(f"{debug_prefix}_largest.png", largest)
        cv2.imwrite(f"{debug_prefix}_filled.png", filled)

    dbg["areas_sorted"] = areas_sorted
    return filled, dbg


def overlay_mask(bgr: np.ndarray, mask: np.ndarray, alpha: float=0.45) -> np.ndarray:
    colored = np.zeros_like(bgr); colored[:,:,1] = mask
    return cv2.addWeighted(bgr,1.0,colored,alpha,0)


# ----------------------- Area & metric utils ------------------------
def compute_area(mask_pixels: int, px_per_mm: float):
    if px_per_mm is None or px_per_mm <= 0:
        raise RuntimeError("Invalid pixels_per_mm; calibration failed or non-positive.")
    area_mm2 = mask_pixels / (px_per_mm**2)
    area_cm2 = area_mm2 / 100.0
    return area_cm2, area_mm2


def mask_metrics(pred: np.ndarray, gt: np.ndarray) -> dict:
    if pred.shape != gt.shape:
        raise ValueError("GT mask shape mismatch with prediction.")
    p = (pred>0).astype(np.uint8); g = (gt>0).astype(np.uint8)
    tp = int(np.sum((p==1)&(g==1))); fp = int(np.sum((p==1)&(g==0)))
    fn = int(np.sum((p==0)&(g==1))); tn = int(np.sum((p==0)&(g==0)))
    iou  = tp/(tp+fp+fn+1e-9); dice = (2*tp)/(2*tp+fp+fn+1e-9)
    prec = tp/(tp+fp+1e-9); rec = tp/(tp+fn+1e-9); f1 = (2*prec*rec)/(prec+rec+1e-9)
    return dict(IoU=iou, Dice=dice, Precision=prec, Recall=rec, F1=f1, TP=tp, FP=fp, FN=fn, TN=tn)


# ------------------------------ PROCESS -----------------------------
def process_single_image(
    img_path: str, save_prefix: str,
    coin_mm: float=25.0, manual_ppm: float=None, min_leaf_area_mm2: float=300.0,
    white_balance: bool=False, gamma: float=1.0, clahe: bool=False, debug: bool=False,
    coin_is_dark: bool=True, resize_long: int=None, run_env: dict=None, save_steps: bool=False
) -> dict:
    t0 = time.time(); warnings = []
    bgr = read_image(img_path)

    # Resize opsional (agar ringan & konsisten)
    orig_h, orig_w = bgr.shape[:2]
    if resize_long and max(orig_h, orig_w) > int(resize_long):
        scale = float(resize_long) / float(max(orig_h, orig_w))
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)
        bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Preprocess
    t_pre0 = time.time()
    if white_balance: bgr = gray_world_wb(bgr)
    if abs(gamma-1.0) > 1e-3: bgr = apply_gamma(bgr, gamma)
    t_pre1 = time.time()

    # Kalibrasi skala
    t_cal0 = time.time()
    px_per_mm = None; coin_info = None; calib_diag = None; scale_mode = "unknown"

    if manual_ppm is not None:
        if manual_ppm <= 0: raise ValueError("--manual-ppm must be > 0")
        px_per_mm = float(manual_ppm); scale_mode = "manual_ppm"
    else:
        # simpan debug coin bila debug atau save_steps
        dbg_prefix = save_prefix if (debug or save_steps) else None
        px_per_mm, coin_info, calib_diag = detect_coin_pixels_per_mm(
            bgr, coin_mm, warnings, coin_is_dark=coin_is_dark, debug_prefix=dbg_prefix
        )
        if px_per_mm is not None: scale_mode = "coin"
        else: raise RuntimeError("Deteksi lingkar kalibrasi gagal. Perbaiki foto atau gunakan --manual-ppm.")
    t_cal1 = time.time()

    # Segmentasi
    t_seg0 = time.time()
    debug_prefix = save_prefix if (debug or save_steps) else None
    mask, dbg = segment_leaf_mask(bgr, use_clahe=clahe, adaptive_fallback=True, debug_prefix=debug_prefix)
    t_seg1 = time.time()

    # Area & fitur bentuk
    mask_pixels = int(cv2.countNonZero(mask))
    area_cm2, area_mm2 = compute_area(mask_pixels, px_per_mm)

    # Kontur utama → perimeter, convex hull, coverage
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    perimeter_mm = None; convex_area_cm2 = None; bbox_coverage = None
    if cnts:
        cmax = max(cnts, key=cv2.contourArea)
        peri_px = cv2.arcLength(cmax, True)
        perimeter_mm = peri_px / px_per_mm  # px / (px/mm) = mm

        hull = cv2.convexHull(cmax)
        hull_area_px = cv2.contourArea(hull)
        convex_area_mm2 = hull_area_px / (px_per_mm**2)
        convex_area_cm2 = convex_area_mm2 / 100.0

        x,y,w,h = cv2.boundingRect(cmax)
        bbox_area_px = float(w*h) if (w>0 and h>0) else 0.0
        bbox_coverage = (mask_pixels / bbox_area_px) if bbox_area_px>0 else None

    # QC flag
    areas_sorted = dbg.get("areas_sorted", [])
    if area_mm2 < min_leaf_area_mm2: warnings.append(f"area_below_min={area_mm2:.1f}<{min_leaf_area_mm2:.1f}")
    if len(areas_sorted)>=2 and areas_sorted[1] > 0.25*areas_sorted[0]: warnings.append("multiple_large_components")

    # Simpan overlay & mask
    ensure_dir_for_prefix(save_prefix)
    overlay = overlay_mask(bgr, mask, alpha=0.45)
    cv2.imwrite(f"{save_prefix}_overlay.jpg", overlay)
    cv2.imwrite(f"{save_prefix}_mask.png", mask)
    # (coin debug sudah ditulis di detect_coin_pixels_per_mm bila diminta)

    # Meta output
    meta = {
        "schema_version":"1.8",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "image": os.path.abspath(img_path),
        "orig_size": [int(orig_h), int(orig_w)],
        "proc_size": [int(bgr.shape[0]), int(bgr.shape[1])],
        "runtime_ms": int(round((time.time()-t0)*1000)),
        "runtime_ms_pre": int(round((t_pre1 - t_pre0)*1000)),
        "runtime_ms_calib": int(round((t_cal1 - t_cal0)*1000)),
        "runtime_ms_seg": int(round((t_seg1 - t_seg0)*1000)),
        "scale_mode": scale_mode,
        "pixels_per_mm": float(px_per_mm),
        "mask_pixels": int(mask_pixels),
        "area_mm2": float(area_mm2),
        "area_cm2": float(area_cm2),
        "perimeter_mm": (None if perimeter_mm is None else float(perimeter_mm)),
        "convex_area_cm2": (None if convex_area_cm2 is None else float(convex_area_cm2)),
        "bbox_coverage": (None if bbox_coverage is None else float(bbox_coverage)),
        "min_leaf_area_mm2": float(min_leaf_area_mm2),
        "warnings": warnings,
        "calibration": calib_diag,
        "outputs": {
            "overlay_jpg": os.path.abspath(f"{save_prefix}_overlay.jpg"),
            "mask_png": os.path.abspath(f"{save_prefix}_mask.png"),
            "coin_detect_jpg": os.path.abspath(f"{save_prefix}_coin_detect.jpg") if (save_steps or debug) else None,
            "coin_masks": {
                "adaptive": os.path.abspath(f"{save_prefix}_coin_mask_adaptive.png") if (save_steps or debug) else None,
                "hsv": os.path.abspath(f"{save_prefix}_coin_mask_hsv.png") if (save_steps or debug) else None,
                "combined": os.path.abspath(f"{save_prefix}_coin_mask_combined.png") if (save_steps or debug) else None,
                "candidates": os.path.abspath(f"{save_prefix}_coin_candidates.jpg") if (save_steps or debug) else None,
            },
            "result_json": os.path.abspath(f"{save_prefix}_result.json"),
            "result_csv": os.path.abspath(f"{save_prefix}_result.csv"),
        },
        "env": (run_env or None),
        "params": {"coin_mm": float(coin_mm) if manual_ppm is None else None,
                   "manual_ppm": float(manual_ppm) if manual_ppm is not None else None,
                   "white_balance": bool(white_balance), "gamma": float(gamma), "clahe": bool(clahe),
                   "coin_is_dark": bool(coin_is_dark), "save_steps": bool(save_steps)}
    }
    write_json(f"{save_prefix}_result.json", meta)
    with open(f"{save_prefix}_result.csv","w",encoding="utf-8",newline="") as f:
        w = csv.writer(f); header = list(meta.keys()); w.writerow(header); w.writerow([meta[k] for k in header])
    return meta


def _load_gt_area_dict(gt_area_csv: str) -> dict:
    if not gt_area_csv or not os.path.exists(gt_area_csv): return {}
    gt = {}
    with open(gt_area_csv,"r",encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                gt[row["filename"].strip()] = float(row["area_gt_cm2"])
            except Exception:
                pass
    return gt


def process_folder(
    data_folder: str, out_folder: str, coin_mm: float=25.0, manual_ppm: float=None,
    min_leaf_area_mm2: float=300.0, white_balance: bool=False, gamma: float=1.0, clahe: bool=False, debug: bool=False,
    gt_area_csv: str=None, camera_model: str="unknown", lighting_condition: str="unknown", background_color: str="unknown",
    summary_out: str=None, coin_is_dark: bool=True, resize_long: int=None, run_env: dict=None, save_steps: bool=False
) -> str:
    ensure_dir(out_folder)
    results = []
    img_paths = sorted([p for p in glob.glob(os.path.join(data_folder,"*")) if os.path.isfile(p)])
    gt_area_map = _load_gt_area_dict(gt_area_csv)

    for p in img_paths:
        base = os.path.splitext(os.path.basename(p))[0]
        prefix = os.path.join(out_folder, base)
        try:
            meta = process_single_image(
                img_path=p, save_prefix=prefix,
                coin_mm=coin_mm, manual_ppm=manual_ppm, min_leaf_area_mm2=min_leaf_area_mm2,
                white_balance=white_balance, gamma=gamma, clahe=clahe, debug=debug, coin_is_dark=coin_is_dark,
                resize_long=resize_long, run_env=run_env, save_steps=save_steps
            )
            print(f"[OK] {p} -> {meta['area_cm2']:.2f} cm^2 | {meta['scale_mode']} | {meta['runtime_ms']} ms")
            results.append(meta)
        except Exception as e:
            print(f"[FAIL] {p}: {e}")

    # summary csv
    def _write_summary(path):
        with open(path,"w",encoding="utf-8",newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "filename","area_cm2","area_mm2","pixels_per_mm","mask_pixels",
                "perimeter_mm","convex_area_cm2","bbox_coverage",
                "scale_mode","runtime_ms","runtime_ms_pre","runtime_ms_calib","runtime_ms_seg","warnings",
                "radius_px","diameter_px","calib_method","calib_circularity","calib_eccentricity",
                "segmentation_method","camera_model","lighting_condition","background_color",
                "manual_area_cm2","error_percent","orig_h","orig_w","proc_h","proc_w"
            ])
            for r in results:
                calib = r.get("calibration") or {}
                fname = os.path.basename(r["image"])
                area_pred = float(r["area_cm2"])
                area_gt = gt_area_map.get(fname, "")
                err_pct = ""
                if fname in gt_area_map:
                    gtval = gt_area_map[fname]
                    err_pct = (area_pred - gtval) / (gtval + 1e-9) * 100.0
                w.writerow([
                    fname, r["area_cm2"], r["area_mm2"], r["pixels_per_mm"], r["mask_pixels"],
                    r.get("perimeter_mm",""), r.get("convex_area_cm2",""), r.get("bbox_coverage",""),
                    r["scale_mode"], r["runtime_ms"], r.get("runtime_ms_pre",""), r.get("runtime_ms_calib",""), r.get("runtime_ms_seg",""),
                    "|".join(r["warnings"]),
                    calib.get("radius_px",""), calib.get("diameter_px",""), calib.get("method",""),
                    calib.get("circularity",""), calib.get("eccentricity",""),
                    "LAB-A Otsu", camera_model, lighting_condition, background_color,
                    area_gt, err_pct,
                    (r.get("orig_size",[None,None])[0]), (r.get("orig_size",[None,None])[1]),
                    (r.get("proc_size",[None,None])[0]), (r.get("proc_size",[None,None])[1])
                ])

    summary_path = summary_out or os.path.join(out_folder, "summary.csv")
    try:
        _write_summary(summary_path)
    except PermissionError:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        summary_path = os.path.join(out_folder, f"summary_{ts}.csv")
        _write_summary(summary_path)

    print(f"\nSummary saved to {summary_path}")
    return summary_path


# ------------------------------ EVALUATE ----------------------------
def load_area_gt(gt_area_csv: str) -> dict:
    if not gt_area_csv or not os.path.exists(gt_area_csv): return {}
    gt = {}
    with open(gt_area_csv,"r",encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                gt[row["filename"]] = float(row["area_gt_cm2"])
            except Exception:
                pass
    return gt


def aggregate_regression_errors(pairs: list) -> dict:
    if not pairs: return {}
    diffs = [pred - gt for (gt, pred) in pairs]
    abs_err = [abs(d) for d in diffs]; sq_err = [d*d for d in diffs]
    m = len(pairs)
    mae = sum(abs_err)/m; rmse = math.sqrt(sum(sq_err)/m)
    mape = 100.0 * sum((abs(pred-gt)/(gt+1e-9)) for (gt,pred) in pairs)/m
    bias = sum(diffs)/m
    return dict(MAE=mae, RMSE=rmse, MAPE=mape, Bias=bias, N=m)


def _bland_altman(pairs: list):
    if not pairs: return {}
    gts = np.array([g for g,p in pairs], dtype=float)
    preds = np.array([p for g,p in pairs], dtype=float)
    diffs = preds - gts
    mean_diff = float(np.mean(diffs))
    sd_diff   = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0
    loa_low   = mean_diff - 1.96*sd_diff
    loa_high  = mean_diff + 1.96*sd_diff
    return dict(mean_bias=mean_diff, sd=sd_diff, loa_low=loa_low, loa_high=loa_high)


def _bootstrap_ci(values: list, nboot=2000, alpha=0.05, rng_seed=42):
    if not values: return None, None
    vals = np.array(values, dtype=float)
    rng = np.random.default_rng(rng_seed)
    stats = []
    for _ in range(nboot):
        samp = rng.choice(vals, size=len(vals), replace=True)
        stats.append(float(np.mean(samp)))
    lo = float(np.percentile(stats, 100*alpha/2))
    hi = float(np.percentile(stats, 100*(1-alpha/2)))
    return lo, hi


def evaluate_results(results_folder: str, gt_area_csv: str=None, gt_mask_dir: str=None, summary_out: str=None) -> str:
    metas = sorted(glob.glob(os.path.join(results_folder,"*_result.json")))
    if not metas: raise FileNotFoundError("No *_result.json found in results_folder.")

    area_gt = load_area_gt(gt_area_csv)
    has_area = bool(area_gt)
    has_mask = bool(gt_mask_dir) and os.path.isdir(gt_mask_dir)

    rows = []; reg_pairs = []
    for mp in metas:
        with open(mp,"r",encoding="utf-8") as f: meta = json.load(f)
        img_name = os.path.basename(meta["image"]); base = os.path.splitext(img_name)[0]
        pred_area = float(meta["area_cm2"]); pred_mask_path = meta["outputs"].get("mask_png", None)
        gt_area_val = area_gt.get(img_name, None)

        metrics = {}
        TP = FP = FN = TN = 0
        pred_pixels = gt_pixels = 0
        
        if has_mask and pred_mask_path and os.path.exists(pred_mask_path):
            gt_mask_path = os.path.join(gt_mask_dir, f"{base}.png")
            if os.path.exists(gt_mask_path):
                pred_mask = cv2.imread(pred_mask_path, cv2.IMREAD_GRAYSCALE)
                gt_mask = cv2.imread(gt_mask_path, cv2.IMREAD_GRAYSCALE)
                if pred_mask is not None and gt_mask is not None:
                    if gt_mask.shape != pred_mask.shape:
                        gt_mask = cv2.resize(gt_mask,(pred_mask.shape[1],pred_mask.shape[0]),interpolation=cv2.INTER_NEAREST)
                    metrics = mask_metrics(pred_mask, gt_mask)
                    # ===== TAMBAHAN BARU =====
                    pred_bin = (pred_mask > 0).astype(np.uint8)
                    gt_bin   = (gt_mask > 0).astype(np.uint8)

                    TP = int(np.sum((pred_bin == 1) & (gt_bin == 1)))
                    FP = int(np.sum((pred_bin == 1) & (gt_bin == 0)))
                    FN = int(np.sum((pred_bin == 0) & (gt_bin == 1)))
                    TN = int(np.sum((pred_bin == 0) & (gt_bin == 0)))

                    pred_pixels = int(np.sum(pred_bin))
                    gt_pixels   = int(np.sum(gt_bin))

        if has_area and gt_area_val is not None: reg_pairs.append((gt_area_val, pred_area))

        rows.append({
            "filename": img_name,
            "area_pred_cm2": pred_area,
            "area_gt_cm2": gt_area_val if gt_area_val is not None else "",

            # METRIK
            "IoU": metrics.get("IoU",""),
            "Dice": metrics.get("Dice",""),
            "Precision": metrics.get("Precision",""),
            "Recall": metrics.get("Recall",""),
            "F1": metrics.get("F1",""),

            # TAMBAHAN BARU 🔥
            "TP": TP,
            "FP": FP,
            "FN": FN,
            "TN": TN,
            "pred_pixels": pred_pixels,
            "gt_pixels": gt_pixels,

            "scale_mode": meta.get("scale_mode",""),
            "pixels_per_mm": meta.get("pixels_per_mm",""),
            "runtime_ms": meta.get("runtime_ms",""),
            "warnings": "|".join(meta.get("warnings",[])),
        })

    # Agregat numerik
    agg_reg = aggregate_regression_errors(reg_pairs) if reg_pairs else {}
    agg_cls = {}
    if any(r["IoU"] != "" for r in rows):
        ious  = [float(r["IoU"]) for r in rows if r["IoU"] != ""]
        dices = [float(r["Dice"]) for r in rows if r["Dice"] != ""]
        precs = [float(r["Precision"]) for r in rows if r["Precision"] != ""]
        recs  = [float(r["Recall"]) for r in rows if r["Recall"] != ""]
        f1s   = [float(r["F1"]) for r in rows if r["F1"] != ""]
        mean = lambda xs: sum(xs)/max(1,len(xs))
        agg_cls = dict(IoU_mean=mean(ious), Dice_mean=mean(dices), Precision_mean=mean(precs),
                       Recall_mean=mean(recs), F1_mean=mean(f1s), N=len(ious))

    # Bland–Altman & CI bootstrap untuk MAE/RMSE/MAPE (mean)
    ba = _bland_altman(reg_pairs) if reg_pairs else {}
    mae_vals = [abs(p-g) for (g,p) in reg_pairs]
    rmse_vals = [ (p-g)**2 for (g,p) in reg_pairs ]  # untuk CI mean(RMSE^2), ambil akar setelah rata-rata?
    mape_vals = [100.0*abs(p-g)/(g+1e-9) for (g,p) in reg_pairs]

    mae_lo, mae_hi = _bootstrap_ci(mae_vals) if mae_vals else (None, None)
    rmse_mean_lo, rmse_mean_hi = _bootstrap_ci(rmse_vals) if rmse_vals else (None, None)
    rmse_lo = math.sqrt(rmse_mean_lo) if rmse_mean_lo is not None else None
    rmse_hi = math.sqrt(rmse_mean_hi) if rmse_mean_hi is not None else None
    mape_lo, mape_hi = _bootstrap_ci(mape_vals) if mape_vals else (None, None)

    out_path = summary_out or os.path.join(results_folder,"evaluation_summary.csv")
    with open(out_path,"w",encoding="utf-8",newline="") as f:
        w = csv.writer(f)
        # Per-file
        w.writerow([
            "filename","area_pred_cm2","area_gt_cm2",
            "IoU","Dice","Precision","Recall","F1",
            "TP","FP","FN","TN","pred_pixels","gt_pixels",
            "scale_mode","pixels_per_mm","runtime_ms","warnings"
        ])
        for r in rows:
            w.writerow([r["filename"],r["area_pred_cm2"],r["area_gt_cm2"],r["IoU"],r["Dice"],r["Precision"],r["Recall"],r["F1"],r["TP"], r["FP"], r["FN"], r["TN"],r["pred_pixels"], r["gt_pixels"],r["scale_mode"],r["pixels_per_mm"],r["runtime_ms"],r["warnings"]])
        # Agregat regresi
        w.writerow([]); w.writerow(["# Aggregate regression (area):","MAE","RMSE","MAPE","Bias","N"])
        if agg_reg: w.writerow(["",f"{agg_reg['MAE']:.4f}",f"{agg_reg['RMSE']:.4f}",f"{agg_reg['MAPE']:.2f}%",f"{agg_reg['Bias']:.4f}",agg_reg['N']])
        else: w.writerow(["","","","","",0])
        # CI
        w.writerow([]); w.writerow(["# 95% bootstrap CI:","MAE_lo","MAE_hi","RMSE_lo","RMSE_hi","MAPE_lo","MAPE_hi"])
        w.writerow(["",
                    ("" if mae_lo is None else f"{mae_lo:.4f}"),
                    ("" if mae_hi is None else f"{mae_hi:.4f}"),
                    ("" if rmse_lo is None else f"{rmse_lo:.4f}"),
                    ("" if rmse_hi is None else f"{rmse_hi:.4f}"),
                    ("" if mape_lo is None else f"{mape_lo:.2f}%"),
                    ("" if mape_hi is None else f"{mape_hi:.2f}%")
        ])
        # Agregat segmentasi
        w.writerow([]); w.writerow(["# Aggregate segmentation (mask):","IoU_mean","Dice_mean","Precision_mean","Recall_mean","F1_mean","N"])
        if agg_cls: w.writerow(["",f"{agg_cls['IoU_mean']:.4f}",f"{agg_cls['Dice_mean']:.4f}",f"{agg_cls['Precision_mean']:.4f}",f"{agg_cls['Recall_mean']:.4f}",f"{agg_cls['F1_mean']:.4f}",agg_cls['N']])
        else: w.writerow(["","","","","","",0])
        # Bland–Altman
        w.writerow([]); w.writerow(["# Bland–Altman:","bias_mean","SD_diff","LoA_low","LoA_high"])
        if ba: w.writerow(["",f"{ba['mean_bias']:.4f}",f"{ba['sd']:.4f}",f"{ba['loa_low']:.4f}",f"{ba['loa_high']:.4f}"])
        else: w.writerow(["","","",""])
    print(f"Evaluation summary saved to {out_path}")
    return out_path


# ------------------------------ CLI --------------------------------
def main():
    cv2.setNumThreads(0); cv2.ocl.setUseOpenCL(False)
    ap = argparse.ArgumentParser(description="Leaf area research-grade pipeline (process & evaluate).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # process
    app = sub.add_parser("process", help="Process one image or a folder (batch).")
    g_in = app.add_argument_group("Input")
    g_in.add_argument("--image", help="Path ke foto daun (single image).")
    g_in.add_argument("--data-folder", help="Folder input gambar (non-recursive).")
    g_in.add_argument("--resize-long", type=int, help="Resize sisi terpanjang sebelum proses (px).")

    g_out = app.add_argument_group("Output")
    g_out.add_argument("--save-prefix", default=None, help="Prefix untuk single image.")
    g_out.add_argument("--out-folder", default=None, help="Folder output untuk batch.")
    g_out.add_argument("--debug", action="store_true", help="Simpan gambar debug & coin detection.")
    g_out.add_argument("--save-steps", action="store_true", help="Simpan step Ainv/thresh/largest/filled & coin masks.")

    g_cal = app.add_argument_group("Calibration")
    g_cal.add_argument("--coin-mm", type=float, default=25.0, help="Diameter lingkar kalibrasi (mm).")
    g_cal.add_argument("--manual-ppm", type=float, default=None, help="Bypass kalibrasi otomatis.")
    g_cal.add_argument("--coin-is-dark", action="store_true", help="Optimalkan deteksi untuk koin/lingkar gelap.")

    g_seg = app.add_argument_group("Segmentation & QC")
    g_seg.add_argument("--min-leaf-area-mm2", type=float, default=300.0, help="Ambang minimum luas (mm^2).")
    g_seg.add_argument("--white-balance", action="store_true", help="Gray-world white balance.")
    g_seg.add_argument("--gamma", type=float, default=1.0, help="Gamma correction (0.9~1.2).")
    g_seg.add_argument("--clahe", action="store_true", help="CLAHE pada L-channel LAB.")

    g_meta = app.add_argument_group("Metadata for summary.csv")
    g_meta.add_argument("--gt-area-csv", help="CSV ground-truth area (filename,area_gt_cm2) untuk dihitung error di summary.")
    g_meta.add_argument("--camera-model", default="unknown", help="Tag kamera untuk summary.")
    g_meta.add_argument("--lighting", dest="lighting_condition", default="unknown", help="Tag pencahayaan untuk summary.")
    g_meta.add_argument("--background", dest="background_color", default="unknown", help="Tag latar untuk summary.")
    g_meta.add_argument("--summary-out", help="Path custom nama summary.csv (opsional).")

    g_sys = app.add_argument_group("System & Reproducibility")
    g_sys.add_argument("--seed", type=int, default=42, help="Seed untuk reproducibility.")
    g_sys.add_argument("--threads", type=int, default=0, help="Batasi thread OpenCV (0 = default).")
    g_sys.add_argument("--log-hw", action="store_true", help="Log versi Python/OpenCV/Numpy dan info OS/CPU.")

    # evaluate
    aev = sub.add_parser("evaluate", help="Evaluate predictions against ground-truth.")
    aev.add_argument("--results-folder", required=True, help="Folder yang berisi *_result.json.")
    aev.add_argument("--gt-area-csv", help="CSV ground-truth area (filename,area_gt_cm2).")
    aev.add_argument("--gt-mask-dir", help="Folder GT mask (PNG biner).")
    aev.add_argument("--summary-out", help="Path file keluaran ringkasan evaluasi (CSV).")

    args = ap.parse_args()

    # Threads & seed & env
    if getattr(args, "threads", 0) and args.threads > 0:
        cv2.setNumThreads(args.threads)
    random.seed(getattr(args, "seed", 42))
    np.random.seed(getattr(args, "seed", 42))
    run_env = {}
    if getattr(args, "log_hw", False):
        run_env = {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "os": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "threads": int(args.threads),
            "seed": int(args.seed),
        }

    if args.cmd == "process":
        if not args.image and not args.data_folder:
            raise ValueError("Harus salah satu: --image atau --data-folder")

        if args.image:
            if not args.save_prefix:
                base = os.path.splitext(os.path.basename(args.image))[0]
                args.save_prefix = os.path.join("output", base)
            meta = process_single_image(
                img_path=args.image, save_prefix=args.save_prefix,
                coin_mm=args.coin_mm, manual_ppm=args.manual_ppm, min_leaf_area_mm2=args.min_leaf_area_mm2,
                white_balance=args.white_balance, gamma=args.gamma, clahe=args.clahe, debug=args.debug,
                coin_is_dark=args.coin_is_dark, resize_long=args.resize_long, run_env=run_env, save_steps=args.save_steps
            )
            print(json.dumps({
                "image": meta["image"], "area_cm2": meta["area_cm2"], "area_mm2": meta["area_mm2"],
                "pixels_per_mm": meta["pixels_per_mm"], "scale_mode": meta["scale_mode"],
                "runtime_ms": meta["runtime_ms"], "warnings": meta["warnings"], "outputs": meta["outputs"]
            }, indent=2))
        else:
            if not args.out_folder: args.out_folder = "output_batch"
            process_folder(
                data_folder=args.data_folder, out_folder=args.out_folder,
                coin_mm=args.coin_mm, manual_ppm=args.manual_ppm, min_leaf_area_mm2=args.min_leaf_area_mm2,
                white_balance=args.white_balance, gamma=args.gamma, clahe=args.clahe, debug=args.debug,
                gt_area_csv=args.gt_area_csv, camera_model=args.camera_model,
                lighting_condition=args.lighting_condition, background_color=args.background_color,
                summary_out=args.summary_out, coin_is_dark=args.coin_is_dark,
                resize_long=args.resize_long, run_env=run_env, save_steps=args.save_steps
            )

    elif args.cmd == "evaluate":
        evaluate_results(results_folder=args.results_folder, gt_area_csv=args.gt_area_csv,
                         gt_mask_dir=args.gt_mask_dir, summary_out=args.summary_out)


if __name__ == "__main__":
    main()
