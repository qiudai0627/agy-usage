# agy-usage · Antigravity 实时用量与每周限额监控台

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-success)
![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Python%20Stdlib)-brightgreen)

专为 **Google Antigravity (`agy` CLI / 桌面端)** 打造的跨平台纯本地实时用量与配额监控工具（**macOS + Windows + Linux**，零第三方依赖，仅需 Python 3.9+ 标准库）。

---

## 核心特性

1. **官方双限额池实时监控（毫秒级同步，4 位小数精度）**
   - 自动识别并分离 **Google Gemini 自家模型池** 与 **Claude / GPT 第三方模型池 (`3p`)**。
   - 同屏追踪两套池子各自的 **当前用量（5 小时滚动窗口）** 与 **每周限额（7 天周期）**、精确重置倒计时（CST）、时间进度 vs 额度消耗配速比、日均安全预算、耗尽预测与每 1% 折合有效 Token。
   - **全模型与全订阅档位自适应**：自动适配 Free / AI Pro / AI Ultra 等任意档位与新老模型。

2. **四端形态齐全（针对刘海屏 Mac 与 Windows 专项优化）**
   - **Web 可视化监控台**（`http://127.0.0.1:18420`，暗色/亮色双主题，每 3 秒自动刷新）：双池同屏对比、Tab 切换趋势图（5h 燃速 / 24h 柱图 / 7d 趋势 / 限额剩余曲线）、7×24 热力图、缓存节省分析、会话逐轮上下文膨胀曲线抽屉、CSV 导出与手动录入限额。
   - **macOS 防刘海毛玻璃悬浮胶囊 + 顶部菜单栏 (`AGY Usage.app`)**：原生 Swift 编译（~150 KB），默认在屏幕右上角菜单栏正下方显示原生暗色毛玻璃胶囊 `● G 9% │ C 55%`（彻底解决 14"/16" MacBook Pro 摄像头刘海遮挡菜单栏图标的问题），支持自由拖拽记忆位置、单击弹出四桶进度菜单、可随时在菜单内开关胶囊或开启登录自启。
   - **Windows 右下角桌面迷你悬浮胶囊 (`tray_widget.pyw`)**：纯标准库无黑框运行，常驻任务栏上方显示实时状态，双击展开详情面板、可自由拖动、右键呼出菜单。
   - **`agy` 底部实时状态栏 + 终端 TUI (`agy-usage` / `agy-usage watch`)**。

3. **100% 本地隐私安全（MIT 开源协议）**
   - 不索取任何账号密码或 OAuth Token，不上传任何遥测数据。
   - 运行时快照保存在系统个人缓存目录（macOS/Linux: `~/.cache/agy-usage/`；Windows: `%LOCALAPPDATA%\agy-usage\`），项目目录零个人数据残留。

---

## 快速安装与启动

### 方式 1：一行命令全自动安装（最推荐，零拦截弹窗）

- **macOS / Linux**：打开终端复制粘贴回车：
  ```bash
  curl -fsSL https://raw.githubusercontent.com/qiudai0627/agy-usage/main/install.sh | bash
  ```
- **Windows PowerShell**：打开 PowerShell 复制粘贴回车（需本机已安装 Python 3.9+）：
  ```powershell
  irm https://raw.githubusercontent.com/qiudai0627/agy-usage/main/install.ps1 | iex
  ```

### 方式 2：下载压缩包双击启动（免敲命令行）
从 [GitHub Releases](https://github.com/qiudai0627/agy-usage/releases) 下载 `agy-usage-release.zip` 并解压：
- **macOS**：在访达（Finder）中直接双击 **`Start-Mac.command`**（首次若提示未识别开发者，右键点“打开”即可）。
- **Windows**：在资源管理器直接双击 **`Start-Windows.bat`**。

> **提示**：若安装时已有正在运行的 `agy` 终端窗口，在该 `agy` 输入框执行一次安装输出提示的 `/statusline ...` 命令（或重开一个 `agy` 窗口），即可立刻开始同步实时限额。

---

## 常用命令

```bash
agy-usage                    # 终端即时完整报告（支持 -w 5h/today/24h/week/7d/all）
agy-usage watch              # 终端实时刷新大屏（每 2s，适合 tmux 分屏）
agy-usage daemon status      # 查看后台 Web 看板状态（start / stop / restart）
agy-usage web                # 前台启动 Web 看板（默认 http://127.0.0.1:18420）
agy-usage json               # 导出结构化 JSON
```

## 打包干净分享包（含自动隐私门禁）

```bash
./scripts/package-release.sh
```
自动提取纯源码与脚本到临时沙箱，执行**个人路径 / 用户名 / GitHub 账号 / 邮箱零泄露扫描**，通过后生成 `~/.cache/agy-usage/agy-usage-release.zip`。

## 卸载还原

- **macOS / Linux**：`./uninstall.sh`
- **Windows**：`powershell -ExecutionPolicy Bypass -File .\uninstall.ps1`

## 开源协议

本项目基于 [MIT License](./LICENSE) 开源。
