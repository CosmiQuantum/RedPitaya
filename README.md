# RedPitayaDAQ

Python interfaces for collecting channel 1 voltage data on a Red Pitaya and
launching acquisitions from a host computer over SSH. The installable package
contains only `src/RedPitayaDAQ`.

**Status:** packaging and imports are supported, but the existing acquisition
workflow has runtime defects described below. Hardware acquisition has not been
validated. The examples describe the API and require those defects to be fixed
before a complete acquisition can succeed.

## Installation

From the repository root, with Python 3.9 or newer:

```sh
python -m pip install .
```

For editable development, use `python -m pip install -e .`.
NumPy and h5py are declared dependencies. The local driver additionally requires
the Red Pitaya vendor `rp` Python bindings, supplied by the device environment;
they are not installed from PyPI by this package. The remote interface uses
system `ssh` and `scp` executables and requires working SSH authentication.

```python
from RedPitayaDAQ import RedPitayaRemoteInterface

remote = RedPitayaRemoteInterface(ip="192.168.137.111", local_dir="rp_data")
remote.update_laser_params(power_mW=3.0, wavelength_nm=1550)
```

The package root does not import `rp`. On the device, import the driver explicitly:

```python
from RedPitayaDAQ.RedPitayaLocalDriver import RedPitayaLocalDriver

driver = RedPitayaLocalDriver()
```

## Local acquisition API

`RedPitayaLocalDriver` runs on the device. Channel 1's physical jumper must be set
to the high-voltage range. Its methods are:

| Method | Purpose |
| --- | --- |
| `check(result, operation)` | Raise `RuntimeError` when an API status differs from `rp.RP_OK`. |
| `setParameters(sampling_rate_wanted, scan_duration, chunk_samples)` | Derive decimation and rate from a 125 MHz clock, align chunks down to eight samples, and calculate sample/chunk counts. |
| `collectData(sampling_rate_wanted=32000, scan_duration=10, chunk_samples=32000, start_timestamp=None, extra_metadata={})` | Acquire voltage chunks, write HDF5 files, and return a relative `Path` to the run directory. |

Sampling rates are in samples per second and durations in seconds. The actual
rate is `125000000 / round(125000000 / requested_rate)`. Inputs are not validated;
use positive rates and durations and chunk sizes of at least eight samples within
the device's buffer capacity. The final chunk is collected in full, so the run
may contain more samples than requested. Acquisition occurs in separate chunks,
with setup and file-writing time between them.

`start_timestamp` uses `%Y%m%d_%H%M%S`; when omitted, the device's local time is
used. Data is written relative to the working directory:

```text
<timestamp>_N<total_chunks>/
    <timestamp>_chunk1_of<total_chunks>.h5
    ...
```

Each file contains a one-dimensional `Voltage (V)` dataset and file attributes:
`date`, `total_samples`, `chunk_samples`, `total_chunks`, `current_chunk`,
`scan_duration`, `sampling_rate`, and `decimation`. Additional metadata is intended
to accept scalar numbers and strings. Hardware stop, AXI disable, and release are
attempted when leaving the acquisition block.

## Remote acquisition API

`RedPitayaRemoteInterface(ip="192.168.137.111", local_dir="rp_data")` defaults to
SSH user `root` and device working directory `/home/jupyter/RedPitaya`. These are
stored in `RP_USER` and `RP_WORKDIR`; the latter is a `PurePosixPath`.

| Method | Purpose |
| --- | --- |
| `update_laser_params(power_mW=None, wavelength_nm=None)` | Set metadata values; does not control a laser. |
| `update_local_datadir(local_folder)` | Change the download destination. |
| `run_acquisition(sampling_rate_sps=None, scan_duration_sec=None)` | Launch the device command, stream stdout, and intend to return `(remote_folder, elapsed_seconds)`. Supplied overrides persist on the instance. |
| `copy_last_acquisition(remote_output_folder, local_folder_override=None, remove=True)` | Recursively copy a run using SCP and return its local `Path`. By default, delete the remote run after successful copying. |

Defaults are 32,000 samples/s, 900 seconds, 960,000 samples per chunk, and laser
metadata of 3 mW and 1550 nm. Elapsed time includes the SSH command's startup and
execution overhead. Supply trusted run directory names to the copy method and
use `remove=False` to retain data on the device.

The current remote command imports `RedPitayaLocalDriver` as a top-level module.
It expects `RedPitayaLocalDriver.py` in its device working directory (or otherwise
on `PYTHONPATH`), plus vendor bindings at `/opt/redpitaya/lib/python`. Installing
the package alone on the device does not satisfy that top-level import.

## Command-line interface

The remote module can be invoked with:

```sh
python -m RedPitayaDAQ --help
```

The remote module provides `parse_cli_args()` and `run_full_daq()`; the latter
starts acquisition and downloads with remote deletion.

| Option | Short | Default | Intended validation |
| --- | --- | --- | --- |
| `--ip` | `-i` | `192.168.137.111` | IPv4 address |
| `--outdir` | `-o` | `rp_data` | Local destination |
| `--samprate` | `-r` | `32000` | Integer in (0, 100000] samples/s |
| `--duration` | `-d` | `900` | (0, 3600] seconds; currently defective |
| `--laserpower` | `-l` | `3.0` | [0, 17] mW |
| `--laserwavelen` | `-w` | `1550` | [1520, 1570] nm |

Checked invalid values produce messages and fall back to defaults. These CLI
checks do not apply to direct method calls.

## Existing acquisition limitations

The documentation and packaging changes preserve the original runtime logic:

- `setParameters` returns numeric keys mapped to parameter names, while
  `collectData` looks up string keys, causing `KeyError` before initialization.
- Additional metadata iteration does not use `.items()`, and assignment refers
  to undefined `f_attrs`.
- The generated remote command uses undefined names for its metadata keys.
  Folder validation and return also use undefined `output_folder`.
- The local destination override refers to undefined `local_folder`. Remote
  cleanup passes a `PurePosixPath` to `shlex.quote`; its exception handler also
  constructs `CalledProcessError` without required arguments.
- Duration validation checks the sampling-rate flag. `run_full_daq` passes an
  acquisition result tuple as the folder argument instead of unpacking it.

## Repository layout

`src/RedPitayaDAQ` contains the packaged interfaces. `legacy/` holds earlier
laptop/device control and runner scripts. `tools/` contains reconstruction
algorithms and a data-checking notebook. Neither directory is installed as part
of the package.

Function and method docstrings added in this documentation pass carry
`[AI generated]`; revised existing method docstrings carry `[AI edit]`.
