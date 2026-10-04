# Omarchy Wave

简体中文 | [English](README.md)

https://github.com/user-attachments/assets/5a807081-1bbd-4bc5-9d78-faf9676b68cd

在 Omarchy 空白工作区底部显示随系统音乐起伏的连续波浪，颜色自动跟随当前主题。

## 功能

- 监听浏览器、音乐播放器等应用的系统播放输出，无需应用提供媒体控制接口。
- 监听所有正在播放的输出设备，支持耳机切换及多个设备同时播放。
- 每块显示器独立判断是否空白；浮动窗口、固定窗口和特殊工作区中的可见窗口也会使波浪隐藏。
- 使用 24 个频段绘制平滑曲线，音乐停止后平滑收拢并淡出。
- 自动跟随 Omarchy 主题的强调色，不获取输入、不抢焦点、不预留屏幕空间。
- 所有屏幕都有可见窗口时停止音频采集。Python 后端仅使用标准库，不保存录音。

## 安装

需要支持服务插件的 Omarchy（Quickshell）环境、Hyprland、Python 3，以及提供 `pactl` 和 `parec` 的 `libpulse`。

```sh
git clone https://github.com/manateelazycat/omarchy-wave.git
cd omarchy-wave
bash install.sh
```

安装器会将插件安装至 `~/.config/omarchy/plugins/io.github.manateelazycat.wave/` 并自动启用，之前的配置和插件备份在 `~/.local/state/omarchy-wave/backups/`。重新安装会保留已有 `settings.json`。

## 配置

修改 `~/.config/omarchy/plugins/io.github.manateelazycat.wave/settings.json`：

```json
{
  "height": 56,
  "opacity": 0.76,
  "sensitivity": 1.0
}
```

| 配置 | 含义 | 范围 |
| --- | --- | --- |
| `height` | 波浪最大高度，使用逻辑像素 | 16–160 |
| `opacity` | 波浪填充透明度 | 0.1–1.0 |
| `sensitivity` | 音乐反应强度 | 0.2–4.0 |

保存后即时生效。颜色自动使用 Shell 的 `Color.accent`，无需单独配置；系统提示音等其他播放声音也会驱动波浪。

## 管理和诊断

```sh
omarchy-shell io.github.manateelazycat.wave status
omarchy plugin disable io.github.manateelazycat.wave
omarchy plugin enable io.github.manateelazycat.wave
```

状态包含各屏幕的空白判断、正在采集的输出设备、音频是否活跃、当前主题颜色和后端错误。没有音频播放或没有空白工作区时不显示波浪。

## 开发

```sh
python3 -m unittest discover -s tests -v
omarchy plugin validate .
```

`Service.qml` 管理后端与主题绑定，`WaveSurface.qml` 绘制波浪。`wave_backend.py` 通过输出设备的 monitor 获取立体声音频并执行 FFT，通过 Hyprland 事件刷新工作区状态。插件停用时会停止音频采集并退出子进程。

## 许可证

Copyright (C) 2026 ManateeLazyCat

[GPL-3.0-only](LICENSE)。
