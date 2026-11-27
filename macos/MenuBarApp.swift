import Cocoa
import Darwin
import Foundation

// Native macOS Menu Bar + Notch-Proof Floating Glass Pill for Antigravity CLI (agy-usage).
// Zero external dependencies; includes single-instance lock, multi-monitor hot-unplug clamping,
// wake/offline auto-recovery, dynamic pill width, and Candidate A/B integration.

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

struct NotificationsInfo: Decodable {
    let enabled: Bool?
}

struct WeekOverWeekInfo: Decodable {
    let comparable: Bool?
    let badge_text: String?
}

struct StatsResponse: Decodable {
    let generated_at_cst: String
    let live_session: LiveSession
    let quota: QuotaInfo
    let notifications: NotificationsInfo?
    let week_over_week: WeekOverWeekInfo?
    let windows: [String: WinSummary]
}

final class MenuInfoRowView: NSView {
    init(attributedText: NSAttributedString, vPad: CGFloat = 5, leftInset: CGFloat = 18) {
        let textBounds = attributedText.boundingRect(
            with: NSSize(width: 600, height: 80),
            options: [.usesLineFragmentOrigin, .usesFontLeading]
        )
        let rowW = max(248, ceil(textBounds.width) + leftInset + 16)
        let labelH = ceil(textBounds.height) + 2
        let rowH = max(21, labelH + vPad)
        super.init(frame: NSRect(x: 0, y: 0, width: rowW, height: rowH))

        let label = NSTextField(labelWithAttributedString: attributedText)
        label.lineBreakMode = .byClipping
        label.frame = NSRect(
            x: leftInset,
            y: floor((rowH - labelH) / 2.0),
            width: rowW - leftInset - 10,
            height: labelH
        )
        label.autoresizingMask = [.width]
        addSubview(label)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

final class PillContentView: NSView {
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
    private var pillBlurView: NSVisualEffectView!
    private var pillLabel: NSTextField!
    private var sharedMenu: NSMenu = NSMenu()
    private var timer: Timer?
    private var lockFD: Int32 = -1
    private var offlineCount: Int = 0
    private var lastAutoRecovery: Date = .distantPast

    private let port: Int = Int(ProcessInfo.processInfo.environment["AGY_USAGE_PORT"] ?? "18420") ?? 18420
    private var lastStats: StatsResponse?

    private let activateNote = NSNotification.Name("local.agy.usage.menubar.activate")
    private let showPillKey = "AGYUsageShowFloatingPill"
    private let pillXKey = "AGYUsagePillOriginX"
    private let pillYKey = "AGYUsagePillOriginY"
    private let appearanceKey = "AGYUsageAppearance"
    private let langPrefKey = "AGYUsageLangPref"
    private let pillHeight: CGFloat = 28

    private var langPref: String {
        get {
            let v = UserDefaults.standard.string(forKey: langPrefKey) ?? "auto"
            if v == "zh-CN" || v == "zh-TW" || v == "en" || v == "auto" { return v }
            return "auto"
        }
        set {
            UserDefaults.standard.set(newValue, forKey: langPrefKey)
        }
    }

    private func resolvedLang() -> String {
        if langPref != "auto" { return langPref }
        let first = (Locale.preferredLanguages.first ?? "en").lowercased()
        if first.contains("hant") || first.contains("zh-tw") || first.contains("zh-hk") || first.contains("zh-mo") {
            return "zh-TW"
        }
        if first.hasPrefix("zh") { return "zh-CN" }
        return "en"
    }

    private func tr(_ cn: String, _ tw: String, _ en: String) -> String {
        switch resolvedLang() {
        case "zh-CN": return cn
        case "zh-TW": return tw
        default: return en
        }
    }

    private struct ThemePalette {
        let gemTag: NSColor
        let cldTag: NSColor
        let sep: NSColor
        let ok: NSColor
        let warn: NSColor
        let crit: NSColor
        let expired: NSColor
        let border: NSColor
        let tint: NSColor
    }

    private static func hexColor(_ hex: UInt32, alpha: CGFloat = 1.0) -> NSColor {
        let r = CGFloat((hex >> 16) & 0xFF) / 255.0
        let g = CGFloat((hex >> 8) & 0xFF) / 255.0
        let b = CGFloat(hex & 0xFF) / 255.0
        return NSColor(srgbRed: r, green: g, blue: b, alpha: alpha)
    }

    private var appearancePref: String {
        get {
            let v = UserDefaults.standard.string(forKey: appearanceKey) ?? "system"
            if v == "light" || v == "tongtou" || v == "dark" || v == "system" { return v }
            return "system"
        }
        set {
            UserDefaults.standard.set(newValue, forKey: appearanceKey)
            applyAppearance()
        }
    }

    private func resolvedTheme(for appearance: NSAppearance? = nil) -> String {
        if appearancePref == "light" || appearancePref == "tongtou" || appearancePref == "dark" {
            return appearancePref
        }
        let eff = appearance ?? pillView?.effectiveAppearance ?? NSApp.effectiveAppearance
        let isDark = eff.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        return isDark ? "dark" : "light"
    }

    private func palette(for theme: String) -> ThemePalette {
        switch theme {
        case "light":
            return ThemePalette(
                gemTag: Self.hexColor(0x0EA5E9),
                cldTag: Self.hexColor(0x8B5CF6),
                sep: Self.hexColor(0x94A3B8, alpha: 0.78),
                ok: Self.hexColor(0x10B981),
                warn: Self.hexColor(0xF59E0B),
                crit: Self.hexColor(0xF43F5E),
                expired: Self.hexColor(0x94A3B8),
                border: Self.hexColor(0xF472B6, alpha: 0.50),
                tint: NSColor.clear
            )
        case "tongtou":
            return ThemePalette(
                gemTag: Self.hexColor(0x38A3A5),
                cldTag: Self.hexColor(0xC08A4B),
                sep: Self.hexColor(0x94A3B8, alpha: 0.75),
                ok: Self.hexColor(0x10B981),
                warn: Self.hexColor(0xF59E0B),
                crit: Self.hexColor(0xF43F5E),
                expired: Self.hexColor(0x94A3B8),
                border: Self.hexColor(0x7BA7A7, alpha: 0.54),
                tint: NSColor.clear
            )
        default:
            return ThemePalette(
                gemTag: Self.hexColor(0x38BDF8),
                cldTag: Self.hexColor(0xC084FC),
                sep: Self.hexColor(0x94A3B8, alpha: 0.72),
                ok: Self.hexColor(0x34D399),
                warn: Self.hexColor(0xFBBF24),
                crit: Self.hexColor(0xF87171),
                expired: Self.hexColor(0x94A3B8),
                border: Self.hexColor(0x38BDF8, alpha: 0.44),
                tint: NSColor.clear
            )
        }
    }

    private func valueColor(usedPct: Double, expired: Bool, pal: ThemePalette) -> NSColor {
        if expired { return pal.expired }
        if usedPct >= 80.0 { return pal.crit }
        if usedPct >= 55.0 { return pal.warn }
        return pal.ok
    }

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

    private func acquireSingleInstanceLock() -> Bool {
        let myPID = ProcessInfo.processInfo.processIdentifier
        let bundleID = Bundle.main.bundleIdentifier ?? "local.agy.usage.menubar"
        let peers = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
        if peers.contains(where: { $0.processIdentifier != myPID && !$0.isTerminated }) {
            return false
        }

        let cacheDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".cache/agy-usage")
        try? FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)
        let lockPath = cacheDir.appendingPathComponent(".menubar.lock").path
        let fd = open(lockPath, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        if fd >= 0 {
            if flock(fd, LOCK_EX | LOCK_NB) != 0 {
                close(fd)
                return false
            }
            lockFD = fd
        }
        return true
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if !acquireSingleInstanceLock() {
            DistributedNotificationCenter.default().postNotificationName(
                activateNote,
                object: nil,
                userInfo: nil,
                deliverImmediately: true
            )
            NSApplication.shared.terminate(nil)
            return
        }

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        setupFloatingPill()
        applyAppearance()
        updateIndicators(compactBar: "AGY", pillText: tr("AGY 连接中…", "AGY 連線中…", "AGY Connecting…"), level: "ok")
        rebuildMenu()
        updatePillVisibility()
        fetchStats(autoStartDaemon: true)

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleScreenChange),
            name: NSApplication.didChangeScreenParametersNotification,
            object: nil
        )
        NSWorkspace.shared.notificationCenter.addObserver(
            self,
            selector: #selector(handleWake),
            name: NSWorkspace.didWakeNotification,
            object: nil
        )
        DistributedNotificationCenter.default().addObserver(
            self,
            selector: #selector(handleExternalActivate),
            name: activateNote,
            object: nil
        )

        timer = Timer.scheduledTimer(withTimeInterval: 6.0, repeats: true) { [weak self] _ in
            self?.fetchStats(autoStartDaemon: false)
        }
    }

    @objc private func handleScreenChange() {
        ensurePillOnVisibleScreen(save: true)
    }

    @objc private func handleWake() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            guard let self = self else { return }
            self.ensurePillOnVisibleScreen(save: false)
            self.updatePillVisibility()
            self.fetchStats(autoStartDaemon: true)
        }
    }

    @objc private func handleExternalActivate() {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.showFloatingPill = true
            self.ensurePillOnVisibleScreen(save: true)
            self.fetchStats(autoStartDaemon: true)
        }
    }

    private func defaultTopRightOrigin(width: CGFloat) -> NSPoint {
        let vf = NSScreen.main?.visibleFrame ?? NSScreen.screens.first?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        return NSPoint(x: vf.maxX - width - 14, y: vf.maxY - pillHeight - 8)
    }

    private func clampedOrigin(for candidate: NSRect) -> NSPoint {
        let screens = NSScreen.screens
        if !screens.isEmpty {
            let center = NSPoint(x: candidate.midX, y: candidate.midY)
            if let host = screens.first(where: { $0.visibleFrame.contains(center) }) ??
                screens.first(where: {
                    let inter = $0.visibleFrame.intersection(candidate)
                    return !inter.isNull && inter.width >= candidate.width * 0.6 && inter.height >= candidate.height * 0.8
                }) {
                let vf = host.visibleFrame
                let cx = min(max(candidate.origin.x, vf.minX + 6), vf.maxX - candidate.width - 6)
                let cy = min(max(candidate.origin.y, vf.minY + 6), vf.maxY - candidate.height - 6)
                return NSPoint(x: cx, y: cy)
            }
        }
        return defaultTopRightOrigin(width: candidate.width)
    }

    private func ensurePillOnVisibleScreen(save: Bool) {
        guard pillPanel != nil else { return }
        let cur = pillPanel.frame
        let safeOrigin = clampedOrigin(for: cur)
        if abs(safeOrigin.x - cur.origin.x) > 0.5 || abs(safeOrigin.y - cur.origin.y) > 0.5 {
            pillPanel.setFrameOrigin(safeOrigin)
        }
        if save {
            UserDefaults.standard.set(Double(safeOrigin.x), forKey: pillXKey)
            UserDefaults.standard.set(Double(safeOrigin.y), forKey: pillYKey)
        }
    }

    private func setupFloatingPill() {
        let w: CGFloat = 168
        let h: CGFloat = pillHeight
        var origin = defaultTopRightOrigin(width: w)
        if UserDefaults.standard.object(forKey: pillXKey) != nil {
            let savedX = CGFloat(UserDefaults.standard.double(forKey: pillXKey))
            let savedY = CGFloat(UserDefaults.standard.double(forKey: pillYKey))
            origin = clampedOrigin(for: NSRect(x: savedX, y: savedY, width: w, height: h))
        }

        pillPanel = NSPanel(
            contentRect: NSRect(x: origin.x, y: origin.y, width: w, height: h),
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
        pillView.wantsLayer = true
        pillView.layer?.cornerRadius = h / 2
        pillView.layer?.masksToBounds = true
        pillView.layer?.borderWidth = 1.0

        pillBlurView = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: w, height: h))
        pillBlurView.material = .hudWindow
        pillBlurView.blendingMode = .behindWindow
        pillBlurView.state = .active
        pillBlurView.alphaValue = 0.50
        pillBlurView.autoresizingMask = [.width, .height]
        pillView.addSubview(pillBlurView)

        pillLabel = NSTextField(labelWithString: "● AGY")
        pillLabel.alignment = .center
        pillLabel.frame = NSRect(x: 10, y: 5, width: w - 20, height: 18)
        pillLabel.textColor = .labelColor
        pillView.addSubview(pillLabel)

        pillView.onClick = { [weak self] in
            guard let self = self else { return }
            if self.lastStats == nil {
                self.fetchStats(autoStartDaemon: true)
            }
            self.sharedMenu.popUp(positioning: nil, at: NSPoint(x: 0, y: -4), in: self.pillView)
        }
        pillView.onPositionChanged = { [weak self] _ in
            self?.ensurePillOnVisibleScreen(save: true)
        }

        pillPanel.contentView = pillView
    }

    private func resizePill(toFit attrText: NSAttributedString) {
        guard pillPanel != nil else { return }
        let idealW = min(268, max(136, ceil(attrText.size().width) + 26))
        let oldFrame = pillPanel.frame
        if abs(idealW - oldFrame.width) >= 2 {
            // Keep right edge anchored so expanding text doesn't drift off-screen
            let anchoredX = oldFrame.maxX - idealW
            let cand = NSRect(x: anchoredX, y: oldFrame.origin.y, width: idealW, height: pillHeight)
            let safePt = clampedOrigin(for: cand)
            pillPanel.setFrame(NSRect(x: safePt.x, y: safePt.y, width: idealW, height: pillHeight), display: true)
            pillView.frame = NSRect(x: 0, y: 0, width: idealW, height: pillHeight)
            pillBlurView.frame = NSRect(x: 0, y: 0, width: idealW, height: pillHeight)
            pillLabel.frame = NSRect(x: 10, y: 5, width: idealW - 20, height: 18)
        }
    }

    private func updatePillVisibility() {
        if showFloatingPill {
            ensurePillOnVisibleScreen(save: false)
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

    private func dotColor(for level: String, pal: ThemePalette) -> NSColor {
        switch level {
        case "critical": return pal.crit
        case "warning": return pal.warn
        default: return pal.ok
        }
    }

    private func updateIndicators(compactBar: String, pillText: String, level: String) {
        let pal = palette(for: resolvedTheme())
        let dot = dotColor(for: level, pal: pal)

        if let button = statusItem.button {
            let barPal = palette(for: resolvedTheme(for: button.effectiveAppearance))
            let attr = NSMutableAttributedString()
            attr.append(NSAttributedString(string: "●", attributes: [
                .foregroundColor: dotColor(for: level, pal: barPal),
                .font: NSFont.systemFont(ofSize: 9.5, weight: .bold)
            ]))
            attr.append(NSAttributedString(string: compactBar, attributes: [
                .font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .medium)
            ]))
            button.attributedTitle = attr
        }

        let pillAttr = NSMutableAttributedString()
        pillAttr.append(NSAttributedString(string: "● ", attributes: [
            .foregroundColor: dot,
            .font: NSFont.systemFont(ofSize: 10.5, weight: .bold)
        ]))
        pillAttr.append(NSAttributedString(string: pillText, attributes: [
            .foregroundColor: NSColor.labelColor,
            .font: NSFont.monospacedDigitSystemFont(ofSize: 11.5, weight: .semibold)
        ]))
        pillLabel.attributedStringValue = pillAttr
        resizePill(toFit: pillAttr)
    }

    private func updateQuotaIndicators(gem: QuotaBucket?, cld: QuotaBucket?, fallback: QuotaBucket?, level: String) {
        let pillPal = palette(for: resolvedTheme())
        let pillFont = NSFont.monospacedDigitSystemFont(ofSize: 11.5, weight: .bold)
        let pillTagFont = NSFont.systemFont(ofSize: 11.5, weight: .heavy)
        let barFont = NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .medium)
        let barTagFont = NSFont.systemFont(ofSize: 11, weight: .semibold)

        let pillAttr = NSMutableAttributedString()
        pillAttr.append(NSAttributedString(string: "● ", attributes: [
            .foregroundColor: dotColor(for: level, pal: pillPal),
            .font: NSFont.systemFont(ofSize: 10.5, weight: .bold)
        ]))

        let barPal = palette(for: resolvedTheme(for: statusItem.button?.effectiveAppearance))
        let barAttr = NSMutableAttributedString()
        barAttr.append(NSAttributedString(string: "●", attributes: [
            .foregroundColor: dotColor(for: level, pal: barPal),
            .font: NSFont.systemFont(ofSize: 9.5, weight: .bold)
        ]))

        var hasAny = false
        let appendPair = { (tag: String, bucket: QuotaBucket, isGem: Bool, includeBarPct: Bool) in
            guard let u = bucket.used_pct else { return }
            let exp = bucket.reset_passed == true
            if hasAny {
                pillAttr.append(NSAttributedString(string: " │ ", attributes: [.foregroundColor: pillPal.sep, .font: pillFont]))
                barAttr.append(NSAttributedString(string: "│", attributes: [.foregroundColor: barPal.sep, .font: barFont]))
            }
            let pTagCol = isGem ? pillPal.gemTag : pillPal.cldTag
            let bTagCol = isGem ? barPal.gemTag : barPal.cldTag
            let pValCol = self.valueColor(usedPct: u, expired: exp, pal: pillPal)
            let bValCol = self.valueColor(usedPct: u, expired: exp, pal: barPal)

            pillAttr.append(NSAttributedString(string: "\(tag) ", attributes: [.foregroundColor: pTagCol, .font: pillTagFont]))
            pillAttr.append(NSAttributedString(string: String(format: "%.0f%%", u), attributes: [.foregroundColor: pValCol, .font: pillFont]))

            barAttr.append(NSAttributedString(string: tag, attributes: [.foregroundColor: bTagCol, .font: barTagFont]))
            let barValFmt = includeBarPct ? "%.0f%%" : "%.0f"
            barAttr.append(NSAttributedString(string: String(format: barValFmt, u), attributes: [.foregroundColor: bValCol, .font: barFont]))
            hasAny = true
        }

        let hasBoth = (gem?.used_pct != nil) && (cld?.used_pct != nil)
        if let g = gem {
            appendPair("G", g, true, !hasBoth)
        }
        if let c = cld {
            appendPair("C", c, false, true)
        }
        if !hasAny, let first = fallback, let u = first.used_pct {
            let exp = first.reset_passed == true
            let isGem = (first.pool_key ?? "").hasPrefix("gemini")
            pillAttr.append(NSAttributedString(string: "AGY ", attributes: [.foregroundColor: isGem ? pillPal.gemTag : pillPal.cldTag, .font: pillTagFont]))
            pillAttr.append(NSAttributedString(string: String(format: "%.0f%%", u), attributes: [.foregroundColor: valueColor(usedPct: u, expired: exp, pal: pillPal), .font: pillFont]))
            barAttr.append(NSAttributedString(string: String(format: "%.0f%%", u), attributes: [.foregroundColor: valueColor(usedPct: u, expired: exp, pal: barPal), .font: barFont]))
        }

        if let button = statusItem.button {
            button.attributedTitle = barAttr
        }
        pillLabel.attributedStringValue = pillAttr
        resizePill(toFit: pillAttr)
    }

    private func fetchStats(autoStartDaemon: Bool) {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/stats?window=7d") else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 2.5

        URLSession.shared.dataTask(with: req) { [weak self] data, resp, _ in
            guard let self = self else { return }
            if let data = data,
               let http = resp as? HTTPURLResponse, http.statusCode == 200,
               let decoded = try? JSONDecoder().decode(StatsResponse.self, from: data) {
                DispatchQueue.main.async {
                    self.offlineCount = 0
                    self.lastStats = decoded
                    self.applyStats(decoded)
                    self.rebuildMenu()
                }
            } else if autoStartDaemon {
                self.lastAutoRecovery = Date()
                self.startDaemonSilently()
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                    self.fetchStats(autoStartDaemon: false)
                }
            } else {
                DispatchQueue.main.async {
                    self.offlineCount += 1
                    if self.offlineCount >= 3 && Date().timeIntervalSince(self.lastAutoRecovery) >= 60.0 {
                        self.lastAutoRecovery = Date()
                        self.startDaemonSilently()
                    }
                    self.updateIndicators(compactBar: "AGY", pillText: self.tr("AGY 离线 (点此恢复)", "AGY 離線 (點此恢復)", "AGY Offline (Click)"), level: "warning")
                    self.rebuildMenu()
                }
            }
        }.resume()
    }

    private func applyStats(_ st: StatsResponse) {
        if st.quota.has_live_quota {
            let gemW = st.quota.buckets.first { ($0.pool_key ?? "").hasPrefix("gemini") && $0.window_kind == "weekly" }
            let cldW = st.quota.buckets.first { $0.pool_key == "claude_gpt" && $0.window_kind == "weekly" }

            var worst = "ok"
            for b in st.quota.buckets {
                if b.status == "critical" { worst = "critical"; break }
                if b.status == "warning" { worst = "warning" }
            }
            updateQuotaIndicators(gem: gemW, cld: cldW, fallback: st.quota.buckets.first, level: worst)
        } else {
            let todayTok = st.windows["today"]?.billable_tokens ?? 0
            let tokStr = fmtTokens(todayTok)
            updateIndicators(compactBar: tokStr, pillText: "AGY \(tokStr)", level: "ok")
        }
    }

    private func makeDisabledItem(_ title: String, monospaced: Bool = false, color: NSColor? = nil, bold: Bool = false, fontSize: CGFloat = 11.5) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        let weight: NSFont.Weight = bold ? .semibold : .regular
        let font: NSFont = monospaced
            ? NSFont.monospacedSystemFont(ofSize: fontSize - 0.5, weight: weight)
            : NSFont.systemFont(ofSize: fontSize, weight: weight)
        let resolvedColor: NSColor
        if let c = color {
            resolvedColor = c.withAlphaComponent(bold ? 0.72 : 0.58)
        } else {
            resolvedColor = NSColor.labelColor.withAlphaComponent(bold ? 0.68 : 0.55)
        }
        let attr = NSAttributedString(string: title, attributes: [
            .font: font,
            .foregroundColor: resolvedColor
        ])
        item.view = MenuInfoRowView(attributedText: attr, vPad: bold ? 5 : 4)
        return item
    }

    private func makeBucketMenuItem(_ b: QuotaBucket, pal: ThemePalette) -> NSMenuItem {
        let used = b.used_pct ?? 0.0
        let exp = b.reset_passed == true
        let tag = b.window_kind == "five_hour"
            ? tr("当前5h", "當前5h", "5h Win")
            : tr("每周7d", "每週7d", "7d Wk ")
        let rstTime = b.reset_time_cst ?? "-"
        let rst = exp
            ? tr("待刷新", "待更新", "Refresh")
            : (rstTime == "-" ? "" : "\(tr("重置", "重置", "Resets")) \(rstTime)")
        let usedWord = tr("已用", "已用", "Used")
        let monoReg = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        let monoSemi = NSFont.monospacedSystemFont(ofSize: 11, weight: .semibold)
        let valCol = valueColor(usedPct: used, expired: exp, pal: pal)

        let attr = NSMutableAttributedString()
        attr.append(NSAttributedString(string: "  \(tag)  ", attributes: [.font: monoReg, .foregroundColor: NSColor.labelColor.withAlphaComponent(0.55)]))
        attr.append(NSAttributedString(string: asciiBar(used), attributes: [.font: monoReg, .foregroundColor: valCol.withAlphaComponent(0.68)]))
        attr.append(NSAttributedString(string: String(format: "  %@ %5.1f%%", usedWord, used), attributes: [.font: monoSemi, .foregroundColor: valCol.withAlphaComponent(0.75)]))
        if !rst.isEmpty {
            attr.append(NSAttributedString(string: "  (\(rst))", attributes: [.font: monoReg, .foregroundColor: NSColor.labelColor.withAlphaComponent(0.45)]))
        }

        let item = NSMenuItem(title: attr.string, action: nil, keyEquivalent: "")
        item.view = MenuInfoRowView(attributedText: attr, vPad: 4)
        return item
    }

    private func rebuildMenu() {
        let menu = NSMenu()

        if let st = lastStats {
            let tier = (st.live_session.plan_tier ?? "").isEmpty || st.live_session.plan_tier == "-"
                ? ""
                : " · \(st.live_session.plan_tier!)"
            menu.addItem(makeDisabledItem(
                "\(tr("Antigravity 实时监控", "Antigravity 即時監控", "Antigravity Live Monitor"))\(tier)",
                color: NSColor.labelColor,
                bold: true,
                fontSize: 12.0
            ))
            menu.addItem(makeDisabledItem("\(tr("主模型", "主模型", "Model")): \(st.live_session.active_model ?? "-")"))
            menu.addItem(NSMenuItem.separator())

            if st.quota.has_live_quota {
                let pal = palette(for: resolvedTheme())
                let gemBuckets = st.quota.buckets.filter { ($0.pool_key ?? "").hasPrefix("gemini") }
                let cldBuckets = st.quota.buckets.filter { $0.pool_key == "claude_gpt" }

                if !gemBuckets.isEmpty {
                    menu.addItem(makeDisabledItem(tr("▸ Google Gemini 模型池", "▸ Google Gemini 模型池", "▸ Google Gemini Pool"), color: pal.gemTag, bold: true))
                    for b in gemBuckets {
                        menu.addItem(makeBucketMenuItem(b, pal: pal))
                    }
                }

                if !cldBuckets.isEmpty {
                    if !gemBuckets.isEmpty { menu.addItem(NSMenuItem.separator()) }
                    menu.addItem(makeDisabledItem(tr("▸ Claude / GPT 第三方池", "▸ Claude / GPT 第三方池", "▸ Claude / GPT Pool (3P)"), color: pal.cldTag, bold: true))
                    for b in cldBuckets {
                        menu.addItem(makeBucketMenuItem(b, pal: pal))
                    }
                }
            } else {
                menu.addItem(makeDisabledItem(tr("等待新开的 Antigravity 会话推送实时额度", "等待新開的 Antigravity 對話推送即時額度", "Waiting for new Antigravity chat to push quota")))
            }

            menu.addItem(NSMenuItem.separator())
            if let wt = st.windows["today"], let w7 = st.windows["7d"] {
                menu.addItem(makeDisabledItem(tr("今日有效: \(fmtTokens(wt.billable_tokens)) (\(wt.calls)次)",
                                                 "今日有效: \(fmtTokens(wt.billable_tokens)) (\(wt.calls)次)",
                                                 "Today: \(fmtTokens(wt.billable_tokens)) (\(wt.calls) calls)")))
                menu.addItem(makeDisabledItem(String(format: tr("近7日有效: %@ · 省 $%.0f", "近7日有效: %@ · 省 $%.0f", "Last 7d: %@ · Saved $%.0f"),
                                                     fmtTokens(w7.billable_tokens), w7.cache_saved_usd)))
            }
            menu.addItem(makeDisabledItem("\(tr("同步于", "同步於", "Synced")) \(st.generated_at_cst)"))
        } else {
            menu.addItem(makeDisabledItem("\(tr("本地监控服务离线", "本機監控服務離線", "Local service offline")) (127.0.0.1:\(port))"))
            let startItem = NSMenuItem(title: tr("立即启动本地监控服务", "立即啟動本機監控服務", "Start Local Monitor Service"), action: #selector(manualRefresh), keyEquivalent: "s")
            startItem.target = self
            menu.addItem(startItem)
        }

        menu.addItem(NSMenuItem.separator())

        let openItem = NSMenuItem(title: tr("打开完整 Web 监控台 (11国语言)", "開啟完整 Web 監控台 (11國語言)", "Open Web Dashboard (11 Languages)"), action: #selector(openDashboard), keyEquivalent: "o")
        openItem.target = self
        menu.addItem(openItem)

        let refItem = NSMenuItem(title: tr("立即刷新", "立即重新整理", "Refresh Now"), action: #selector(manualRefresh), keyEquivalent: "r")
        refItem.target = self
        menu.addItem(refItem)

        let appearMenu = NSMenu()
        let appearChoices = [
            (tr("浅色", "淺色", "Light"), "light"),
            (tr("通透", "通透", "Airy"), "tongtou"),
            (tr("深色", "深色", "Dark"), "dark"),
            (tr("跟随系统", "跟隨系統", "System"), "system")
        ]
        for pair in appearChoices {
            let it = NSMenuItem(title: pair.0, action: #selector(setAppearancePref(_:)), keyEquivalent: "")
            it.target = self
            it.representedObject = pair.1
            it.state = appearancePref == pair.1 ? .on : .off
            appearMenu.addItem(it)
        }
        let appearRoot = NSMenuItem(title: tr("外观", "外觀", "Appearance"), action: nil, keyEquivalent: "")
        appearRoot.submenu = appearMenu
        menu.addItem(appearRoot)

        let langMenu = NSMenu()
        for pair in [(tr("跟随系统", "跟隨系統", "Auto (System)"), "auto"), ("简体中文", "zh-CN"), ("繁體中文", "zh-TW"), ("English", "en")] {
            let it = NSMenuItem(title: pair.0, action: #selector(setLangPref(_:)), keyEquivalent: "")
            it.target = self
            it.representedObject = pair.1
            it.state = langPref == pair.1 ? .on : .off
            langMenu.addItem(it)
        }
        let langRoot = NSMenuItem(title: tr("语言 / Language", "語言 / Language", "Language / 语言"), action: nil, keyEquivalent: "")
        langRoot.submenu = langMenu
        menu.addItem(langRoot)

        let pillToggle = NSMenuItem(title: tr("显示桌面悬浮胶囊（防刘海遮挡）", "顯示桌面懸浮膠囊（防瀏海遮擋）", "Show Floating Desktop Pill"), action: #selector(togglePill), keyEquivalent: "")
        pillToggle.target = self
        pillToggle.state = showFloatingPill ? .on : .off
        menu.addItem(pillToggle)

        let resetPosItem = NSMenuItem(title: tr("重置悬浮胶囊位置", "重置懸浮膠囊位置", "Reset Pill Position"), action: #selector(resetPillPosition), keyEquivalent: "")
        resetPosItem.target = self
        menu.addItem(resetPosItem)

        let notifyOn = lastStats?.notifications?.enabled ?? false
        let notifyItem = NSMenuItem(title: tr("额度告警与回血通知 (80%/95%)", "額度告警與回血通知 (80%/95%)", "Quota Alerts & Reset Notify (80%/95%)"), action: #selector(toggleNotifications), keyEquivalent: "")
        notifyItem.target = self
        notifyItem.state = notifyOn ? .on : .off
        menu.addItem(notifyItem)

        let autoItem = NSMenuItem(title: tr("登录时自动启动", "登入時自動啟動", "Launch at Login"), action: #selector(toggleLaunchAtLogin), keyEquivalent: "")
        autoItem.target = self
        autoItem.state = FileManager.default.fileExists(atPath: launchAgentURL.path) ? .on : .off
        menu.addItem(autoItem)

        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(title: tr("退出小工具", "結束小工具", "Quit"), action: #selector(quitApp), keyEquivalent: "q")
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

    private func applyAppearance() {
        switch appearancePref {
        case "dark":
            NSApp.appearance = NSAppearance(named: .darkAqua)
            if pillBlurView != nil {
                pillBlurView.appearance = NSAppearance(named: .vibrantDark)
            }
        case "light", "tongtou":
            NSApp.appearance = NSAppearance(named: .aqua)
            if pillBlurView != nil {
                pillBlurView.appearance = NSAppearance(named: .vibrantLight)
            }
        default:
            NSApp.appearance = nil
            if pillBlurView != nil {
                pillBlurView.appearance = nil
            }
        }
        refreshPillChrome()
    }

    private func refreshPillChrome() {
        guard pillView != nil else { return }
        let theme = resolvedTheme()
        let pal = palette(for: theme)
        pillBlurView?.material = .hudWindow
        pillBlurView?.alphaValue = 0.50
        pillView.layer?.borderColor = pal.border.cgColor
        pillView.layer?.backgroundColor = NSColor.clear.cgColor
    }

    @objc private func setAppearancePref(_ sender: NSMenuItem) {
        guard let val = sender.representedObject as? String else { return }
        appearancePref = val
        rebuildMenu()
        if let st = lastStats {
            applyStats(st)
        }
    }

    @objc private func setLangPref(_ sender: NSMenuItem) {
        guard let val = sender.representedObject as? String else { return }
        langPref = val
        rebuildMenu()
        if let st = lastStats {
            applyStats(st)
        } else {
            updateIndicators(compactBar: "AGY", pillText: tr("AGY 离线 (点此恢复)", "AGY 離線 (點此恢復)", "AGY Offline (Click)"), level: "warning")
        }
    }

    @objc private func togglePill() {
        showFloatingPill.toggle()
        rebuildMenu()
    }

    @objc private func resetPillPosition() {
        UserDefaults.standard.removeObject(forKey: pillXKey)
        UserDefaults.standard.removeObject(forKey: pillYKey)
        showFloatingPill = true
        let pt = defaultTopRightOrigin(width: pillPanel.frame.width)
        pillPanel.setFrameOrigin(pt)
        pillPanel.orderFrontRegardless()
        rebuildMenu()
    }

    @objc private func toggleNotifications() {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/preferences") else { return }
        let cur = lastStats?.notifications?.enabled ?? false
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["notifications_enabled": !cur])
        URLSession.shared.dataTask(with: req) { [weak self] _, _, _ in
            DispatchQueue.main.async {
                self?.fetchStats(autoStartDaemon: false)
            }
        }.resume()
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
        if lockFD >= 0 {
            flock(lockFD, LOCK_UN)
            close(lockFD)
            lockFD = -1
        }
        NSApplication.shared.terminate(nil)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
