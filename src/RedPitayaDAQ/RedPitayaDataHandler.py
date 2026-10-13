import h5py
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

from scipy.signal import welch
from recon_algorithms import ( ## Needs to come from the other repo, not a copied file
    apply_matched_filter,
)

def loadData(filename, drop_last_sample=True):
    '''
    Loads a given file and runs a PSD on it
    Arguments
    - filename:             path and name of file to load
    Returns
    - times:                time domain for data
    - voltages:             voltage data from file
    - f_data:               sample frequencies
    - data_psd:             psd of data
    '''
    file = Path(filename)

    with h5py.File(file, "r") as f:
        ## Exclude the final sample of this file from analysis.
        if drop_last_sample: voltages = voltages[:-1]
        sampling_rate_real = f.attrs["sampling_rate"]

    n_samples = len(voltages)
    times = np.arange(n_samples) / sampling_rate_real

    data_f, data_psd = welch(voltages, fs=sampling_rate_real, nperseg=n_samples // 8)

    return times, voltages, data_f, data_psd

def plotData(filename, psd=True, trace=True):
    '''
    Plots a trace or psd based on a file given to it
    Arguments
    - filename:             path name of the file
    - psd:                  true or false to plot a psd
    - trace:                true or false to plot a trace
    Returns
    - requested graphs
    '''

    times, voltages, f_data, data_psd = loadData(filename)

    if trace:
        fg0 = plt.figure(figsize=(7,6))
        ax0 = fg0.gca()
        ax0.plot(times, voltages, label='Raw trace [V]')
        ax0.set_xlabel("Time (s)")
        ax0.set_ylabel("Voltage Read (V)")
        ax0.set_title(filename)
    else:
        fg0 = None
        ax0 = None
    
    if psd:
        fg1 = plt.figure(figsize=(7,6))
        ax1 = fg1.gca()
        ax1.plot(f_data, data_psd)
        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_xlabel("Frequency (Hz)")
        ax1.set_ylabel("Voltage PSD (V^2 / Hz)")
        ax1.set_title(filename)
    else:
        fg1 = None
        ax1 = None
        
    plt.show()
    return fg0, fg1

def applyMatchFilter(filename, window=50):
    '''
    Load a given file and plots the waveform with detected jumps
    Arguments:
    - filename:             path and name of file
    - window:               matched-filter window in samples
    Returns:
    - trace with jumps labeled
    '''
    time, voltages, f_data, data_psd = loadData(filename)

    jump_t, jump_a = apply_matched_filter(time, voltages, window, peak_find_sigma = 5, filter_template = None)

    plt.figure()
    for i in range(len(jump_t)):
        plt.axvline(jump_t[i], color = "r", label = "Found jumps" if i == 0 else None)

    plt.plot(time, voltages)
    plt.xlabel("Time (s)")
    plt.ylabel("Voltage (V)")
    plt.text(0, -0.1, f"Found jumps: {len(jump_t)}", transform = plt.gca().transAxes, verticalalignment = "top")
    plt.legend()

def get_multijumps(filename, window=50):
    '''
    Load a given file and return +-320 points around each jump (+-10 ms at 32000 Hz, but should be done automatically later)
    Arguments:
    - filename:             path and name of file
    - window:               matched-filter window in samples
    Returns:
    - jump_v:               list of waveform segments around detected jumps
    '''
    time, voltages, _, _ = loadData(filename)

    jump_t, jump_a = apply_matched_filter(time, voltages, window, peak_find_sigma = 5,filter_template = None)

    jump_v = []

    for i in range(len(jump_t)):
        jump_id = np.argmin(np.abs(time - jump_t[i]))
        jump_v.append(voltages[jump_id - 320 : jump_id + 320])

    return jump_v

def graph_multijumps(filename, window=50):
    '''
    Load a given file and plot +-10 ms around each jump, as well as an average of all the jumps
    Arguments:
    - filename:             path and name of file
    - window:               matched-filter window in samples
    Returns:
    - overlayed traces, with averaged trace in red
    '''
    data = get_multijumps(filename, window = window)

    with h5py.File(filename, "r") as f:
        sampling_rate = f.attrs["sampling_rate"]

    times = np.arange(-320, 320) / sampling_rate * 1000

    
    plt.figure()
    for i in range(len(data)):
        plt.plot(times, data[i], alpha = 0.1)

    average_jump = np.mean(np.array(data), axis = 0)

    plt.plot(times, average_jump, color = "r", linewidth = 2, label = "Average")
    plt.xticks([-10, 0, 10])
    plt.axvline(0, color = "black", label = "Point of detected jump")

    plt.text(0, -0.1, f"Found jumps: {len(data)}", transform = plt.gca().transAxes, verticalalignment = "top")

    plt.xlabel("Time relative to jump (ms)")
    plt.ylabel("Voltage (V)")
    plt.legend()