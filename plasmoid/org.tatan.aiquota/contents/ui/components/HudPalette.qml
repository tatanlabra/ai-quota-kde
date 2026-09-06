pragma Singleton

import QtQuick
import org.kde.kirigami as Kirigami

// Unico fichero del plasmoide con colores literales, y unico sitio donde se decide
// un tamano de letra. El HUD mantiene a proposito su identidad oscura en vez de
// heredar el esquema de Plasma: es un instrumento de lectura rapida, como un panel
// de vuelo, y su fondo no debe cambiar con el tema del escritorio. Lo que si escala
// con el sistema son los tamanos, que salen de Kirigami.Units y de la fuente del tema.
QtObject {
    id: hudPalette

    // ── Identidad de cada proveedor ─────────────────────────────────────────
    // accent: anillo externo y titulo · deep: anillo interno · glyphColor: null salvo
    // que el proveedor no tenga logo propio y haya que tenir su glifo Nerd Font.
    readonly property var providers: ({
        "claude":   { accent: "#ff7518", deep: "#b23c0e", icon: "claude.svg",      mask: true,  glyph: "\uf069", glyphColor: null },
        "codex":    { accent: "#57ff8d", deep: "#0b9e3a", icon: "codex.png",       mask: true,  glyph: "\uf0e8", glyphColor: null },
        "gemini":   { accent: "#2f80ff", deep: "#0b39c4", icon: "gemini_blue.png", mask: false, glyph: "\uf005", glyphColor: null },
        "copilot":  { accent: "#c084fc", deep: "#7e22ce", icon: "copilot.svg",     mask: true,  glyph: "C", glyphColor: null },
        "deepseek": { accent: "#fff36d", deep: "#9b7c00", icon: "deepseek.svg",    mask: true,  glyph: "\uf06e", glyphColor: null }
    })

    readonly property color fallbackAccent: "#36c8ff"

    // ── Chrome del HUD ──────────────────────────────────────────────────────
    readonly property color bg: "#08080f"
    readonly property color panel: "#0e1120"
    readonly property color border: "#2b3150"
    readonly property color accent: "#36c8ff"
    readonly property color text: "#e6ecff"
    readonly property color muted: "#a7adc2"
    readonly property color dim: "#929bb4"
    readonly property color track: "#23233a"
    readonly property color trackSpent: "#303047"

    // ── Semantica ───────────────────────────────────────────────────────────
    readonly property color danger: "#ff5555"
    readonly property color warning: "#ffaa00"
    readonly property color caution: "#ffaa44"
    readonly property color estimate: "#d8922e"
    readonly property color noData: "#666688"
    readonly property color errorBg: "#220000"
    readonly property color errorText: "#ff4444"

    readonly property color confidenceOfficial: "#2f80ff"
    readonly property color confidenceLocal: "#48b7a8"
    readonly property color confidenceEstimate: "#d8922e"
    readonly property color confidenceUnknown: "#6b6b86"

    // ── Tipografia ──────────────────────────────────────────────────────────
    // Las Orbitron viajan dentro del paquete: sin FontLoader estaban ahi de adorno,
    // 32 KB que ningun QML cargaba mientras los titulos usaban la monoespaciada.
    readonly property FontLoader orbitronBold: FontLoader {
        source: Qt.resolvedUrl("../../fonts/Orbitron-700.ttf")
    }
    readonly property FontLoader orbitronBlack: FontLoader {
        source: Qt.resolvedUrl("../../fonts/Orbitron-800.ttf")
    }

    readonly property string display: hudPalette.orbitronBlack.status === FontLoader.Ready
        ? hudPalette.orbitronBlack.name
        : hudPalette.mono
    readonly property string displaySoft: hudPalette.orbitronBold.status === FontLoader.Ready
        ? hudPalette.orbitronBold.name
        : hudPalette.mono

    // Cifras tabulares. Si la Nerd Font no esta instalada se cae a la monoespaciada
    // del tema en vez de dejar que Qt elija una proporcional y baile la alineacion.
    readonly property string mono: Qt.fontFamilies().indexOf("IosevkaTerm Nerd Font") !== -1
        ? "IosevkaTerm Nerd Font"
        : Kirigami.Theme.fixedWidthFont.family
    readonly property string glyphFont: "Symbols Nerd Font"

    // ── Escala ──────────────────────────────────────────────────────────────
    // Todo tamano sale de aqui: con escala 1.25 y Fira Sans 11 los numeros absolutos
    // absolutos de antes no crecian con el sistema: una etiqueta de nueve pixeles y un
    // popup de 620 se quedaban igual de pequenos con la pantalla al doble.
    readonly property int unit: Kirigami.Units.gridUnit
    readonly property real base: Kirigami.Theme.defaultFont.pointSize

    function fs(factor) {
        return Math.round(hudPalette.base * factor * 10) / 10
    }

    function shortName(key) {
        const names = {claude: "Claude", codex: "Codex", gemini: "Gemini",
                       copilot: "Copilot", deepseek: "DeepSeek"}
        return names[key] || key
    }

    function providerOf(key) {
        return hudPalette.providers[key] || null
    }

    function accentOf(key) {
        const p = hudPalette.providers[key]
        return p ? p.accent : hudPalette.fallbackAccent
    }

    function deepOf(key) {
        const p = hudPalette.providers[key]
        return p ? p.deep : hudPalette.fallbackAccent
    }

    function glyphOf(key) {
        const p = hudPalette.providers[key]
        return p ? p.glyph : "?"
    }

    function glyphColorOf(key) {
        const p = hudPalette.providers[key]
        return p ? p.glyphColor : null
    }

    function iconOf(key) {
        const p = hudPalette.providers[key]
        return p && p.icon !== "" ? Qt.resolvedUrl("../../icons/" + p.icon) : ""
    }

    function iconIsMaskOf(key) {
        const p = hudPalette.providers[key]
        return p ? p.mask === true : false
    }

    function iconColorOf(key) {
        const p = hudPalette.providers[key]
        if (!p)
            return hudPalette.text
        return p.mask ? p.accent : hudPalette.text
    }
}
