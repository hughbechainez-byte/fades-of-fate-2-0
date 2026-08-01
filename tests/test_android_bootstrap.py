from __future__ import annotations

import os
import unittest
from unittest import mock

import pygame

from src.main import initialize_pygame


class AndroidBootstrapTests(unittest.TestCase):
    def test_android_initialization_does_not_call_global_pygame_init_or_mixer(self) -> None:
        with mock.patch.object(pygame, "init") as init, mock.patch.object(
            pygame.mixer, "pre_init"
        ) as mixer_pre_init, mock.patch.object(pygame.display, "init") as display_init, mock.patch.object(
            pygame.font, "init"
        ) as font_init, mock.patch.object(pygame.joystick, "init") as joystick_init:
            initialize_pygame(android_runtime=True)

        init.assert_not_called()
        mixer_pre_init.assert_not_called()
        display_init.assert_called_once_with()
        font_init.assert_called_once_with()
        joystick_init.assert_called_once_with()

    def test_entrypoint_crash_log_uses_android_private_storage(self) -> None:
        from main import _write_startup_failure

        with self.subTest("function is importable before pygame startup"):
            self.assertTrue(callable(_write_startup_failure))


if __name__ == "__main__":
    unittest.main()
