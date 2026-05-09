import math
import numpy as np


def basic_wave_direct(wave_type, length, n_freq, /, rise_time=2):
    """
    Generate a wave procedurally
    
    :param length: length of the signal
    :param n_freq: frequency, relative of the sampling frequency (frequency / sample rate)
    :param rise_time: Rise or fall time of the signal on discontinuities
    """
    if n_freq > 0.5:
        raise ValueError("Requested signal of more than the Nyquist frequency")

    wave_sig = np.arange(length) * n_freq
    if wave_type == "sine":
        wave_sig = np.sin(2 * np.pi * wave_sig)
    elif wave_type == "saw":
        wave_sig += .5
        wave_sig -= np.floor(wave_sig)
        delta = rise_time * n_freq
        wave_sig = wave_sig * (1 + delta) - delta
        wave_sig = np.maximum(0, wave_sig) - np.minimum(0, wave_sig) / delta
        wave_sig = 2 * wave_sig - 1
    elif wave_type in ("triangle", "square"):
        wave_sig += 0.25
        wave_sig -= np.floor(wave_sig)
        wave_sig = 1 - 2 * np.abs(1 - 2 * wave_sig)
        if wave_type == "square":
            # a square is implemented as a clipped triangle wave,
            # this is an easy way to have a controlled slew rate
            wave_sig = np.clip(wave_sig / (n_freq * rise_time * 2), -1, 1)
    else:
        raise ValueError(f"Wave type {wave_type} not known")
    return wave_sig


def basic_wave_harmonics(wave_type, length, n_freq, /, n=100, cutoff=0.45):
    """
    Generate a wave by summing harmonics
    
    :param length: length of the signal
    :param n_freq: frequency, relative of the sampling frequency (frequency / sample rate)
    :param rise_time: Rise or fall time of the signal on discontinuities
    :param n Maximal order of harmonics to consider
    """
    if n_freq > 0.5:
        raise ValueError("Requested signal of more than the Nyquist frequency")
    
    harmonic_n = np.arange(n_freq, 0.5, n_freq)[:n]
    # tail off harmonics as we reach frequency 0.5
    # (assume the 10% engineering margin was used, so actually 0.45 will already be 0)
    harmonic_weights = np.clip((cutoff - harmonic_n) * 10, 0, 1)
    k = np.arange(1, 1+len(harmonic_n))

    theta = np.arange(length) * n_freq * 2 * np.pi

    if wave_type == "sine":
        # shortcut
        return np.sin(theta)
    elif wave_type == "saw":
        m1 = (k % 2) * 2 - 1
        harmonic_weights *= (2/np.pi) * m1 / k
    elif wave_type == "triangle":
        m1 = np.array([0, 1, 0, -1])[k % 4]
        harmonic_weights *= (8/(np.pi * np.pi)) * m1 / np.pow(k, 2)
        print(harmonic_weights[:3])
    elif wave_type == "square":
        harmonic_weights *= (4/np.pi) * (k % 2) / k
    else:
        raise ValueError(f"Wave type {wave_type} not known")
    
    wave_sig = np.zeros_like(theta)
    for k1, w in zip(k, harmonic_weights):
        if abs(w) > 0.00001:
            wave_sig += np.sin(k1 * theta) * w
    return wave_sig


def basic_wave(wave_type, length, n_freq, /, use_max_harmonics=50, rise_time=2, harmonic_cutoff=.45):
    """
    Generate a wave. Depending on frequency, it will be generated procedurally
    or via adding harmonics.
    
    :param length: length of the signal
    :param n_freq: frequency, relative of the sampling frequency (frequency / sample rate)
    :param use_max_harmonics: how much harmonics to reach before we switch to direct mode
    :param rise_time: Rise or fall time of the signal on discontinuities in direct mode
    :param harmonic_cutoff: maximal frequency of harmonic to generate, relative to sample rate
    """
    # if we generate less than 25 harmonics, use procedural so we can avoid strong
    # harmonics that alias
    if n_freq < harmonic_cutoff / use_max_harmonics:
        return basic_wave_direct(wave_type, length, n_freq, rise_time)
    else:
        return basic_wave_harmonics(wave_type, length, n_freq, n=use_max_harmonics, cutoff=harmonic_cutoff)

if __name__ == "__main__":
    from matplotlib import pyplot as plt
    types = ("sine", "triangle", "square", "saw")

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(len(types), 2, figsize=[10, 6])
    
    for (ax1, ax2), wt in zip(ax, types):
        y1 = basic_wave_direct(wt, 600, 0.005, rise_time=4)
        ax1.set_title(wt)
        ax1.set_ylim([-1.3, 1.3])
        ax1.plot(y1, "b", linewidth=2)

        y2 = basic_wave_harmonics(wt, 600, 0.005)
        ax2.set_title(wt)
        ax2.set_ylim([-1.3, 1.3])
        for n in range(1, 5):
            y3 = basic_wave_harmonics(wt, 600, 0.005, n=n)
            ax2.plot(y3, " ygrc"[n], linewidth=1, alpha=.4)
        ax2.plot(y2, "b", linewidth=2)
    plt.tight_layout()
    plt.show()
    exit()
