import rp
import time
import h5py, numbers
import numpy as np
from pathlib import Path
from datetime import datetime

class RedPitayaLocalDriver:
    '''Interface for running DAQ scripts locally on a RedPitaya.'''

    DATESTRING_FMT = "%Y%m%d_%H%M%S"

    def check(self, result, operation):
        """Check a status returned by the Red Pitaya API. [AI edit]

        Args:
            result: API status code; success is ``rp.RP_OK``.
            operation: Operation name included in the error message.

        Raises:
            RuntimeError: If the status does not indicate success.
        """
        if result != rp.RP_OK:
            raise RuntimeError(f"{operation} failed:{result}")

    def setParameters(self, sampling_rate_wanted, scan_duration, chunk_samples):
        """Calculate acquisition parameters from the 125 MHz clock. [AI edit]

        Args:
            sampling_rate_wanted: Requested sampling rate in samples per second.
            scan_duration: Requested acquisition duration in seconds.
            chunk_samples: Samples per chunk, rounded down to a multiple of eight.

        Returns:
            dict: Calculated rate, decimation, total samples, chunk count, and
            aligned chunk size, keyed by ``sampling_rate_real``, ``decimation``,
            ``total_samples``, ``needed_chunks``, and ``chunk_samples``.

        Notes:
            Inputs are not validated. Zero divisors can raise ZeroDivisionError.
            The final chunk is acquired in full, so the requested sample count
            may be exceeded.
        """

        ## Getting actual sampling rate from the red pitaya clock
        clock = 125 * 10**6
        decimation = round(clock / sampling_rate_wanted)
        sampling_rate_real = clock / decimation

        ## Samples and chunks which will need to be collected. Note the chunk samples will need to be a multiple of 8
        total_samples = round(scan_duration * sampling_rate_real)

        if total_samples <= chunk_samples:
            total_samples = (total_samples // 8) * 8
            chunk_samples = total_samples
            
        chunk_samples = (chunk_samples // 8) * 8
        needed_chunks = int(np.ceil(total_samples / chunk_samples))

        print("Parameters set:")
        print("Requested sampling rate (Hz):", sampling_rate_wanted)
        print("Actual sampling rate (Hz):", sampling_rate_real)
        print("Decimation:", decimation)
        print("Target sampled duration (s):", scan_duration)
        print("Total samples:", total_samples)
        print("Samples per chunk:", chunk_samples)
        print("Total chunks:", needed_chunks)

        return {
            "sampling_rate_real": sampling_rate_real, 
            "decimation": decimation, 
            "total_samples": total_samples, 
            "needed_chunks": needed_chunks, 
            "chunk_samples": chunk_samples, 
        }

    def collectData(self, sampling_rate_wanted=32000, scan_duration=10, chunk_samples=32000, start_timestamp=None, extra_metadata=None):
        """Acquire channel 1 voltage chunks and save HDF5 files. [AI edit]

        Args:
            sampling_rate_wanted: Requested samples per second (default 32000).
            scan_duration: Requested acquisition duration in seconds (default 10).
            chunk_samples: Samples per file, aligned down to a multiple of eight.
            start_timestamp: Optional timestamp in ``DATESTRING_FMT`` format;
                defaults to the device's current local time.
            extra_metadata: Optional mapping of additional HDF5 attributes with
                scalar numeric or string values.

        Returns:
            pathlib.Path: Relative run directory named ``<timestamp>_N<chunks>``.

        Raises:
            RuntimeError: If a checked hardware operation fails.
            ValueError: If the supplied timestamp cannot be parsed.
            TimeoutError: If a chunk buffer does not fill within its expected
                sampling duration plus ten seconds.

        Notes:
            Requires the device's ``rp`` bindings and channel 1's physical jumper
            set to the high-voltage range. Files contain a ``Voltage (V)`` dataset
            and acquisition attributes. Acquisition is stopped and the API is
            released in the acquisition block's finally clause.
        """

        ## Set the parameters and determine the real parameters
        real_params = self.setParameters(sampling_rate_wanted, scan_duration, chunk_samples)
        sampling_rate_real = real_params["sampling_rate_real"]
        decimation = real_params["decimation"]
        total_samples = real_params["total_samples"]
        needed_chunks = real_params["needed_chunks"]
        chunk_samples = real_params["chunk_samples"]

        ## Set up folder
        if start_timestamp is None:
            start_time = datetime.now()
        else:
            start_time = datetime.strptime(start_timestamp, self.DATESTRING_FMT)
        run_folder = Path(f"{start_time.strftime(self.DATESTRING_FMT)}_N{needed_chunks}")
        run_folder.mkdir(exist_ok = True)

        ## Connect to the RedPitaya
        self.check(rp.rp_Init(), "rp_Init")
        print("Connected")

        ## Try to do the acquisition
        try:
            ## Prepare circular memory
            self.check(rp.rp_AcqSetGain(rp.RP_CH_1, rp.RP_LOW), "rp_AcqSetGain")
            get_memory = rp.rp_AcqAxiGetMemoryRegion()
            self.check(get_memory[0], "rp_AcqAxiGetMemoryRegion")
            memory_start = get_memory[1]

            samples_collected = 0
            chunk_number = 0

            while samples_collected < total_samples:
                time_start = time.monotonic()
                
                chunk_number += 1
                print(f"Collecting chunk {chunk_number}")

                ## Set up acquisition
                self.check(rp.rp_AcqReset(), "rp_AcqReset")
                self.check(rp.rp_AcqSetGain(rp.RP_CH_1, rp.RP_LOW), "rp_AcqSetGain") #added line to set gain after reset
                self.check(rp.rp_AcqAxiSetDecimationFactor(decimation), "rp_AcqAxiSetDecimationFactor")
                self.check(rp.rp_AcqAxiSetTriggerDelay(rp.RP_CH_1, chunk_samples), "rp_AcqAxiSetTriggerDelay")
                self.check(rp.rp_AcqAxiSetBufferSamples(rp.RP_CH_1, memory_start, chunk_samples), "rp_AcqAxiSetBufferSamples")
                self.check(rp.rp_AcqAxiEnable(rp.RP_CH_1, True), "rp_AcqAxiEnable")

                ## Acquisition
                self.check(rp.rp_AcqStart(), "rp_AcqStart")
                self.check(rp.rp_AcqSetTriggerSrc(rp.RP_TRIG_SRC_NOW), "rp_AcqSetTriggerSrc")

                # Allow the expected acquisition time plus a margin.
                timeout_sec = chunk_samples / sampling_rate_real + 15.0
                deadline = time.monotonic() + timeout_sec
                
                while True:
                    buffer_fill = rp.rp_AcqAxiGetBufferFillState(rp.RP_CH_1)
                    self.check(buffer_fill[0], "rp_AcqAxiGetBufferFillState")

                    if buffer_fill[1]:
                        break

                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"Chunk {chunk_number}: buffer did not fill "
                            f"within {timeout_sec:.1f} seconds"
                        )

                    time.sleep(0.001)

                self.check(rp.rp_AcqStop(), "rp_AcqStop")

                time_save = time.monotonic()
                
                # move buffer data into data file
                memory_end = rp.rp_AcqAxiGetWritePointerAtTrig(rp.RP_CH_1)
                self.check(memory_end[0], "rp_AcqAxiGetWritePointerAtTrig")
                voltage_data = rp.fBuffer(chunk_samples)
                data_result = rp.rp_AcqAxiGetDataV(rp.RP_CH_1, memory_end[1], chunk_samples, voltage_data)
                self.check(data_result[0], "rp_AcqAxiGetDataV")

                output = run_folder / (f"{start_time.strftime(self.DATESTRING_FMT)}_chunk{chunk_number}_of{needed_chunks}.h5")

                with h5py.File(output, "w") as f:
                    dataset = f.create_dataset("Voltage (V)", data = np.array([voltage_data[i] for i in range(chunk_samples)]))

                    ## Store the DAQ metadata
                    f.attrs["date"] = start_time.strftime(self.DATESTRING_FMT)
                    f.attrs["total_samples"] = total_samples
                    f.attrs["chunk_samples"] = chunk_samples
                    f.attrs["total_chunks"] = needed_chunks
                    f.attrs["current_chunk"] = chunk_number
                    f.attrs["scan_duration"] = scan_duration
                    f.attrs["sampling_rate"] = sampling_rate_real
                    f.attrs["decimation"] = decimation

                    ## Store arbitrary metadata
                    if extra_metadata is None: extra_metadata = {}
                    for k,v in extra_metadata.items():
                        if isinstance(v, numbers.Number) or isinstance(v, str):
                            f.attrs[k] = v
                        else:
                            print(f"Bad metadata: {k} is not a scalar number or string")
                    # f.attrs["laser_power"] = laser_power
                    # f.attrs["laser_wavelength"] = laser_wavelength

                print(f"Saved {output}")

                samples_collected += chunk_samples

                self.check(rp.rp_AcqAxiEnable(rp.RP_CH_1, False), "rp_AcqAxiEnable(False)")

                time_end = time.monotonic()
                print(f"Time for chunk to acquire: {time_save - time_start}")
                print(f"Time for chunk to save: {time_end - time_save}")
                print(f"Time for chunk total: {time_end - time_start}")

        ## Release hardware after done collecting
        finally:
            try:
                rp.rp_AcqStop()
            except Exception:
                pass

            try:
                rp.rp_AcqAxiEnable(rp.RP_CH_1, False)
            except Exception:
                pass

            rp.rp_Release()
            print("Red Pitaya released")

        return run_folder
