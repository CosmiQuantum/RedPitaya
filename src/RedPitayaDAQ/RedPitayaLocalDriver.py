import rp
import h5py, numbers
import numpy as np
from pathlib import Path
from datetime import datetime

class RedPitayaLocalDriver:
    '''Interface for running DAQ scripts locally on a RedPitaya.'''

    DATESTRING_FMT = "%Y%m%d_%H%M%S"

    def check(self, result, operation):
        '''
        Checks if a hardware command has gone through
        Arguments
        - result:                   red pitaya will either return 0 or rp.ok if the command has worked
        - operation:                command you are sending
        Returns
        - If red pitaya confirms the command went through, then nothing is returned. Otherwise it will raise an error
        '''
        if result != rp.RP_OK:
            raise RuntimeError(f"{operation} failed:{result}")

    def setParameters(self, sampling_rate_wanted, scan_duration, chunk_samples):
        '''
        Sets parameters for data acquisition
        Arguments
        - sampling_rate_wanted:     frequency you want to sample in. Due to decimation, it will be slightly different
        - scan_duration:            time of scan in seconds
        - chunk_samples:            amount of samples to load into memory at once before saving that chunk
        Returns
        - sampling_rate_real:       actual rate at which the sampling will occur
        - decimation:               the red pitaya clock will sample at its own rate, decimation divides the clock to get effective sampling rate as we want
        - total_samples:            total samples that will need to be collected for the run
        - needed_chunks:            how many separate files will be needed for the total run
        '''

        ## Getting actual sampling rate from the red pitaya clock
        clock = 125 * 10**6
        decimation = round(clock / sampling_rate_wanted)
        sampling_rate_real = clock / decimation

        ## Samples and chunks which will need to be collected. Note the chunk samples will need to be a multiple of 8
        total_samples = round(scan_duration * sampling_rate_real)
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
            sampling_rate_real: "sampling_rate_real", 
            decimation: "decimation", 
            total_samples: "total_samples", 
            needed_chunks: "needed_chunks", 
            chunk_samples: "chunk_samples", 
        }

    def collectData(self, sampling_rate_wanted=32000, scan_duration=10, chunk_samples=32000, start_timestamp=None, extra_metadata={}):
        '''
        Collects data for a period of time at wanted sampling rate. Importantly, this is for input 1 with the physical limiter set to high voltage
        Arguments
        - sampling_rate_wanted:     frequency you want to sample in. Due to decimation, it will be slightly different
        - scan_duration:            time of scan in seconds
        - chunk_samples:            amount of samples to load into memory at once before saving that chunk
        - laser_power:              laser power in milliwatts
        - laser_wavelength:         laser wavelength in nanometers
        - start_timestamp:          laptop time
        Returns
        - run_folder:               the folder in which data is saved
        '''

        ## Set the parameters and determine the real parameters
        real_params = self.setParameters(sampling_rate_wanted, scan_duration, chunk_samples)
        sampling_rate_real = real_params["sampling_rate_real"]
        decimation = real_params["decimation"]
        total_samples = real_params["total_samples"]
        needed_chunks = real_params["needed_chunks"]
        chunk_samples = real_params["chunk_samples"]

        ## Connect to the RedPitaya
        self.check(rp.rp_Init(), "rp_Init")
        print("Connected")

        ## Set up folder
        if start_timestamp is None:
            start_time = datetime.now()
        else:
            start_time = datetime.strptime(start_timestamp, self.DATESTRING_FMT)
        run_folder = Path(f"{start_time.strftime(self.DATESTRING_FMT)}_N{needed_chunks}")
        run_folder.mkdir(exist_ok = True)

        ## Try to do the acquisition
        try:
            ## Prepare circular memory
            self.check(rp.rp_AcqSetGain(rp.RP_CH_1, rp.RP_HIGH), "rp_AcqSetGain")
            get_memory = rp.rp_AcqAxiGetMemoryRegion()
            self.check(get_memory[0], "rp_AcqAxiGetMemoryRegion")
            memory_start = get_memory[1]

            samples_collected = 0
            chunk_number = 0

            while samples_collected < total_samples:
                chunk_number += 1
                print(f"Collecting chunk {chunk_number}")

                ## Set up acquisition
                self.check(rp.rp_AcqReset(), "rp_AcqReset")
                self.check(rp.rp_AcqAxiSetDecimationFactor(decimation), "rp_AcqAxiSetDecimationFactor")
                self.check(rp.rp_AcqAxiSetTriggerDelay(rp.RP_CH_1, chunk_samples), "rp_AcqAxiSetTriggerDelay")
                self.check(rp.rp_AcqAxiSetBufferSamples(rp.RP_CH_1, memory_start, chunk_samples), "rp_AcqAxiSetBufferSamples")
                self.check(rp.rp_AcqAxiEnable(rp.RP_CH_1, True), "rp_AcqAxiEnable")

                ## Acquisition
                self.check(rp.rp_AcqStart(), "rp_AcqStart")
                self.check(rp.rp_AcqSetTriggerSrc(rp.RP_TRIG_SRC_NOW), "rp_AcqSetTriggerSrc")

                while True:
                    buffer_fill = rp.rp_AcqAxiGetBufferFillState(rp.RP_CH_1)
                    self.check(buffer_fill[0], "rp_AcqAxiGetBufferFillState")
                    if buffer_fill[1]:
                        break

                self.check(rp.rp_AcqStop(), "rp_AcqStop")

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
                    for k,v in extra_metadata:
                        if isinstance(v, numbers.Number) or isinstance(v, str):
                            f_attrs[k] = v
                        else:
                            print(f"Bad metadata: {k} is not a scalar number or string")
                    # f.attrs["laser_power"] = laser_power
                    # f.attrs["laser_wavelength"] = laser_wavelength

                print(f"Saved {output}")

                samples_collected += chunk_samples

                self.check(rp.rp_AcqAxiEnable(rp.RP_CH_1, False), "rp_AcqAxiEnable(False)")

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
