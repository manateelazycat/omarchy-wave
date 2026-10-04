#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 ManateeLazyCat
# SPDX-License-Identifier: GPL-3.0-only

"""System-output spectrum and visible-workspace state; standard library only."""

from __future__ import annotations

import array
import cmath
import json
import math
import os
from pathlib import Path
import selectors
import signal
import socket
import subprocess
import sys
import time

RATE = 12000
FFT_SIZE = 512
BAND_COUNT = 24
FRAME_BYTES = FFT_SIZE * 2 * 4
NOISE_FLOOR = 0.0008
FRAME_INTERVAL = 1 / 30
HEARTBEAT_INTERVAL = 1.0


def command_json(command: list[str]):
    result = subprocess.run(command, capture_output=True, timeout=2, check=True)
    return json.loads(result.stdout)


def empty_screens(monitors: list[dict], clients: list[dict]) -> dict[str, bool]:
    """Use active workspaces plus actual geometry, including pins and scratchpads.

    Hyprland's client `visible` flag can also be true on inactive workspaces,
    so workspace membership must be checked independently.
    """
    live = [m for m in monitors if not m.get("disabled") and m.get("dpmsStatus", True)]
    visible_workspaces = {
        m.get(key, {}).get("id")
        for m in live for key in ("activeWorkspace", "specialWorkspace")
        if m.get(key, {}).get("id", 0) != 0
    }
    result = {}
    for monitor in live:
        scale = max(0.1, monitor.get("scale", 1))
        width, height = monitor["width"], monitor["height"]
        if monitor.get("transform", 0) % 2:
            width, height = height, width
        mx, my = monitor["x"], monitor["y"]
        right, bottom = mx + width / scale, my + height / scale
        occupied = False
        for client in clients:
            if not client.get("mapped", True) or client.get("hidden", False):
                continue
            if client.get("visible") is False:
                continue
            if not client.get("pinned") and client.get("workspace", {}).get("id") not in visible_workspaces:
                continue
            cx, cy = client.get("at", [0, 0])
            cw, ch = client.get("size", [0, 0])
            if cw > 0 and ch > 0 and cx < right and cx + cw > mx and cy < bottom and cy + ch > my:
                occupied = True
                break
        result[monitor["name"]] = not occupied
    return result


class Spectrum:
    def __init__(self):
        bits = FFT_SIZE.bit_length() - 1
        self.order = [int(f"{i:0{bits}b}"[::-1], 2) for i in range(FFT_SIZE)]
        self.window = [0.5 - 0.5 * math.cos(2 * math.pi * i / (FFT_SIZE - 1)) for i in range(FFT_SIZE)]
        self.twiddles = {
            size: [cmath.exp(-2j * math.pi * k / size) for k in range(size // 2)]
            for size in (2 ** p for p in range(1, bits + 1))
        }
        edges = [45 * (5500 / 45) ** (i / BAND_COUNT) for i in range(BAND_COUNT + 1)]
        self.ranges = [
            range(max(1, round(lo * FFT_SIZE / RATE)),
                  min(FFT_SIZE // 2, max(round(lo * FFT_SIZE / RATE) + 1, round(hi * FFT_SIZE / RATE))))
            for lo, hi in zip(edges, edges[1:])
        ]
        self.weights = [(math.sqrt(lo * hi) / 160) ** 0.28 for lo, hi in zip(edges, edges[1:])]
        self.reference = 0.008

    def fft(self, samples: list[complex]) -> list[complex]:
        mean = sum(samples) / FFT_SIZE
        data = [complex((samples[i] - mean) * self.window[i]) for i in self.order]
        for size, twiddles in self.twiddles.items():
            half = size // 2
            for start in range(0, FFT_SIZE, size):
                for k, twiddle in enumerate(twiddles):
                    even = data[start + k]
                    odd = data[start + k + half] * twiddle
                    data[start + k] = even + odd
                    data[start + k + half] = even - odd
        return data

    def analyze(self, pcm: bytes) -> tuple[list[float], float]:
        if len(pcm) < FRAME_BYTES:
            return [0.0] * BAND_COUNT, 0.0
        values = array.array("f")
        values.frombytes(pcm[-FRAME_BYTES:])
        if sys.byteorder != "little":
            values.byteswap()
        if any(not math.isfinite(v) for v in values):
            return [0.0] * BAND_COUNT, 0.0
        rms = math.sqrt(sum(v * v for v in values) / len(values))
        if rms < NOISE_FLOOR:
            self.reference = max(0.008, self.reference * 0.99)
            return [0.0] * BAND_COUNT, 0.0
        # Pack left + j*right into one FFT. Mirrored bins recover the average
        # channel power without cancelling out-of-phase stereo material.
        spectrum = self.fft([complex(values[i], values[i + 1]) for i in range(0, len(values), 2)])
        power = [(abs(spectrum[i]) ** 2 + abs(spectrum[-i]) ** 2) / 4
                 for i in range(FFT_SIZE // 2)]
        magnitudes = [
            math.sqrt(sum(power[i] for i in indexes) / len(indexes)) * 4 / FFT_SIZE * weight
            for indexes, weight in zip(self.ranges, self.weights)
        ]
        self.reference = max(0.008, max(magnitudes), self.reference * 0.992)
        level = min(1.0, math.log1p(rms * 70) / math.log1p(0.18 * 70))
        bands = [min(1.0, math.sqrt(value / self.reference) * level) for value in magnitudes]
        return bands, level


class Capture:
    def __init__(self, sink: dict):
        self.name = sink["name"]
        monitor = sink.get("monitor_source_name") or self.name + ".monitor"
        self.process = subprocess.Popen([
            "parec", "--device=" + monitor, "--raw", "--format=float32le",
            "--rate=" + str(RATE), "--channels=2", "--latency-msec=40",
            "--process-time-msec=20", "--client-name=omarchy-wave",
            "--stream-name=Omarchy Wave", "--property=media.role=production",
            "--property=stream.capture.sink=true", "--property=target.object=" + monitor,
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.buffer = bytearray()
        self.updated = 0.0
        self.spectrum = Spectrum()

    def read(self):
        data = os.read(self.process.stdout.fileno(), 65536)
        if not data:
            return False
        self.buffer.extend(data)
        # Keep complete stereo frames and only the most recent FFT window.
        excess = max(0, len(self.buffer) - FRAME_BYTES - 7)
        if excess:
            del self.buffer[:excess - excess % 8]
        self.updated = time.monotonic()
        return True

    def analyze(self, now: float):
        usable = len(self.buffer) - len(self.buffer) % 8
        if now - self.updated > 0.25 or usable < FRAME_BYTES:
            return [0.0] * BAND_COUNT, 0.0
        return self.spectrum.analyze(bytes(self.buffer[:usable]))

    def stop(self):
        stop_process(self.process)


def stop_process(process: subprocess.Popen):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=0.5)
    if process.stdout:
        process.stdout.close()


class Backend:
    def __init__(self):
        self.selector = selectors.DefaultSelector()
        self.captures: dict[str, Capture] = {}
        self.screens: dict[str, bool] = {}
        self.errors: dict[str, str] = {}
        self.hypr_socket = None
        self.subscription = None
        self.running = True
        self.desktop_due = 0.0
        self.audio_due = 0.0
        self.next_emit = 0.0
        self.last_sample = -FRAME_INTERVAL
        self.last_packet = None
        self.heartbeat_due = 0.0
        self.connect_due = 0.0

    def drop_capture(self, name: str):
        capture = self.captures.pop(name)
        self.selector.unregister(capture.process.stdout)
        capture.stop()
        self.next_emit = 0.0

    def refresh_desktop(self):
        previous = self.screens
        try:
            self.screens = empty_screens(command_json(["hyprctl", "-j", "monitors"]),
                                        command_json(["hyprctl", "-j", "clients"]))
            self.errors.pop("desktop", None)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            self.screens = {}
            self.errors["desktop"] = "Cannot read Hyprland state: " + str(error)
        if previous != self.screens:
            self.audio_due = 0.0
            self.next_emit = 0.0
        self.desktop_due = time.monotonic() + 2

    def refresh_audio(self):
        wanted = {}
        try:
            if any(self.screens.values()):
                sinks = command_json(["pactl", "-f", "json", "list", "sinks"])
                inputs = command_json(["pactl", "-f", "json", "list", "sink-inputs"])
                active_indexes = {s["sink"] for s in inputs if not s.get("corked") and not s.get("mute")}
                for sink in sinks:
                    volumes = sink.get("volume", {}).values()
                    audible = not volumes or any(v.get("value", 0) > 0 for v in volumes)
                    if sink["index"] in active_indexes and not sink.get("mute") and audible:
                        wanted[sink["name"]] = sink
            self.errors.pop("audio", None)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            self.errors["audio"] = "Cannot read PipeWire/PulseAudio outputs: " + str(error)
        for name in list(self.captures):
            if name not in wanted or self.captures[name].process.poll() is not None:
                self.drop_capture(name)
        for name, sink in wanted.items():
            if name in self.captures:
                continue
            try:
                capture = Capture(sink)
                self.captures[name] = capture
                self.selector.register(capture.process.stdout, selectors.EVENT_READ, ("pcm", name))
            except OSError as error:
                self.errors["audio"] = "Cannot start parec: " + str(error)
        self.audio_due = time.monotonic() + 3

    def connect_events(self):
        if self.hypr_socket is None:
            signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
            runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            path = Path(runtime) / "hypr" / signature / ".socket2.sock"
            connection = socket.socket(socket.AF_UNIX)
            try:
                connection.settimeout(0.5)
                connection.connect(str(path))
                connection.setblocking(False)
                self.selector.register(connection, selectors.EVENT_READ, ("hypr", ""))
                self.hypr_socket = connection
            except OSError:
                connection.close()
        if self.subscription is None:
            try:
                self.subscription = subprocess.Popen(
                    ["pactl", "subscribe"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    env={**os.environ, "LC_ALL": "C"})
                os.set_blocking(self.subscription.stdout.fileno(), False)
                self.selector.register(self.subscription.stdout, selectors.EVENT_READ, ("pulse", ""))
            except OSError:
                self.subscription = None
        self.connect_due = time.monotonic() + 3

    def read_event(self, key):
        kind, name = key.data
        if kind == "pcm":
            try:
                alive = self.captures[name].read()
            except OSError:
                alive = False
            if not alive:
                self.drop_capture(name)
                self.audio_due = time.monotonic() + 1
            else:
                # New PCM wakes idle analysis, while bursts remain capped at 30 Hz.
                due = max(self.last_sample + FRAME_INTERVAL, time.monotonic())
                self.next_emit = min(self.next_emit, due)
            return
        try:
            data = key.fileobj.recv(65536) if kind == "hypr" else os.read(key.fd, 65536)
        except OSError:
            data = b""
        if not data:
            self.selector.unregister(key.fileobj)
            if kind == "hypr":
                self.hypr_socket.close()
                self.hypr_socket = None
                self.screens = {}
                self.desktop_due = 0.0
            else:
                stop_process(self.subscription)
                self.subscription = None
                self.audio_due = 0.0
            return
        if kind == "hypr":
            # Ignore title/focus noise; membership, visibility and geometry matter.
            names = {line.split(b">>", 1)[0] for line in data.splitlines()}
            events = {b"workspace", b"workspacev2", b"focusedmon", b"openwindow", b"closewindow",
                      b"movewindow", b"movewindowv2", b"changefloatingmode", b"pin", b"activespecial",
                      b"activespecialv2", b"monitoradded", b"monitoraddedv2", b"monitorremoved",
                      b"configreloaded", b"togglegroup", b"changegroupactive", b"moveintogroup",
                      b"moveoutofgroup", b"minimize", b"windowstate"}
            if names & events:
                self.desktop_due = min(self.desktop_due, time.monotonic() + 0.025)
        elif any(b"on " + event in data for event in (b"sink #", b"sink-input #", b"server #", b"card #")):
            self.audio_due = min(self.audio_due, time.monotonic() + 0.05)

    def emit(self, now: float):
        bands = [0.0] * BAND_COUNT
        level = 0.0
        if any(self.screens.values()):
            for capture in self.captures.values():
                values, loudness = capture.analyze(now)
                bands = [max(a, b) for a, b in zip(bands, values)]
                level = max(level, loudness)
        packet = {"screens": self.screens, "sinks": list(self.captures), "active": level > 0,
                  "level": round(level, 4), "bands": [round(v, 4) for v in bands],
                  "error": "; ".join(self.errors.values())}
        if packet != self.last_packet or now >= self.heartbeat_due:
            print(json.dumps(packet, separators=(",", ":")), flush=True)
            self.last_packet = packet
            self.heartbeat_due = now + HEARTBEAT_INTERVAL
        self.last_sample = now
        self.next_emit = now + (FRAME_INTERVAL if level else HEARTBEAT_INTERVAL)

    def run(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: setattr(self, "running", False))
        try:
            while self.running:
                now = time.monotonic()
                if now >= self.connect_due:
                    self.connect_events()
                if now >= self.desktop_due:
                    self.refresh_desktop()
                if now >= self.audio_due:
                    self.refresh_audio()
                now = time.monotonic()
                if now >= self.next_emit:
                    self.emit(now)
                due = min(self.desktop_due, self.audio_due, self.next_emit, self.connect_due)
                for key, _ in self.selector.select(max(0, min(0.25, due - time.monotonic()))):
                    self.read_event(key)
        except BrokenPipeError:
            pass
        finally:
            for name in list(self.captures):
                self.drop_capture(name)
            if self.subscription is not None:
                stop_process(self.subscription)
            if self.hypr_socket is not None:
                self.hypr_socket.close()
            self.selector.close()


if __name__ == "__main__":
    Backend().run()
