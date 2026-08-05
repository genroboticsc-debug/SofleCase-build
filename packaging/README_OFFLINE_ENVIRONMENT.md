# DracuLad Kailh Complete Offline Handoff

This bundle preserves the full current task state. It contains:

- a complete Git branch snapshot;
- every current Kailh reverse-engineering and validation script;
- the pinned independent STEP reference and SHA-256 record;
- generated STEP/STL candidates, analysis models, logs and validation reports;
- Linux CPython 3.13 and Windows CPython 3.12 dependency wheelhouses;
- the `cadquery-ocp` wheel that supplies the OpenCascade/OCP CAD kernel;
- the official Windows CPython 3.12.10 embeddable distribution;
- `get-pip.py` and the Microsoft Visual C++ x64 runtime installer;
- exact package locks, `pip freeze`, `pip inspect`, OS/Python information;
- offline setup scripts and SHA-256 checksums for every packaged file.

## Windows offline setup

Open PowerShell in `environment` and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_offline_windows.ps1
```

The script uses the bundled Python and wheelhouse. It does not contact PyPI.

## Linux offline setup

Install CPython 3.13 with `venv` support, then run:

```bash
chmod +x setup_offline_linux.sh
./setup_offline_linux.sh
```

## Rebuild and validation

The current scripts are under `workspace/draculad_kailh`. The exact reference is under `reference`. Each attempted build has its own folder under `runtime_results`, including console output, exit code, produced CAD files and independent validation output when a candidate was produced.

`MASTER_STATUS.json` is the authoritative index. A failed experimental candidate is retained with its evidence; it is not silently omitted or represented as passing.
