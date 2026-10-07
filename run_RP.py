import subprocess
import re
import shlex
from pathlib import Path
from datetime import datetime

RP_IP = "192.168.137.111"
RP_USER = "root"
REMOTE_DIR = "/home/jupyter/RedPitaya"

LOCAL_DATA_DIR = Path.home() / "Desktop" / "gitorr" / "RedPitaya" / "data" / "orr"

# scan and laser settings
SAMPLING_RATE = 32000
SCAN_DURATION = 900
CHUNK_SAMPLES = 960000
LASER_POWER = 3        
LASER_WAVELENGTH = 1550  


def main():
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # get laptop time
    start_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    remote_python = (
        "import redPitayaControlDevice as rpc; "
        "folder = rpc.collectData("
        f"sampling_rate_wanted={SAMPLING_RATE}, "
        f"scan_duration={SCAN_DURATION}, "
        f"chunk_samples={CHUNK_SAMPLES}, "
        f"laser_power={LASER_POWER}, "
        f"laser_wavelength={LASER_WAVELENGTH}, "
        f"start_timestamp={start_timestamp!r}"
        "); "
        "print(f'OUTPUT_FOLDER={folder}')"
    )

    ssh_command = ["ssh", f"{RP_USER}@{RP_IP}", (f"cd {REMOTE_DIR} && "f"PYTHONPATH=/opt/redpitaya/lib/python:$PYTHONPATH "f'python3 -u -c "{remote_python}"')]

    print("Starting Red Pitaya acquisition...", flush=True)
    output_folder = None

    with subprocess.Popen(ssh_command, stdout=subprocess.PIPE, text=True, bufsize=1) as process:
        for line in process.stdout:
            print(line, end="", flush=True)
            if line.partition("=")[0].strip() == "OUTPUT_FOLDER":
                output_folder = line.split("=", 1)[1].strip()

        returncode = process.wait()

    if returncode != 0:
        raise SystemExit(returncode)

    if output_folder is None:
        raise RuntimeError("No OUTPUT_FOLDER line was returned by the Red Pitaya.")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_N[1-9]\d*", output_folder) is None:
        raise RuntimeError(f"Unexpected output folder; cleanup skipped: {output_folder!r}")

    remote_folder = f"{REMOTE_DIR}/{output_folder}"

    print(f"Copying {remote_folder} to {LOCAL_DATA_DIR}...")

    subprocess.run(["scp", "-r", f"{RP_USER}@{RP_IP}:{remote_folder}", str(LOCAL_DATA_DIR)], check=True)

    #  delete folder after download
    print(f"Downloaded data to laptop, removing data from the RP")
    try:
        subprocess.run(["ssh", f"{RP_USER}@{RP_IP}", f"rm -r -- {shlex.quote(remote_folder)}"], check=True)
    except subprocess.CalledProcessError:
        print(f"Downloaded data is saved locally at {LOCAL_DATA_DIR / output_folder}.")
        print(f"Remote cleanup failed. Check the remaining files at {remote_folder}.")
        raise

    print("Saved locally to:")
    print(LOCAL_DATA_DIR / Path(output_folder).name)


if __name__ == "__main__":
    main()
