pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "components"

// Popup de detalle: Claude · Codex · Gemini · DeepSeek, dona doble + % libre + presupuesto.
Item {
    id: full
    required property var plasmoidItem
    readonly property var pi: full.plasmoidItem

    implicitWidth: 620
    implicitHeight: mainCol.implicitHeight + 24

    Rectangle {
        anchors.fill: parent
        color: "#08080f"
        radius: 8
    }

    ColumnLayout {
        id: mainCol
        anchors { fill: parent; margins: 12 }
        spacing: 10

        // ── Header ───────────────────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "AI QUOTA HUD"
                color: "#36c8ff"
                font.pixelSize: 14
                font.bold: true
                font.family: "IosevkaTerm Nerd Font"
                font.letterSpacing: 3
            }
            Item { Layout.fillWidth: true }
            Text {
                text: full.pi.report && full.pi.report.generated_at
                    ? full.pi.report.generated_at.substring(11, 16) + " local"
                    : "sin datos"
                color: "#444466"
                font.pixelSize: 9
                font.family: "IosevkaTerm Nerd Font"
            }
        }

        Text {
            Layout.fillWidth: true
            text: "arco = % libre  ·  doble = 2 ventanas (externo = 1ª)  ·  simple = ventana única  ·  punteado = caché"
            color: "#6a6a8c"
            font.pixelSize: 10
            font.family: "IosevkaTerm Nerd Font"
        }

        // ── Error banner ─────────────────────────────────────────────────────
        Rectangle {
            visible: full.pi.lastError !== ""
            Layout.fillWidth: true
            height: 24
            color: "#220000"
            radius: 4
            Text {
                anchors.centerIn: parent
                text: "⚠ " + full.pi.lastError
                color: "#ff4444"
                font.pixelSize: 10
                font.family: "IosevkaTerm Nerd Font"
            }
        }

        // ── Columnas: Claude · Codex · Gemini · DeepSeek ─────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ProviderColumn {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                pi: full.pi; keyId: "claude"; title: "CLAUDE"; glyph: "\uf069"
                iconSource: Qt.resolvedUrl("../icons/claude.svg")
                iconIsMask: true; iconMaskColor: "#e6ecff"
                innerCol: "#b23c0e"; outerCol: "#ff7518"
            }
            ProviderColumn {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                pi: full.pi; keyId: "codex"; title: "CODEX"; glyph: "\uf0e8"
                iconSource: Qt.resolvedUrl("../icons/codex.png")
                innerCol: "#0b9e3a"; outerCol: "#57ff8d"
            }
            ProviderColumn {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                pi: full.pi; keyId: "gemini"; title: "GEMINI"; glyph: "\uf005"
                iconSource: Qt.resolvedUrl("../icons/gemini_blue.png")
                innerCol: "#0b39c4"; outerCol: "#2f80ff"
            }
            ProviderColumn {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                pi: full.pi; keyId: "deepseek"; title: "DEEPSEEK"; glyph: "\uf06e"
                iconSource: Qt.resolvedUrl("../icons/deepseek.svg")
                iconIsMask: true; iconMaskColor: "#fff36d"
                innerCol: "#9b7c00"; outerCol: "#fff36d"
            }
        }

        // ── Warnings ─────────────────────────────────────────────────────────
        Repeater {
            model: full.pi.report ? (full.pi.report.warnings || []) : []
            delegate: Text {
                required property string modelData
                Layout.fillWidth: true
                text: "⚠ " + modelData
                color: "#ffaa44"
                font.pixelSize: 9
                font.family: "IosevkaTerm Nerd Font"
                wrapMode: Text.WordWrap
            }
        }

        // ── Footer: fuente + refresh ─────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: full.pi.report && full.pi.report.network_used ? "🌐 en vivo · 💾 local" : "💾 local"
                color: "#444466"
                font.pixelSize: 9
                font.family: "IosevkaTerm Nerd Font"
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                width: 84; height: 22
                color: refreshArea.containsMouse ? "#1a2a3a" : "#0d1a27"
                radius: 4
                border.color: "#36c8ff"
                border.width: 1
                Text {
                    anchors.centerIn: parent
                    text: full.pi.busy ? "⟳ …" : "⟳ refresh"
                    color: "#36c8ff"
                    font.pixelSize: 10
                    font.family: "IosevkaTerm Nerd Font"
                }
                MouseArea {
                    id: refreshArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: full.pi.triggerRefresh()
                }
            }
        }
    }

    // ── Columna de proveedor (dona doble + detalle + presupuesto) ────────────
    component ProviderColumn: ColumnLayout {
        id: pc
        required property var pi
        required property string keyId
        required property string title
        required property string glyph
        required property color innerCol
        required property color outerCol
        property url iconSource: ""
        property bool iconIsMask: false
        property color iconMaskColor: "#e6ecff"

        spacing: 7

        // Ventanas que el proveedor expone de verdad: 2 → dona doble, 1 → anillo único.
        // Se leen del reporte, así que un cambio de esquema upstream (p.ej. Codex, que
        // dejó de exponer la ventana de 5h) se refleja solo, sin editar el QML.
        readonly property var gauges: pc.pi.gaugeWindows(pc.keyId)

        DonutGauge {
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: 2
            implicitWidth: 92
            implicitHeight: 92
            label: pc.glyph
            singleRing: pc.pi.gaugeSingleRing(pc.keyId)
            stale: pc.pi.providerStale(pc.keyId)
            iconSource: pc.iconSource
            iconIsMask: pc.iconIsMask
            iconMaskColor: pc.iconMaskColor
            innerColor: pc.innerCol
            outerColor: pc.outerCol
            outerFraction: pc.pi.gaugeOuterFraction(pc.keyId)
            innerFraction: pc.pi.gaugeInnerFraction(pc.keyId)
            centerText: pc.pi.donutCenterText(pc.keyId, pc.gauges)
        }

        // Nombre del proveedor con su logo oficial al lado.
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 5
            Kirigami.Icon {
                implicitWidth: 15
                implicitHeight: 15
                source: pc.iconSource
                isMask: pc.iconIsMask
                color: pc.iconMaskColor
                visible: String(pc.iconSource) !== ""
                smooth: true
            }
            Text {
                text: pc.title
                color: pc.outerCol
                font.pixelSize: 12
                font.bold: true
                font.family: "IosevkaTerm Nerd Font"
                font.letterSpacing: 2
            }
        }

        // Estado: caché preservada (stale) o sin datos en vivo.
        Text {
            readonly property string st: pc.pi.providerStatusText(pc.keyId)
            Layout.alignment: Qt.AlignHCenter
            visible: st !== ""
            text: st
            color: "#ffaa44"
            font.pixelSize: 9
            font.family: "IosevkaTerm Nerd Font"
        }

        // Ventanas: una línea por ventana expuesta, rotulada con su duración real.
        Repeater {
            model: pc.gauges
            delegate: WindowLine {
                required property string modelData
                pi: pc.pi
                keyId: pc.keyId
                windowId: modelData
                name: pc.pi.windowShortName(pc.keyId, modelData)
            }
        }

        // Presupuesto extra: créditos, USD o saldo CLP.
        Text {
            readonly property string extra: pc.pi.extraInfoText(pc.keyId)
            Layout.alignment: Qt.AlignHCenter
            visible: extra !== ""
            text: extra
            color: "#8888aa"
            font.pixelSize: 10
            font.family: "IosevkaTerm Nerd Font"
        }
    }

    // ── Línea de ventana: "5h    82% libre · reset 19:00 UTC" ─────────────────
    component WindowLine: RowLayout {
        id: wl
        required property var pi
        required property string keyId
        required property string windowId
        required property string name

        readonly property real frac: wl.pi.remainingFraction(wl.keyId, wl.windowId)
        readonly property color tone: {
            if (wl.frac < 0) return "#555577"
            if (wl.frac <= 0.10) return "#ff4444"
            if (wl.frac <= 0.30) return "#ffaa00"
            return "#aaccdd"
        }

        Layout.fillWidth: true
        spacing: 6

        Text {
            text: wl.name
            color: "#8888aa"
            font.pixelSize: 10
            font.family: "IosevkaTerm Nerd Font"
        }
        Text {
            text: wl.frac < 0 ? wl.pi.extraInfoText(wl.keyId) : wl.pi.remainingText(wl.keyId, wl.windowId) + " libre"
            color: wl.tone
            font.pixelSize: 11
            font.bold: true
            font.family: "IosevkaTerm Nerd Font"
        }
        Item { Layout.fillWidth: true }
        Text {
            text: wl.pi.resetText(wl.keyId, wl.windowId)
            color: "#555577"
            font.pixelSize: 9
            font.family: "IosevkaTerm Nerd Font"
        }
    }
}
