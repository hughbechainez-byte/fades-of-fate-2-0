#!/usr/bin/env python3
"""Generate the original looping Second Street chiptune with no dependencies."""

from __future__ import annotations

import argparse
from array import array
import math
from pathlib import Path
import random
import sys
import wave


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "audio"
    / "second_street_loop.wav"
)


def _midi(note: int) -> float:
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def _oscillator(kind: str, phase: float, duty: float = 0.5) -> float:
    position = phase % 1.0
    if kind == "pulse":
        return 1.0 if position < duty else -1.0
    if kind == "triangle":
        return 1.0 - 4.0 * abs(position - 0.5)
    if kind == "saw":
        return 2.0 * position - 1.0
    raise ValueError(f"Unknown oscillator: {kind}")


def _add_tone(
    mix: list[float],
    sample_rate: int,
    start: float,
    duration: float,
    frequency: float,
    amplitude: float,
    kind: str,
    duty: float = 0.5,
) -> None:
    first = max(0, round(start * sample_rate))
    count = max(1, round(duration * sample_rate))
    last = min(len(mix), first + count)
    attack = min(0.008, duration * 0.15)
    release = min(0.045, duration * 0.28)
    for frame in range(first, last):
        local = (frame - first) / sample_rate
        attack_gain = min(1.0, local / attack) if attack > 0.0 else 1.0
        remaining = duration - local
        release_gain = min(1.0, remaining / release) if release > 0.0 else 1.0
        envelope = max(0.0, min(attack_gain, release_gain))
        mix[frame] += (
            amplitude
            * envelope
            * _oscillator(kind, local * frequency, duty=duty)
        )


def _add_kick(
    mix: list[float], sample_rate: int, start: float, amplitude: float = 0.72
) -> None:
    duration = 0.17
    first = round(start * sample_rate)
    count = round(duration * sample_rate)
    phase = 0.0
    for offset in range(count):
        frame = first + offset
        if frame >= len(mix):
            break
        local = offset / sample_rate
        progress = local / duration
        frequency = 142.0 * (1.0 - progress) + 47.0
        phase += frequency / sample_rate
        envelope = max(0.0, 1.0 - progress) ** 3.0
        click = 0.22 if offset < sample_rate * 0.004 else 0.0
        mix[frame] += amplitude * envelope * math.sin(math.tau * phase) + click


def _add_noise_hit(
    mix: list[float],
    sample_rate: int,
    start: float,
    duration: float,
    amplitude: float,
    seed: int,
    bright: bool,
) -> None:
    first = round(start * sample_rate)
    count = round(duration * sample_rate)
    rng = random.Random(seed)
    previous = 0.0
    for offset in range(count):
        frame = first + offset
        if frame >= len(mix):
            break
        progress = offset / max(1, count)
        raw = rng.uniform(-1.0, 1.0)
        if bright:
            filtered = raw - previous * 0.82
        else:
            filtered = raw * 0.58 + previous * 0.42
        previous = raw
        envelope = max(0.0, 1.0 - progress) ** (5.5 if bright else 2.4)
        mix[frame] += amplitude * envelope * filtered


def build_second_street_loop(
    sample_rate: int = 22_050, bpm: float = 132.0, bars: int = 8
) -> tuple[array, float]:
    """Return signed 16-bit mono PCM and its exact duration."""

    if sample_rate < 8_000:
        raise ValueError("sample_rate must be at least 8000 Hz")
    if not 60.0 <= bpm <= 220.0:
        raise ValueError("bpm must be between 60 and 220")
    if not 1 <= bars <= 64:
        raise ValueError("bars must be between 1 and 64")

    seconds_per_beat = 60.0 / bpm
    bar_seconds = seconds_per_beat * 4.0
    duration = bar_seconds * bars
    frame_count = round(duration * sample_rate)
    duration = frame_count / sample_rate
    mix = [0.0] * frame_count

    # A minor street-groove progression: Am - F - C - G.
    roots = (45, 41, 48, 43)
    triads = (
        (57, 60, 64),
        (53, 57, 60),
        (60, 64, 67),
        (55, 59, 62),
    )
    melody = (
        69, 72, 76, 72, 67, 69, 64, -1,
        65, 69, 72, 69, 64, 65, 60, -1,
        67, 72, 76, 79, 76, 72, 67, 64,
        67, 71, 74, 71, 69, 67, 62, -1,
    )

    for bar in range(bars):
        progression = bar % 4
        bar_start = bar * bar_seconds
        root = roots[progression]

        bass_pattern = (root, root, root + 7, root, root + 12, root + 7, root, root + 7)
        for step, note in enumerate(bass_pattern):
            _add_tone(
                mix,
                sample_rate,
                bar_start + step * seconds_per_beat / 2.0,
                seconds_per_beat * 0.43,
                _midi(note),
                0.19,
                "triangle",
            )

        chord = triads[progression]
        for step in range(16):
            note = chord[step % len(chord)] + (12 if step % 4 == 3 else 0)
            _add_tone(
                mix,
                sample_rate,
                bar_start + step * seconds_per_beat / 4.0,
                seconds_per_beat * 0.17,
                _midi(note),
                0.075,
                "pulse",
                duty=0.25,
            )

        for step in range(8):
            note = melody[(bar % 4) * 8 + step]
            if note >= 0:
                _add_tone(
                    mix,
                    sample_rate,
                    bar_start + step * seconds_per_beat / 2.0,
                    seconds_per_beat * (0.38 if step % 2 else 0.44),
                    _midi(note),
                    0.105,
                    "pulse",
                    duty=0.375,
                )

        for beat in range(4):
            beat_start = bar_start + beat * seconds_per_beat
            _add_kick(mix, sample_rate, beat_start, 0.67 if beat in (0, 2) else 0.52)
            if beat in (1, 3):
                _add_noise_hit(
                    mix,
                    sample_rate,
                    beat_start,
                    0.19,
                    0.23,
                    seed=1_000 + bar * 8 + beat,
                    bright=False,
                )
            for half in range(2):
                _add_noise_hit(
                    mix,
                    sample_rate,
                    beat_start + half * seconds_per_beat / 2.0,
                    0.055,
                    0.075 if half == 0 else 0.10,
                    seed=2_000 + bar * 16 + beat * 2 + half,
                    bright=True,
                )

    # Soft-limit, reduce to 8-bit amplitude steps, and sample-hold for a subtle
    # console crunch while retaining a broadly compatible 16-bit WAV container.
    peak = max(1e-9, max(abs(sample) for sample in mix))
    gain = min(1.0, 0.88 / peak)
    fade_frames = min(round(sample_rate * 0.008), frame_count // 2)
    pcm = array("h")
    held = 0.0
    for frame, sample in enumerate(mix):
        if frame % 2 == 0:
            shaped = math.tanh(sample * gain * 1.25) / math.tanh(1.25)
            held = round(max(-1.0, min(1.0, shaped)) * 127.0) / 127.0
        edge_gain = 1.0
        if frame < fade_frames:
            edge_gain = frame / max(1, fade_frames)
        elif frame >= frame_count - fade_frames:
            edge_gain = (frame_count - 1 - frame) / max(1, fade_frames)
        pcm.append(round(held * edge_gain * 30_500.0))

    return pcm, duration


def write_wav(path: Path, pcm: array, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_pcm = array("h", pcm)
    if sys.byteorder != "little":
        output_pcm.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(output_pcm.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the original Second Street 8-bit-style music loop."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-rate", type=int, default=22_050)
    parser.add_argument("--bpm", type=float, default=132.0)
    parser.add_argument("--bars", type=int, default=8)
    args = parser.parse_args()

    try:
        pcm, duration = build_second_street_loop(
            sample_rate=args.sample_rate, bpm=args.bpm, bars=args.bars
        )
        output = args.output.expanduser().resolve()
        write_wav(output, pcm, args.sample_rate)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Audio generation failed: {error}\n")

    print(
        f"Generated {output} "
        f"({duration:.3f}s, {args.sample_rate} Hz, mono 16-bit WAV)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

