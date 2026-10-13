import os, argparse
import subprocess
import re, shlex
from pathlib import Path, PurePosixPath
from datetime import datetime

class RedPitayaRemoteInterface:
    '''Interface for calling DAQ scripts from a local machine to a remote RedPitaya.'''

    SAMPLING_RATE_SPS = 32000    ## Default: 32 ksps; can be overwritten via CLI could probably go higher?
    SCAN_DURATION_S   = 900      ## Default: 900 sec; can be overwritten via CLI 
    CHUNK_SAMPLES     = 960000   ## Maximum RP buffer size, do not increase
    LASER_POWER_MW    = 3.0      ## Default: 3 mW (setpoint); user supplied via CLI (not used elsewhere than metadata)
    LASER_WAVELENGTH_NM = 1550   ## Default: 1550 nm (setpoint); user supplied via CLI (not used elsewhere than metadata)

    DATESTRING_FMT = "%Y%m%d_%H%M%S"

    def __init__(self, ip="192.168.137.111", local_dir="rp_data"):
        """Configure the remote connection and local data destination. [AI generated] [AI edit]

        Args:
            ip: Device IP address, default ``192.168.137.111``.
            local_dir: Local download directory, default ``rp_data``.

        Notes:
            Uses SSH user ``root`` and remote directory
            ``/home/jupyter/RedPitaya``; no connection is opened here.
        """
        ## Define the connection / local details for Red Pitaya
        self.RP_USER = "root"
        self.RP_WORKDIR = PurePosixPath("/home/jupyter/RedPitaya") ## always needs to resolve as UNIX path for RP
        self.RP_IP = ip

        ## Define where we will duplicate DAQ data on local machine
        self.LOCAL_DATA_DIR = Path(local_dir)

    def update_laser_params(self, power_mW=None, wavelength_nm=None):
        """Update laser setpoints used as acquisition metadata. [AI generated] [AI edit]

        Args:
            power_mW: Power in milliwatts, converted to float when supplied.
            wavelength_nm: Wavelength in nanometers, converted to float when
                supplied. ``None`` leaves each corresponding value unchanged.

        Notes:
            These values do not control laser hardware and are not range-checked.
        """
        if power_mW is not None:
            print("Updating LASER_POWER_MW to",power_mW,"mW")
            self.LASER_POWER_MW = float(power_mW)
        if wavelength_nm is not None:
            print("Updating LASER_WAVELENGTH_NM to",wavelength_nm,"nm")
            self.LASER_WAVELENGTH_NM = float(wavelength_nm)

    def update_local_datadir(self, local_folder):
        """Set the destination directory for future downloads. [AI generated] [AI edit]

        Args:
            local_folder: Path-like destination; created later during copying.
        """
        print("Updating LOCAL_DATA_DIR to",local_folder)
        self.LOCAL_DATA_DIR = Path(local_folder)

    def run_acquisition(self, sampling_rate_sps=None, scan_duration_sec=None):
        """Launch a device acquisition over SSH and stream its output. [AI generated] [AI edit]

        Args:
            sampling_rate_sps: Optional samples-per-second override, stored as float.
            scan_duration_sec: Optional duration override in seconds, stored as float.

        Returns:
            tuple[str, float]: Remote output directory name and elapsed
            SSH acquisition time in seconds, including startup overhead.

        Raises:
            SystemExit: If the remote command exits with a nonzero status.
            RuntimeError: If the remote output does not identify its output folder.

        Notes:
            Requires SSH authentication and the package installed on the device.
            The returned folder name is validated before it is returned.
        """
        ## Update parameters if provided
        if sampling_rate_sps is not None:
            print("Updating SAMPLING_RATE_SPS to",sampling_rate_sps,"sps")
            self.SAMPLING_RATE_SPS = float(sampling_rate_sps)
        if scan_duration_sec is not None:
            print("Updating SCAN_DURATION_S to",scan_duration_sec,"sec")
            self.SCAN_DURATION_S = float(scan_duration_sec)

        ## Get the current timestamp
        start_timestamp  = datetime.now()
        start_timestring = start_timestamp.strftime(self.DATESTRING_FMT)

        ## Write the python script we need to execute on the RP
        remote_python = (
            #"from RedPitayaLocalDriver import RedPitayaLocalDriver; "
            "from RedPitayaDAQ.RedPitayaLocalDriver import RedPitayaLocalDriver; "
            "rpc = RedPitayaLocalDriver(); "
            "folder = rpc.collectData("
            f"sampling_rate_wanted={self.SAMPLING_RATE_SPS}, "
            f"scan_duration={self.SCAN_DURATION_S}, "
            f"chunk_samples={self.CHUNK_SAMPLES}, "
            f"start_timestamp={start_timestring!r}, "
            "extra_metadata={"
            f"'laser_power': {self.LASER_POWER_MW}, "
            f"'laser_wavelength': {self.LASER_WAVELENGTH_NM}, "
            "}); "
            "print(f'OUTPUT_FOLDER={folder}')"
        )

        ## Run the following set of commands over SSH connection as root
        ssh_command = [
            "ssh", 
            f"{self.RP_USER}@{self.RP_IP}", 
            (f"cd {self.RP_WORKDIR} && "f"PYTHONPATH=/opt/redpitaya/lib/python:$PYTHONPATH "f'python3 -u -c "{remote_python}"')]

        print("Starting Red Pitaya acquisition...", flush=True)
        remote_output_folder = None

        ## Run and time the execution of the DAQ script (can be used to infer deadtime)
        daq_start_ts = datetime.now()
        with subprocess.Popen(ssh_command, stdout=subprocess.PIPE, text=True, bufsize=1) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
                if line.partition("=")[0].strip() == "OUTPUT_FOLDER":
                    remote_output_folder = line.split("=", 1)[1].strip()

            returncode = process.wait()
        daq_end_ts = datetime.now()
        daq_duration_sec = (daq_end_ts-daq_start_ts).total_seconds()

        if returncode != 0:
            raise SystemExit(returncode)

        if remote_output_folder is None:
            raise RuntimeError("No OUTPUT_FOLDER line was returned by the Red Pitaya.")

        ## By default, this expects the default datestring format: "%Y%m%d_%H%M%S"
        if re.fullmatch(r"\d{4}\d{2}\d{2}_\d{2}\d{2}\d{2}_N[1-9]\d*", remote_output_folder) is None:
            raise RuntimeError(f"Unexpected output folder; cleanup skipped: {remote_output_folder!r}")

        return remote_output_folder, daq_duration_sec

    def copy_last_acquisition(self, remote_output_folder, local_folder_override=None, remove=True):
        """Download a remote run directory using SCP. [AI generated] [AI edit]

        Args:
            remote_output_folder: Run directory name relative to ``RP_WORKDIR``.
            local_folder_override: Optional alternative download destination.
            remove: Whether to delete the remote directory after successful SCP;
                defaults to True.

        Returns:
            pathlib.Path: Local path of the downloaded run directory.

        Raises:
            subprocess.CalledProcessError: If SCP or remote cleanup fails.

        Notes:
            Remote cleanup is destructive. Supply a trusted run directory name.
        """
        ## Define where the data lives on the RP (ensure UNIX path)
        remote_folder = self.RP_WORKDIR / remote_output_folder

        ## Send to a different local folder than one in class scope, if forced
        if local_folder_override is not None:
            local_output_path = Path(local_folder_override)
        else:
            local_output_path = self.LOCAL_DATA_DIR

        ## Now we have parent level (destination) local directory for saving data
        ## create it if it doesn't exist
        if not local_output_path.exists():
            local_output_path.mkdir(parents=True, exist_ok=True) 

        ## Run the data transfer command via SCP
        print(f"Copying {remote_folder} to {local_output_path}...")
        subprocess.run([ "scp", 
                         "-r", 
                         f"{self.RP_USER}@{self.RP_IP}:{remote_folder}", 
                         str(local_output_path)
                       ], check=True)
        print("Done. Downloaded data to local host.")
        local_data_path = local_output_path / remote_output_folder
        print(f"Downloaded data is saved locally at {local_data_path}.")

        ## Delete folder after download
        if remove:
            print(f"Removing data from the RP...")
            try:
                subprocess.run([ "ssh", 
                                f"{self.RP_USER}@{self.RP_IP}", 
                                f"rm -r -- {shlex.quote(str(remote_folder))}"
                            ], check=True)
            except subprocess.CalledProcessError:
                print(f"Remote cleanup failed. Check the remaining files at {remote_folder}.")
                raise 

        return local_data_path

def parse_cli_args():
    """Parse acquisition options from the process command line. [AI generated] [AI edit]

    Returns:
        argparse.Namespace: ``ip``, ``outdir``, ``samprate``, ``duration``,
        ``laserpower``, and ``laserwavelen`` options. Invalid checked values
        are replaced with class defaults and a message is printed.

    Raises:
        SystemExit: For help output or invalid argparse syntax.

    Notes:
        Checks IPv4 syntax, sampling rates in (0, 100000] samples per second,
        duration in (0, 3600] seconds, power in [0, 17] mW, and wavelength
        in [1520, 1570] nm.
    """
    ## Initialize the parser wrapper
    parser = argparse.ArgumentParser(description="Run a DAQ script from a local machine on a remote RedPitaya.")

    ## Create a blank instance of the local interface class from which to pull default parameters
    blank = RedPitayaRemoteInterface()

    ## Command-line arguments for basic configuration
    parser.add_argument('--ip',             '-i', type=str, default=blank.RP_IP,
                        help=f'IP address of Red Pitaya. Default: {blank.RP_IP}')
    parser.add_argument('--outdir',         '-o', type=str, default=str(blank.LOCAL_DATA_DIR),
                        help=f'IP address of Red Pitaya. Default: {blank.LOCAL_DATA_DIR}')

    ## Command-line arguments for DAQ configuration
    parser.add_argument('--samprate',       '-r', type=int, default=blank.SAMPLING_RATE_SPS,
                        help=f'Sampling rate specified in samples per second. Default: {blank.SAMPLING_RATE_SPS}')
    parser.add_argument('--duration',       '-d', type=float, default=blank.SCAN_DURATION_S,
                        help=f'Total duration of the acquisition specified in seconds. Default: {blank.SCAN_DURATION_S}')

    ## Command-line arguments for laser setpoints
    parser.add_argument('--laserpower',     '-l', type=float, default=blank.LASER_POWER_MW,
                        help=f'Power setpoint of laser specified in mW. Default: {blank.LASER_POWER_MW}')
    parser.add_argument('--laserwavelen',   '-w', type=float, default=blank.LASER_WAVELENGTH_NM,
                        help=f'Wavelength setpoint of laser specified in nm. Default: {blank.LASER_WAVELENGTH_NM}')

    ## Process inputs into an object namespace, then validate
    args = parser.parse_args()

    ## Validate arguments for basic configuration
    valid_ip = re.match(r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)$", args.ip) is not None
    if not valid_ip: 
        print(f"Invalid IP: {args.ip}. Using default: {blank.RP_IP}")
        args.ip = blank.RP_IP

    ## Validate arguments for DAQ configuration
    valid_samprate = (args.samprate > 0) and (args.samprate <= int(1e5)) 
    if not valid_samprate: 
        print(f"Invalid sampling rate: {args.samprate} sps (Maximum is 100 ksps). Using default: {blank.SAMPLING_RATE_SPS} sps")
        args.samprate = blank.SAMPLING_RATE_SPS

    valid_duration = (args.duration > 0) and (args.duration <= 3600) 
    if not valid_duration: 
        print(f"Invalid DAQ duration: {args.duration} sec (Maximum is 1 hour). Using default: {blank.SCAN_DURATION_S} sec")
        args.duration = blank.SCAN_DURATION_S

    ## Validate arguments for laser setpoints
    valid_laserpower = (args.laserpower >= 0.0) and (args.laserpower <= 17.0) 
    if not valid_laserpower: 
        print(f"Invalid laser power setpoint: {args.laserpower} mW (Maximunm: 17 mW). Using default: {blank.LASER_POWER_MW} mW")
        args.laserpower = blank.LASER_POWER_MW

    valid_laserwavelen = (args.laserwavelen >= 1520.0) and (args.laserwavelen <= 1570.0) 
    if not valid_laserwavelen: 
        print(f"Invalid laser wavelength setpoint: {args.laserpower} nm (1520-1570 allowed). Using default: {blank.LASER_WAVELENGTH_NM} nm")
        args.laserwavelen = blank.LASER_WAVELENGTH_NM

    ## Delete blank class instance, return validated arguments
    del blank
    return args

def run_full_daq():
    """Run the command-line acquisition and download workflow. [AI generated] [AI edit]

    Notes:
        Parses options, sets laser metadata, starts acquisition, and requests
        download with remote deletion using the returned acquisition folder.
    """
    ## Parse the command line arguments
    args = parse_cli_args()

    ## Update the metadata with the command line arguments
    rp = RedPitayaRemoteInterface(ip=args.ip, local_dir=args.outdir)
    rp.update_laser_params(power_mW=args.laserpower, wavelength_nm=args.laserwavelen)

    ## Run acquisition and copy the data locally
    remote_output_dir, daq_duration_sec = rp.run_acquisition(
        sampling_rate_sps=args.samprate, 
        scan_duration_sec=args.duration
    )
    local_output_dir  = rp.copy_last_acquisition(remote_output_dir, remove=True)

    print("Done.")

if __name__ == "__main__":
    run_full_daq()
