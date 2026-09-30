// Original instrumental bed: local synthesis only, no recordings or services.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const rate = 48000;
const seconds = 40;
const samples = rate * seconds;
const left = new Float64Array(samples);
const right = new Float64Array(samples);
const tau = Math.PI * 2;
const chords = [
  [48, 55, 60, 64, 71],
  [45, 52, 57, 60, 67],
  [41, 48, 53, 57, 64],
  [43, 50, 55, 59, 62],
];

function note(start, length, midi, amplitude, pan, kind) {
  const frequency = 440 * 2 ** ((midi - 69) / 12);
  const offset = Math.round(start * rate);
  const end = Math.min(samples - offset, Math.round(length * rate));
  const l = Math.sqrt((1 - pan) / 2);
  const r = Math.sqrt((1 + pan) / 2);
  for (let n = 0; n < end; n++) {
    const t = n / rate;
    const envelope =
      kind === "pad"
        ? Math.min(1, t / 0.85) * Math.min(1, (length - t) / 1.2)
        : (1 - Math.exp(-t * 140)) *
          Math.exp(-t * 3.8) *
          Math.min(1, (length - t) / 0.1);
    const phase = tau * frequency * t;
    const value =
      kind === "pad"
        ? Math.sin(phase) * 0.72 +
          Math.sin(phase * 1.0015) * 0.21 +
          Math.sin(phase * 2) * 0.07
        : Math.sin(phase) +
          Math.sin(phase * 2) * 0.24 * Math.exp(-t * 5) +
          Math.sin(phase * 3) * 0.08;
    left[offset + n] += value * envelope * amplitude * l;
    right[offset + n] += value * envelope * amplitude * r;
  }
}

for (let bar = 0; bar < 9; bar++) {
  const chord = chords[bar % 4];
  chord.forEach((midi, index) =>
    note(bar * 4, 5.2, midi, 0.023, (index - 2) * 0.26, "pad"),
  );
  const motif = [2, 3, 4, 3, 1, 2];
  for (let step = 0; step < motif.length; step++) {
    const start = bar * 4 + [0.5, 1.25, 2, 2.5, 3.25, 3.5][step];
    if (start > 34) continue;
    const midi = chord[motif[step]] + 12;
    note(start, 2.2, midi, 0.035, step % 2 ? 0.32 : -0.32, "pluck");
    note(start + 0.25, 1.6, midi, 0.008, step % 2 ? -0.5 : 0.5, "pluck");
  }
}
chords[0].forEach((midi, index) =>
  note(34, 6, midi, 0.028, (index - 2) * 0.25, "pad"),
);
[72, 76, 79, 83].forEach((midi, index) =>
  note(34.3 + index * 0.17, 3, midi, 0.043, (index - 1.5) * 0.2, "pluck"),
);

// Soft accent notes land on the five scene boundaries.
[5.6, 12.2, 19.8, 27.4, 34].forEach((time, index) =>
  note(time, 1.8, [79, 76, 79, 74, 72][index], 0.025, 0, "pluck"),
);
let peak = 0;
for (let i = 0; i < samples; i++) {
  const t = i / rate;
  const fade = Math.min(1, t / 1.5, (seconds - t) / 2);
  left[i] *= fade;
  right[i] *= fade;
  peak = Math.max(peak, Math.abs(left[i]), Math.abs(right[i]));
}
const gain = 0.55 / peak;
const buffer = Buffer.alloc(44 + samples * 4);
buffer.write("RIFF", 0);
buffer.writeUInt32LE(buffer.length - 8, 4);
buffer.write("WAVEfmt ", 8);
buffer.writeUInt32LE(16, 16);
buffer.writeUInt16LE(1, 20);
buffer.writeUInt16LE(2, 22);
buffer.writeUInt32LE(rate, 24);
buffer.writeUInt32LE(rate * 4, 28);
buffer.writeUInt16LE(4, 32);
buffer.writeUInt16LE(16, 34);
buffer.write("data", 36);
buffer.writeUInt32LE(samples * 4, 40);
for (let i = 0; i < samples; i++) {
  buffer.writeInt16LE(Math.round(left[i] * gain * 32767), 44 + i * 4);
  buffer.writeInt16LE(Math.round(right[i] * gain * 32767), 46 + i * 4);
}
writeFileSync(
  fileURLToPath(new URL("../public/atlas-score.wav", import.meta.url)),
  buffer,
);
console.log(
  "Created original score: 40 seconds, stereo, 48 kHz; peak -5.2 dBFS.",
);
