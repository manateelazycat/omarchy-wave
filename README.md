# Omarchy Wave

在空白工作区底部显示随系统音乐起伏的连续波浪，颜色自动跟随 Omarchy 主题的强调色。

- 监听系统播放输出，兼容浏览器、音乐播放器等应用，无需应用提供媒体控制接口。
- 监听所有正在播放的输出设备；支持耳机切换，以及多个设备同时播放。
- 每块显示器独立判断是否空白；浮动窗口、固定窗口和特殊工作区中的可见窗口也会使波浪隐藏。
- 使用 24 个频段绘制平滑填充曲线，音乐停止后平滑收拢并淡出。
- 不获取输入、不抢焦点、不为窗口预留空间。所有屏幕都有窗口时停止音频采集。
- Python 后端仅使用标准库，不保存录音。

## 安装

需要使用 Quickshell 桌面 Shell 的 Omarchy、Hyprland、Python 3，以及提供 `pactl` / `parec` 的 `libpulse`。当前开发机器已具备这些依赖。

在项目目录运行：

```bash
bash install.sh
```

插件安装至 `~/.config/omarchy/plugins/io.github.manateelazycat.wave/` 并自动启用。安装前备份保存在 `~/.local/state/omarchy-wave/backups/`。重新安装会保留已有 `settings.json`。

也可以通过 Omarchy 的插件安装命令从发布后的 Git 仓库安装。

## 配置

修改已安装目录中的 `settings.json` 即时生效：

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

颜色使用 Shell 的 `Color.accent`，无需单独配置。系统提示音等其他播放声音也会驱动波浪。

## 管理和诊断

```bash
omarchy-shell io.github.manateelazycat.wave status
omarchy plugin disable io.github.manateelazycat.wave
omarchy plugin enable io.github.manateelazycat.wave
```

状态包含各屏幕的空白判断、正在采集的输出设备、音频是否活跃、当前主题颜色和后端错误。没有音乐或没有空白工作区时不显示波浪。

## 开发验证

```bash
python3 -m unittest discover -s tests -v
omarchy plugin validate .
```

`Service.qml` 管理后端与主题绑定，`WaveSurface.qml` 绘制底部曲线，`wave_backend.py` 通过输出设备的 monitor 获取立体声音频并执行 FFT，通过 Hyprland 事件刷新工作区状态。采集和子进程在插件停用时一起退出。

## 许可证

Copyright (C) 2026 ManateeLazyCat

本项目按 GNU 通用公共许可证第 3 版（`GPL-3.0-only`）发布，完整条款见 [LICENSE](LICENSE)。
