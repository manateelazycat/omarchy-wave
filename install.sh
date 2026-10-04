#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 ManateeLazyCat
# SPDX-License-Identifier: GPL-3.0-only

set -euo pipefail

plugin_id=io.github.manateelazycat.wave
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
backup_dir="$HOME/.local/state/omarchy-wave/backups/$(date +%Y%m%d-%H%M%S-%N)"

for dependency in python3 parec pactl hyprctl omarchy omarchy-shell; do
  command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; exit 1; }
done
omarchy plugin validate "$source_dir"
mkdir -p "$backup_dir"
if [[ -f "$HOME/.config/omarchy/shell.json" ]]; then
  cp -p "$HOME/.config/omarchy/shell.json" "$backup_dir/shell.json"
fi
if [[ -d "$plugin_dir" ]]; then
  cp -a "$plugin_dir" "$backup_dir/plugin"
  omarchy plugin disable "$plugin_id"
fi
mkdir -p "$plugin_dir"
for file in manifest.json Service.qml WaveSurface.qml wave_backend.py README.md LICENSE; do
  install -m 644 "$source_dir/$file" "$plugin_dir/$file"
done
if [[ ! -f "$plugin_dir/settings.json" ]]; then
  install -m 644 "$source_dir/settings.json" "$plugin_dir/settings.json"
fi
omarchy-shell shell rescanPlugins >/dev/null
# Discovery runs asynchronously in the shell, especially on the first install.
discovered=false
for attempt in {1..50}; do
  if omarchy-shell shell listPlugins | python3 -c 'import json,sys; sys.exit(0 if any(p.get("id") == sys.argv[1] for p in json.load(sys.stdin)) else 1)' "$plugin_id"; then
    discovered=true
    break
  fi
  sleep 0.1
done
if [[ $discovered != true ]]; then
  echo "Omarchy shell did not discover the plugin. Backup: $backup_dir" >&2
  exit 1
fi
omarchy plugin enable "$plugin_id"
printf 'Installed to %s\nBackup: %s\n' "$plugin_dir" "$backup_dir"
