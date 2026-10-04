// SPDX-FileCopyrightText: 2026 ManateeLazyCat
// SPDX-License-Identifier: GPL-3.0-only

import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Ui

PanelWindow {
  id: panel

  property bool eligible: false
  property int waveHeight: 56
  property real waveOpacity: 0.76
  property color waveColor: "#7aa2f7"
  property real audioLevel: 0
  property var bands: []
  property real phase: 0
  property int frame: 0

  anchors { left: true; right: true; bottom: true }
  implicitHeight: waveHeight + 2
  color: "transparent"
  visible: eligible && audioLevel > 0.001 && !remapGuard.remapping
  exclusionMode: ExclusionMode.Ignore
  mask: Region {}
  WlrLayershell.namespace: "omarchy-wave"
  WlrLayershell.layer: WlrLayer.Bottom
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

  ScreenMoveRemap {
    id: remapGuard
    window: panel
  }

  onFrameChanged: wave.requestPaint()
  onWaveColorChanged: wave.requestPaint()
  onWaveOpacityChanged: wave.requestPaint()
  onVisibleChanged: if (visible) wave.requestPaint()

  Canvas {
    id: wave
    anchors.fill: parent
    renderStrategy: Canvas.Threaded
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    function heights(back) {
      var count = panel.bands.length
      var points = []
      var gain = Math.min(1, panel.audioLevel * 4)
      for (var i = 0; i < count; i++) {
        // Blend neighbouring frequency bands into broad, soft crests.
        var a = panel.bands[Math.max(0, i - 1)] || 0
        var b = panel.bands[i] || 0
        var c = panel.bands[Math.min(count - 1, i + 1)] || 0
        var energy = a * 0.22 + b * 0.56 + c * 0.22
        var drift = 0.94 + 0.06 * Math.sin(panel.phase + i * 0.85 + (back ? 1.5 : 0))
        var crest = 2.5 * gain + panel.waveHeight * 0.86 * energy * drift
        points.push(height - Math.min(panel.waveHeight, crest * (back ? 0.78 : 1)))
      }
      return points
    }

    function draw(ctx, points, alpha) {
      if (points.length < 2) return
      var step = width / (points.length - 1)
      ctx.beginPath()
      ctx.moveTo(0, height)
      ctx.lineTo(0, points[0])
      for (var i = 0; i < points.length - 1; i++) {
        var previous = points[Math.max(0, i - 1)]
        var current = points[i]
        var next = points[i + 1]
        var following = points[Math.min(points.length - 1, i + 2)]
        ctx.bezierCurveTo(
          i * step + step / 3, current + (next - previous) / 6,
          (i + 1) * step - step / 3, next - (following - current) / 6,
          (i + 1) * step, next)
      }
      ctx.lineTo(width, height)
      ctx.closePath()
      ctx.fillStyle = Qt.rgba(panel.waveColor.r, panel.waveColor.g, panel.waveColor.b, alpha)
      ctx.fill()
    }

    onPaint: {
      var ctx = getContext("2d")
      ctx.clearRect(0, 0, width, height)
      if (!panel.eligible || panel.audioLevel <= 0.001) return
      var fade = Math.min(1, panel.audioLevel * 8)
      draw(ctx, heights(true), panel.waveOpacity * 0.16 * fade)
      draw(ctx, heights(false), panel.waveOpacity * fade)
    }
  }
}
