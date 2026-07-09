# Particle Tracking from `.bin` Files (Trackpy) — Local + SLURM Array

This repository runs Trackpy detection + linking on microscope `.bin` movies with per-movie metadata files.

**Assumptions**
- Each movie is `something.bin`
- Its metadata is `something_meta.json` in the same directory
- Outputs are written **next to the `.bin` file**:
  - `something_detections.csv`
  - `something_trajectories.csv`

---

## Files

- `track_one_bin.py` (or your current script name, e.g. `track_in_BIN.py`)  
  Runs detection + tracking for **one** `.bin` file (ideal for SLURM array jobs).
- `parameters_tr_4x_20fps.yaml`  
  Parameters (with comments) for detection, background, and tracking.
- `trackpy_array.sh`  
  SLURM array job script (one `.bin` per array task).
- `submit.sh`  
  Convenience wrapper: finds all `.bin` files, creates `bin_list.txt`, submits the SLURM array.
- `bin_list.txt`  
  Auto-generated manifest of `.bin` paths (one per line).

---

## Python environment setup (local)

You need Python plus these packages:
- `numpy`
- `pandas`
- `trackpy`
- `pyyaml`

Example install (pip):
```bash
pip install numpy pandas trackpy pyyaml