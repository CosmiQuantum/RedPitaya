import numpy as np
from scipy.signal import correlate, find_peaks, fftconvolve

def apply_matched_filter(event_time_axis, event_waveform, window_samples, peak_find_sigma=5, filter_template=None):
    '''
    Applies a matched filter to a given waveform in order to extract properties of a discrete
    jump in the waveform.
    Arguments:
    - event_time_axis   time values of the waveform
    - event_waveform    y-axis values of the waveform
    - window_samples    number of samples used to define the window
    - peak_find_sigma   number of standard deviations to use as threshold for peak finding alogrithm
    - filter_template   template for matched filter; total length = 2x window_samples
    Returns:
    - jump_times        times of the located jumps in this waveform
    - jump_amps         reconstructed amplitude of the located jumps in this waveform
    '''
    ts = event_time_axis
    wf = event_waveform

    ## Set up fourier transformed filter to compare to
    ## This is the template/filter, which is simply a modified heaviside function
    if filter_template is None:
        match_to_fourier = np.r_[-np.ones(window_samples), np.ones(window_samples)]
    else:
        match_to_fourier = filter_template

    compare = fftconvolve(wf, match_to_fourier[::-1], mode = "same")
    compare = compare[0:-window_samples]
    
    ## Find peaks and convert to time and amplitude
    peaks, properties = find_peaks(compare, prominence=peak_find_sigma*np.std(compare), distance=window_samples)
    jump_ids = peaks
    jump_times = np.array(ts[jump_ids])

    ## Array for multiple jumps detected
    jump_amps = np.array([ 
        np.mean(wf[j:j + window_samples]) - np.mean(wf[j - window_samples:j]) 
        for j in jump_ids ])

    return jump_times, jump_amps

def apply_leastsq_fit(event_time_axis, event_waveform, window_samples, peak_find_sigma=8, fit_template=None):
    '''
    Applies a least-squares fit to a given waveform in order to extract properties of a discrete
    jump in the waveform.
    Arguments:
    - event_time_axis   time values of the waveform
    - event_waveform    y-axis values of the waveform
    - window_samples    number of samples used to define the window
    - fit_template      model for least-squares fit; total length = 2x window_samples
    Returns:
    - jump_times        times of the located jumps in this waveform
    - jump_amps         reconstructed amplitude of the located jumps in this waveform
    '''
    ts = event_time_axis
    wf = event_waveform

    fit_scores = np.zeros(len(wf))
    amplitudes = np.zeros(len(wf))

    for i in range (window_samples, len(wf) - window_samples):
        ## Takes +- window around the point of the graph being tested
        x = ts[i - window_samples:i + window_samples]
        y = wf[i - window_samples:i + window_samples]

        ## Create a model to fit against
        if fit_template is None:
            model = np.heaviside(x - ts[i], 1)
        else:
            model = fit_template

        ## Perform least squares fit
        stack = np.column_stack([x, np.ones_like(x), model])  ## Columns multiply m, b, and A, respectively
        parameters, _, _, _ = np.linalg.lstsq(stack, y)  ## Solve stack @ parameters ~= y
        m, b, A = parameters  ## Local slope, intercept, and step amplitude
        y_fit = stack @ parameters  ## Evaluate y_fit = m*x + b + A*model

        ## Find residuals of the fit
        residual = np.sum((y - y_fit)**2)

        ## Place the results into array
        amplitudes[i] = A
        fit_scores[i] = abs(A) / (residual**0.5)

    ## Peak finding in the array based on fits
    peaks, properties = find_peaks(fit_scores, prominence = peak_find_sigma*np.std(fit_scores), distance = window_samples)

    jump_ids = peaks
    jump_times = ts[jump_ids]
    jump_amps = amplitudes[jump_ids]

    return jump_times, jump_amps

def truth_check(jump_times, jump_amps, true_jumps, true_amps):
    '''
    Compares a reconstructed event to the truth values of jump times and amplitudes from a simulated
    waveform.
    Arguments:
    - jump_times    Time of jumps located in reconstructed event using a particular reconstruction algorithm
    - jump_amps     Amplitude of jumps located in reconstructed event using a particular reconstruction algorithm
    - true_jumps    Time of jumps located in truth event 
    - true_amps     Amplitude of jumps located in truth event 
    Returns:
    - time_diffs    Fractional difference in reconstructed vs truth times of jumps
    - amp_diffs     Fractional difference in reconstructed vs truth amplitudes of jumps
    '''
    time_diffs = np.nan * np.ones(len(true_jumps))
    amp_diffs = np.nan * np.ones(len(true_jumps))

    ## First compare the number of reconstructed jumps to truth
    mismatched_lengths = False
    if (len(jump_times) != len(true_jumps)) or (len(jump_amps) != len(true_amps)):
        mismatched_lengths = True
        print("Reconstructed event found a different number of jumps than truth.")

    ## Now sort each of the arrays by time
    recon_sorted_idx = np.argsort(jump_times)
    truth_sorted_idx = np.argsort(jump_times)

    recon_times = jump_times[recon_sorted_idx]
    recon_ampls = jump_amps[recon_sorted_idx]

    truth_times = jump_times[truth_sorted_idx]
    truth_ampls = jump_amps[truth_sorted_idx]

    ## Iterates through the time-sorted arrays and compares the reconstructed time, amplitude
    ## to the truth value for corresponding entries
    for j_idx in np.arange(len(truth_times)):
        if mismatched_lengths and j_idx > (len(recon_times)-1):
            break

        time_diffs[j_idx] = (recon_times[j_idx] - truth_times[j_idx])/truth_times[j_idx]
        amp_diffs[j_idx]  = (recon_ampls[j_idx] - truth_ampls[j_idx])/truth_ampls[j_idx]

    return time_diffs, amp_diffs

def run_filter_and_check_simulatedevent(event, window_samples, peak_find_sigma=5, filter_template=None):
    '''
    Applies a matched filter to a given waveform in order to extract properties of a discrete
    jump in the waveform.
    Arguments:
    - event             dictionary containing event and truth information of a simulated waveform
    - window_samples    number of samples used to define the window
    - peak_find_sigma   number of standard deviations to use as threshold for peak finding alogrithm
    - filter_template   template for matched filter; total length = 2x window_samples
    Returns:
    - jump_times        times of the located jumps in this waveform
    - jump_amps         reconstructed amplitude of the located jumps in this waveform
    - true_jumps        Time of jumps located in truth event 
    - true_amps         Amplitude of jumps located in truth event 
    - time_diffs        Fractional difference in reconstructed vs truth times of jumps
    - amp_diffs         Fractional difference in reconstructed vs truth amplitudes of jumps
    '''

    ## Run the matched filter
    jump_times, jump_amps = apply_matched_filter(event["ts"], event["wf"], window_samples, 
        peak_find_sigma=peak_find_sigma, filter_template=filter_template)

    ## Extract truth from event
    true_jumps = np.array(event["truth"]["JS_t0s"])
    true_amp = np.array(event["truth"]["JS_amps"])

    ## Compare to truth
    time_diffs, amp_diffs = truth_check(jump_times, jump_amps, true_jumps, true_amps)

    return jump_times, jump_amps, true_jumps, true_amps, time_diffs, amp_diffs
