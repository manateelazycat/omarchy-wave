# SPDX-FileCopyrightText: 2026 ManateeLazyCat
# SPDX-License-Identifier: GPL-3.0-only

import array
import math
import unittest

from wave_backend import BAND_COUNT, FFT_SIZE, RATE, Spectrum, empty_screens


def pcm(frequency=440, amplitude=0.1, antiphase=False):
    values = array.array("f")
    for i in range(FFT_SIZE):
        value = amplitude * math.sin(2 * math.pi * frequency * i / RATE)
        values.extend((value, -value if antiphase else value))
    return values.tobytes()


def monitor(name="DP-1", workspace=1, x=0, **extra):
    return {"name": name, "id": 0, "x": x, "y": 0, "width": 1920, "height": 1080,
            "scale": 1, "activeWorkspace": {"id": workspace}, "specialWorkspace": {"id": 0}, **extra}


def client(workspace=1, at=None, **extra):
    return {"workspace": {"id": workspace}, "at": at or [0, 0], "size": [800, 600],
            "mapped": True, "hidden": False, "visible": True, **extra}


class SpectrumTests(unittest.TestCase):
    def test_silence_and_short_frames(self):
        spectrum = Spectrum()
        self.assertEqual(spectrum.analyze(pcm(amplitude=0)), ([0.0] * BAND_COUNT, 0.0))
        self.assertEqual(spectrum.analyze(b"\0" * 8), ([0.0] * BAND_COUNT, 0.0))

    def test_noise_floor_does_not_activate_animation(self):
        self.assertEqual(Spectrum().analyze(pcm(amplitude=0.0002))[1], 0)

    def test_peak_moves_with_frequency(self):
        bass, _ = Spectrum().analyze(pcm(frequency=90))
        treble, _ = Spectrum().analyze(pcm(frequency=3500))
        self.assertLess(bass.index(max(bass)), treble.index(max(treble)))
        self.assertGreater(max(bass), 0.1)
        self.assertGreater(max(treble), 0.1)

    def test_volume_changes_height(self):
        quiet, quiet_level = Spectrum().analyze(pcm(amplitude=0.01))
        loud, loud_level = Spectrum().analyze(pcm(amplitude=0.3))
        self.assertGreater(loud_level, quiet_level)
        self.assertGreater(max(loud), max(quiet))

    def test_stereo_antiphase_does_not_cancel(self):
        regular = Spectrum().analyze(pcm())
        antiphase = Spectrum().analyze(pcm(antiphase=True))
        self.assertEqual(regular, antiphase)

    def test_nonfinite_input_is_discarded(self):
        data = array.array("f", [float("nan")] * FFT_SIZE * 2).tobytes()
        self.assertEqual(Spectrum().analyze(data)[1], 0)


class WorkspaceTests(unittest.TestCase):
    def test_each_monitor_is_independent(self):
        screens = empty_screens([monitor(), monitor("DP-2", 2, 1920)], [client()])
        self.assertEqual(screens, {"DP-1": False, "DP-2": True})

    def test_other_workspace_does_not_block(self):
        self.assertTrue(empty_screens([monitor()], [client(workspace=5)])["DP-1"])

    def test_floating_and_pinned_windows_block(self):
        self.assertFalse(empty_screens([monitor()], [client(floating=True)])["DP-1"])
        self.assertFalse(empty_screens([monitor()], [client(workspace=5, pinned=True)])["DP-1"])

    def test_special_workspace_is_visible(self):
        screen = monitor(specialWorkspace={"id": -99})
        self.assertFalse(empty_screens([screen], [client(workspace=-99)])["DP-1"])
        self.assertTrue(empty_screens([monitor()], [client(workspace=-99)])["DP-1"])

    def test_hidden_and_unmapped_clients_do_not_block(self):
        self.assertTrue(empty_screens([monitor()], [client(hidden=True), client(mapped=False)])["DP-1"])

    def test_floating_window_overlapping_two_screens_blocks_both(self):
        screens = [monitor(), monitor("DP-2", 2, 1920)]
        occupied = empty_screens(screens, [client(at=[1750, 100], floating=True)])
        self.assertEqual(occupied, {"DP-1": False, "DP-2": False})

    def test_disabled_and_sleeping_screens_are_excluded(self):
        self.assertEqual(empty_screens([monitor(disabled=True), monitor(dpmsStatus=False)], []), {})

    def test_rotation_and_scaling_use_logical_geometry(self):
        screen = monitor(transform=1, scale=2)
        self.assertFalse(empty_screens([screen], [client(at=[500, 700])])["DP-1"])
        self.assertTrue(empty_screens([screen], [client(at=[550, 100])])["DP-1"])


if __name__ == "__main__":
    unittest.main()
