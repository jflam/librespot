#!/usr/bin/env python3
"""Create original deterministic stereo PCM and encode it locally; never play it."""
import array
import math
from pathlib import Path
import subprocess
import sys
import wave

root = Path(__file__).resolve().parent
(root / "fixtures").mkdir(exist_ok=True)
rate, seconds = 44100, 16
samples = array.array("h")
seed = 123456789
for frame in range(rate * seconds):
    t = frame / rate
    seed = (1664525 * seed + 1013904223) & 0xFFFFFFFF
    noise = (seed / 2**31 - 1) * math.exp(-35 * (t % .375))
    gate = min(1, t / .02, (seconds - t) / .02)
    if 7.5 <= t < 7.75:
        gate = 0
    for channel in range(2):
        notes = (110, 164.81, 220, 277.18) if channel == 0 else (130.81, 196, 261.63, 329.63)
        chord = sum(math.sin(math.tau * hz * t) for hz in notes) * .06
        transient = noise * (.18 if channel == 0 else -.14)
        value = (chord + transient) * gate
        samples.append(round(max(-1, min(1, value)) * 32767))
if sys.byteorder != "little":
    samples.byteswap()
path = root / "fixtures/synthetic.wav"
with wave.open(str(path), "wb") as out:
    out.setnchannels(2)
    out.setsampwidth(2)
    out.setframerate(rate)
    out.writeframes(samples.tobytes())
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
                "-c:a", "vorbis", "-strict", "experimental", "-b:a", "160k",
                str(root / "fixtures/synthetic.ogg")], check=True)
print("Generated original 16-second 44.1 kHz stereo Vorbis fixture.")
