import Cocoa
import Foundation

// Native macOS Menu Bar + Notch-Proof Floating Glass Pill for Antigravity CLI (agy-usage).
// Zero external dependencies; solves 14"/16" MacBook Pro camera-notch menu bar overflow.

struct QuotaBucket: Decodable {
    let id: String
    let label: String
    let pool_key: String?
    let window_kind: String
    let used_pct: Double?
    let remaining_pct: Double?
    let reset_time_cst: String?
    let reset_in_text: String?
    let status: String?
    let reset_passed: Bool?
}

struct QuotaInfo: Decodable {
    let has_live_quota: Bool
    let buckets: [QuotaBucket]
}

struct WinSummary: Decodable {
    let calls: Int
    let billable_tokens: Int
    let cache_hit_pct: Double
    let cache_saved_usd: Double
}

struct LiveSession: Decodable {
    let plan_tier: String?
    let active_model: String?
}

struct StatsResponse: Decodable {
    let generated_at_cst: String
    let live_session: LiveSession
    let quota: QuotaInfo
    let windows: [String: WinSummary]
}

final class PillContentView: NSVisualEffectView {
    var onClick: (() -> Void)?
    var onPositionChanged: ((NSPoint) -> Void)?
    private var dragStartMouse: NSPoint = .zero
    private var dragStartOrigin: NSPoint = .zero
    private var dragged = false

    override func mouseDown(with event: NSEvent) {
        dragged = false
        dragStartMouse = NSEvent.mouseLocation
        dragStartOrigin = window?.frame.origin ?? .zero
    }

    override func mouseDragged(with event: NSEvent) {
        guard let win = window else { return }
        let cur = NSEvent.mouseLocation
        let dx = cur.x - dragStartMouse.x
        let dy = cur.y - dragStartMouse.y
        if hypot(dx, dy) > 3 { dragged = true }
        let next = NSPoint(x: dragStartOrigin.x + dx, y: dragStartOrigin.y + dy)
        win.setFrameOrigin(next)
    }

    override func mouseUp(with event: NSEvent) {
        if dragged {
            if let origin = window?.frame.origin {
                onPositionChanged?(origin)
            }
        } else {
            onClick?()
        }
    }

    override func rightMouseUp(with event: NSEvent) {
        onClick?()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var pillPanel: NSPanel!
    private var pillView: PillContentView!
    private var pillLabel: NSTextField!
    private var sharedMenu: NSMenu = NSMenu()
    private var timer: Timer?
    private let port: Int = Int(ProcessInfo.processInfo.environment["AGY_USAGE_PORT"] ?? "18420") ?? 18420
    private var lastStats: StatsResponse?

    private let showPillKey = "AGYUsageShowFloatingPill"
    private let pillXKey = "AGYUsagePillOriginX"
    private let pillYKey = "AGYUsagePillOriginY"

    private var showFloatingPill: Bool {
        get {
            if UserDefaults.standard.object(forKey: showPillKey) == nil { return true }
            return UserDefaults.standard.bool(forKey: showPillKey)
        }
        set {
            UserDefaults.standard.set(newValue, forKey: showPillKey)
            updatePillVisibility()
        }
    }

    private var launchAgentURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/local.agy.usage.menubar.plist")
    }

    private var cliPath: String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/.local/bin/agy-usage"
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        setupFloatingPill()
        updateIndicators(compactBar: "AGY", pillText: "AGY 连接中…", level: "ok")
        rebuildMenu()
        updatePillVisibility()
        fetchStats(autoStartDaemon: true)

        timer = Timer.scheduledTimer(withTimeInterval: 6.0, repeats: true) { [weak self] _ in
            self?.fetchStats(autoStartDaemon: false)
        }
    }

    private func setupFloatingPill() {
        let w: CGFloat = 168
        let h: CGFloat = 28
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        var x = screen.maxX - w - 14
        var y = screen.maxY - h - 8
        if UserDefaults.standard.object(forKey: pillXKey) != nil {
            let savedX = CGFloat(UserDefaults.standard.double(forKey: pillXKey))
            let savedY = CGFloat(UserDefaults.standard.double(forKey: pillYKey))
            if screen.insetBy(dx: -40, dy: -40).contains(NSPoint(x: savedX, y: savedY)) {
                x = savedX
                y = savedY
            }
        }

        pillPanel = NSPanel(
            contentRect: NSRect(x: x, y: y, width: w, height: h),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        pillPanel.level = .statusBar
        pillPanel.isOpaque = false
        pillPanel.backgroundColor = .clear
        pillPanel.hasShadow = true
        pillPanel.hidesOnDeactivate = false
        pillPanel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]

        pillView = PillContentView(frame: NSRect(x: 0, y: 0, width: w, height: h))
        pillView.material = .hudWindow
        pillView.blendingMode = .behindWindow
        pillView.state = .active
        pillView.appearance = NSAppearance(named: .vibrantDark)
        pillView.wantsLayer = true
        pillView.layer?.cornerRadius = h / 2
        pillView.layer?.masksToBounds = true
        pillView.layer?.borderWidth = 1.0
        pillView.layer?.borderColor = NSColor(calibratedWhite: 1.0, alpha: 0.16).cgColor

        pillLabel = NSTextField(labelWithString: "● AGY")
        pillLabel.alignment = .center
        pillLabel.frame = NSRect(x: 8, y: 5, width: w - 16, height: 18)
        pillLabel.textColor = .white
        pillView.addSubview(pillLabel)

        pillView.onClick = { [weak self] in
            guard let self = self else { return }
            self.sharedMenu.popUp(positioning: nil, at: NSPoint(x: 0, y: -4), in: self.pillView)
        }
        pillView.onPositionChanged = { [weak self] pt in
            guard let self = self else { return }
            UserDefaults.standard.set(Double(pt.x), forKey: self.pillXKey)
            UserDefaults.standard.set(Double(pt.y), forKey: self.pillYKey)
        }

        pillPanel.contentView = pillView
    }

    private func updatePillVisibility() {
        if showFloatingPill {
            pillPanel.orderFrontRegardless()
        } else {
            pillPanel.orderOut(nil)
        }
    }

    private func fmtTokens(_ n: Int) -> String {
        let d = Double(n)
        if d >= 1_000_000_000 { return String(format: "%.2fB", d / 1_000_000_000) }
        if d >= 1_000_000 { return String(format: "%.2fM", d / 1_000_000) }
        if d >= 1_000 { return String(format: "%.1fk", d / 1_000) }
        return "\(n)"
    }

    private func asciiBar(_ usedPct: Double, width: Int = 8) -> String {
        let clamped = max(0.0, min(100.0, usedPct))
        let filled = Int((clamped / 100.0 * Double(width)).rounded())
        return String(repeating: "█", count: filled) + String(repeating: "░", count: max(0, width - filled))
    }

    private func updateIndicators(compactBar: String, pillText: String, level: String) {
        let dotColor: NSColor
        switch level {
        case "critical": dotColor = NSColor.systemRed
        case "warning": dotColor = NSColor.systemOrange
        default: dotColor = NSColor.systemGreen
        }

        if let button = statusItem.button {
            let attr = NSMutableAttributedString()
            attr.append(NSAttributedString(string: "●", attributes: [
                .foregroundColor: dotColor,
                .font: NSFont.systemFont(ofSize: 9.5, weight: .bold)
            ]))
            attr.append(NSAttributedString(string: compactBar, attributes: [
                .font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .medium)
            ]))
            button.attributedTitle = attr
        }

        let pillAttr = NSMutableAttributedString()
        pillAttr.append(NSAttributedString(string: "● ", attributes: [
            .foregroundColor: dotColor,
            .font: NSFont.systemFont(ofSize: 10.5, weight: .bold)
        ]))
        pillAttr.append(NSAttributedString(string: pillText, attributes: [
            .foregroundColor: NSColor.white,
            .font: NSFont.monospacedDigitSystemFont(ofSize: 11.5, weight: .semibold)
        ]))
        pillLabel.attributedStringValue = pillAttr
    }

    private func fetchStats(autoStartDaemon: Bool) {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/stats?window=7d") else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 2.0

        URLSession.shared.dataTask(with: req) { [weak self] data, resp, _ in
            guard let self = self else { return }
            if let data = data,
               let http = resp as? HTTPURLResponse, http.statusCode == 200,
               let decoded = try? JSONDecoder().decode(StatsResponse.self, from: data) {
                DispatchQueue.main.async {
                    self.lastStats = decoded
                    self.applyStats(decoded)
                    self.rebuildMenu()
                }
            } else if autoStartDaemon {
                self.startDaemonSilently()
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                    self.fetchStats(autoStartDaemon: false)
                }
            } else {
                DispatchQueue.main.async {
                    self.updateIndicators(compactBar: "AGY", pillText: "AGY 离线 (点此启动)", level: "warning")
                    self.rebuildMenu()
                }
            }
        }.resume()
    }

    private func applyStats(_ st: StatsResponse) {
        if st.quota.has_live_quota {
            let gemW = st.quota.buckets.first { ($0.pool_key ?? "").hasPrefix("gemini") && $0.window_kind == "weekly" }
            let cldW = st.quota.buckets.first { $0.pool_key == "claude_gpt" && $0.window_kind == "weekly" }

            var pillParts: [String] = []
            var barParts: [String] = []
            if let g = gemW, let u = g.used_pct {
                pillParts.append(String(format: "G %.0f%%", u))
                barParts.append(String(format: "%.0f", u))
            }
            if let c = cldW, let u = c.used_pct {
                pillParts.append(String(format: "C %.0f%%", u))
                barParts.append(String(format: "%.0f%%", u))
            }
            if pillParts.isEmpty, let first = st.quota.buckets.first, let u = first.used_pct {
                pillParts.append(String(format: "AGY %.0f%%", u))
                barParts.append(String(format: "%.0f%%", u))
            }

            var worst = "ok"
            for b in st.quota.buckets {
                if b.status == "critical" { worst = "critical"; break }
                if b.status == "warning" { worst = "warning" }
            }
            updateIndicators(
                compactBar: barParts.joined(separator: "│"),
                pillText: pillParts.joined(separator: " │ "),
                level: worst
            )
        } else {
            let todayTok = st.windows["today"]?.billable_tokens ?? 0
            let tokStr = fmtTokens(todayTok)
            updateIndicators(compactBar: tokStr, pillText: "AGY \(tokStr)", level: "ok")
        }
    }

    private func makeDisabledItem(_ title: String, monospaced: Bool = false) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        item.isEnabled = false
        if monospaced {
            item.attributedTitle = NSAttributedString(string: title, attributes: [
                .font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular),
                .foregroundColor: NSColor.labelColor
            ])
        }
        return item
    }

    private func rebuildMenu() {
        let menu = NSMenu()

        if let st = lastStats {
            let tier = (st.live_session.plan_tier ?? "").isEmpty || st.live_session.plan_tier == "-"
                ? ""
                : " · \(st.live_session.plan_tier!)"
            let hdr = NSMenuItem(title: "Antigravity 实时监控\(tier)", action: nil, keyEquivalent: "")
            hdr.attributedTitle = NSAttributedString(string: hdr.title, attributes: [
                .font: NSFont.systemFont(ofSize: 12, weight: .bold)
            ])
            menu.addItem(hdr)
            menu.addItem(makeDisabledItem("主模型: \(st.live_session.active_model ?? "-")"))
            menu.addItem(NSMenuItem.separator())

            if st.quota.has_live_quota {
                let gemBuckets = st.quota.buckets.filter { ($0.pool_key ?? "").hasPrefix("gemini") }
                let cldBuckets = st.quota.buckets.filter { $0.pool_key == "claude_gpt" }

                if !gemBuckets.isEmpty {
                    menu.addItem(makeDisabledItem("▸ Google Gemini 模型池"))
                    for b in gemBuckets {
                        let used = b.used_pct ?? 0.0
                        let tag = b.window_kind == "five_hour" ? "当前5h" : "每周7d"
                        let rst = (b.reset_passed == true) ? "待刷新" : "重置 \(b.reset_time_cst ?? "-")"
                        let line = String(format: "  %@  %@  已用 %5.1f%%  (%@)", tag, asciiBar(used), used, rst)
                        menu.addItem(makeDisabledItem(line, monospaced: true))
                    }
                }

                if !cldBuckets.isEmpty {
                    if !gemBuckets.isEmpty { menu.addItem(NSMenuItem.separator()) }
                    menu.addItem(makeDisabledItem("▸ Claude / GPT 第三方池 (3P)"))
                    for b in cldBuckets {
                        let used = b.used_pct ?? 0.0
                        let tag = b.window_kind == "five_hour" ? "当前5h" : "每周7d"
                        let rst = (b.reset_passed == true) ? "待刷新" : "重置 \(b.reset_time_cst ?? "-")"
                        let line = String(format: "  %@  %@  已用 %5.1f%%  (%@)", tag, asciiBar(used), used, rst)
                        menu.addItem(makeDisabledItem(line, monospaced: true))
                    }
                }
            } else {
                menu.addItem(makeDisabledItem("等待 agy 推送实时周限额 (/statusline)"))
            }

            menu.addItem(NSMenuItem.separator())
            if let wt = st.windows["today"], let w7 = st.windows["7d"] {
                menu.addItem(makeDisabledItem("今日有效: \(fmtTokens(wt.billable_tokens)) (\(wt.calls)次)"))
                menu.addItem(makeDisabledItem(String(format: "近7日有效: %@ · 缓存省 $%.0f (%.1f%%)",
                                                     fmtTokens(w7.billable_tokens), w7.cache_saved_usd, w7.cache_hit_pct)))
            }
            menu.addItem(makeDisabledItem("同步于 \(st.generated_at_cst)"))
        } else {
            menu.addItem(makeDisabledItem("正在连接本地监控服务 (127.0.0.1:\(port))..."))
        }

        menu.addItem(NSMenuItem.separator())

        let openItem = NSMenuItem(title: "打开完整 Web 监控台", action: #selector(openDashboard), keyEquivalent: "o")
        openItem.target = self
        menu.addItem(openItem)

        let refItem = NSMenuItem(title: "立即刷新", action: #selector(manualRefresh), keyEquivalent: "r")
        refItem.target = self
        menu.addItem(refItem)

        let pillToggle = NSMenuItem(title: "显示桌面悬浮胶囊（防刘海遮挡）", action: #selector(togglePill), keyEquivalent: "")
        pillToggle.target = self
        pillToggle.state = showFloatingPill ? .on : .off
        menu.addItem(pillToggle)

        let autoItem = NSMenuItem(title: "登录时自动启动", action: #selector(toggleLaunchAtLogin), keyEquivalent: "")
        autoItem.target = self
        autoItem.state = FileManager.default.fileExists(atPath: launchAgentURL.path) ? .on : .off
        menu.addItem(autoItem)

        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(title: "退出小工具", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        sharedMenu = menu
        statusItem.menu = menu
    }

    private func startDaemonSilently() {
        guard FileManager.default.isExecutableFile(atPath: cliPath) else { return }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: cliPath)
        proc.arguments = ["daemon", "start", "--port", "\(port)", "--no-open"]
        try? proc.run()
    }

    @objc private func openDashboard() {
        startDaemonSilently()
        if let url = URL(string: "http://127.0.0.1:\(port)") {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func manualRefresh() {
        fetchStats(autoStartDaemon: true)
    }

    @objc private func togglePill() {
        showFloatingPill.toggle()
        rebuildMenu()
    }

    @objc private func toggleLaunchAtLogin() {
        let fm = FileManager.default
        if fm.fileExists(atPath: launchAgentURL.path) {
            try? fm.removeItem(at: launchAgentURL)
        } else {
            guard let execPath = Bundle.main.executablePath else { return }
            let plist: [String: Any] = [
                "Label": "local.agy.usage.menubar",
                "ProgramArguments": [execPath],
                "RunAtLoad": true,
                "KeepAlive": false
            ]
            try? fm.createDirectory(at: launchAgentURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            if let data = try? PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0) {
                try? data.write(to: launchAgentURL)
            }
        }
        rebuildMenu()
    }

    @objc private func quitApp() {
        NSApplication.shared.terminate(nil)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
