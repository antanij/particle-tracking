# Particle Tracking Workflow (BIN)

This repository contains scripts and configuration files for running particle tracking locally or on an HPC cluster using SLURM array jobs.

## Files

- track_in_BIN.py
  - Main tracking script (runs one dataset/experiment per invocation depending on your arguments).
- parameters_tr_4x_20fps.yaml
  - YAML configuration for tracking parameters.
- submit_all_BIN_jobs.sh
  - Convenience wrapper to submit SLURM jobs (typically calls sbatch on the array script).
- trackpy_array.sh
  - SLURM array job script to run many tracking tasks across a job array.

## Prerequisites

- Python 3 environment with required dependencies installed for track_in_BIN.py.
- Access to a SLURM cluster for array runs.

## Local run

Adjust paths and arguments as needed for your data layout. The command below uses the provided YAML parameters file.

Example:
```bash
python track_in_BIN.py --bin "/path/to/something.bin" --config parameters_tr_4x_20fps.yaml
```

If your script expects different arguments (for example input/output paths), adapt accordingly:
```bash
python track_in_BIN.py --params parameters_tr_4x_20fps.yaml --input /path/to/input --output /path/to/output
```

## SLURM array run

### 1) Edit trackpy_array.sh

- Set SBATCH directives (partition, time, memory, etc.).
- Ensure the script loads the correct modules / activates the correct environment.
- Ensure the script calls:
  - track_in_BIN.py
  - parameters_tr_4x_20fps.yaml
- Ensure the array task id is used to select which input/job to run (commonly via $SLURM_ARRAY_TASK_ID).

### 2) Submit the array

Submit directly:
```bash
sbatch trackpy_array.sh
```

Or submit via the wrapper (if it is set up to do so):
```bash
bash submit_all_BIN_jobs.sh
```

### 3) Typical array sizing

If you have N independent inputs/jobs, configure the array range in trackpy_array.sh, for example:
```bash
#SBATCH --array=0-99
```

Then in your array script, map each task id to one dataset. Common approaches:
- Read the Nth line from a text file list of inputs using $SLURM_ARRAY_TASK_ID
- Use a fixed naming pattern derived from $SLURM_ARRAY_TASK_ID

## Outputs

- Outputs depend on track_in_BIN.py and the parameters in parameters_tr_4x_20fps.yaml.
- Check your SLURM stdout/stderr logs for progress and errors.

## Notes

- Keep parameters_tr_4x_20fps.yaml under version control so runs are reproducible.
- If you change the CLI of track_in_BIN.py, update both local and SLURM run commands accordingly.
