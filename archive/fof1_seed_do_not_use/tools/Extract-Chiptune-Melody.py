"""Render the dominant melodic contour of a song as a deliberately lo-fi OGG.

This is intentionally a small, offline tool: it makes a menu-friendly
monophonic lead without redistributing or retaining the original full mix.
Requires FFmpeg and NumPy; the shipped game only needs the resulting OGG.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np


ANALYSIS_RATE = 8_000
OUTPUT_RATE = 11_025


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "FFmpeg failed without a diagnostic.")


def _extract_melody(samples: np.ndarray) -> tuple[np.ndarray, int]:
    frame_size, hop = 2048, 256
    if len(samples) < frame_size:
        return np.zeros(1, dtype=np.float32), hop
    window = np.hanning(frame_size).astype(np.float32)
    frequencies = np.fft.rfftfreq(frame_size, 1.0 / ANALYSIS_RATE)
    candidates = np.arange(45, 89)
    note_frequencies = 440.0 * np.power(2.0, (candidates - 69) / 12.0)
    notes: list[float] = []
    previous = 0.0
    for start in range(0, len(samples) - frame_size, hop):
        frame = samples[start : start + frame_size]
        energy = float(np.sqrt(np.mean(frame * frame)))
        spectrum = np.abs(np.fft.rfft(frame * window))
        scores = []
        for frequency in note_frequencies:
            harmonics = frequency * np.array((1.0, 2.0, 3.0, 4.0))
            bins = np.clip(np.searchsorted(frequencies, harmonics), 1, len(spectrum) - 1)
            scores.append(float(spectrum[bins[0]] + spectrum[bins[1]] * 0.55 + spectrum[bins[2]] * 0.28 + spectrum[bins[3]] * 0.12))
        best_index = int(np.argmax(scores))
        confidence = scores[best_index] / max(1e-6, float(np.median(scores)))
        note = float(candidates[best_index]) if energy > 0.012 and confidence > 2.0 else 0.0
        if note and previous:
            while note - previous > 8:
                note -= 12
            while previous - note > 8:
                note += 12
        if note:
            previous = note
        notes.append(note)
    contour = np.asarray(notes, dtype=np.float32)
    # A short median removes one-frame octave glitches without flattening runs.
    for index in range(2, max(2, len(contour) - 2)):
        windowed = contour[index - 2 : index + 3]
        voiced = windowed[windowed > 0]
        if len(voiced) >= 3:
            contour[index] = float(np.median(voiced))
    return contour, hop


def _render_pulse(contour: np.ndarray, hop: int, duration: float) -> np.ndarray:
    output_length = int(duration * OUTPUT_RATE)
    positions = np.minimum(len(contour) - 1, (np.arange(output_length) * ANALYSIS_RATE // OUTPUT_RATE // hop).astype(int))
    notes = contour[positions]
    frequencies = np.where(notes > 0, 440.0 * np.power(2.0, (notes - 69.0) / 12.0), 0.0)
    phase = np.cumsum(frequencies / OUTPUT_RATE)
    # Narrow pulse + a little triangle body reads as an 8-bit melody, not a
    # bit-crushed version of the original recording.
    pulse = np.where((phase % 1.0) < 0.28, 1.0, -1.0)
    triangle = 1.0 - 4.0 * np.abs((phase % 1.0) - 0.5)
    amplitude = np.where(frequencies > 0, 0.42, 0.0)
    transitions = np.r_[True, np.diff(notes) != 0]
    fade = max(1, int(OUTPUT_RATE * 0.008))
    for index in np.flatnonzero(transitions):
        amplitude[index : min(output_length, index + fade)] *= np.linspace(0.0, 1.0, min(fade, output_length - index))
    return np.clip((pulse * 0.78 + triangle * 0.22) * amplitude, -0.8, 0.8).astype(np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a chiptune-style melody from an audio file.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--duration", type=float, default=90.0)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    if not args.input.is_file() or args.duration <= 0:
        raise SystemExit("Input must be a file and --duration must be positive.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fades-melody-") as temporary:
        raw = Path(temporary) / "source.raw"
        wav = Path(temporary) / "melody.wav"
        _run([args.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(args.input), "-t", str(args.duration), "-vn", "-ac", "1", "-ar", str(ANALYSIS_RATE), "-f", "s16le", "-y", str(raw)])
        samples = np.fromfile(raw, dtype="<i2").astype(np.float32) / 32768.0
        contour, hop = _extract_melody(samples)
        rendered = _render_pulse(contour, hop, min(args.duration, len(samples) / ANALYSIS_RATE))
        with wave.open(str(wav), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(OUTPUT_RATE)
            output.writeframes((rendered * 32767.0).astype("<i2").tobytes())
        _run([args.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(wav), "-af", "acrusher=bits=4:samples=8:mix=1:mode=lin:aa=0,alimiter=limit=0.75", "-ac", "1", "-ar", str(OUTPUT_RATE), "-c:a", "libvorbis", "-q:a", "5", "-y", str(args.output)])
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
