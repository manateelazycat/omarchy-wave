# Omarchy Wave

English | [简体中文](README.zh-CN.md)

https://github.com/user-attachments/assets/5a807081-1bbd-4bc5-9d78-faf9676b68cd

Music-reactive waves along the bottom of empty Omarchy workspaces, with colors that follow your theme.

## Features

- Reacts to system audio from browsers, music players and other apps, without requiring media controls.
- Monitors all playing audio outputs, including headphone switching and simultaneous playback on multiple devices.
- Detects empty workspaces on each monitor independently. Visible floating, pinned and special-workspace windows hide the waves.
- Draws smooth curves from 24 frequency bands. Waves settle and fade out when playback stops.
- Follows the Omarchy theme's accent color. Takes no input or focus and reserves no screen space.
- Stops audio capture when every screen has visible windows. The Python backend uses only the standard library and saves no recordings.

## Install

Requires Omarchy with Quickshell and service plugin support, Hyprland, Python 3, and `libpulse` for `pactl` and `parec`.

```sh
git clone https://github.com/manateelazycat/omarchy-wave.git
cd omarchy-wave
bash install.sh
```

The installer enables the plugin in `~/.config/omarchy/plugins/io.github.manateelazycat.wave/` and backs up the previous configuration and plugin to `~/.local/state/omarchy-wave/backups/`. Reinstalling preserves your existing `settings.json`.

## Configuration

Edit `~/.config/omarchy/plugins/io.github.manateelazycat.wave/settings.json`:

```json
{
  "height": 56,
  "opacity": 0.76,
  "sensitivity": 1.0
}
```

| Setting | Description | Range |
| --- | --- | --- |
| `height` | Maximum wave height in logical pixels | 16–160 |
| `opacity` | Wave fill opacity | 0.1–1.0 |
| `sensitivity` | Response strength | 0.2–4.0 |

Changes apply when saved. Color follows the Shell's `Color.accent` automatically. Other system sounds also drive the waves.

## Manage and diagnose

```sh
omarchy-shell io.github.manateelazycat.wave status
omarchy plugin disable io.github.manateelazycat.wave
omarchy plugin enable io.github.manateelazycat.wave
```

Status reports each screen's empty-workspace state, captured audio outputs, audio activity, theme color and backend errors. Waves remain hidden when no audio is playing or no workspace is empty.

## Development

```sh
python3 -m unittest discover -s tests -v
omarchy plugin validate .
```

`Service.qml` manages the backend and theme bindings; `WaveSurface.qml` draws the waves. `wave_backend.py` captures stereo audio from output monitors, computes the FFT and refreshes workspace state through Hyprland events. Audio capture and subprocesses stop when the plugin is disabled.

## License

Copyright (C) 2026 ManateeLazyCat

[GPL-3.0-only](LICENSE).
