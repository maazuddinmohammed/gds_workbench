"""Original score for the Atlas-Film composition.

Standard-library synthesis only: no samples, voices or licensed material.
Sections follow the scene timing in src/atlas-film/timeline.ts.
Run: python3 scripts/generate-film-score.py  (writes public/audio/atlas-film-score.wav)
"""
import argparse
import array
import math
import random
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATE = 24000
parser = argparse.ArgumentParser()
parser.add_argument("--seconds", type=float, default=243)
parser.add_argument("--output", default="atlas-film-score.wav")
args = parser.parse_args()
SECONDS = args.seconds
N = int(SECONDS * RATE)

BPM = 100
BEAT = 60 / BPM
BAR = BEAT * 4
CHORD_LEN = BAR * 2
# Dm - Bb - F - C, voiced warmly.
CHORDS = [
    (146.83, 220.00, 293.66, 349.23),
    (116.54, 174.61, 233.08, 293.66),
    (130.81, 174.61, 220.00, 261.63),
    (130.81, 196.00, 261.63, 329.63),
]
ROOTS = [73.42, 58.27, 87.31, 65.41]

# Section intensities (start second, name).
SECTIONS = [(0, "intro"), (8, "pulse"), (48, "build"), (112, "drive"), (148, "lift"), (204, "steady"), (234, "outro")]


def section(t):
    name = SECTIONS[0][1]
    for start, n in SECTIONS:
        if t >= start:
            name = n
    return name


def chord_at(t):
    return int(t // CHORD_LEN) % 4


left = array.array("f", bytes(4 * N))
right = array.array("f", bytes(4 * N))


def add(start_s, samples, gain_l, gain_r=None):
    gain_r = gain_l if gain_r is None else gain_r
    i0 = int(start_s * RATE)
    for k, v in enumerate(samples):
        i = i0 + k
        if i >= N:
            break
        left[i] += v * gain_l
        right[i] += v * gain_r


# ── one-shot drums ──
rng = random.Random(7)
KICK = []
phase = 0.0
for k in range(int(0.45 * RATE)):
    t = k / RATE
    freq = 45 + 75 * math.exp(-t * 28)
    phase += 2 * math.pi * freq / RATE
    KICK.append(math.sin(phase) * math.exp(-t * 7) * min(1, t / 0.002))
HAT = []
prev = 0.0
for k in range(int(0.06 * RATE)):
    n = rng.uniform(-1, 1)
    HAT.append((n - prev) * math.exp(-k / RATE * 70))
    prev = n
SNARE = []
prev = 0.0
for k in range(int(0.25 * RATE)):
    t = k / RATE
    n = rng.uniform(-1, 1)
    SNARE.append(((n - prev * 0.5) * 0.6 * math.exp(-t * 22) + math.sin(2 * math.pi * 185 * t) * 0.5 * math.exp(-t * 30)))
    prev = n
BOOM = []
for k in range(int(2.5 * RATE)):
    t = k / RATE
    BOOM.append(math.sin(2 * math.pi * (38 + 30 * math.exp(-t * 4)) * t) * math.exp(-t * 1.6) * min(1, t / 0.01))


def pluck(freq, dur, decay, bright=0.25):
    out = []
    for k in range(int(dur * RATE)):
        t = k / RATE
        env = math.exp(-t * decay) * min(1, t / 0.004)
        out.append((math.sin(2 * math.pi * freq * t) + bright * math.sin(2 * math.pi * freq * 2 * t) + bright * 0.4 * math.sin(2 * math.pi * freq * 3 * t)) * env)
    return out


# ── sequencing ──
kick_times = []
sixteenth = BEAT / 4
step = 0
t = 0.0
while t < SECONDS - 0.5:
    sec = section(t)
    beat_pos = step % 16
    ci = chord_at(t)
    chord = CHORDS[ci]
    # kick
    if sec in ("build",) and beat_pos in (0, 8):
        add(t, KICK, 0.55)
        kick_times.append(t)
    if sec in ("drive", "lift", "steady") and beat_pos % 4 == 0:
        add(t, KICK, 0.55 if sec != "steady" else 0.45)
        kick_times.append(t)
    # snare on 2 and 4
    if sec in ("drive", "lift") and beat_pos in (4, 12):
        add(t, SNARE, 0.16, 0.14)
    # hats on off-beats
    if sec in ("pulse", "build", "drive", "lift") and beat_pos % 4 == 2:
        add(t, HAT, 0.10, 0.07)
    if sec == "lift" and beat_pos % 2 == 1:
        add(t, HAT, 0.04, 0.06)
    # bass on 8ths
    if sec in ("pulse", "build", "drive", "lift", "steady") and beat_pos % 2 == 0:
        root = ROOTS[ci]
        octave = 2 if beat_pos % 4 == 2 else 1
        add(t, pluck(root * octave, 0.32, 9, 0.35), 0.20)
    # arpeggio on 16ths
    if sec in ("build", "drive", "lift", "steady"):
        pattern = [0, 1, 2, 3, 2, 3, 1, 2]
        note = chord[pattern[step % 8]] * (4 if sec == "lift" else 2)
        g = {"build": 0.07, "drive": 0.08, "lift": 0.08, "steady": 0.05}[sec]
        pan = 0.35 if step % 2 == 0 else -0.35
        add(t, pluck(note, 0.22, 16, 0.15), g * (1 - pan), g * (1 + pan))
    step += 1
    t = step * sixteenth

# intro bells and the logo impact
add(1.6, BOOM, 0.5)
for i, (tt, fr) in enumerate([(0.2, 587.33), (1.0, 880.0), (1.75, 1174.66), (2.6, 880.0), (3.4, 1318.51), (4.6, 1174.66)]):
    add(tt, pluck(fr, 2.0, 2.2, 0.05), 0.08 * (1.2 if i % 2 else 0.8), 0.08 * (0.8 if i % 2 else 1.2))
# outro bells
for i, (tt, fr) in enumerate([(234.4, 587.33), (235.4, 880.0), (236.4, 1174.66), (237.4, 1396.91)]):
    add(tt, pluck(fr, 3.0, 1.6, 0.05), 0.08, 0.08)
add(234.2, BOOM, 0.35)

# ── sidechain envelope from kicks ──
duck = array.array("f", [1.0]) * N
for kt in kick_times:
    i0 = int(kt * RATE)
    for k in range(int(0.3 * RATE)):
        i = i0 + k
        if i >= N:
            break
        duck[i] = min(duck[i], 1 - 0.45 * math.exp(-k / RATE * 9))

# ── pad (continuous) ──
pad_level = {"intro": 0.9, "pulse": 0.75, "build": 0.7, "drive": 0.6, "lift": 0.6, "steady": 0.7, "outro": 0.9}
for n in range(N):
    t = n / RATE
    ci = chord_at(t)
    age = t % CHORD_LEN
    blend = min(1.0, age / 1.2)
    blend = blend * blend * (3 - 2 * blend)
    cur = CHORDS[ci] if t < 234 else CHORDS[0]
    prv = CHORDS[(ci - 1) % 4] if t < 234 else CHORDS[0]
    s_cur = 0.0
    s_prv = 0.0
    for fr in cur:
        s_cur += math.sin(2 * math.pi * fr * 1.0015 * t) + math.sin(2 * math.pi * fr * 0.9985 * t)
    if blend < 1:
        for fr in prv:
            s_prv += math.sin(2 * math.pi * fr * 1.0015 * t) + math.sin(2 * math.pi * fr * 0.9985 * t)
    pad = (s_cur * blend + s_prv * (1 - blend)) / 8
    lvl = pad_level[section(t)]
    swell = min(1.0, t / 3.0)
    p = pad * 0.22 * lvl * swell * (0.75 + 0.25 * duck[n])
    left[n] = left[n] * (0.6 + 0.4 * duck[n]) + p
    right[n] = right[n] * (0.6 + 0.4 * duck[n]) + p

# ── echo, fade, soft clip, write ──
out = array.array("h")
dl, dr = int(0.36 * RATE), int(0.54 * RATE)
peak = 1e-9
mixed_l = array.array("f", bytes(4 * N))
mixed_r = array.array("f", bytes(4 * N))
for n in range(N):
    l = left[n] + (left[n - dl] * 0.18 if n >= dl else 0)
    r = right[n] + (right[n - dr] * 0.18 if n >= dr else 0)
    t = n / RATE
    fade = min(1.0, t / 1.5, (SECONDS - t) / 5)
    fade = math.sin(max(0.0, fade) * math.pi / 2) ** 2
    l = math.tanh(l * 1.2) * fade
    r = math.tanh(r * 1.2) * fade
    mixed_l[n] = l
    mixed_r[n] = r
    peak = max(peak, abs(l), abs(r))
gain = 0.89 / peak
for n in range(N):
    out.extend((round(mixed_l[n] * gain * 32767), round(mixed_r[n] * gain * 32767)))

path = ROOT / "public/audio" / args.output
with wave.open(str(path), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(out.tobytes())
rms = math.sqrt(sum(v * v for v in out) / len(out)) / 32768
print(f"Atlas film score: {SECONDS:.0f}s; RMS {20 * math.log10(rms):.1f} dBFS -> {path.name}")
