"""Original instrumental score; standard-library synthesis, no voices or samples."""
import argparse
import array
import math
from pathlib import Path
import wave

ROOT = Path(__file__).resolve().parents[1]
RATE = 24000
parser = argparse.ArgumentParser()
parser.add_argument("--seconds", type=int, default=156)
parser.add_argument("--output", default="score.wav")
args = parser.parse_args()
SECONDS = args.seconds
chords = [(146.83, 220.0, 293.66, 329.63), (130.81, 196.0, 261.63, 329.63),
          (174.61, 220.0, 261.63, 349.23), (164.81, 246.94, 293.66, 329.63)]
mono = array.array("f")
for n in range(SECONDS * RATE):
    t = n / RATE
    chord_index = int(t // 8) % 4
    chord = chords[chord_index]
    age = t % 8
    blend = min(1.0, age / 1.1)
    blend = blend * blend * (3 - 2 * blend)
    pad = sum(math.sin(2 * math.pi * frequency * t) for frequency in chord) / 4
    if blend < 1:
        previous = chords[(chord_index - 1) % 4]
        old_pad = sum(math.sin(2 * math.pi * frequency * t) for frequency in previous) / 4
        pad = pad * blend + old_pad * (1 - blend)
    note_age = t % 1.6
    note_frequency = chord[int(t / 1.6) % 4] * 2
    note = (math.sin(2 * math.pi * note_frequency * note_age)
            + .15 * math.sin(2 * math.pi * note_frequency * 3 * note_age))
    note *= math.exp(-note_age * 3.8) * min(1.0, note_age / .035)
    mono.append(pad * .32 + note * .17)

stereo = array.array("h")
left_delay, right_delay = int(.23 * RATE), int(.37 * RATE)
for n, sample in enumerate(mono):
    t = n / RATE
    fade = min(1.0, t / 2.5, (SECONDS - t) / 4)
    fade = math.sin(fade * math.pi / 2) ** 2
    left = sample * .86 + (mono[n - left_delay] * .14 if n >= left_delay else 0)
    right = sample * .86 + (mono[n - right_delay] * .14 if n >= right_delay else 0)
    stereo.extend((round(left * fade * 32767), round(right * fade * 32767)))

path = ROOT / "public/audio" / args.output
with wave.open(str(path), "wb") as wav:
    wav.setnchannels(2)
    wav.setsampwidth(2)
    wav.setframerate(RATE)
    wav.writeframes(stereo.tobytes())
peak = max(abs(v) for v in stereo) / 32768
rms = math.sqrt(sum(v * v for v in stereo) / len(stereo)) / 32768
print(f"Original stereo score: {SECONDS}s; peak {20 * math.log10(peak):.1f} dBFS; RMS {20 * math.log10(rms):.1f} dBFS")
