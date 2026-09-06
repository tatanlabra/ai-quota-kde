pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import org.kde.kirigami as Kirigami
import "."

// Contextual preview: readable details for the donut under the pointer.
Item {
    id: tooltip
    required property var plasmoidItem
    readonly property var pi: tooltip.plasmoidItem
    readonly property string providerKey: pi.visibleProviders.indexOf(pi.hoveredProvider) >= 0
        ? pi.hoveredProvider : (pi.visibleProviders[0] || "claude")
    implicitWidth: Math.min(Kirigami.Units.gridUnit * 26, Screen.width * 0.9)
    implicitHeight: mainColumn.implicitHeight + Kirigami.Units.largeSpacing * 4
    Rectangle {
        anchors.fill: parent
        color: HudPalette.bg
        radius: Kirigami.Units.cornerRadius
        border.color: HudPalette.border
        border.width: 1
    }
    ColumnLayout {
        id: mainColumn
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing * 2
        spacing: Kirigami.Units.largeSpacing
        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing
            ProviderGauge {
                implicitWidth: Kirigami.Units.gridUnit * 3.2
                implicitHeight: implicitWidth
                pi: tooltip.pi
                providerKey: tooltip.providerKey
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredWidth: 0
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: tooltip.pi.providerDisplayName(tooltip.providerKey)
                    color: HudPalette.accentOf(tooltip.providerKey)
                    font.family: HudPalette.displaySoft
                    font.pointSize: HudPalette.fs(1.1)
                    wrapMode: Text.Wrap
                }
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    visible: text !== ""
                    text: tooltip.pi.providerStatusText(tooltip.providerKey)
                    color: HudPalette.caution
                    font.pointSize: HudPalette.fs(0.9)
                    wrapMode: Text.Wrap
                }
            }
        }
        Repeater {
            model: tooltip.pi.detailWindows(tooltip.providerKey)
            delegate: MetricLine {
                required property string modelData
                pi: tooltip.pi
                providerKey: tooltip.providerKey
                windowId: modelData
                accent: HudPalette.accentOf(tooltip.providerKey)
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            text: i18n("Click for all providers · white marks count days to reset")
            color: HudPalette.muted
            font.pointSize: HudPalette.fs(0.85)
            wrapMode: Text.Wrap
        }
    }
}
