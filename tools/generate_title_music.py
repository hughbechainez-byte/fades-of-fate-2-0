#!/usr/bin/env python3
"""Generate the original, clean Fades of Fate title loop.

The composition and waveform are created locally from simple oscillators. No
recording, sample library, or copyrighted melody is used. OGG encoding uses a
local FFmpeg installation so the shipped asset remains compact.
"""

from __future__ import annotations

import argparse
from array import array
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

from generate_audio import _add_kick, _add_noise_hit, _add_tone, _midi


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "audio"
    / "fades_title_original.ogg"
)


def _triangle(phase: float) -> float:
    return 1.0 - 4.0 * abs((phase % 1.0) - 0.5)


def _add_warm_voice(
    mix: list[float],
    sample_rate: int,
    start: float,
    duration: float,
    frequency: float,
    amplitude: float,
    *,
    attack: float = 0.045,
    release: float = 0.12,
    triangle_mix: float = 0.24,
) -> None:
    """Add a clean sine/triangle voice with a soft, keys-like envelope."""

    first = max(0, round(start * sample_rate))
    last = min(len(mix), first + max(1, round(duration * sample_rate)))
    for frame in range(first, last):
        local = (frame - first) / sample_rate
        attack_gain = min(1.0, local / max(0.001, min(attack, duration * 0.35)))
        release_gain = min(
            1.0,
            max(0.0, duration - local) / max(0.001, min(release, duration * 0.42)),
        )
        envelope = min(attack_gain, release_gain)
        phase = local * frequency
        source = (
            (1.0 - triangle_mix) * math.sin(math.tau * phase)
            + triangle_mix * _triangle(phase)
            + 0.055 * math.sin(math.tau * phase * 2.0 + 0.31)
        )
        mix[frame] += amplitude * envelope * source


def _add_warm_bass(
    mix: list[float],
    sample_rate: int,
    start: float,
    duration: float,
    note: int,
    amplitude: float,
) -> None:
    """Add a rounded syncopated bass note with no bitcrush or sample hold."""

    frequency = _midi(note)
    first = max(0, round(start * sample_rate))
    last = min(len(mix), first + max(1, round(duration * sample_rate)))
    for frame in range(first, last):
        local = (frame - first) / sample_rate
        progress = local / max(0.001, duration)
        attack = min(1.0, local / 0.014)
        release = min(1.0, max(0.0, duration - local) / 0.075)
        envelope = min(attack, release) ** 0.72
        phase = local * frequency * (1.0 + 0.004 * math.exp(-progress * 8.0))
        source = (
            0.78 * math.sin(math.tau * phase)
            + 0.17 * _triangle(phase)
            + 0.07 * math.sin(math.tau * phase * 2.0)
        )
        mix[frame] += amplitude * envelope * source


def _swung_sixteenth(bar_start: float, step: int, beat: float, swing: float) -> float:
    pair = step // 2
    within_pair = step % 2
    return bar_start + pair * beat / 2.0 + (swing * beat / 2.0 if within_pair else 0.0)


def build_title_loop(
    sample_rate: int = 22_050,
    bpm: float = 86.0,
    bars: int = 16,
) -> tuple[array, float]:
    """Return a clean original neo-soul/jazz-influenced chip title loop."""

    if sample_rate < 8_000:
        raise ValueError("sample_rate must be at least 8000 Hz")
    if not 68.0 <= bpm <= 120.0:
        raise ValueError("bpm must be between 68 and 120")
    if bars != 16:
        raise ValueError("the evolved title arrangement is authored as exactly 16 bars")

    beat = 60.0 / bpm
    bar_seconds = beat * 4.0
    duration = bars * bar_seconds
    frames = round(duration * sample_rate)
    duration = frames / sample_rate
    mix = [0.0] * frames
    swing = 0.61

    # Original progression and close-position voicings. The inner voices move
    # mostly by step through m9, maj9, 11 and 13 colors instead of jumping as
    # block triads. No melody, recording, or artist-specific phrase is reused.
    roots = (38, 43, 36, 41, 35, 40, 33, 33, 34, 36, 33, 38, 43, 36, 33, 33)
    voicings = (
        (53, 57, 60, 64),       # Dm9
        (53, 57, 59, 64),       # G13
        (52, 55, 59, 62),       # Cmaj9
        (52, 55, 57, 60),       # Fmaj9
        (50, 53, 57, 59),       # Bm7b5
        (50, 53, 56, 59),       # E7(b9)
        (52, 55, 59, 60),       # Am9
        (55, 58, 61, 65),       # A7(b13)
        (53, 57, 60, 62),       # Bbmaj9
        (52, 57, 58, 62),       # C13
        (52, 55, 59, 60),       # Am9
        (53, 55, 57, 60, 64),   # Dm11
        (53, 57, 58, 62),       # Gm9
        (52, 57, 58, 62),       # C13
        (52, 55, 57, 60),       # Fmaj9/A
        (55, 57, 61, 65),       # A7(b13), resolving to Dm9
    )

    # A compact, singable original motif enters after the harmony is
    # established, then receives octave answers and a final turnaround.
    lead_events: dict[int, tuple[tuple[float, int, float], ...]] = {
        2: ((3.00, 69, 0.34), (3.56, 72, 0.28)),
        3: ((0.18, 74, 0.82), (1.52, 72, 0.38), (2.22, 69, 0.64), (3.32, 67, 0.30)),
        4: ((0.48, 69, 0.36), (1.22, 72, 0.30), (1.76, 74, 0.82), (3.02, 77, 0.36), (3.55, 76, 0.28)),
        5: ((0.20, 74, 0.58), (1.02, 72, 0.42), (1.76, 69, 0.78), (3.00, 67, 0.32), (3.52, 69, 0.28)),
        6: ((0.18, 72, 0.34), (0.76, 76, 0.34), (1.48, 77, 0.66), (2.50, 76, 0.32), (3.02, 74, 0.62)),
        7: ((0.16, 72, 0.58), (1.16, 69, 0.34), (1.78, 67, 0.38), (2.48, 64, 0.66), (3.52, 69, 0.25)),
        8: ((0.48, 74, 0.36), (1.20, 77, 0.30), (1.76, 81, 0.82), (3.02, 79, 0.36), (3.55, 77, 0.28)),
        9: ((0.18, 76, 0.58), (1.02, 74, 0.42), (1.76, 72, 0.78), (3.00, 69, 0.32), (3.52, 72, 0.28)),
        10: ((0.20, 72, 0.34), (0.78, 76, 0.34), (1.50, 79, 0.66), (2.52, 76, 0.32), (3.04, 74, 0.58)),
        11: ((0.16, 72, 0.72), (1.36, 69, 0.38), (2.08, 67, 0.34), (2.72, 65, 0.66), (3.58, 64, 0.22)),
        13: ((0.52, 69, 0.34), (1.22, 72, 0.28), (1.76, 74, 0.78), (3.04, 76, 0.38)),
        14: ((0.18, 77, 0.62), (1.16, 76, 0.34), (1.80, 72, 0.74), (3.04, 69, 0.42)),
        15: ((0.20, 67, 0.34), (0.78, 69, 0.34), (1.52, 72, 0.62), (2.52, 69, 0.34), (3.06, 64, 0.44)),
    }

    bass_patterns = (
        ((0.00, 0, 0.70), (0.86, 12, 0.32), (1.68, 7, 0.44), (2.52, 12, 0.52), (3.52, 99, 0.28)),
        ((0.00, 0, 0.62), (1.28, 7, 0.38), (2.06, 12, 0.58), (3.20, 7, 0.34), (3.62, 99, 0.24)),
        ((0.00, 0, 0.74), (1.54, 12, 0.34), (2.34, 7, 0.36), (3.06, 12, 0.44), (3.58, 99, 0.25)),
        ((0.00, 0, 0.66), (0.72, 7, 0.28), (1.76, 12, 0.52), (2.72, 7, 0.34), (3.54, 99, 0.26)),
    )

    for bar in range(bars):
        start = bar * bar_seconds
        chord = voicings[bar]
        root = roots[bar]
        next_root = roots[(bar + 1) % bars]

        # Lush pad plus quiet, syncopated chip-key answers.
        for voice_index, note in enumerate(chord):
            _add_warm_voice(
                mix,
                sample_rate,
                start + 0.015,
                bar_seconds - 0.045,
                _midi(note),
                0.026 if voice_index < 4 else 0.020,
                attack=0.060,
                release=0.145,
                triangle_mix=0.18,
            )
        key_hits = (0.12, 1.82, 3.08) if bar % 2 == 0 else (0.62, 2.18, 3.46)
        for hit_index, beat_position in enumerate(key_hits):
            for note in chord[-2:]:
                _add_tone(
                    mix,
                    sample_rate,
                    start + beat_position * beat,
                    beat * (0.25 if hit_index < 2 else 0.18),
                    _midi(note + (12 if bar >= 8 and hit_index == 2 else 0)),
                    0.020,
                    "pulse",
                    duty=0.25,
                )

        pattern = bass_patterns[bar % len(bass_patterns)]
        approach = next_root - 1 if next_root > root else next_root + 1
        for beat_position, offset, note_length in pattern:
            note = approach if offset == 99 else root + offset
            _add_warm_bass(
                mix,
                sample_rate,
                start + beat_position * beat,
                note_length * beat,
                note,
                0.145,
            )

        # Laid-back swung pocket. The sparse opening grows by small ghost hats
        # and kicks rather than by simply becoming louder.
        kick_steps = (0, 7, 10) if bar < 4 else ((0, 3, 7, 10, 14) if bar % 4 != 3 else (0, 6, 10, 15))
        for step in kick_steps:
            _add_kick(
                mix,
                sample_rate,
                _swung_sixteenth(start, step, beat, swing),
                0.30 if step == 0 else 0.23,
            )
        for step in (4, 12):
            snare_time = _swung_sixteenth(start, step, beat, swing) + 0.026
            _add_noise_hit(
                mix,
                sample_rate,
                snare_time,
                0.17,
                0.115,
                seed=7_000 + bar * 20 + step,
                bright=False,
            )
            _add_warm_voice(
                mix,
                sample_rate,
                snare_time,
                0.11,
                176.0,
                0.040,
                attack=0.003,
                release=0.07,
                triangle_mix=0.32,
            )
        hat_steps = range(0, 16, 2) if bar < 4 or bar == 12 else range(16)
        for step in hat_steps:
            if step % 2 and (bar + step) % 3 == 0:
                continue
            _add_noise_hit(
                mix,
                sample_rate,
                _swung_sixteenth(start, step, beat, swing),
                0.038 if step % 2 == 0 else 0.026,
                0.031 if step % 2 == 0 else 0.018,
                seed=8_000 + bar * 32 + step,
                bright=True,
            )

        for beat_position, note, note_length in lead_events.get(bar, ()):
            lead_start = start + beat_position * beat
            _add_tone(
                mix,
                sample_rate,
                lead_start,
                note_length * beat,
                _midi(note),
                0.057,
                "pulse",
                duty=0.375,
            )
            _add_warm_voice(
                mix,
                sample_rate,
                lead_start + 0.012,
                note_length * beat * 0.92,
                _midi(note - 12),
                0.018,
                attack=0.018,
                release=0.08,
                triangle_mix=0.20,
            )

    peak = max(1e-9, max(abs(sample) for sample in mix))
    gain = 0.91 / peak
    edge = min(round(sample_rate * 0.007), frames // 2)
    pcm = array("h")
    for frame, sample in enumerate(mix):
        # Gentle peak control only: no bitcrush, sample hold, or hard clipping.
        shaped = math.tanh(sample * gain * 1.04) / math.tanh(1.04)
        edge_gain = 1.0
        if frame < edge:
            edge_gain = math.sin((frame / max(1, edge)) * math.pi / 2.0) ** 2
        elif frame >= frames - edge:
            remaining = (frames - 1 - frame) / max(1, edge)
            edge_gain = math.sin(max(0.0, remaining) * math.pi / 2.0) ** 2
        pcm.append(round(max(-1.0, min(1.0, shaped)) * edge_gain * 30_500.0))
    return pcm, duration


def _write_wav(path: Path, pcm: array, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_pcm = array("h", pcm)
    if sys.byteorder != "little":
        output_pcm.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(output_pcm.tobytes())


def write_audio(path: Path, pcm: array, sample_rate: int) -> None:
    """Write WAV directly or encode OGG with the local FFmpeg binary."""

    path = path.resolve()
    if path.suffix.lower() == ".wav":
        _write_wav(path, pcm, sample_rate)
        return
    if path.suffix.lower() != ".ogg":
        raise ValueError("output must end in .wav or .ogg")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to generate an OGG asset")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fades-title-") as temporary:
        wave_path = Path(temporary) / "title.wav"
        _write_wav(wave_path, pcm, sample_rate)
        subprocess.run(
            (
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(wave_path),
                "-map_metadata",
                "-1",
                "-fflags",
                "+bitexact",
                "-c:a",
                "libvorbis",
                "-flags:a",
                "+bitexact",
                "-q:a",
                "5",
                "-serial_offset",
                "1931",
                str(path),
            ),
            check=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-rate", type=int, default=22_050)
    parser.add_argument("--bpm", type=float, default=86.0)
    parser.add_argument("--bars", type=int, default=16)
    args = parser.parse_args()
    try:
        pcm, duration = build_title_loop(args.sample_rate, args.bpm, args.bars)
        write_audio(args.output, pcm, args.sample_rate)
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        parser.exit(1, f"Title music generation failed: {error}\n")
    print(f"Generated {args.output.resolve()} ({duration:.3f}s, original clean loop)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
