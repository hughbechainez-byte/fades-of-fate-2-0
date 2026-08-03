"""Resilient music and synthesized arcade sound effects.

The module imports without pygame and stays usable when Windows has no active
audio device.  Game code can therefore call the module-level helpers without
special-case guards; playback methods simply return ``False`` while muted.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import io
import math
import os
from pathlib import Path
import random
import sys
import threading
import weakref
import wave
from typing import Any, Optional

from .config import content_root

try:
    from .logger import breadcrumb
except (ImportError, ValueError):
    try:
        from logger import breadcrumb
    except ImportError:
        def breadcrumb(_event: str, **_details: Any) -> None:
            return None


SFX_NAMES = (
    "punch",
    "heavy_hit",
    "hit",
    "whoosh",
    "bb_gun",
    "pickup",
    "jump",
    "land",
    "dodge",
    "super",
    "dog",
    "chief_bite",
    "laugh",
    "menu",
    "dave_grunt_1",
    "dave_grunt_2",
    "dave_downed",
    "dave_chief",
    "shelly_grunt_1",
    "shelly_grunt_2",
    "shelly_downed",
    "shelly_chief",
    "enemy_grunt",
    "enemy_downed",
)
BGM_TRACKS = {"second_street": "second_street_loop.wav"}
AUDIO_ASSET_ENV = "FADES_OF_FATE_AUDIO_DIR"

CHARACTER_VOICE_SFX: dict[str, dict[str, tuple[str, ...]]] = {
    "black_dave": {
        "grunt": ("dave_grunt_1", "dave_grunt_2"),
        "hurt": ("dave_grunt_2", "dave_grunt_1"),
        "downed": ("dave_downed",),
        "chief": ("dave_chief",),
    },
    "shelly": {
        "grunt": ("shelly_grunt_1", "shelly_grunt_2"),
        "hurt": ("shelly_grunt_2", "shelly_grunt_1"),
        "downed": ("shelly_downed",),
        "chief": ("shelly_chief",),
    },
    "jermaine": {
        "grunt": ("dave_grunt_2", "dave_grunt_1"),
        "hurt": ("dave_grunt_1", "dave_grunt_2"),
        "downed": ("dave_downed",),
        "chief": ("dave_chief",),
    },
}

# Loud transient effects and voices are trimmed independently before the
# user-facing SFX volume is applied. This keeps a crowded four-player fight
# punchy without clipping the complete mix.
SFX_GAINS = {
    "heavy_hit": 0.88,
    "super": 0.82,
    "dog": 0.86,
    "chief_bite": 0.90,
    "dave_downed": 0.88,
    "shelly_downed": 0.88,
    "enemy_downed": 0.82,
}


@dataclass(frozen=True)
class AudioConfig:
    """Mixer settings that can be replaced from a future settings screen."""

    music_volume: float = 0.42
    sfx_volume: float = 0.76
    mixer_frequency: int = 44_100
    mixer_channels: int = 2
    mixer_buffer: int = 512
    synth_frequency: int = 22_050


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _assets_directory() -> Path:
    override = os.environ.get(AUDIO_ASSET_ENV)
    if override:
        return Path(override).expanduser().resolve()

    candidates: list[Path] = []
    content_root_path = content_root()
    candidates.append(content_root_path / "assets" / "audio")
    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "assets" / "audio")
    if bundle_root:
        candidates.append(Path(bundle_root) / "assets" / "audio")
    candidates.extend(
        (
            Path(__file__).resolve().parents[1] / "assets" / "audio",
            Path.cwd() / "assets" / "audio",
        )
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return candidates[0].resolve()


def _square(phase: float, duty: float = 0.5) -> float:
    return 1.0 if phase % 1.0 < duty else -1.0


def _triangle(phase: float) -> float:
    return 1.0 - 4.0 * abs((phase % 1.0) - 0.5)


def character_voice_effects(character: str, event: str) -> tuple[str, ...]:
    """Return deterministic voice variants for a character gameplay event."""

    try:
        return CHARACTER_VOICE_SFX[character][event]
    except KeyError as error:
        supported = {
            name: tuple(events)
            for name, events in CHARACTER_VOICE_SFX.items()
        }
        raise KeyError(
            f"Unknown character voice event {character!r}/{event!r}; "
            f"supported mappings: {supported}"
        ) from error


def _voice_tone(
    time: float,
    progress: float,
    pitch_start: float,
    pitch_end: float,
    formants: tuple[float, float, float],
    phase_offset: float = 0.0,
) -> float:
    """Create a compact synthetic vocal source without imitating a real voice."""

    pitch = pitch_start + (pitch_end - pitch_start) * progress
    vibrato = 1.0 + 0.018 * math.sin(math.tau * (5.1 * time + phase_offset))
    phase = time * pitch * vibrato
    glottal = (
        0.66 * math.sin(math.tau * phase)
        + 0.22 * math.sin(math.tau * phase * 2.0 + 0.18)
        + 0.10 * math.sin(math.tau * phase * 3.0 + 0.41)
        + 0.05 * math.sin(math.tau * phase * 4.0 + 0.73)
    )
    # A light additive formant layer makes the original oscillator source read
    # as a vowel while remaining fully generated and non-identifiable.
    resonance = (
        0.15 * math.sin(math.tau * formants[0] * time)
        + 0.075 * math.sin(math.tau * formants[1] * time + 0.34)
        + 0.035 * math.sin(math.tau * formants[2] * time + 0.68)
    )
    return glottal * 0.78 + resonance


def _synthesize_voice_sample(
    name: str, time: float, duration: float, noise: random.Random
) -> float:
    """Generate original grunts, downed cries, and intelligible Chief calls."""

    is_dave = name.startswith("dave_")
    is_shelly = name.startswith("shelly_")
    if not (is_dave or is_shelly or name.startswith("enemy_")):
        raise KeyError(name)

    base_pitch = 132.0 if is_dave else (207.0 if is_shelly else 154.0)
    phase_offset = 0.13 if is_shelly else 0.0
    breath = noise.uniform(-1.0, 1.0)

    if name.endswith("chief"):
        # CH onset, long EE vowel, and F release. The two pitch/formant sets
        # keep Dave and Shelly clearly distinct without using a sampled person.
        if time < 0.105:
            local = time / 0.105
            gate = math.sin(math.pi * local) ** 0.75
            return breath * gate * (0.36 + 0.24 * _square(time * 1850.0, 0.34))
        if time < duration - 0.14:
            local = (time - 0.105) / max(0.001, duration - 0.245)
            gate = math.sin(math.pi * min(1.0, local)) ** 0.42
            formants = (310.0, 2280.0, 3020.0) if is_dave else (355.0, 2440.0, 3220.0)
            return _voice_tone(
                time,
                local,
                base_pitch * 1.10,
                base_pitch * 0.92,
                formants,
                phase_offset,
            ) * gate
        local = (time - (duration - 0.14)) / 0.14
        return breath * max(0.0, 1.0 - local) ** 1.5 * 0.48

    progress = time / duration
    attack = min(1.0, progress / 0.10)
    release = max(0.0, (1.0 - progress) / 0.28)
    envelope = min(attack, release) ** 0.62
    if name.endswith("downed"):
        # A sustained open AH with falling pitch and breath gives the requested
        # downed "aghh" while keeping the source fully synthetic.
        formants = (760.0, 1120.0, 2480.0) if is_dave else (825.0, 1280.0, 2740.0)
        voice = _voice_tone(
            time,
            progress,
            base_pitch * 1.14,
            base_pitch * 0.58,
            formants,
            phase_offset,
        )
        rasp = breath * (0.07 + 0.12 * progress)
        return (voice + rasp) * envelope

    variant_two = name.endswith("_2")
    formants = (610.0, 1040.0, 2380.0) if is_dave else (700.0, 1210.0, 2670.0)
    pitch_scale = 1.08 if variant_two else 1.0
    voice = _voice_tone(
        time,
        progress,
        base_pitch * pitch_scale,
        base_pitch * (0.72 if variant_two else 0.79),
        formants,
        phase_offset,
    )
    return (voice + breath * 0.09) * envelope


def _synthesize_sample(name: str, time: float, duration: float, noise: random.Random) -> float:
    progress = time / duration
    remaining = max(0.0, 1.0 - progress)

    if name == "punch":
        frequency = 145.0 - 80.0 * progress
        body = math.sin(math.tau * frequency * time) * remaining**2
        crack = noise.uniform(-1.0, 1.0) * remaining**5
        return 0.75 * body + 0.45 * crack

    if name == "hit":
        body = math.sin(math.tau * (88.0 - 28.0 * progress) * time)
        crack = noise.uniform(-1.0, 1.0)
        metallic = _square(time * 410.0, 0.28)
        return (0.55 * body + 0.55 * crack + 0.18 * metallic) * remaining**3

    if name == "heavy_hit":
        low = math.sin(math.tau * (72.0 - 24.0 * progress) * time)
        crack = noise.uniform(-1.0, 1.0)
        return (0.72 * low + 0.54 * crack) * remaining**2.6

    if name == "whoosh":
        sweep = noise.uniform(-1.0, 1.0) * math.sin(math.pi * progress)
        whistle = math.sin(math.tau * (360.0 + 980.0 * progress) * time)
        return (0.68 * sweep + 0.20 * whistle) * math.sin(math.pi * progress)

    if name == "bb_gun":
        snap = noise.uniform(-1.0, 1.0) * remaining**12
        spring = math.sin(math.tau * (940.0 - 520.0 * progress) * time) * remaining**5
        return 0.82 * snap + 0.42 * spring

    if name == "pickup":
        note = 740.0 if progress < 0.45 else 1110.0
        return (0.65 * _triangle(time * note) + 0.25 * _square(time * note, 0.28)) * remaining**1.4

    if name == "jump":
        frequency = 260.0 + 680.0 * progress**1.3
        phase = time * frequency
        return (0.72 * _square(phase, 0.35) + 0.28 * _triangle(phase * 0.5)) * (
            math.sin(math.pi * progress) ** 0.55
        )

    if name == "land":
        body = math.sin(math.tau * (92.0 - 44.0 * progress) * time)
        dust = noise.uniform(-1.0, 1.0)
        return (0.64 * body + 0.31 * dust) * remaining**3.2

    if name == "dodge":
        sweep = noise.uniform(-1.0, 1.0)
        tone = math.sin(math.tau * (510.0 + 620.0 * progress) * time)
        return (0.58 * sweep + 0.22 * tone) * math.sin(math.pi * progress) * remaining**0.3

    if name == "super":
        sweep = 54.0 + 42.0 * progress
        wave_body = math.sin(math.tau * sweep * time + 7.0 * math.sin(time * 9.0))
        pulse = _square(time * (11.0 + 5.0 * progress), 0.62)
        grit = noise.uniform(-1.0, 1.0) * 0.16
        return (0.78 * wave_body + 0.18 * pulse + grit) * remaining**0.75

    if name == "dog":
        burst_position = time % 0.24
        gate = max(0.0, 1.0 - burst_position / 0.18) ** 1.6
        throat = 128.0 + 18.0 * math.sin(math.tau * 22.0 * time)
        growl = _square(time * throat, 0.42)
        breath = noise.uniform(-1.0, 1.0)
        return (0.72 * growl + 0.38 * breath) * gate * remaining**0.35

    if name == "chief_bite":
        bark_gate = max(0.0, 1.0 - progress) ** 1.25
        throat = _square(time * (154.0 - 24.0 * progress), 0.44)
        snap = noise.uniform(-1.0, 1.0) * remaining**8
        return (0.66 * throat + 0.50 * snap) * bark_gate

    if name == "laugh":
        syllable = int(time / 0.13)
        local = (time % 0.13) / 0.13
        gate = math.sin(math.pi * local) ** 0.7
        frequency = 205.0 + syllable * 13.0 + 25.0 * math.sin(math.tau * local)
        voice = 0.65 * _square(time * frequency, 0.46)
        voice += 0.35 * _triangle(time * frequency * 0.5)
        return voice * gate * remaining**0.3

    if name == "menu":
        frequency = 690.0 if progress < 0.48 else 920.0
        return _square(time * frequency, 0.25) * remaining**1.8

    if name.startswith(("dave_", "shelly_", "enemy_")):
        return _synthesize_voice_sample(name, time, duration, noise)

    raise KeyError(f"Unknown synthesized sound effect: {name}")


def _sfx_duration(name: str) -> float:
    return {
        "punch": 0.16,
        "heavy_hit": 0.25,
        "hit": 0.22,
        "whoosh": 0.21,
        "bb_gun": 0.16,
        "pickup": 0.24,
        "jump": 0.29,
        "land": 0.20,
        "dodge": 0.24,
        "super": 1.10,
        "dog": 0.68,
        "chief_bite": 0.34,
        "laugh": 0.78,
        "menu": 0.12,
        "dave_grunt_1": 0.29,
        "dave_grunt_2": 0.34,
        "dave_downed": 0.96,
        "dave_chief": 0.72,
        "shelly_grunt_1": 0.28,
        "shelly_grunt_2": 0.35,
        "shelly_downed": 1.02,
        "shelly_chief": 0.76,
        "enemy_grunt": 0.31,
        "enemy_downed": 0.82,
    }[name]


def synthesize_sfx_wav(name: str, sample_rate: int = 22_050) -> bytes:
    """Return a deterministic in-memory WAV for one of :data:`SFX_NAMES`."""

    if name not in SFX_NAMES:
        raise KeyError(f"Unknown sound effect {name!r}; choose from {SFX_NAMES}")
    if sample_rate < 8_000:
        raise ValueError("sample_rate must be at least 8000 Hz")

    duration = _sfx_duration(name)
    frame_count = max(1, round(duration * sample_rate))
    seed = sum((index + 1) * ord(char) for index, char in enumerate(name))
    noise = random.Random(seed)
    pcm = array("h")
    for frame in range(frame_count):
        value = _synthesize_sample(name, frame / sample_rate, duration, noise)
        value = math.tanh(value * 1.15) / math.tanh(1.15)
        # Preserve vocal detail; arcade effects retain coarser amplitude steps.
        levels = 2047.0 if name.startswith(("dave_", "shelly_", "enemy_")) else 63.0
        value = round(_clamp(value) * levels) / levels
        pcm.append(round(value * 30_500.0))

    if sys.byteorder != "little":
        pcm.byteswap()
    target = io.BytesIO()
    with wave.open(target, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())
    return target.getvalue()


class AudioManager:
    """Small, failure-tolerant facade over ``pygame.mixer``."""

    # ``pygame.mixer.music`` is process-global even when more than one game or
    # AudioManager object exists. Track its logical owner at the same scope so
    # a second state/controller cannot accidentally create a stale handoff.
    _music_lock = threading.RLock()
    _music_owner: Optional[weakref.ReferenceType["AudioManager"]] = None
    _music_source: Optional[str] = None

    def __init__(
        self,
        config: Optional[AudioConfig] = None,
        assets_directory: Optional[Path] = None,
    ) -> None:
        self.config = config or AudioConfig()
        self.assets_directory = (assets_directory or _assets_directory()).resolve()
        self.available = False
        self.status_reason = "not initialized"
        self.current_track: Optional[str] = None
        self._music_volume = _clamp(self.config.music_volume, 0.0, 1.0)
        self._sfx_volume = _clamp(self.config.sfx_volume, 0.0, 1.0)
        self._initialized = False
        self._pygame: Any = None
        self._sounds: dict[str, Any] = {}
        self._voice_indices: dict[tuple[str, str], int] = {}

    def initialize(self) -> bool:
        """Initialize pygame's mixer and prebuild all sound effects."""

        if self._initialized:
            return self.available
        self._initialized = True
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame

            self._pygame = pygame
            if pygame.mixer.get_init() is None:
                pygame.mixer.pre_init(
                    frequency=self.config.mixer_frequency,
                    size=-16,
                    channels=self.config.mixer_channels,
                    buffer=self.config.mixer_buffer,
                )
                pygame.mixer.init()
            pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))

            for name in SFX_NAMES:
                data = synthesize_sfx_wav(name, self.config.synth_frequency)
                sound = pygame.mixer.Sound(file=io.BytesIO(data))
                sound.set_volume(self._effect_volume(name))
                self._sounds[name] = sound

            self.available = True
            self.status_reason = "ready"
            breadcrumb(
                "audio_initialized",
                mixer=pygame.mixer.get_init(),
                sfx=list(SFX_NAMES),
                assets=str(self.assets_directory),
            )
        except Exception as error:
            self.available = False
            self.status_reason = f"{type(error).__name__}: {error}"
            self._sounds.clear()
            breadcrumb("audio_unavailable", reason=self.status_reason)
        return self.available

    def music_path(self, track: str = "second_street") -> Path:
        """Resolve a named original background track."""

        try:
            filename = BGM_TRACKS[track]
        except KeyError as error:
            raise KeyError(
                f"Unknown music track {track!r}; choose from {tuple(BGM_TRACKS)}"
            ) from error
        return self.assets_directory / filename

    def play_music(self, track: str = "second_street", *, loop: bool = True) -> bool:
        """Load and play an original background track; return success."""

        if not self.initialize():
            return False
        path = self.music_path(track)
        if not path.is_file():
            self.status_reason = f"music file not found: {path}"
            breadcrumb("music_missing", track=track, path=str(path))
            return False
        try:
            source = str(path.resolve())
            if self._adopt_existing_music(source, track):
                breadcrumb("music_already_playing", track=track)
                return True
            with self._music_lock:
                self._stop_music_immediately()
                self._pygame.mixer.music.load(str(path))
                self._pygame.mixer.music.set_volume(self._music_volume)
                self._pygame.mixer.music.play(-1 if loop else 0)
                self._claim_music(source, track)
            breadcrumb("music_started", track=track, loop=loop)
            return True
        except Exception as error:
            self.status_reason = f"{type(error).__name__}: {error}"
            breadcrumb("music_failed", track=track, reason=self.status_reason)
            return False

    def play_music_file(self, filename: str | Path, *, loop: bool = True) -> bool:
        """Play a user-selectable WAV/OGG/MP3 file from the external audio folder."""

        if not self.initialize():
            return False
        path = Path(filename)
        if not path.is_absolute():
            path = self.assets_directory / path
        if not path.is_file():
            self.status_reason = f"music file not found: {path}"
            breadcrumb("music_missing", filename=str(filename), path=str(path))
            return False
        try:
            source = str(path.resolve())
            if self._adopt_existing_music(source, path.name):
                breadcrumb("music_already_playing", filename=path.name)
                return True
            # pygame exposes one global streaming-music channel.  Stop it
            # explicitly before loading a replacement: fadeout(0) is not a
            # reliable hard stop on every Windows mixer backend.
            with self._music_lock:
                self._stop_music_immediately()
                self._pygame.mixer.music.load(str(path))
                self._pygame.mixer.music.set_volume(self._music_volume)
                self._pygame.mixer.music.play(-1 if loop else 0)
                self._claim_music(source, path.name)
            breadcrumb("music_started", filename=path.name, loop=loop)
            return True
        except Exception as error:
            self.status_reason = f"{type(error).__name__}: {error}"
            breadcrumb("music_failed", filename=str(filename), reason=self.status_reason)
            return False

    def _music_is_busy(self) -> bool:
        """Return the stream state without making mock/no-audio paths brittle."""

        if not self.available or self._pygame is None:
            return False
        get_busy = getattr(self._pygame.mixer.music, "get_busy", None)
        if not callable(get_busy):
            return False
        try:
            return bool(get_busy())
        except Exception:
            return False

    def _stop_music_immediately(self) -> None:
        """Hard-stop the singleton music stream before a track handoff."""

        if not self.available or self._pygame is None:
            return
        with self._music_lock:
            music = self._pygame.mixer.music
            music.stop()
            unload = getattr(music, "unload", None)
            if callable(unload):
                try:
                    unload()
                except Exception:
                    # Older SDL_mixer builds can reject unload despite a successful
                    # stop.  Loading the replacement remains safe in that case.
                    pass
            owner = self._music_owner() if self._music_owner is not None else None
            if owner is not None:
                owner.current_track = None
            type(self)._music_owner = None
            type(self)._music_source = None
            self.current_track = None

    def _same_music_stream(self, other: "AudioManager") -> bool:
        if self._pygame is None or other._pygame is None:
            return False
        try:
            return self._pygame.mixer.music is other._pygame.mixer.music
        except AttributeError:
            return False

    def _adopt_existing_music(self, source: str, display_name: str) -> bool:
        """Adopt the singleton stream without restarting an identical track."""

        with self._music_lock:
            owner = self._music_owner() if self._music_owner is not None else None
            if (
                owner is not None
                and self._music_source == source
                and self._same_music_stream(owner)
                and self._music_is_busy()
            ):
                owner.current_track = None
                self._claim_music(source, display_name)
                return True
            return False

    def _claim_music(self, source: str, display_name: str) -> None:
        owner = self._music_owner() if self._music_owner is not None else None
        if owner is not None and owner is not self:
            owner.current_track = None
        type(self)._music_owner = weakref.ref(self)
        type(self)._music_source = source
        self.current_track = display_name

    def _effect_volume(self, name: str) -> float:
        return _clamp(self._sfx_volume * float(SFX_GAINS.get(name, 1.0)), 0.0, 1.0)

    def play_sfx(self, name: str) -> bool:
        """Play a synthesized effect; unknown names raise ``KeyError``."""

        if name not in SFX_NAMES:
            raise KeyError(f"Unknown sound effect {name!r}; choose from {SFX_NAMES}")
        if not self.initialize():
            return False
        try:
            channel = self._sounds[name].play()
            if channel is None:
                self.status_reason = "no free mixer channel"
                return False
            return True
        except Exception as error:
            self.status_reason = f"{type(error).__name__}: {error}"
            breadcrumb("sfx_failed", effect=name, reason=self.status_reason)
            return False

    def play_character_voice(self, character: str, event: str) -> bool:
        """Play an original voice event, round-robining meaningful variants."""

        variants = character_voice_effects(character, event)
        key = (character, event)
        index = self._voice_indices.get(key, 0)
        effect = variants[index % len(variants)]
        played = self.play_sfx(effect)
        if played:
            self._voice_indices[key] = index + 1
            breadcrumb(
                "character_voice_played",
                character=character,
                voice_event=event,
                effect=effect,
            )
        return played

    def set_music_volume(self, volume: float) -> None:
        """Set live music volume in the inclusive range 0.0 to 1.0."""

        value = _clamp(float(volume), 0.0, 1.0)
        self._music_volume = value
        if self.initialize():
            self._pygame.mixer.music.set_volume(value)

    def set_sfx_volume(self, volume: float) -> None:
        """Set all synthesized effect volumes in the range 0.0 to 1.0."""

        value = _clamp(float(volume), 0.0, 1.0)
        self._sfx_volume = value
        if self.initialize():
            for name, sound in self._sounds.items():
                sound.set_volume(self._effect_volume(name))

    def pause_music(self) -> None:
        if self.available:
            self._pygame.mixer.music.pause()

    def resume_music(self) -> None:
        if self.available:
            self._pygame.mixer.music.unpause()

    def stop_music(self, fade_ms: int = 250) -> None:
        if self.available:
            if int(fade_ms) <= 0:
                self._stop_music_immediately()
            else:
                self._pygame.mixer.music.fadeout(int(fade_ms))
                owner = self._music_owner() if self._music_owner is not None else None
                if owner is not None:
                    owner.current_track = None
                type(self)._music_owner = None
                type(self)._music_source = None
        self.current_track = None

    def shutdown(self) -> None:
        """Release mixer resources.  The manager can be initialized again."""

        if self._pygame is not None:
            try:
                self._pygame.mixer.stop()
                self._pygame.mixer.music.stop()
                self._pygame.mixer.quit()
            except Exception:
                pass
        owner = self._music_owner() if self._music_owner is not None else None
        if owner is not None:
            owner.current_track = None
        type(self)._music_owner = None
        type(self)._music_source = None
        self.available = False
        self._initialized = False
        self._sounds.clear()
        self._voice_indices.clear()
        self.current_track = None
        self.status_reason = "shut down"
        breadcrumb("audio_shutdown")


_DEFAULT_AUDIO: Optional[AudioManager] = None


def get_audio() -> AudioManager:
    """Return the process-wide audio manager."""

    global _DEFAULT_AUDIO
    if _DEFAULT_AUDIO is None:
        _DEFAULT_AUDIO = AudioManager()
    return _DEFAULT_AUDIO


def initialize_audio() -> bool:
    """Initialize the default manager; safe to call repeatedly."""

    return get_audio().initialize()


def play_music(track: str = "second_street", *, loop: bool = True) -> bool:
    return get_audio().play_music(track, loop=loop)


def play_sfx(name: str) -> bool:
    return get_audio().play_sfx(name)


def play_character_voice(character: str, event: str) -> bool:
    return get_audio().play_character_voice(character, event)


def shutdown_audio() -> None:
    get_audio().shutdown()
