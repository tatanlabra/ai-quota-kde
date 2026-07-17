pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    readonly property string statusCmd: "sh -lc '$HOME/.local/bin/ai-quota-monitor status --json'"
    readonly property string refreshCmd: "sh -lc '$HOME/.local/bin/ai-quota-monitor refresh --online'"
    readonly property int pollInterval: 60000     // 1 min: relee caché (barato, sin red)

    property var report: null
    property string lastError: ""
    property bool busy: false

    Plasmoid.icon: "utilities-system-monitor"
    Plasmoid.title: "AI Quota HUD"
    Plasmoid.status: root.busy ? PlasmaCore.Types.ActiveStatus : PlasmaCore.Types.PassiveStatus

    toolTipMainText: "AI Quota — % libre por ventana"
    toolTipSubText: root.report
        ? "🔍 Claude  " + root.windowsSummary("claude")
            + (root.extraInfoText("claude") !== "" ? "  ·  " + root.extraInfoText("claude") : "") + "\n"
          + "🛠️ Codex   " + root.windowsSummary("codex")
            + (root.extraInfoText("codex") !== "" ? "  ·  " + root.extraInfoText("codex") : "") + "\n"
          + "🌐 Gemini  " + root.windowsSummary("gemini") + "  (agy, est.)" + "\n"
          + "DeepSeek " + root.extraInfoText("deepseek")
        : "Sin datos — ejecuta: ai-quota-monitor refresh"

    compactRepresentation: CompactRepresentation { plasmoidItem: root }
    fullRepresentation: FullRepresentation { plasmoidItem: root }

    // ── Poll barato: relee la caché (no toca la red) ──────────────────────
    Timer {
        id: pollTimer
        interval: root.pollInterval
        repeat: true
        running: true
        onTriggered: root.loadStatus()
    }

    // El fetch en vivo periódico lo hace el timer systemd (ai-quota-monitor.timer,
    // cada 5 min). El widget NO sondea online en bucle para no duplicar llamadas y
    // gatillar rate limiting (HTTP 429); solo lee la caché y refresca al abrirse.

    // ── Watchdog: evita que un read colgado deje busy=true para siempre ────
    Timer {
        id: busyWatchdog
        interval: 15000
        repeat: false
        running: root.busy
        onTriggered: root.busy = false
    }

    // Al abrir el popup, dispara un refresh fresco on-demand.
    onExpandedChanged: if (root.expanded) root.triggerRefresh()

    // ── DataSource para leer estado ───────────────────────────────────────
    Plasma5Support.DataSource {
        id: statusSource
        engine: "executable"
        connectedSources: []
        property string currentCommand: ""

        onNewData: function(sourceName, data) {
            if (sourceName !== currentCommand) return
            root.busy = false
            statusSource.connectedSources = []
            statusSource.currentCommand = ""
            const stdout = String(data["stdout"] || "")
            const exitCode = Number(data["exit code"] || 0)
            if (exitCode !== 0 || !stdout.trim()) {
                root.lastError = "status --json falló (exit " + exitCode + ")"
                return
            }
            try {
                root.report = JSON.parse(stdout)
                root.lastError = ""
            } catch (e) {
                root.lastError = "JSON inválido: " + String(e)
            }
        }
    }

    // ── DataSource para refresh manual ───────────────────────────────────
    Plasma5Support.DataSource {
        id: refreshSource
        engine: "executable"
        connectedSources: []
        property string currentCommand: ""

        onNewData: function(sourceName, data) {
            if (sourceName !== currentCommand) return
            refreshSource.connectedSources = []
            refreshSource.currentCommand = ""
            root.loadStatus()
        }
    }

    // ── Funciones públicas ────────────────────────────────────────────────
    function loadStatus() {
        if (root.busy) return
        root.busy = true
        statusSource.currentCommand = root.statusCmd
        statusSource.connectedSources = [root.statusCmd]
    }

    function triggerRefresh() {
        refreshSource.currentCommand = root.refreshCmd
        refreshSource.connectedSources = [root.refreshCmd]
    }

    function getProviderByKey(key) {
        if (!root.report || !root.report.providers) return null
        for (var i = 0; i < root.report.providers.length; i++) {
            if (root.report.providers[i].id === key) return root.report.providers[i]
        }
        return null
    }

    function getWindowByKey(provider, windowId) {
        if (!provider || !provider.windows) return null
        for (var i = 0; i < provider.windows.length; i++) {
            if (provider.windows[i].id === windowId) return provider.windows[i]
        }
        return null
    }

    function windowOf(providerKey, windowId) {
        return getWindowByKey(getProviderByKey(providerKey), windowId)
    }

    // Fracción FALTANTE (remaining) 0..1 de una ventana; -1 si no hay dato.
    function remainingFraction(providerKey, windowId) {
        var w = windowOf(providerKey, windowId)
        if (!w || w.percent === null || w.percent === undefined) return -1
        return Math.max(0, 1 - w.percent)
    }

    function remainingText(providerKey, windowId) {
        var f = remainingFraction(providerKey, windowId)
        return f < 0 ? "—" : Math.round(f * 100) + "%"
    }

    function resetText(providerKey, windowId) {
        var w = windowOf(providerKey, windowId)
        if (!w || !w.reset_at) return ""
        // Convierte el ISO (UTC) a la hora local del sistema (America/Santiago).
        var d = new Date(w.reset_at)
        if (isNaN(d.getTime())) return w.reset_at.substring(11, 16)
        return "reset " + Qt.formatTime(d, "HH:mm")
    }

    // ¿La ventana proviene de caché preservada (fetch en vivo falló)?
    function windowStale(providerKey, windowId) {
        var w = windowOf(providerKey, windowId)
        return !!(w && w.stale_since)
    }

    // ¿Algún dato del proveedor quedó preservado/stale?
    function providerStale(providerKey) {
        var p = getProviderByKey(providerKey)
        if (!p || !p.windows) return false
        for (var i = 0; i < p.windows.length; i++)
            if (p.windows[i].stale_since) return true
        return false
    }

    // ¿El proveedor está degradado (fetch en vivo fallando ahora)?
    function providerDegraded(providerKey) {
        var p = getProviderByKey(providerKey)
        return !!(p && p.status && p.status !== "ok")
    }

    // Etiqueta de estado del proveedor para el popup: "" si todo OK.
    function providerStatusText(providerKey) {
        var p = getProviderByKey(providerKey)
        if (!p) return ""
        // stale_since más antiguo entre sus ventanas.
        var oldest = null
        if (p.windows) {
            for (var i = 0; i < p.windows.length; i++) {
                var s = p.windows[i].stale_since
                if (s && (oldest === null || s < oldest)) oldest = s
            }
        }
        if (oldest) return "⚠ caché · " + ageText(oldest)
        if (p.status && p.status !== "ok") return "⚠ sin datos en vivo"
        return ""
    }

    // "hace Xm" desde un ISO; "" si no aplica.
    function ageText(iso) {
        if (!iso) return ""
        var d = new Date(iso)
        if (isNaN(d.getTime())) return ""
        var mins = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000))
        if (mins < 60) return "hace " + mins + "m"
        var hrs = Math.round(mins / 60)
        return "hace " + hrs + "h"
    }

    // ── Ventanas de cuota que el proveedor expone REALMENTE ───────────────────
    // El esquema no es fijo: Codex pasó de (5h + semana) a solo semana según el plan.
    // La UI se dibuja desde lo que trae el reporte, no desde un modelo hardcodeado, así
    // que un cambio de ventanas upstream se refleja solo, sin tocar el QML.
    readonly property var windowOrder: ["session", "weekly", "daily", "balance"]

    function gaugeWindows(providerKey) {
        var p = root.getProviderByKey(providerKey)
        if (!p || !p.windows) return []
        var out = []
        for (var i = 0; i < root.windowOrder.length; i++) {
            var w = root.getWindowByKey(p, root.windowOrder[i])
            if (w && w.percent !== null && w.percent !== undefined) out.push(root.windowOrder[i])
        }
        return out
    }

    function gaugeOuterFraction(providerKey) {
        var g = root.gaugeWindows(providerKey)
        return g.length > 0 ? root.remainingFraction(providerKey, g[0]) : -1
    }

    function gaugeInnerFraction(providerKey) {
        var g = root.gaugeWindows(providerKey)
        return g.length > 1 ? root.remainingFraction(providerKey, g[1]) : -1
    }

    function gaugeSingleRing(providerKey) {
        return root.gaugeWindows(providerKey).length < 2
    }

    // Nombre corto de la ventana. La duración real viene en la etiqueta ("Weekly (7d)"):
    // se usa esa, para no seguir rotulando "5h" una ventana que ya no dura 5h.
    function windowShortName(providerKey, windowId) {
        var w = root.windowOf(providerKey, windowId)
        var m = w && w.label ? String(w.label).match(/\((\d+[mhd])\)/) : null
        if (m) return m[1]
        switch (windowId) {
        case "session": return "5h"
        case "weekly":  return "semana"
        case "daily":   return "día"
        case "balance": return "saldo"
        }
        return windowId
    }

    // Resumen de una línea: "5h 82% · 7d 91%", o "7d 95%" si solo hay una ventana.
    function windowsSummary(providerKey) {
        var g = root.gaugeWindows(providerKey)
        if (g.length === 0) return "—"
        var parts = []
        for (var i = 0; i < g.length; i++)
            parts.push(root.windowShortName(providerKey, g[i]) + " " + root.remainingText(providerKey, g[i]))
        return parts.join(" · ")
    }

    // Texto del centro de la dona: el % libre más crítico entre las ventanas dadas.
    function donutCenterText(providerKey, windowIds) {
        var best = 2
        for (var i = 0; i < windowIds.length; i++) {
            var f = remainingFraction(providerKey, windowIds[i])
            if (f >= 0 && f < best) best = f
        }
        return best <= 1 ? Math.round(best * 100) + "%" : ""
    }

    // Saldo de créditos (solo Codex/wham); -1 si no hay.
    function creditsOf(providerKey) {
        var w = windowOf(providerKey, "credits")
        return (w && w.used !== undefined && w.used !== null) ? Math.round(w.used) : -1
    }

    function _fmtCount(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + "M"
        if (n >= 1000)    return (n / 1000).toFixed(0) + "k"
        return String(Math.round(n))
    }

    // Info extra de presupuesto/uso, compacta. Combina lo disponible: uso local de
    // Claude Code (ccusage), créditos, USD y saldo DeepSeek en CLP. "" si no hay nada.
    function extraInfoText(providerKey) {
        var parts = []
        var l = windowOf(providerKey, "local")
        if (l && l.used !== undefined && l.used !== null && l.used > 0)
            parts.push("🔥 " + _fmtCount(l.used) + " tok")
        var c = windowOf(providerKey, "credits")
        if (c && c.used !== undefined && c.used !== null)
            parts.push("💳 " + Math.round(c.used) + " créd")
        var u = windowOf(providerKey, "usd")
        if (u && u.used !== undefined && u.used !== null) {
            var lim = (u.limit !== undefined && u.limit !== null && u.limit > 0) ? "/$" + Math.round(u.limit) : ""
            parts.push("💵 $" + u.used.toFixed(2) + lim)
        }
        var b = windowOf(providerKey, "balance")
        if (b && b.used !== undefined && b.used !== null) {
            if (b.unit === "clp_estimated")
                parts.push("$" + Math.round(b.used) + " CLP")
            else
                parts.push(b.used.toFixed ? b.used.toFixed(2) + " " + (b.unit || "") : String(b.used))
        }
        return parts.join("  ·  ")
    }

    function pctDisplay(win) {
        if (!win) return "—"
        if (win.percent !== null && win.percent !== undefined) {
            return Math.round(win.percent * 100) + "%"
        }
        if (win.used !== undefined) {
            const u = win.used
            if (u >= 1000000) return (u / 1000000).toFixed(1) + "M"
            if (u >= 1000)    return (u / 1000).toFixed(0) + "k"
            return String(Math.round(u))
        }
        return "—"
    }

    function worstPct() {
        if (!root.report || !root.report.providers) return -1
        var max = -1
        for (var i = 0; i < root.report.providers.length; i++) {
            var p = root.report.providers[i]
            for (var j = 0; j < p.windows.length; j++) {
                var w = p.windows[j]
                if (w.percent !== null && w.percent !== undefined) {
                    if (w.percent > max) max = w.percent
                }
            }
        }
        return max
    }

    Component.onCompleted: {
        root.loadStatus()      // muestra la caché al instante
        root.triggerRefresh()  // y dispara una actualización fresca
    }
}
