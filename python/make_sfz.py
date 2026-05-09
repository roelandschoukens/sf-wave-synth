"""
Take a SFZ file containing a basic sound wave and a few filters, and
create a SFZ file consisting of a simple SFZ file and a whole bunch of .wav
files with the samples.
"""

import dataclasses
import math
import os
import sys
import wave
import numpy as np
import scipy.fft
import scipy.signal
import argparse
import re
import warnings

import basic_wave


import matplotlib as mpl
import matplotlib.pyplot as plt

from sfz_parser import *


mpl.rcParams['path.snap'] = False
mpl.rcParams['lines.antialiased'] = True  # For lines
mpl.rcParams['patch.antialiased'] = True  # For patches/shapes
mpl.rcParams['text.antialiased'] = True   # For text
plt.rcParams['figure.titlesize'] = 10
plt.rcParams['axes.titlesize'] = 10
keys = ['font.size', 'axes.labelsize', 'xtick.labelsize', 'ytick.labelsize', 'legend.fontsize']
for key in keys:
    plt.rcParams[key] = 8

class Fail(Exception):
    pass


NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MIDI_C0_NR = 12 # MIDI key assigned to C0
MIDI_A_440_NR = 69
INV_NOTE_MAP = {"C" : 0, "D" : 2, "E" : 4, "F" : 5, "G" : 7, "A" : 9, "B" : 11}

def note_name_to_key(s):
    if m := re.match(r"([A-G])(#*)(B*)(\d)$", s.upper()):
        key = MIDI_C0_NR + INV_NOTE_MAP[m[1]] + 12 * int(m[4]) + len(m[2]) - len(m[3])
        return key
    raise ValueError(f"Not a note name: '{s}'")

def key_to_freq(key):
    return 440 * 2 ** ((key - MIDI_A_440_NR) / 12)

def freq_to_key(freq):
    """ returns a floating point number, use round() before getting a note name """
    return 12 * math.log2(freq / 440) + MIDI_A_440_NR

def key_to_notename(key):
    return f"{NOTE_NAMES[key % 12]}{(key - MIDI_C0_NR) // 12}"

WAVE_TYPES = ("saw", "sine", "triangle", "square")

# data to be extracted
@dataclasses.dataclass
class Filter:
    btype : str
    poles : int
    freq : float
    Q : float | None


def filter_b_a(f : Filter, sample_f):
    if f.btype == "lowpass" and f.poles == 2 and f.Q is not None:
        # low pass filter, 2nd order
        # use formulas found on https://gusbertianalog.com/2nd-digital-filter/
        # "A Simple 2nd Order Low-Pass Filter"
        # by G. F. Gusberti
        # It is not quite your usual knee frequency / Q factor filter, but it remains
        # well behaved for very high knee frequencies
        ff = f.freq / sample_f
        # for Q < 1.0, the knee frequency of the filter below shifts by this ratio
        # so compensate
        if f.Q < .5:
            warnings.warn(f"{f.btype} filter with Q < {f.Q:.1} requested, using Q = 0.5 instead.")

        q = max(.50001, f.Q)
        ff *= math.sqrt(1 - math.pow(0.5 / q, 6))
        omega_0 = 2 * math.pi * ff
        alpha = math.sin(omega_0) / (2 * q)
        b0 = 0.5 - 0.5 * math.cos(omega_0)
        b1 = 2 * b0
        b2 = b0
        a0 = 1 + alpha
        a1 = -2 * math.cos(omega_0)
        a2 = 1 - alpha
        return [b0, b1, b2], [a0, a1, a2]

    if f.btype == "bandpass":
        return scipy.signal.iirpeak(f.freq, f.Q, fs=sample_f)

    if f.btype == "bandstop":
        return scipy.signal.iirnotch(f.freq, f.Q, fs=sample_f)

    if f.Q is not None and not math.isclose(f.Q, math.sqrt(.5), rel_tol=0.001):
        warnings.warn(f"{f.btype} filter with Q={f.Q:.1} requested, but Q factor is not implemented for this type.")
    return scipy.signal.butter(f.poles, f.freq, f.btype, fs=sample_f)


def parse_input(fn):
    globals = []
    filter_settings = {}

    with open(fn) as in_f:
        tokens = sfz_tokens(in_f)

        t = next(tokens)
        if (t != Header("global")):
            raise Fail("First line must be a <global> header")
        globals.append(t)
        t = next(tokens)

        while isinstance(t, Instr):
            globals.append(t)
            t = next(tokens)

        if (t != Header("group")):
            raise Fail("Must have one <group> with one <region>")
        t = next(tokens)

        while isinstance(t, Instr):
            filter_settings[t.opcode] = t.value
            t = next(tokens)

        if (t != Header("region")):
            raise Fail("Must have one <group> with one <region>")
        t = next(tokens)

        while isinstance(t, Instr):
            filter_settings[t.opcode] = t.value
            t = next(tokens)

        # should run out here
        if t != End():
            raise Fail("Must have one <group> with one <region>")
    return globals, filter_settings


def resonance_to_q(resonance):
    """ approximation for resonance setting to Q

    The setting is in dB.
    
    For resonance 0dB this returns √2, which should result in a Butterworth filter.
    """
    x = (10 ** (resonance / 20))
    return math.sqrt(x * x - 0.5)


def q_to_resonance(q):
    """ approximation for Q to resonance setting conversion in dB
     
    For Q = √2 this returns 0dB.
    """
    return 20 * math.log10(math.sqrt(0.5 + q*q))


def get_filter_settings(filter_settings, key_suffix):
    """ Get one of the filter settigns from the filters defined in the source SFZ
    file, and return the matching Filter settings. If the SFZ file does not specify
    this filter, return None
    """
    ftype = filter_settings.get(f"fil{key_suffix}_type")
    freq = float(filter_settings.get(f"cutoff{key_suffix}"))
    resonance = filter_settings.get(f"resonance{key_suffix}")
    if ftype and freq:
        Q = resonance_to_q(float(resonance)) if resonance is not None else None
        if m := re.match(r"([a-z]+)_(\d+)p", ftype):
            btype = dict(
                lpf="lowpass",
                hpf="highpass",
                bpf="bandpass",
                brf="bandstop").get(m[1])
            poles = int(m[2])
        if btype:
            return Filter(btype, poles, freq, Q)
        else:
            raise Fail(f"Filter type {ftype} is not supported")
    return None


def make_wave(freq, wave_type, gain, filter_settings : list[Filter], sampling_freq):
    """
    Generate a wave sample for a given frequency and settings
    
    :param freq: Frequency in Hertz
    :param wave_type: Type of basis wave form to start with
    :param gain: amplification of basis wave form (usually < 1.0)
    :param filter_settings: list of filters to apply
    :param sampling_freq: sampling frequency for the wave sample
    """

    # there is a small improvement from supersampling
    SUPERSAMPLE = 3
    # minimum samples in the loop. The frequency is rounded so that the loop
    # is an exact multiple of the period, so lower numbers introduce more
    # out of tune samples.
    # this rounded freqency is returned.
    MIN_LOOP_SAMPLES = 400

    # minimal number of quiet samples generated after the basic wave form
    MIN_QUIET_TAIL = 10

    # take 2 periods, or enough periods to reach minimum loop samples, whichever
    # is more. Round freq so this is an integer number of samples
    # this will be our loop size
    n_p = max(2, math.ceil(MIN_LOOP_SAMPLES * freq / sampling_freq))
    loop_n = math.floor(0.5 + n_p * sampling_freq / freq)
    freq = n_p * sampling_freq / loop_n

    sampling_freq_ss = SUPERSAMPLE * sampling_freq

    filter_b_a_list = [filter_b_a(f, sampling_freq_ss) for f in filter_settings]

    # length of those periods, add one extra period on top of our chosen loop interval
    len_s = (n_p + 1) / freq

    # Estimate how long it takes to the filter to decay to steady state
    # initially, 1 cycle, or the minimal given by MIN_QUIET_TAIL
    filter_s = max(1 / freq, MIN_QUIET_TAIL / sampling_freq)
    for _f, (b, a) in zip(filter_settings, filter_b_a_list):
        # for filter with high Q factors, ensure we pad with enough cycles
        # to make the filter resonance settle
        n1 = math.ceil(0.5 * sampling_freq_ss / freq) # impulse: 1 for half a period
        n2 = n1
        while True:
            ir = scipy.signal.lfilter(b, a, np.concat([np.ones(n1), np.zeros(n2)]))
            if np.all(np.abs(ir[-n2 // 4:]) < 1e-5):
                break
            n2 = n2 * 3 // 2
        filter_s = max(filter_s, n2 / sampling_freq_ss)
    
    # round up to number of periods, add at least half a period
    filter_s = math.ceil(filter_s  * freq + .5) / freq

    # decide how big the sample is
    # allow for the filter to decay (both at the start and the end)
    # add a few extra samples so if we don't have filtering, we have a proper 
    # zero crossing at the end
    len_signal = math.floor((filter_s + len_s) * sampling_freq_ss)
    len_padding = math.floor(filter_s * sampling_freq_ss)

    # generate waveform for the first samples
    # we just use harmonics, because even at low frequencies the
    # aliasing created by such waves is easily noticeable.
    freq_n = freq / sampling_freq_ss
    wave_sig = basic_wave.basic_wave_harmonics(
        wave_type, len_signal, freq_n, cutoff=0.45/SUPERSAMPLE, n=20000)
    
    wave_sig *= gain

    wave_sig = np.concat([wave_sig, np.zeros(len_padding)])

    # filtering
    for b, a in filter_b_a_list:
        wave_sig = scipy.signal.lfilter(b, a, wave_sig)
        
    # trim silence
    trim_pos = np.nonzero(np.abs(wave_sig) > 1e-5)[0][-1]
    trim_pos = max(len_signal + MIN_QUIET_TAIL * SUPERSAMPLE, trim_pos)
    # align to non-supersampled samples
    trim_pos -= (trim_pos % SUPERSAMPLE)
    wave_sig = wave_sig[0:trim_pos]
    

    if SUPERSAMPLE > 1:
        # filter.decimate uses a non-casual filter, messing up the end
        # of our loop part. A simple average seems to be enough.
        wave_sig = np.average(np.reshape(wave_sig, (-1, SUPERSAMPLE)), axis=-1)
    offs_sig_end = len_signal // SUPERSAMPLE

    # time
    t = np.arange(len(wave_sig)) * (1 / sampling_freq)

    loop_b = offs_sig_end
    loop_a = loop_b - loop_n

    return freq, t, wave_sig, [loop_a, loop_b]


def loop_error(wave_sig, loop_a, loop_b, test_n):
    loop_test = wave_sig[loop_a-test_n:loop_a] - wave_sig[loop_b-test_n:loop_b]
    return np.max(np.abs(loop_test))


def make_filter_plot(f_settings : list[Filter], sampling_freq):
    if len(f_settings) == 0:
        return None
    
    S = sampling_freq * 2
    ticks = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10e3, 20e3]
    tick_lbls = [str(x) if x <= 1000 else f"{x/1000:.0f}k" for x in ticks]
    freq = np.logspace(math.log10(17), math.log10(sampling_freq - 1), 500, base=10)

    # Bode plots of each filter, and of the end result
    nplot = 1 + len(f_settings)
    h_total = None
    fig, ax = plt.subplots(3, 1, figsize=[5, 2 * nplot])
    for i, filt in enumerate(f_settings + [None]):
        if filt is not None:
            b, a = filter_b_a(filt, S)
            freq_, h = scipy.signal.freqz(b, a, fs=S, worN=freq)

            if h_total is None:
                h_total = h
            else:
                h_total *= h
            fdesc = f"{filt.btype}, {filt.poles}p, {filt.freq:.1f}Hz"
            if (filt.btype in ("bandpass", "bandstop", "lowpass") and filt.poles == 2):
                fdesc += f", Q={filt.Q:.1f}"
        else:
            h = h_total
            fdesc = "Total filter"

        db = 20*np.log10(np.maximum(abs(h), 1e-5))
        phase = np.rad2deg(np.angle(h))

        ax[i].set_title(f"Filter {i}: " + fdesc)
        ax[i].set_xlim([np.min(freq), np.max(freq)])
        ax[i].set_xscale("log")
        ax[i].set_xticks(ticks, labels=tick_lbls)
        ax[i].set_ylabel("Amplitude [dB]", color='blue')
        ax[i].plot(freq, db, color='blue')
        tx = ax[i].twinx()
        tx.set_ylabel("Phase angle", color='red')
        tx.set_ylim([-180, 180])
        tx_yt = np.arange(-180, 180 + 1, 45)
        tx.set_yticks(tx_yt, labels=tx_yt)
        tx.plot(freq, phase, ":", color='red', linewidth=.8)
        ax[i].grid(True)

    fig.tight_layout()

    return fig


def make_plot(freq, t, y, loop_a, loop_b, sampling_freq):
    fig = plt.figure(figsize=[10, 6])

    # layout
    gs = fig.add_gridspec(2, 2, width_ratios=[1, 2])
    ax_s = fig.add_subplot(gs[0, :])
    ax_d = fig.add_subplot(gs[1, 0])
    ax_w = fig.add_subplot(gs[1, 1])

    # waveform + loop error
    ax_w.plot(t, y)
    for l in [loop_a, loop_b]:
        ax_w.plot([l / sampling_freq, l / sampling_freq], [-1, 1], "r:")

    # for the loop error plot: use the minimum of:
    # half the loop, and the time available after the filter decay
    test_n1 = min((loop_b - loop_a) // 2, loop_a * 1 // 4)
    # at least one period though
    test_n1 = max(test_n1, math.floor(sampling_freq / freq))
    # but never more than loop_a
    test_n1 = min(test_n1, loop_a)

    y_diff_1 = y[loop_a-test_n1:loop_a] - y[loop_b-test_n1:loop_b]
    ax_w.plot(t[loop_b-test_n1:loop_b], 1000 * y_diff_1)

    # detail of how the samples match up
    test_n = min(loop_a, math.floor(1.5 * sampling_freq / freq))
    test_n = min(100, test_n)
    ax_d.plot(t[:test_n], y[loop_b - test_n:loop_b], "g.-", linewidth=2, markersize=3)
    ax_d.plot(t[test_n - 5:2 * test_n], y[loop_a - 5:loop_a + test_n], "k.-", linewidth=1, markersize=3)

    # spectrum
    # this should ideally have most energy in the harmonics
    EPS = np.finfo(np.float32).smallest_normal
    fft = scipy.fft.fft(y[loop_a:loop_b])
    fft_clip = len(fft) // 2 + 1
    fft_fold = (len(fft) - 1) // 2
    fft[1:fft_fold] += fft[-1:-fft_fold:-1]
    fft = fft[:fft_clip]
    fft_dB = 20 * np.log10(np.abs(fft) + EPS)
    fft_max = np.max(fft_dB)
    fhz = np.arange(fft_clip) * sampling_freq / freq / (loop_b - loop_a)

    fft_min = fft_max - 200
    ax_s.bar(fhz, fft_dB - fft_min, bottom=fft_min, width=fhz[1])
    fhz_units = np.arange(fhz[-1])
    ax_s.set_xticks(fhz_units, minor=True)
    ax_s.set_ylim([fft_min, fft_max + 5])
    ax_s.set_ylabel("dB")

    # title
    fkey = freq_to_key(freq)
    key = math.floor(0.5 + fkey)
    cents = 100 * (fkey - key)
    ax_s.set_title(f"{freq:.2f}Hz ({key_to_notename(key)} {cents:+.1f} cents)")

    return fig


if __name__ == "__main__":
        
    D = """\
This generates a soundfont from a simple wave synthesis process. The synthesis
is described with an .sfz file with this structure:

- one <global> tag, followed by opcodes, these are copied to the output
- one <group> tag, followed by filter parameters: fil_type, fil2_type, and
    related cutoff and resonance parameters
- one <region> tag, with:
- one <sample>, with of the simple wave types (eg *saw), and lokey
    and hikey opcodes.\
"""

    parser = argparse.ArgumentParser(
        description=D,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # our custom parsing
    def parse_volume(s):
        try:
            if s[-2:].lower() == "db":
                return 10 ** (0.1 * float(s[:-2]))
            else:
                return float(s)
        except ValueError:
            raise argparse.ArgumentTypeError(
                "Not a valid gain notation: expect scale factor as float, or a number with 'dB' suffix.")


    parser.register('type', 'volume', parse_volume)

    def parse_frequency(s):
        try:
            if s[-2:].lower() == "hz":
                # frequency in Hz
                return float(s[:-2])
            elif s[0].lower() == "k":
                # MIDI key: kNN
                return key_to_freq(float(s[1:]))
            else:
                # note name
                return key_to_freq(note_name_to_key(s))
        except ValueError:
            raise argparse.ArgumentTypeError(
                "Not a valid pitch notation: expect note name (eg. 'C4'), key number ('k<key>') or frequency ('<freq>Hz').")

            

    parser.register('type', 'frequency', parse_frequency)

    parser.add_argument("input", metavar="INPUT.SFZ", help="Input file. This file uses a subset of the .sfz spec to specify wave type and filter type")
    parser.add_argument("--sampling-freq", "-s", metavar="FREQ", default=44100, type=float, help="Sampling frequency for exported WAV samples")
    parser.add_argument("--gain", "-g", type="volume", metavar="NNdB", help="Gain for the wave generator. If none, the 'volume' opcode"
                        " value from the <group> tag is used. Given as a scale factor (no suffix) or amplitude decibels ('dB' suffix).")
    action_gr = parser.add_argument_group("actions")
    action_gr.add_argument("--plot", action='append', default=[], type="frequency", metavar="FREQ", help="Show a plot of one of the frequencies")
    action_gr.add_argument("--plot-filter", action="store_true", help="Show the filter spectra of the filters specified in the SFZ file")
    action_gr.add_argument("--output", "-o", metavar="OUT.SFZ", help="Output a SFZ file based on samples, along with the samples in .wav format")
    sfz_gr = parser.add_argument_group("SFZ output options")
    sfz_gr.add_argument("--wav-pattern", metavar='"NAME_{}"', help="pattern used to generate sample wav files, must contain a single {} placeholder. By default, based on the output file name")
    sfz_gr.add_argument("--plot-all", action="store_true", help="Save plots along with the wave samples")
    sfz_gr.add_argument("--autogain", action="store_true", help="Lower gain if a sample clips")

    args = parser.parse_args()

    try:
        header, instructions = parse_input(args.input)
        filters_settings = [
            get_filter_settings(instructions, ""),
            get_filter_settings(instructions, "2") ]

        wave_type = instructions["sample"]
        if wave_type[0] != "*" or (wave_type[1:] not in WAVE_TYPES):
            raise Fail("Sample must be one of the simple oscillator types: \n" +
                    ", ".join(f"*{t}" for t in WAVE_TYPES))
        wave_type = wave_type[1:]
        
        filters_settings = [s for s in filters_settings if s is not None]
            
        if args.gain is None:
            if f := instructions.get("volume"):
                f = float(f)
                print(f"Volume: {f * 100:.1f}% ({20 * math.log10(f):.1f}dB)")
                args.gain = f
                del instructions["volume"]
            else:
                args.gain = 1.0

        if args.plot_filter:
            make_filter_plot(filters_settings, args.sampling_freq)

        for freq in args.plot:
            freq, t, y, [loop_a, loop_b] = make_wave(freq, wave_type, args.gain, filters_settings, args.sampling_freq)
            make_plot(freq, t, y, loop_a, loop_b, args.sampling_freq)

        # show all open figures
        plt.show(block=True)

        if args.output:
            # SFZ output requested
            wav_pattern = args.wav_pattern
            if wav_pattern is None:
                wav_pattern = os.path.splitext(os.path.basename(args.output))[0] + "_{}.wav"

            warnings = 0
            peak = 0
            worst_cents = 0
            with open(args.output, "wt") as sfzfh:
                # first write global settings
                for entry in header:
                    sfzfh.write(str(entry))
                    sfzfh.write("\n")
                sfzfh.write("<group>\n")
                sfzfh.write("loop_mode=loop_continuous\n")

                # if volume was given, but overridden on the command line, retain it for the output
                if (v := instructions.get("volume")) is not None:
                    sfzfh.write(f"volume={v}\n")

                for key in range(int(instructions["lokey"]), int(instructions["hikey"]) + 1):
                    # generate waveform
                    info = ""
                    freq = key_to_freq(key)
                    freq_r, t, y, [loop_a, loop_b] = make_wave(freq, wave_type, args.gain, filters_settings, args.sampling_freq)

                    if args.plot_all:
                        # make plot if requested
                        fig = make_plot(freq_r, t, y, loop_a, loop_b, args.sampling_freq)
                        plt.savefig(wav_pattern.format(key).removesuffix(".wav") + ".png")
                        plt.close(fig)

                    le = loop_error(y, loop_a, loop_b, math.ceil(args.sampling_freq / freq_r))
                    if le > 1e-4:
                        print(f"Loop error is {le * 1000:.1f}/1000")
                        warnings += 1

                    this_peak = np.max(np.abs(y))
                    if this_peak > 1:
                        if args.autogain:
                            g = 1 / this_peak
                            info += f"  gain: {20 * math.log10(g):.1f}dB"
                            y *= g
                        else:
                            print(f"warning, signal is clipped, maximum was {this_peak:.2f}.")
                            warnings += 1
                    peak = max(peak, this_peak)

                    fn = wav_pattern.format(key)
                    sfzfh.write(f"<region> sample={fn} key={key}"
                                f" loop_start={loop_a} loop_end={loop_b - 1}\n")
                    fn_full = os.path.join(os.path.dirname(args.output), fn)
                    with wave.open(fn_full, "wb") as wfh:
                        wfh.setnchannels(1)
                        wfh.setframerate(args.sampling_freq)
                        wfh.setnframes(len(y))
                        wfh.setsampwidth(2)
                        y_16 = (0x7fff * np.clip(y, -1, 1)).astype(np.uint16)
                        wfh.writeframes(y_16.tobytes())
                    cent = 1200 * math.log2(freq_r / freq)
                    worst_cents = max(worst_cents, abs(cent))
                    print(f"{key:3d}  {key_to_notename(key):3s} {cent:+4.1f}ct  {freq_r:>7.1f}Hz  {fn_full}" + info)
            if warnings > 0:
                print(f"{warnings} warnings during export")
            print(f"Peak: {peak*100:.1f}% ({20 * math.log10(peak):.1f}dB)")
            print(f"Worst case tuning: {worst_cents:.2f}cent")
    except Fail as fail:
        print(str(fail))
        sys.exit(1)