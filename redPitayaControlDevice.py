from pathlib import Path
import numpy as np
import h5py
import rp
from datetime import datetime


def check(result, operation):
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

def setParameters(sampling_rate_wanted = 32000, scan_duration = 10, chunk_samples = 32000):
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

    # getting actual sampling rate from the red pitaya clock
    clock = 125 * 10**6
    decimation = round(clock / sampling_rate_wanted)
    sampling_rate_real = clock / decimation

    # samples and chunks which will need to be collected. Note the chunk samples will need to be a multiple of 8
    total_samples = round(scan_duration * sampling_rate_real)
    chunk_samples = (chunk_samples // 8) * 8
    needed_chunks = int(np.ceil(total_samples / chunk_samples))

    print("Parameters set")
    print("Requested sampling rate (Hz):", sampling_rate_wanted)
    print("Actual sampling rate (Hz):", sampling_rate_real)
    print("Decimation:", decimation)
    print("Target sampled duration (s):", scan_duration)
    print("Total samples:", total_samples)
    print("Samples per chunk:", chunk_samples)
    print("Total chunks:", needed_chunks)

    return sampling_rate_real, decimation, total_samples, needed_chunks, chunk_samples

def collectData(sampling_rate_wanted = 32000, scan_duration = 10, chunk_samples = 32000, laser_power = 3, laser_wavelength = 1550, start_timestamp = None):
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

    sampling_rate_real, decimation, total_samples, needed_chunks, chunk_samples = setParameters(sampling_rate_wanted, scan_duration, chunk_samples)

    check(rp.rp_Init(), "rp_Init")
    print("Connected")

    # folder set up
    if start_timestamp is None:
        start_time = datetime.now()
    else:
        start_time = datetime.strptime(start_timestamp, "%Y-%m-%d_%H-%M-%S")
    run_folder = Path(f"{start_time.strftime('%Y-%m-%d_%H-%M-%S')}_N{needed_chunks}")
    run_folder.mkdir(exist_ok = True)

    try:

        # prepare circular memory
        check(rp.rp_AcqSetGain(rp.RP_CH_1, rp.RP_HIGH), "rp_AcqSetGain")
        get_memory = rp.rp_AcqAxiGetMemoryRegion()
        check(get_memory[0], "rp_AcqAxiGetMemoryRegion")
        memory_start = get_memory[1]

        samples_collected = 0
        chunk_number = 0

        while samples_collected < total_samples:
            chunk_number += 1
            print(f"Collecting chunk {chunk_number}")

            # set up acquisition
            check(rp.rp_AcqReset(), "rp_AcqReset")
            check(rp.rp_AcqAxiSetDecimationFactor(decimation), "rp_AcqAxiSetDecimationFactor")
            check(rp.rp_AcqAxiSetTriggerDelay(rp.RP_CH_1, chunk_samples), "rp_AcqAxiSetTriggerDelay")
            check(rp.rp_AcqAxiSetBufferSamples(rp.RP_CH_1, memory_start, chunk_samples), "rp_AcqAxiSetBufferSamples")
            check(rp.rp_AcqAxiEnable(rp.RP_CH_1, True), "rp_AcqAxiEnable")

            # acquisition
            check(rp.rp_AcqStart(), "rp_AcqStart")
            check(rp.rp_AcqSetTriggerSrc(rp.RP_TRIG_SRC_NOW), "rp_AcqSetTriggerSrc")

            while True:
                buffer_fill = rp.rp_AcqAxiGetBufferFillState(rp.RP_CH_1)
                check(buffer_fill[0], "rp_AcqAxiGetBufferFillState")
                if buffer_fill[1]:
                    break

            check(rp.rp_AcqStop(), "rp_AcqStop")

            # move buffer data into data file
            memory_end = rp.rp_AcqAxiGetWritePointerAtTrig(rp.RP_CH_1)
            check(memory_end[0], "rp_AcqAxiGetWritePointerAtTrig")
            voltage_data = rp.fBuffer(chunk_samples)
            data_result = rp.rp_AcqAxiGetDataV(rp.RP_CH_1, memory_end[1], chunk_samples, voltage_data)
            check(data_result[0], "rp_AcqAxiGetDataV")

            output = run_folder / (f"{start_time.strftime('%Y-%m-%d_%H-%M-%S')}_chunk{chunk_number}_of{needed_chunks}.h5")

            with h5py.File(output, "w") as f:
                dataset = f.create_dataset("Voltage (V)", data = np.array([voltage_data[i] for i in range(chunk_samples)]))
                f.attrs["date"] = start_time.strftime('%Y-%m-%d_%H-%M-%S')
                f.attrs["total_samples"] = total_samples
                f.attrs["chunk_samples"] = chunk_samples
                f.attrs["total_chunks"] = needed_chunks
                f.attrs["current_chunk"] = chunk_number
                f.attrs["scan_duration"] = scan_duration
                f.attrs["sampling_rate"] = sampling_rate_real
                f.attrs["decimation"] = decimation
                f.attrs["laser_power"] = laser_power
                f.attrs["laser_wavelength"] = laser_wavelength

            print(f"Saved {output}")

            samples_collected += chunk_samples

            check(rp.rp_AcqAxiEnable(rp.RP_CH_1, False), "rp_AcqAxiEnable(False)")

    # release hardware after done collecting
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
