pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import "components"

PlasmaExtras.Representation {
    id: full
    required property var plasmoidItem
    readonly property var pi: full.plasmoidItem
    readonly property string activeProvider: pi.visibleProviders.indexOf(pi.selectedProvider) >= 0
        ? pi.selectedProvider : (pi.visibleProviders[0] || "claude")
    implicitWidth: Kirigami.Units.gridUnit * 36
    Layout.minimumWidth: Math.min(Kirigami.Units.gridUnit * 24, Screen.width * 0.9)
    Layout.preferredWidth: Kirigami.Units.gridUnit * 36
    Layout.maximumWidth: Screen.width * 0.95
    Layout.minimumHeight: Math.min(Kirigami.Units.gridUnit * 24, Screen.height * 0.8)
    Layout.preferredHeight: Kirigami.Units.gridUnit * 29
    Layout.maximumHeight: Screen.height * 0.9
    collapseMarginsHint: true
    background: Rectangle { color: HudPalette.bg; radius: Kirigami.Units.cornerRadius }

    header: PlasmaExtras.PlasmoidHeading {
        contentItem: RowLayout {
            spacing: Kirigami.Units.largeSpacing
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: "AI QUOTA HUD"
                color: HudPalette.text
                font.family: HudPalette.display
                font.pointSize: HudPalette.fs(1.05)
                elide: Text.ElideRight
            }
            Text {
                Layout.maximumWidth: full.width * 0.35
                text: full.pi.report && full.pi.report.generated_at
                    ? i18nc("%1 es una fecha y hora", "updated %1", full.pi.localTimeText(full.pi.report.generated_at))
                    : i18n("no data")
                color: HudPalette.muted
                font.pointSize: HudPalette.fs(0.85)
                elide: Text.ElideRight
            }
            PlasmaComponents.ToolButton {
                icon.name: "view-refresh"
                enabled: full.pi.canRefresh
                text: full.pi.refreshButtonText()
                display: PlasmaComponents.AbstractButton.IconOnly
                onClicked: full.pi.requestManualRefresh()
                PlasmaComponents.ToolTip.visible: hovered
                PlasmaComponents.ToolTip.text: full.pi.refreshHint || text
            }
        }
    }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.largeSpacing
        // Overview stays visible while only the selected provider's details scroll.
        RowLayout {
            id: overview
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.largeSpacing
            Layout.rightMargin: Kirigami.Units.largeSpacing
            Layout.topMargin: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing
            Repeater {
                model: full.pi.visibleProviders
                delegate: PlasmaComponents.Button {
                    id: choice
                    required property string modelData
                    objectName: "select-" + modelData
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 0
                    readonly property bool selected: full.activeProvider === modelData
                    Accessible.name: full.pi.providerDisplayName(modelData)
                    onClicked: full.pi.selectedProvider = modelData
                    padding: Kirigami.Units.smallSpacing
                    background: Rectangle {
                        color: choice.selected || choice.hovered ? HudPalette.panel : HudPalette.bg
                        radius: Kirigami.Units.cornerRadius
                        border.color: choice.selected || choice.activeFocus
                            ? HudPalette.accentOf(choice.modelData) : HudPalette.border
                        border.width: 1
                    }
                    contentItem: ColumnLayout {
                        spacing: Kirigami.Units.smallSpacing
                        ProviderGauge {
                            Layout.alignment: Qt.AlignHCenter
                            implicitWidth: Kirigami.Units.gridUnit * 2.6
                            implicitHeight: implicitWidth
                            pi: full.pi
                            providerKey: choice.modelData
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: HudPalette.shortName(choice.modelData)
                            horizontalAlignment: Text.AlignHCenter
                            font.pointSize: HudPalette.fs(0.9)
                            color: choice.selected ? HudPalette.accentOf(choice.modelData) : HudPalette.text
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: full.pi.donutCenterText(choice.modelData, full.pi.gaugeWindows(choice.modelData)) || "—"
                            horizontalAlignment: Text.AlignHCenter
                            font.pointSize: HudPalette.fs(1.05)
                            font.family: HudPalette.mono
                            font.bold: true
                            color: full.pi.donutCenterColor(choice.modelData, full.pi.gaugeWindows(choice.modelData))
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        PlasmaComponents.ScrollView {
            id: details
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff
            ColumnLayout {
                width: details.availableWidth
                spacing: Kirigami.Units.largeSpacing
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    Layout.rightMargin: Kirigami.Units.largeSpacing
                    text: full.pi.providerDisplayName(full.activeProvider)
                    wrapMode: Text.Wrap
                    color: HudPalette.accentOf(full.activeProvider)
                    font.family: HudPalette.displaySoft
                    font.pointSize: HudPalette.fs(1.05)
                }
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    Layout.rightMargin: Kirigami.Units.largeSpacing
                    visible: text !== ""
                    text: full.pi.providerStatusText(full.activeProvider)
                    wrapMode: Text.Wrap
                    color: HudPalette.caution
                    font.pointSize: HudPalette.fs(0.95)
                }
                Repeater {
                    model: full.pi.detailWindows(full.activeProvider)
                    delegate: MetricLine {
                        required property string modelData
                        Layout.leftMargin: Kirigami.Units.largeSpacing
                        Layout.rightMargin: Kirigami.Units.largeSpacing
                        pi: full.pi
                        providerKey: full.activeProvider
                        windowId: modelData
                        accent: HudPalette.accentOf(full.activeProvider)
                        showSource: true
                    }
                }
                Text {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    Layout.rightMargin: Kirigami.Units.largeSpacing
                    visible: text !== ""
                    text: full.pi.lastError
                    wrapMode: Text.Wrap
                    color: HudPalette.errorText
                    font.pointSize: HudPalette.fs(0.9)
                }
                Repeater {
                    model: full.pi.report ? (full.pi.report.warnings || []) : []
                    delegate: Text {
                        required property string modelData
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.leftMargin: Kirigami.Units.largeSpacing
                        Layout.rightMargin: Kirigami.Units.largeSpacing
                        text: "⚠ " + modelData
                        wrapMode: Text.Wrap
                        color: HudPalette.caution
                        font.pointSize: HudPalette.fs(0.9)
                    }
                }
            }
        }
    }
    footer: PlasmaExtras.PlasmoidHeading {
        contentItem: Text {
            text: i18n("Select a provider for details · arcs show quota remaining")
            color: HudPalette.muted
            font.pointSize: HudPalette.fs(0.85)
            wrapMode: Text.Wrap
        }
    }
}
