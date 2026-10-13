# RedPitayaDAQ

Python interfaces for collecting channel 1 voltage data on a Red Pitaya and
launching acquisitions from a host computer over SSH. The installable package
contains only `src/RedPitayaDAQ`.

Hardware acquisition has not been validated in this environment.

## Installation

From the repository root, with Python 3.9 or newer:

```sh
python -m pip install .
```

For editable development, use `python -m pip install -e .`.
NumPy, h5py, Matplotlib, and SciPy are declared dependencies.
The package also imports the external `recon_algorithms` module, which must be
available on `PYTHONPATH`; it is not yet supplied by this package. The local driver additionally requires
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
| `collectData(sampling_rate_wanted=32000, scan_duration=10, chunk_samples=32000, start_timestamp=None, extra_metadata=None)` | Acquire voltage chunks, write HDF5 files, and return a relative `Path` to the run directory. |

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
`scan_duration`, `sampling_rate`, and `decimation`. Additional metadata accepts
scalar numbers and strings. Hardware stop, AXI disable, and release are attempted when leaving the
acquisition block.

Each chunk has a buffer-fill timeout equal to its expected sampling duration plus
10 seconds. A timeout raises `TimeoutError` and runs the hardware cleanup block.
Buffer status is polled with a 1 ms sleep between unsuccessful checks.

## Remote acquisition API

`RedPitayaRemoteInterface(ip="192.168.137.111", local_dir="rp_data")` defaults to
SSH user `root` and device working directory `/home/jupyter/RedPitaya`. These are
stored in `RP_USER` and `RP_WORKDIR`; the latter is a `PurePosixPath`.

| Method | Purpose |
| --- | --- |
| `update_laser_params(power_mW=None, wavelength_nm=None)` | Set metadata values; does not control a laser. |
| `update_local_datadir(local_folder)` | Change the download destination. |
| `run_acquisition(sampling_rate_sps=None, scan_duration_sec=None)` | Launch the device command, stream stdout, and return `(remote_folder, elapsed_seconds)`. Supplied overrides persist on the instance. |
| `copy_last_acquisition(remote_output_folder, local_folder_override=None, remove=True)` | Recursively copy a run using SCP and return its local `Path`. By default, delete the remote run after successful copying. |

Defaults are 32,000 samples/s, 900 seconds, 960,000 samples per chunk, and laser
metadata of 3 mW and 1550 nm. Elapsed time includes the SSH command's startup and
execution overhead. Supply trusted run directory names to the copy method and
use `remove=False` to retain data on the device.

The remote command imports
`RedPitayaDAQ.RedPitayaLocalDriver.RedPitayaLocalDriver`. Install the package in
the device's `python3` environment and ensure its dependencies, including the
external `recon_algorithms` module, are available. The command adds
`/opt/redpitaya/lib/python` to `PYTHONPATH` for the vendor bindings.

## Command-line interface

The remote module can be invoked with:

```sh
python -m RedPitayaDAQ --help
```

The remote module provides `parse_cli_args()` and `run_full_daq()`; the latter
starts acquisition and downloads with remote deletion.

| Option | Short | Default | Validation |
| --- | --- | --- | --- |
| `--ip` | `-i` | `192.168.137.111` | IPv4 address |
| `--outdir` | `-o` | `rp_data` | Local destination |
| `--samprate` | `-r` | `32000` | Integer in (0, 100000] samples/s |
| `--duration` | `-d` | `900` | (0, 3600] seconds |
| `--laserpower` | `-l` | `3.0` | [0, 17] mW |
| `--laserwavelen` | `-w` | `1550` | [1520, 1570] nm |

Checked invalid values produce messages and fall back to defaults. These CLI
checks do not apply to direct method calls.

## Repository layout

`src/RedPitayaDAQ` contains the packaged interfaces. `legacy/` holds earlier
laptop/device control and runner scripts. `tools/` contains reconstruction
algorithms and a data-checking notebook. Neither directory is installed as part
of the package.

Function and method docstrings added in this documentation pass carry
`[AI generated]`; revised existing method docstrings carry `[AI edit]`.
