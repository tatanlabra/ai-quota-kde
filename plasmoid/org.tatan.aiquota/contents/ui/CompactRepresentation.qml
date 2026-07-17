pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "components"

// Cara del panel: donas lado a lado (Claude · Codex · Gemini · DeepSeek).
// Los anillos salen de las ventanas que cada proveedor expone de verdad: dos ventanas →
// dona doble (externo = 1ª, interno = 2ª); una sola → anillo único. Codex, por ejemplo,
// pasó a exponer solo la ventana semanal y aquí se dibuja como anillo único sin tocar QML.
Item {
    id: compact
    required property var plasmoidItem
    readonly property var pi: compact.plasmoidItem

    Layout.minimumWidth: row.implicitWidth
    Layout.preferredWidth: row.implicitWidth

    RowLayout {
        id: row
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        // Claude — azul neón, icono floral.
        DonutGauge {
            Layout.preferredHeight: compact.height
            Layout.preferredWidth: compact.height
            label: "\uf069"
            innerColor: "#b23c0e"
            outerColor: "#ff7518"
            iconSource: Qt.resolvedUrl("../icons/claude.svg")
            iconIsMask: true
            iconMaskColor: "#e6ecff"
            singleRing: compact.pi.gaugeSingleRing("claude")
            outerFraction: compact.pi.gaugeOuterFraction("claude")
            innerFraction: compact.pi.gaugeInnerFraction("claude")
            stale: compact.pi.providerStale("claude")
        }

        // Codex (OpenAI) — verde neón, icono tipo nudo/red.
        DonutGauge {
            Layout.preferredHeight: compact.height
            Layout.preferredWidth: compact.height
            label: "\uf0e8"
            innerColor: "#0b9e3a"
            outerColor: "#57ff8d"
            iconSource: Qt.resolvedUrl("../icons/codex.png")
            singleRing: compact.pi.gaugeSingleRing("codex")
            outerFraction: compact.pi.gaugeOuterFraction("codex")
            innerFraction: compact.pi.gaugeInnerFraction("codex")
            stale: compact.pi.providerStale("codex")
        }

        // Gemini (Google/agy) — magenta, estrella; única ventana diaria → anillo único.
        DonutGauge {
            Layout.preferredHeight: compact.height
            Layout.preferredWidth: compact.height
            label: "\uf005"
            innerColor: "#0b39c4"
            outerColor: "#2f80ff"
            iconSource: Qt.resolvedUrl("../icons/gemini_blue.png")
            iconScale: 0.66
            singleRing: compact.pi.gaugeSingleRing("gemini")
            outerFraction: compact.pi.gaugeOuterFraction("gemini")
            innerFraction: compact.pi.gaugeInnerFraction("gemini")
            stale: compact.pi.providerStale("gemini")
        }

        // DeepSeek — amarillo neón, ojo; saldo único → anillo único (% vs pico histórico).
        DonutGauge {
            Layout.preferredHeight: compact.height
            Layout.preferredWidth: compact.height
            label: "\uf06e"
            innerColor: "#9b7c00"
            outerColor: "#fff36d"
            iconSource: Qt.resolvedUrl("../icons/deepseek.svg")
            iconIsMask: true
            iconMaskColor: "#fff36d"
            singleRing: compact.pi.gaugeSingleRing("deepseek")
            outerFraction: compact.pi.gaugeOuterFraction("deepseek")
            innerFraction: compact.pi.gaugeInnerFraction("deepseek")
            stale: compact.pi.providerStale("deepseek")
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onClicked: compact.pi.expanded = !compact.pi.expanded
    }
}
