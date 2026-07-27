from __future__ import annotations

import io
import unittest
import wave
from unittest import mock

from src.audio import (
    AudioManager,
    SFX_NAMES,
    character_voice_effects,
    synthesize_sfx_wav,
)


class AudioSfxTests(unittest.TestCase):
    def test_every_declared_effect_is_deterministic_non_silent_mono_wav(self) -> None:
        for name in SFX_NAMES:
            with self.subTest(effect=name):
                first = synthesize_sfx_wav(name, sample_rate=8_000)
                second = synthesize_sfx_wav(name, sample_rate=8_000)
                self.assertEqual(first, second)
                self.assertEqual(first[:4], b"RIFF")
                with wave.open(io.BytesIO(first), "rb") as sound:
                    self.assertEqual(sound.getnchannels(), 1)
                    self.assertEqual(sound.getsampwidth(), 2)
                    self.assertEqual(sound.getframerate(), 8_000)
                    payload = sound.readframes(sound.getnframes())
                peaks = [
                    abs(int.from_bytes(payload[index:index + 2], "little", signed=True))
                    for index in range(0, len(payload), 2)
                ]
                self.assertGreater(max(peaks), 1_000)

    def test_character_voice_routes_are_distinct_and_complete(self) -> None:
        self.assertEqual(character_voice_effects("black_dave", "chief"), ("dave_chief",))
        self.assertEqual(character_voice_effects("shelly", "chief"), ("shelly_chief",))
        self.assertEqual(character_voice_effects("black_dave", "downed"), ("dave_downed",))
        self.assertEqual(character_voice_effects("shelly", "downed"), ("shelly_downed",))
        self.assertEqual(len(character_voice_effects("black_dave", "grunt")), 2)
        self.assertEqual(len(character_voice_effects("shelly", "grunt")), 2)
        with self.assertRaises(KeyError):
            character_voice_effects("unknown", "chief")

    def test_voice_playback_round_robins_grunts_but_not_one_shot_calls(self) -> None:
        manager = AudioManager()
        with mock.patch.object(manager, "play_sfx", return_value=True) as play:
            self.assertTrue(manager.play_character_voice("black_dave", "grunt"))
            self.assertTrue(manager.play_character_voice("black_dave", "grunt"))
            self.assertTrue(manager.play_character_voice("black_dave", "grunt"))
            self.assertTrue(manager.play_character_voice("shelly", "chief"))
        self.assertEqual(
            play.call_args_list,
            [
                mock.call("dave_grunt_1"),
                mock.call("dave_grunt_2"),
                mock.call("dave_grunt_1"),
                mock.call("shelly_chief"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
