# SPDX-FileCopyrightText: 2026 ManateeLazyCat
# SPDX-License-Identifier: GPL-3.0-only

import array
import contextlib
import io
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from wave_backend import BAND_COUNT, FFT_SIZE, FRAME_INTERVAL, RATE, Backend, Spectrum, empty_screens


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
        self.assertAlmostEqual(regular[1], antiphase[1], places=12)
        for a, b in zip(regular[0], antiphase[0]):
            self.assertAlmostEqual(a, b, places=12)

    def test_swapping_distinct_channels_preserves_spectrum(self):
        values = array.array("f")
        swapped = array.array("f")
        for i in range(FFT_SIZE):
            left = 0.1 * math.sin(2 * math.pi * 90 * i / RATE) + 0.03
            right = 0.07 * math.cos(2 * math.pi * 3500 * i / RATE) - 0.02
            values.extend((left, right))
            swapped.extend((right, left))
        regular = Spectrum().analyze(values.tobytes())
        reversed_channels = Spectrum().analyze(swapped.tobytes())
        self.assertAlmostEqual(regular[1], reversed_channels[1], places=12)
        for a, b in zip(regular[0], reversed_channels[0]):
            self.assertAlmostEqual(a, b, places=12)
        self.assertGreater(max(regular[0][:8]), 0.1)
        self.assertGreater(max(regular[0][-5:]), 0.1)

    def test_single_channel_audio_remains_active(self):
        original = array.array("f")
        original.frombytes(pcm())
        for channel in (0, 1):
            values = array.array("f", original)
            values[1 - channel::2] = array.array("f", [0.0] * FFT_SIZE)
            bands, level = Spectrum().analyze(values.tobytes())
            self.assertGreater(level, 0.1)
            self.assertGreater(max(bands), 0.1)

    def test_nonfinite_input_is_discarded(self):
        data = array.array("f", [float("nan")] * FFT_SIZE * 2).tobytes()
        self.assertEqual(Spectrum().analyze(data)[1], 0)


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.addCleanup(self.backend.selector.close)
        self.backend.screens = {"DP-1": True}
        self.capture = Mock()
        self.capture.read.return_value = True
        self.capture.analyze.return_value = ([0.0] * BAND_COUNT, 0.0)
        self.backend.captures = {"output": self.capture}
        self.key = SimpleNamespace(data=("pcm", "output"))

    def test_new_pcm_wakes_idle_analysis_within_one_frame(self):
        self.backend.last_sample = 10.0
        self.backend.next_emit = 11.0
        with patch("wave_backend.time.monotonic", return_value=10.01):
            self.backend.read_event(self.key)
        self.assertLessEqual(self.backend.next_emit - 10.01, FRAME_INTERVAL)
        self.assertGreaterEqual(self.backend.next_emit, 10.0 + FRAME_INTERVAL)

    def test_pcm_bursts_do_not_exceed_analysis_frame_rate(self):
        self.backend.last_sample = 10.0
        self.backend.next_emit = 11.0
        with patch("wave_backend.time.monotonic", return_value=10.001):
            for _ in range(20):
                self.backend.read_event(self.key)
        self.assertAlmostEqual(self.backend.next_emit, 10.0 + FRAME_INTERVAL)
        self.capture.analyze.assert_not_called()

    def test_unchanged_silence_only_emits_one_heartbeat_per_second(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for now in (10.0, 10.04, 10.1, 10.99, 11.0):
                self.backend.emit(now)
        packets = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(packets), 2)
        self.assertTrue(all(not packet["active"] for packet in packets))

    def test_audio_onset_and_stop_are_reported_without_waiting_for_heartbeat(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.backend.emit(10.0)
            self.capture.analyze.return_value = ([0.5] * BAND_COUNT, 0.5)
            self.backend.emit(10.04)
            self.capture.analyze.return_value = ([0.0] * BAND_COUNT, 0.0)
            self.backend.emit(10.08)
        packets = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([packet["active"] for packet in packets], [False, True, False])

    def test_workspace_changes_are_reported_during_silence(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.backend.emit(10.0)
            self.backend.screens = {"DP-1": False}
            self.backend.emit(10.01)
        packets = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(packets), 2)
        self.assertFalse(packets[-1]["screens"]["DP-1"])
        self.assertEqual(self.capture.analyze.call_count, 1)


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
