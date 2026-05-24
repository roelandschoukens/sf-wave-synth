# SFZ soundfont synthesizer

**💾 Get the old school sound fonts here:**
 - [🔊 GSM monophonic ringtone](https://raw.githubusercontent.com/roelandschoukens/sf-wave-synth/refs/heads/main/sf2/gsm.sf2)
 - [🔊 PC speaker](https://raw.githubusercontent.com/roelandschoukens/sf-wave-synth/refs/heads/main/sf2/pc-speaker.sf2)

<small>(sound fonts released under <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a> <img src="https://mirrors.creativecommons.org/presskit/icons/cc.svg" height="12" width="12">&nbsp;<img src="https://mirrors.creativecommons.org/presskit/icons/by.svg" height="12" width="12">&nbsp;<img src="https://mirrors.creativecommons.org/presskit/icons/sa.svg" height="12" width="12">)</small>

---------------------------

This program creates a SFZ soundfont starting from a simple waveform and filters.
This is how I made my [GSM](doc/gsm.md) sound font.

> [!TIP]
> This repository has a twin Observable notebook, https://observablehq.com/@roelandschoukens/sound-wave,
> you can try on there if you can recreate that sound. Or try to create this PC speaker beep sound.

### SFZ

SFZ is [a sound font format](https://sfzformat.com/). SFZ is a text based format
and it encodes a very wide feature set. A soundfont created with a simple wave form
and a few filters can in principle be encoded entirely in a self-contained text
file, or if the *basic waveforms* are not supported, a text file with one WAV sample
containing the waveform. For example [gsm-synth.sfz] encodes that GSM sound.

I decided to keep such SFZ files as input format.

Alas, while a lot of tools support SFZ, they only support the most basic of features.
(The script in this repository is no exception to this.) So to get something that is
widely supported we need to create samples for each note.

## How to use

This program starts from a SFZ file that tells which waveform to start with, and
which filters to apply. It will generate a sample for each of the MIDI keys
in the desired range, and a second SFZ file that references those samples.

```sh
python3 make_sfz.py stuff-src.sfz -o stuff-sfz
```

Then if you want you can use a tool like [polyphone](https://www.polyphone.io/) to convert
it to a SF2 file, which embeds all those wav samples, making it much easier to deal with.

## What it does

The program starts with a simple soundwave and a few filters. The basics are simple, but getting
this to sound good for all notes is really finicky:

 - Since saw waves and square waves have a lot of overtones, and aliasing artefacts are really easy to notice, the script creates those waves by combining harmonics.
 - The frequency is slightly modified so a few cycles fit in an exact number of
samples, and the loop lines up exactly.
 - It estimates how long the filter takes to decay. It has to really decay, so we don’t introduce a slight discontinuity when looping.
 - The sample contains an initial part, consisting of that decay time, and then the looped part, consisting of
 those cycles.

Getting any of these wrong results in some of the notes having some weird, whiny character, or even some
notes sounding out of tune despite being in tune within a couple of cents. Turns out our ears are _really
good_ at picking up such imperfections.

But the result is a good sounding font that comes in at well uder a megabyte.

## What’s in the repo

 - `python/`: The main `make_sfz.py` program and some small helper modules
 - `sfz/`: example input for the program
 - `sf2/`: The SF2 soundfonts built from the output for those SFZ files:
    - The PC speaker one contains a ‘large’ and ‘small’ variant. The first one represents the 1990’s, when these speakers were still actual small speakers, with a voice coil and a diaphragm. The second one represents the 2000’s, when nobody cared anymore and you might have found a small moving-iron beeper dangling off a wire.
    - The GSM one.
 - `doc/`: some text and images
