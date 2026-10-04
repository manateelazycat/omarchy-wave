// SPDX-FileCopyrightText: 2026 ManateeLazyCat
// SPDX-License-Identifier: GPL-3.0-only

import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons

Item {
  id: root

  property var shell: null
  property var settings: ({})
  property var emptyScreens: ({})
  property var sinks: []
  property string backendError: ""
  property var targetBands: []
  property var bands: []
  property bool audioActive: false
  property real targetLevel: 0
  property real level: 0
  property real phase: 0
  property int frame: 0
  property bool unloading: false

  readonly property int waveHeight: Math.round(setting("height", 56, 16, 160))
  readonly property real waveOpacity: setting("opacity", 0.76, 0.1, 1)
  readonly property real sensitivity: setting("sensitivity", 1, 0.2, 4)
  readonly property bool anyEmpty: Object.keys(emptyScreens).some(function(name) { return emptyScreens[name] })
  readonly property bool animating: anyEmpty && (audioActive || level > 0.001)
  readonly property string backendPath: decodeURIComponent(String(Qt.resolvedUrl("wave_backend.py")).replace(/^file:\/\//, ""))

  function setting(name, fallback, minimum, maximum) {
    var value = Number(settings[name])
    return settings[name] !== undefined && isFinite(value)
      ? Math.max(minimum, Math.min(maximum, value)) : fallback
  }

  function receive(data) {
    try {
      var packet = JSON.parse(data)
      emptyScreens = packet.screens || ({})
      sinks = packet.sinks || []
      backendError = packet.error || ""
      targetBands = packet.bands || []
      targetLevel = Math.min(1, Math.max(0, Number(packet.level) || 0) * sensitivity)
      audioActive = packet.active === true && anyEmpty
      if (!audioActive) targetLevel = 0
      if (!anyEmpty) {
        level = 0
        bands = []
      }
      backendWatchdog.restart()
    } catch (error) {
      console.warn("Omarchy Wave: invalid backend packet: " + error)
    }
  }

  FileView {
    path: Qt.resolvedUrl("settings.json")
    watchChanges: true
    printErrors: false
    onLoaded: {
      try { root.settings = JSON.parse(text()) }
      catch (error) { console.warn("Omarchy Wave: invalid settings.json: " + error) }
    }
    onFileChanged: reload()
  }

  Process {
    id: backend
    command: ["python3", "-u", root.backendPath]
    stdout: SplitParser { onRead: data => root.receive(data) }
    stderr: SplitParser { onRead: data => console.warn("Omarchy Wave: " + data) }
    onExited: {
      root.audioActive = false
      root.targetLevel = 0
      root.emptyScreens = ({})
      if (!root.unloading) restartTimer.restart()
    }
  }

  Timer {
    id: restartTimer
    interval: 3000
    onTriggered: backend.running = true
  }

  Timer {
    id: backendWatchdog
    interval: 5000
    onTriggered: {
      root.audioActive = false
      root.targetLevel = 0
      root.emptyScreens = ({})
      root.backendError = "Audio backend stopped responding"
      backend.running = false
    }
  }

  FrameAnimation {
    property real elapsed: 0
    running: root.animating
    onTriggered: {
      elapsed += frameTime
      if (elapsed < 1 / 30) return
      var dt = Math.min(elapsed, 0.1)
      elapsed = 0
      var attack = 1 - Math.exp(-dt / 0.065)
      var release = 1 - Math.exp(-dt / 0.22)
      root.level += (root.targetLevel - root.level) * (root.targetLevel > root.level ? attack : release)
      if (!root.audioActive && root.level < 0.001) root.level = 0
      var next = []
      for (var i = 0; i < root.targetBands.length; i++) {
        var old = root.bands[i] || 0
        var target = root.audioActive ? Math.min(1, root.targetBands[i] * root.sensitivity) : 0
        next.push(old + (target - old) * (target > old ? attack : release))
      }
      root.bands = next
      root.phase = (root.phase + dt * (0.35 + root.level * 0.55)) % (Math.PI * 2)
      root.frame++
    }
  }

  Variants {
    model: Quickshell.screens

    WaveSurface {
      required property var modelData
      screen: modelData
      eligible: root.emptyScreens[modelData.name] === true
      waveHeight: root.waveHeight
      waveOpacity: root.waveOpacity
      waveColor: Color.accent
      audioLevel: root.level
      bands: root.bands
      phase: root.phase
      frame: root.frame
    }
  }

  IpcHandler {
    target: "io.github.manateelazycat.wave"
    function status(): string {
      return JSON.stringify({
        active: root.audioActive,
        level: root.level,
        screens: root.emptyScreens,
        sinks: root.sinks,
        color: String(Color.accent),
        height: root.waveHeight,
        opacity: root.waveOpacity,
        sensitivity: root.sensitivity,
        error: root.backendError
      })
    }
  }

  Component.onCompleted: backend.running = true
  Component.onDestruction: {
    root.unloading = true
    backend.running = false
  }
}
