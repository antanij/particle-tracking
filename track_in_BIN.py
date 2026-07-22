import os
import argparse
from typing import Dict, Any, Tuple, List

import numpy as np
import pandas as pd
import trackpy as tp
import yaml

import sys
import time

def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


META_SUFFIX = "_meta.json"


def load_config_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def infer_meta_path(bin_path: str) -> str:
    stem = os.path.splitext(bin_path)[0]
    meta_path = stem + META_SUFFIX
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Expected metadata file {meta_path} for bin {bin_path}")
    return meta_path


# ------------------- metadata + bin IO -------------------
def read_metadata_json(meta_file: str) -> dict:
    import json
    with open(meta_file, "r") as f:
        j = json.load(f)

    def walk(obj):
        if isinstance(obj, dict):
            yield obj
            for v in obj.values():
                yield from walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from walk(v)

    def first_dict_with_keys(keys):
        keys = set(keys)
        for d in walk(j):
            if isinstance(d, dict) and keys.issubset(d.keys()):
                return d
        return None

    cfg = first_dict_with_keys(["Resolution", "BitDepth", "Exposure_ms"])
    if cfg is None:
        for d in walk(j):
            c = d.get("Config") if isinstance(d, dict) else None
            if isinstance(c, dict) and {"Resolution", "BitDepth", "Exposure_ms"}.issubset(c.keys()):
                cfg = c
                break
    if cfg is None:
        raise KeyError(f"{meta_file}: couldn't find Config with Resolution/BitDepth/Exposure_ms")

    res = cfg["Resolution"]
    width = height = None
    if isinstance(res, (list, tuple)) and len(res) >= 2:
        width, height = int(res[0]), int(res[1])
    elif isinstance(res, str):
        s = res.lower().replace(" ", "").replace("x", ",")
        parts = [p for p in s.split(",") if p]
        if len(parts) >= 2:
            width, height = int(parts[0]), int(parts[1])
    elif isinstance(res, dict):
        w = res.get("Width", res.get("width"))
        h = res.get("Height", res.get("height"))
        if w is not None and h is not None:
            width, height = int(w), int(h)

    if width is None or height is None:
        raise ValueError(f"{meta_file}: couldn't parse Resolution={res!r}")

    bit_depth = int(cfg["BitDepth"])
    if bit_depth == 16:
        pixel_type, bytes_per_pixel = "uint16", 2
    elif bit_depth == 8:
        pixel_type, bytes_per_pixel = "uint8", 1
    else:
        raise ValueError(f"Unsupported BitDepth={bit_depth}")

    return {
        "width": int(width),
        "height": int(height),
        "pixel_type": pixel_type,
        "bytes_per_pixel": int(bytes_per_pixel),
        "mirrored_y": False,
    }


def get_n_frames(bin_file: str, width: int, height: int, bytes_per_pixel: int) -> Tuple[int, int]:
    bin_bytes = os.path.getsize(bin_file)
    frame_bytes = width * height * bytes_per_pixel
    if frame_bytes <= 0:
        raise ValueError("Invalid metadata (frame_bytes <= 0).")
    return int(bin_bytes // frame_bytes), int(frame_bytes)


def read_frame_at(fid, *, idx: int, width: int, height: int, dtype, frame_bytes: int, mirrored_y: bool = False):
    fid.seek(idx * frame_bytes, os.SEEK_SET)
    raw = np.fromfile(fid, dtype=dtype, count=width * height)
    if raw.size != width * height:
        raise IOError(f"Unexpected EOF reading frame {idx}")
    frame = raw.reshape((width, height), order="F").T
    if mirrored_y:
        frame = np.flipud(frame)
    return frame.astype(np.float32, copy=False)


def process_one_bin(bin_path: str, cfg: Dict[str, Any]) -> None:
    meta_path = infer_meta_path(bin_path)
    md = read_metadata_json(meta_path)

    W, H = md["width"], md["height"]
    dtype = np.dtype(md["pixel_type"])
    bpp = md["bytes_per_pixel"]
    mirrored_y = md["mirrored_y"]

    T, frame_bytes = get_n_frames(bin_path, W, H, bpp)
    
    

    # --- params ---
    diameter = int(cfg["DETECTION"]["DIAMETER"])
    separation = int(cfg["DETECTION"]["SEPARATION"])
    invert = bool(cfg["DETECTION"]["INVERT"])

    z_q = float(cfg["DETECTION"]["Z_Q"])
    if not (0.0 < z_q < 1.0):
        raise ValueError("DETECTION.Z_Q must be in (0, 1).")

    # Z_Q is the quantile used to set an adaptive threshold (in Z-score units).
    # Example: Z_Q=0.85 means threshold = 85th percentile of fg_z each frame.

    search_range = float(cfg["TRACKING"]["SEARCH_RANGE"])
    memory = int(cfg["TRACKING"]["MEMORY"])
    stub_len = int(cfg["TRACKING"]["STUB_LEN"])

    if cfg["BACKGROUND"]["MODE"] != "chunked_mean":
        raise ValueError("BACKGROUND.MODE must be 'chunked_mean'.")

    chunk_size = int(cfg["BACKGROUND"]["BG_CHUNK_SIZE_FRAMES"])
    if chunk_size <= 0:
        raise ValueError("BACKGROUND.BG_CHUNK_SIZE_FRAMES must be positive.")

    load_chunk = bool(cfg["BACKGROUND"].get("LOAD_CHUNK_TO_RAM", False))
    
    log(f"BIN: {bin_path}")
    log(f"META: {meta_path}")
    log(f"Frames: {T}  |  Chunk size: {chunk_size}  |  Load chunk to RAM: {load_chunk}")

    out_dir = os.path.dirname(os.path.abspath(bin_path))  # same directory as the .bin
    base = os.path.splitext(os.path.basename(bin_path))[0]
    det_csv = os.path.join(out_dir, f"{base}_detections.csv")
    traj_csv = os.path.join(out_dir, f"{base}_trajectories.csv")

    all_feats: List[pd.DataFrame] = []

    n_chunks = (T + chunk_size - 1) // chunk_size
    chunk_idx = 0

    with open(bin_path, "rb") as fid:
        for chunk_start in range(0, T, chunk_size):
            chunk_idx += 1
            chunk_end = min(chunk_start + chunk_size, T)
            K = chunk_end - chunk_start
            
            log(f"Processing chunk {chunk_idx} of {n_chunks} "
            f"(frames {chunk_start}..{chunk_end-1}, K={K})")

            # background compute...
            log("  Computing background...")
            # detection...
            log("  Detecting features...")

            if not load_chunk:
                # ---- low-RAM: streaming mean background, then re-read for detection ----
                acc = np.zeros((H, W), dtype=np.float64)
                for t in range(chunk_start, chunk_end):
                    fr = read_frame_at(fid, idx=t, width=W, height=H, dtype=dtype,
                                       frame_bytes=frame_bytes, mirrored_y=mirrored_y)
                    acc += fr
                bg = (acc / K).astype(np.float32)

                for t in range(chunk_start, chunk_end):
                    fr = read_frame_at(fid, idx=t, width=W, height=H, dtype=dtype,
                                       frame_bytes=frame_bytes, mirrored_y=mirrored_y)

                   work = (fr - bg).astype(float, copy=False)

                    mu = float(work.mean())
                    sig = float(work.std())
                    sig = max(sig, 1e-6)
                    fg_z = (work - mu) / sig

                    thr = float(np.quantile(fg_z, z_q))

                    f = tp.locate(
                        fg_z,
                        diameter=diameter,
                        separation=separation,
                        minmass=0,
                        threshold=thr,
                        invert=invert
                    )
                    f["frame"] = t
                    all_feats.append(f)

            else:
                # ---- faster: load full chunk to RAM once ----
                stack = np.empty((K, H, W), dtype=np.float32)
                for i, t in enumerate(range(chunk_start, chunk_end)):
                    stack[i] = read_frame_at(fid, idx=t, width=W, height=H, dtype=dtype,
                                             frame_bytes=frame_bytes, mirrored_y=mirrored_y)

                bg = stack.mean(axis=0)  # (H, W)

                for i, t in enumerate(range(chunk_start, chunk_end)):
                    fr = stack[i]

                    work = (fr - bg).astype(float, copy=False)

                    mu = float(work.mean())
                    sig = float(work.std())
                    sig = max(sig, 1e-6)
                    fg_z = (work - mu) / sig

                    thr = float(np.quantile(fg_z, z_q))

                    f = tp.locate(
                        fg_z,
                        diameter=diameter,
                        separation=separation,
                        minmass=0,
                        threshold=thr,
                        invert=invert
                    )
                    f["frame"] = t
                    all_feats.append(f)

    features = pd.concat(all_feats, ignore_index=True) if all_feats else pd.DataFrame()
    features.to_csv(det_csv, index=False)

    if len(features) == 0:
        pd.DataFrame().to_csv(traj_csv, index=False)
        return

    tracks0 = tp.link_df(features, search_range=search_range, memory=memory)
    tracks = tp.filter_stubs(tracks0, stub_len).reset_index(drop=True)
    tracks = tracks.sort_values(["particle", "frame"]).reset_index(drop=True)
    tracks.to_csv(traj_csv, index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True, help="Path to .bin file.")
    ap.add_argument("--config", required=True, help="Path to config.yaml.")
    args = ap.parse_args()

    cfg = load_config_yaml(args.config)
    process_one_bin(args.bin, cfg)


if __name__ == "__main__":
    main()
