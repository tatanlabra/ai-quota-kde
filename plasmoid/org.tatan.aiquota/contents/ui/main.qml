pragma ComponentBehavior: Bound

import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import "components"

PlasmoidItem {
    id: root

    property string hoveredProvider: ""
    property string selectedProvider: "claude"

    // El colector es la unidad systemd y nadie mas. El widget lee la cache que
    // ella escribe y, cuando se pide un refresco a mano, arranca esa misma unidad:
    // nunca sale a la red por su cuenta: la recoleccion en vivo desde el widget era
    // el vector documentado del HTTP 429 en la usage endpoint de Claude.
    readonly property string refreshUnit: "ai-quota-monitor.service"
    readonly property string refreshCmd: "systemctl --user start ai-quota-monitor.service"
    // Presupuesto propio: la unidad admite 4 arranques por 600 s (2 los pone el
    // timer), asi que la interfaz se limita a 2 para no dejar al timer sin cupo.
    readonly property int manualBudget: 2
    readonly property int manualWindowMs: 600000
    readonly property int cooldownMs: 120000
    // Configuracion del plasmoide (clic derecho -> Configurar). Los umbrales estaban
    // fijos dentro del calculo de color y no habia forma de ocultar un proveedor.
    readonly property real amberThreshold: Math.max(0.01, Plasmoid.configuration.amberThreshold / 100)
    readonly property real redThreshold: Math.max(0.005, Plasmoid.configuration.redThreshold / 100)
    readonly property bool showResetRing: Plasmoid.configuration.showResetRing
    readonly property int compactMode: Plasmoid.configuration.compactMode

    readonly property var providerOrder: ["claude", "codex", "gemini", "copilot", "deepseek"]

    readonly property var visibleProviders: {
        const cfg = Plasmoid.configuration
        const shown = {
            "claude": cfg.showClaude, "codex": cfg.showCodex, "gemini": cfg.showGemini,
            "copilot": cfg.showCopilot, "deepseek": cfg.showDeepseek
        }
        return root.providerOrder.filter(function(key) { return shown[key] !== false })
    }

    // En modo compacto reducido, el panel muestra solo el proveedor con menos margen.
    readonly property string worstProvider: {
        var worst = ""
        var best = 2
        for (var i = 0; i < root.visibleProviders.length; i++) {
            var key = root.visibleProviders[i]
            var frac = root.gaugeOuterFraction(key)
            var inner = root.gaugeInnerFraction(key)
            if (inner >= 0 && (frac < 0 || inner < frac)) frac = inner
            if (frac >= 0 && frac < best) { best = frac; worst = key }
        }
        return worst !== "" ? worst : (root.visibleProviders.length > 0 ? root.visibleProviders[0] : "claude")
    }

    readonly property var detailOrder: [
        "session", "weekly",
        "antigravity_gemini_weekly", "antigravity_claude_gpt_weekly",
        "antigravity_activity", "gemini_cli_activity",
        "copilot_chat",
        "balance", "budget", "local", "credits", "usd"
    ]
    // Orden = anillos de la dona: el PRIMER id encontrado pinta el anillo EXTERNO y el
    // segundo el INTERNO (ver gaugeWindows/gaugeOuterFraction). Para Antigravity eso
    // deja fuera el grupo de modelos propios de Google (gemini-weekly) y dentro el de
    // terceros (3p-weekly = Claude/GPT facturado por Google), que es lo pedido.
    readonly property var gaugeOrder: [
        "session", "weekly",
        "antigravity_gemini_weekly", "antigravity_claude_gpt_weekly",
        "copilot_chat",
        "budget"
    ]

    property var report: null
    property string lastError: ""
    // idle | running | cooldown | limited
    property string refreshState: "idle"
    property string refreshHint: ""
    // Marcas de tiempo de los arranques manuales, para el presupuesto de la ventana.
    property var manualStarts: []
    readonly property bool busy: root.refreshState === "running"
    readonly property bool canRefresh: root.refreshState === "idle"
    // Se enciende para el gate de reactividad; deja como mucho 300 lineas al dia.
    property bool debugReloads: false

    Plasmoid.icon: "utilities-system-monitor"
    Plasmoid.title: "AI Quota HUD"
    // Activo cuando hay datos que mostrar. Antes alternaba con `busy`, que subia
    // y bajaba en cada tick del poll sin significar nada para quien mira.
    Plasmoid.status: root.report ? PlasmaCore.Types.ActiveStatus : PlasmaCore.Types.PassiveStatus

    // El texto queda disponible para lectores de pantalla; la presentación visual usa
    // toolTipItem y nunca inicia I/O adicional al pasar el cursor.
    toolTipMainText: i18n("AI Quota HUD — quota, activity and balance")
    toolTipSubText: root.accessibleSummary()
    toolTipItem: QuotaTooltip { plasmoidItem: root }

    compactRepresentation: CompactRepresentation { plasmoidItem: root }
    fullRepresentation: FullRepresentation { plasmoidItem: root }

    // Lee la cache que escribe el timer systemd. No arranca Python ni sale a la red:
    // `status --json` solo hacia `cat` de este mismo fichero, pero levantando el venv
    // con typer, rich y pydantic ~1440 veces al dia para leer 7 KB.
    StatusFile {
        id: statusFile
        onLoaded: function(raw) {
            try {
                root.report = JSON.parse(raw)
                root.lastError = ""
                if (root.debugReloads)
                    console.warn("aiquota: reloaded", root.report ? root.report.generated_at : "?")
            } catch (e) {
                root.lastError = i18nc("%1 es el mensaje de error del parser", "invalid JSON: %1", String(e))
            }
        }
        onFailed: function(message) {
            root.lastError = i18nc("%1 es el mensaje de error al leer el fichero", "unreadable cache: %1", message)
        }
    }

    ShellRunner {
        id: refreshRunner
        onFinished: function(exitCode, stdout, stderr) {
            if (exitCode === 0) {
                root.refreshState = "cooldown"
                root.refreshHint = ""
                cooldownTimer.restart()
                // La relectura la dispara el watcher al reescribirse el fichero.
                return
            }
            // systemd rechaza el arranque cuando se agota StartLimitBurst.
            if (String(stderr).indexOf("repeated too quickly") !== -1) {
                root.refreshState = "limited"
                root.refreshHint = i18n("systemd rate-limited the collector; wait a few minutes")
                cooldownTimer.restart()
                return
            }
            root.refreshState = "idle"
            root.refreshHint = String(stderr).trim() || i18nc("%1 es un codigo de salida", "systemctl exited %1", exitCode)
            root.lastError = root.refreshHint
        }
    }

    Timer {
        id: cooldownTimer
        interval: root.cooldownMs
        onTriggered: {
            root.refreshState = "idle"
            root.refreshHint = ""
        }
    }

    // Arranca el colector por su unidad, que sigue siendo el unico escritor de la
    // cache y el unico que habla con la red. systemd deduplica: si ya esta corriendo,
    // este arranque se une al job en curso en vez de lanzar una segunda recoleccion.
    function requestManualRefresh() {
        if (!root.canRefresh)
            return false
        const now = Date.now()
        const recent = []
        for (var i = 0; i < root.manualStarts.length; i++) {
            if (now - root.manualStarts[i] < root.manualWindowMs)
                recent.push(root.manualStarts[i])
        }
        if (recent.length >= root.manualBudget) {
            root.manualStarts = recent
            root.refreshState = "limited"
            root.refreshHint = i18ncp("%1 es cuantos refrescos manuales permite la ventana",
                                      "%1 manual refresh already requested in the last 10 minutes",
                                      "%1 manual refreshes already requested in the last 10 minutes",
                                      root.manualBudget)
            cooldownTimer.restart()
            return false
        }
        recent.push(now)
        root.manualStarts = recent
        root.refreshState = "running"
        root.refreshHint = ""
        if (!refreshRunner.run(root.refreshCmd)) {
            root.refreshState = "idle"
            return false
        }
        return true
    }

    function refreshButtonText() {
        switch (root.refreshState) {
        case "running": return "⟳ …"
        case "cooldown": return i18nc("el botón espera antes de poder pulsarse otra vez", "⟳ wait")
        case "limited": return i18nc("systemd limitó los arranques", "⚠ limited")
        }
        return i18nc("botón que arranca el colector", "⟳ refresh")
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

    function metricKind(win) {
        if (!win) return "unknown"
        if (win.metric_kind) return String(win.metric_kind)
        return win.id === "balance" ? "balance" : "quota"
    }

    function renewalKind(win) {
        if (!win) return "unknown"
        if (win.renewal_kind) return String(win.renewal_kind)
        if (win.id === "balance" || win.id === "budget" || win.id === "credits") return "none"
        if (win.id === "daily") return "calendar_cutoff"
        return win.reset_at ? "rolling" : "unknown"
    }

    function remainingFraction(providerKey, windowId) {
        var w = windowOf(providerKey, windowId)
        if (!w || metricKind(w) !== "quota" || w.percent === null || w.percent === undefined) return -1
        return Math.max(0, 1 - w.percent)
    }

    function remainingText(providerKey, windowId) {
        var f = remainingFraction(providerKey, windowId)
        return f < 0 ? "—" : Math.round(f * 100) + "%"
    }

    function localTimeText(iso) {
        if (!iso) return ""
        var d = new Date(iso)
        return isNaN(d.getTime()) ? "" : Qt.formatDateTime(d, "ddd d MMM · HH:mm")
    }

    function _countdown(deltaMs) {
        var mins = Math.max(0, Math.ceil(deltaMs / 60000))
        if (mins < 24 * 60) {
            var hours = Math.floor(mins / 60)
            return i18nc("cuenta atrás en horas y minutos", "in %1h %2m", hours, mins % 60)
        }
        var days = Math.floor(mins / (24 * 60))
        var hours = Math.floor((mins % (24 * 60)) / 60)
        return i18nc("cuenta atrás en días y horas", "in %1d %2h", days, hours)
    }

    function _renewalDayText(d, now) {
        var today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
        var tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000)
        var target = new Date(d.getFullYear(), d.getMonth(), d.getDate())
        var day = target.getTime() === today.getTime() ? i18n("today")
            : target.getTime() === tomorrow.getTime() ? i18n("tomorrow")
            : Qt.formatDate(d, "ddd d MMM")
        return day + ", " + Qt.formatTime(d, "HH:mm")
    }

    function renewalText(providerKey, windowId) {
        var w = windowOf(providerKey, windowId)
        if (!w) return ""
        var kind = renewalKind(w)
        if (kind === "none") return i18n("no renewal")
        if (!w.reset_at) return ""
        var d = new Date(w.reset_at)
        if (isNaN(d.getTime())) return ""
        var delta = d.getTime() - Date.now()
        if (delta <= 0) return kind === "calendar_cutoff" ? i18n("local cutoff pending") : i18n("renewal pending")
        if (kind === "calendar_cutoff") {
            if (metricKind(w) === "quota")
                return i18nc("%1 es un día y una hora, %2 una cuenta atrás",
                             "observed reset %1 · %2", _renewalDayText(d, new Date()), _countdown(delta))
            return i18nc("%1 es un día y una hora, %2 una cuenta atrás",
                         "local cutoff %1 · %2", _renewalDayText(d, new Date()), _countdown(delta))
        }
        return i18nc("%1 es un día y una hora, %2 una cuenta atrás",
                     "renews %1 · %2", _renewalDayText(d, new Date()), _countdown(delta))
    }

    function windowStale(providerKey, windowId) {
        var w = windowOf(providerKey, windowId)
        return !!(w && w.stale_since)
    }

    function providerStale(providerKey) {
        var p = getProviderByKey(providerKey)
        if (!p || !p.windows) return false
        for (var i = 0; i < p.windows.length; i++)
            if (p.windows[i].stale_since) return true
        return false
    }

    function ageText(iso) {
        if (!iso) return ""
        var d = new Date(iso)
        if (isNaN(d.getTime())) return ""
        var mins = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000))
        if (mins < 60) return i18nc("antigüedad en minutos", "%1m ago", mins)
        return i18nc("antigüedad en horas", "%1h ago", Math.round(mins / 60))
    }

    function providerStatusText(providerKey) {
        var p = getProviderByKey(providerKey)
        if (!p) return ""
        var oldest = null
        if (p.windows) {
            for (var i = 0; i < p.windows.length; i++) {
                var stale = p.windows[i].stale_since
                if (stale && (oldest === null || stale < oldest)) oldest = stale
            }
        }
        if (oldest) return i18nc("dato preservado de caché y su antigüedad", "⚠ cached · %1", ageText(oldest))
        if (p.status && p.status !== "ok") {
            if (providerKey === "deepseek") return i18n("⚠ API balance not configured")
            if (providerKey === "gemini") {
                return windowUsable(windowOf("gemini", "antigravity_gemini_weekly"))
                    ? i18n("⚠ no compatible local log")
                    : i18n("⚠ Antigravity quota unavailable")
            }
            return i18n("⚠ no live data")
        }
        return ""
    }

    function windowUsable(win) {
        return !!(win && win.confidence !== "unknown" && win.source !== "unavailable")
    }

    function hasUsableDetailData(providerKey) {
        var ids = detailWindows(providerKey)
        for (var i = 0; i < ids.length; i++) {
            if (windowUsable(windowOf(providerKey, ids[i]))) return true
        }
        return false
    }

    function gaugeWindows(providerKey) {
        var p = getProviderByKey(providerKey)
        if (!p || !p.windows) return []
        var out = []
        for (var i = 0; i < gaugeOrder.length; i++) {
            var id = gaugeOrder[i]
            var w = getWindowByKey(p, id)
            if (w && metricKind(w) === "quota" && w.percent !== null && w.percent !== undefined)
                out.push(id)
        }
        return out.slice(0, 2)
    }

    function detailWindows(providerKey) {
        var p = getProviderByKey(providerKey)
        if (!p || !p.windows) return []
        var out = []
        for (var i = 0; i < detailOrder.length; i++) {
            if (getWindowByKey(p, detailOrder[i])) out.push(detailOrder[i])
        }
        for (var j = 0; j < p.windows.length; j++) {
            if (out.indexOf(p.windows[j].id) === -1) out.push(p.windows[j].id)
        }
        return out
    }

    function gaugeOuterFraction(providerKey) {
        var ids = gaugeWindows(providerKey)
        return ids.length > 0 ? remainingFraction(providerKey, ids[0]) : -1
    }

    function gaugeInnerFraction(providerKey) {
        var ids = gaugeWindows(providerKey)
        return ids.length > 1 ? remainingFraction(providerKey, ids[1]) : -1
    }

    function gaugeSingleRing(providerKey) {
        return gaugeWindows(providerKey).length < 2
    }

    // El anillo compacto representa siempre el reinicio de cuota más próximo que el
    // reporte conoce. Antigravity mantiene dos relojes: se elige el primero y el
    // popup conserva ambas líneas, por lo que no se presenta como una sola cuota.
    function nextQuotaReset(providerKey) {
        var p = getProviderByKey(providerKey)
        if (!p || !p.windows) return null
        var now = Date.now()
        var earliest = null
        var earliestMs = 0
        for (var i = 0; i < p.windows.length; i++) {
            var w = p.windows[i]
            if (!windowUsable(w) || metricKind(w) !== "quota" || renewalKind(w) === "none" || !w.reset_at)
                continue
            var d = new Date(w.reset_at)
            var resetMs = d.getTime()
            if (isNaN(resetMs) || resetMs < now)
                continue
            if (!earliest || resetMs < earliestMs) {
                earliest = w
                earliestMs = resetMs
            }
        }
        return earliest
    }

    // El tercer anillo contiene hasta siete segmentos blancos, uno por día
    // restante. DeepSeek sólo expone saldo/presupuesto, por lo que nunca dibuja
    // un reloj de reinicio ficticio.
    function resetDaysRemaining(providerKey) {
        if (providerKey === "deepseek") return -1
        var w = nextQuotaReset(providerKey)
        if (!w) return -1
        var d = new Date(w.reset_at)
        if (isNaN(d.getTime())) return -1
        var delta = d.getTime() - Date.now()
        if (delta < 0) return -1
        return Math.max(0, Math.min(7, Math.ceil(delta / (24 * 60 * 60 * 1000))))
    }

    function nextQuotaResetSummary(providerKey) {
        var w = nextQuotaReset(providerKey)
        if (!w) return ""
        var d = new Date(w.reset_at)
        return i18nc("%1 es el nombre de una ventana de cuota, %2 una cuenta atrás",
                     "next reset: %1 · %2", windowShortName(providerKey, w.id),
                     _countdown(d.getTime() - Date.now()))
    }

    function windowShortName(providerKey, windowId) {
        var w = windowOf(providerKey, windowId)
        if (!w) return windowId
        if (windowId === "session" || windowId === "weekly") {
            var duration = String(w.label || "").match(/\((\d+[mhd])\)/)
            return duration ? duration[1] : String(w.label || windowId)
        }
        return String(w.label || windowId)
    }

    function metricValueText(win) {
        if (!win) return "—"
        if (win.confidence === "unknown") return i18n("no data")
        var kind = metricKind(win)
        if (kind === "quota" && win.percent !== null && win.percent !== undefined)
            return i18nc("porcentaje de cuota que queda libre", "%1% free", Math.round((1 - win.percent) * 100))
        var unit = String(win.unit || "")
        var used = Number(win.used || 0)
        if (kind === "balance") {
            if (unit === "usd") return "$" + used.toFixed(2) + " USD"
            if (unit === "cny") return "¥" + used.toFixed(2) + " CNY"
            return used.toFixed(2) + (unit ? " " + unit.toUpperCase() : "")
        }
        if (unit === "requests") return i18nc("abreviatura de solicitudes", "%1 req.", _fmtCount(used))
        if (unit === "tokens") return i18nc("abreviatura de tokens", "%1 tok", _fmtCount(used))
        if (unit === "credits") return i18nc("abreviatura de créditos", "%1 cred.", Math.round(used))
        return _fmtCount(used) + (unit ? " " + unit : "")
    }

    function metricTone(win, accent) {
        if (!win) return HudPalette.confidenceUnknown
        if (win.confidence === "unknown") return HudPalette.confidenceUnknown
        if (win.confidence === "configured_estimate") return HudPalette.caution
        if (metricKind(win) !== "quota" || win.percent === null || win.percent === undefined) return accent
        var frac = 1 - win.percent
        if (frac <= root.redThreshold) return HudPalette.danger
        if (frac <= root.amberThreshold) return HudPalette.warning
        return accent
    }

    function confidenceText(win) {
        if (!win) return ""
        switch (win.confidence) {
        case "official": return i18nc("etiqueta corta: dato oficial del proveedor", "OFFICIAL")
        case "local_observed": return i18nc("etiqueta corta: observado en local", "LOCAL")
        case "configured_estimate": return i18nc("etiqueta corta: estimación configurada", "EST.")
        }
        return i18nc("etiqueta corta: sin dato", "NO DATA")
    }

    function confidenceColor(win) {
        if (!win) return HudPalette.confidenceUnknown
        switch (win.confidence) {
        case "official": return HudPalette.confidenceOfficial
        case "local_observed": return HudPalette.confidenceLocal
        case "configured_estimate": return HudPalette.confidenceEstimate
        }
        return HudPalette.confidenceUnknown
    }

    function windowSourceText(win) {
        if (!win) return ""
        var parts = []
        if (win.source && win.source !== "unknown") parts.push(String(win.source))
        if (win.note) parts.push(String(win.note))
        return parts.join(" · ")
    }

    function _fmtCount(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + "M"
        if (n >= 1000) return (n / 1000).toFixed(0) + "k"
        return String(Math.round(n))
    }

    function providerDisplayName(providerKey) {
        var p = getProviderByKey(providerKey)
        return p && p.label ? String(p.label) : String(providerKey).toUpperCase()
    }

    function providerAccent(providerKey) {
        return HudPalette.accentOf(providerKey)
    }

    function providerInnerColor(providerKey) {
        return HudPalette.deepOf(providerKey)
    }

    function providerIconSource(providerKey) {
        return HudPalette.iconOf(providerKey)
    }

    function providerIconIsMask(providerKey) {
        return HudPalette.iconIsMaskOf(providerKey)
    }

    function providerIconColor(providerKey) {
        return HudPalette.iconColorOf(providerKey)
    }

    // DonutGauge.centerGlyphColor es `var` con centinela `null`: una cadena vacia NO
    // es un color QML valido y aborta el componente entero al cargar, que es como se
    // cayo el HUD el 2026-08-29. Hoy queda enmascarado porque estos proveedores tienen
    // iconSource y el glifo no se pinta, pero la bomba sigue armada si se quita uno.
    function providerGlyphColor(providerKey) {
        return HudPalette.glyphColorOf(providerKey)
    }

    function providerGlyph(providerKey) {
        return HudPalette.glyphOf(providerKey)
    }

    function donutCenterText(providerKey, windowIds) {
        var best = 2
        for (var i = 0; i < windowIds.length; i++) {
            var frac = remainingFraction(providerKey, windowIds[i])
            if (frac >= 0 && frac < best) best = frac
        }
        if (best <= 1) return Math.round(best * 100) + "%"
        var p = getProviderByKey(providerKey)
        if (!p || p.status !== "ok") return "?"
        var ids = detailWindows(providerKey)
        var activity = 0
        for (var j = 0; j < ids.length; j++) {
            var win = windowOf(providerKey, ids[j])
            if (!windowUsable(win)) continue
            if (metricKind(win) === "activity") activity += Number(win.used || 0)
            if (metricKind(win) === "balance" && win.confidence === "official") {
                if (String(win.unit || "") === "usd") return "$" + Number(win.used || 0).toFixed(2)
                return Number(win.used || 0).toFixed(2)
            }
        }
        return activity >= 0 && hasUsableDetailData(providerKey) ? _fmtCount(activity) : ""
    }

    function donutCenterColor(providerKey, windowIds) {
        for (var i = 0; i < windowIds.length; i++) {
            if (remainingFraction(providerKey, windowIds[i]) >= 0) return HudPalette.text
        }
        var p = getProviderByKey(providerKey)
        return p && p.status === "ok" ? providerAccent(providerKey) : HudPalette.confidenceUnknown
    }

    function windowsSummary(providerKey) {
        var ids = detailWindows(providerKey)
        if (ids.length === 0) return i18n("no data")
        var parts = []
        for (var i = 0; i < ids.length; i++) {
            var w = windowOf(providerKey, ids[i])
            parts.push(windowShortName(providerKey, ids[i]) + " " + metricValueText(w))
        }
        return parts.join(" · ")
    }

    function accessibleSummary() {
        if (!root.report) return i18n("No data — start the ai-quota-monitor.service unit")
        var lines = []
        for (var i = 0; i < root.visibleProviders.length; i++) {
            var key = root.visibleProviders[i]
            lines.push(root.providerDisplayName(key) + ": " + windowsSummary(key))
        }
        return lines.join("\n")
    }
}
