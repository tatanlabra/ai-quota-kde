pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "components"

Item {
    id: compact
    required property var plasmoidItem
    readonly property var pi: compact.plasmoidItem
    readonly property var shown: compact.pi.compactMode === 1
        ? [compact.pi.worstProvider] : compact.pi.visibleProviders
    readonly property real cellSize: compact.height
    Layout.minimumWidth: row.implicitWidth
    Layout.preferredWidth: row.implicitWidth

    RowLayout {
        id: row
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing
        Repeater {
            model: compact.shown
            delegate: Rectangle {
                id: cell
                required property string modelData
                Layout.preferredHeight: compact.cellSize
                Layout.preferredWidth: compact.cellSize
                color: hit.containsMouse || activeFocus ? HudPalette.panel : "transparent"
                border.width: activeFocus ? 1 : 0
                border.color: HudPalette.accentOf(modelData)
                radius: Kirigami.Units.cornerRadius
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: compact.pi.providerDisplayName(modelData)
                Accessible.onPressAction: activate()
                function activate() {
                    compact.pi.selectedProvider = modelData
                    compact.pi.expanded = !compact.pi.expanded
                }
                Keys.onReturnPressed: activate()
                Keys.onSpacePressed: activate()
                onActiveFocusChanged: {
                    if (activeFocus) compact.pi.hoveredProvider = modelData
                }
                ProviderGauge {
                    anchors.centerIn: parent
                    width: cell.width - Kirigami.Units.smallSpacing
                    height: width
                    pi: compact.pi
                    providerKey: cell.modelData
                }
                MouseArea {
                    id: hit
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    acceptedButtons: Qt.LeftButton
                    onEntered: compact.pi.hoveredProvider = cell.modelData
                    onClicked: cell.activate()
                }
            }
        }
    }
}
