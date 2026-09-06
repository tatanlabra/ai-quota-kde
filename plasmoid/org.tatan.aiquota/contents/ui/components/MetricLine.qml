pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "."

ColumnLayout {
    id: line
    required property var pi
    required property string providerKey
    required property string windowId
    property color accent: HudPalette.accent
    property bool showSource: false
    readonly property var win: pi.windowOf(providerKey, windowId)
    readonly property color confidenceTone: pi.confidenceColor(win)
    readonly property string confidence: pi.confidenceText(win)
    readonly property string renewal: pi.renewalText(providerKey, windowId)
    readonly property string sourceText: showSource ? pi.windowSourceText(win) : ""
    Layout.fillWidth: true
    Layout.minimumWidth: 0
    Layout.preferredWidth: 0
    spacing: Kirigami.Units.smallSpacing

    RowLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.preferredWidth: 0
        spacing: Kirigami.Units.largeSpacing
        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: 0
            objectName: "metricLabel"
            text: line.pi.windowShortName(line.providerKey, line.windowId)
            color: HudPalette.text
            font.pointSize: HudPalette.fs(0.95)
            wrapMode: Text.Wrap
        }
        Text {
            Layout.maximumWidth: line.width * 0.5
            Layout.minimumWidth: 0
            objectName: "metricValue"
            text: line.pi.metricValueText(line.win)
            color: line.pi.metricTone(line.win, line.accent)
            font.pointSize: HudPalette.fs(1.05)
            font.bold: true
            font.family: HudPalette.mono
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignRight
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: Kirigami.Units.smallSpacing
        Rectangle {
            visible: line.confidence !== ""
            implicitWidth: confidenceLabel.implicitWidth + Kirigami.Units.smallSpacing * 2
            implicitHeight: confidenceLabel.implicitHeight + Kirigami.Units.smallSpacing
            radius: Kirigami.Units.cornerRadius / 2
            color: Qt.rgba(line.confidenceTone.r,
                line.confidenceTone.g, line.confidenceTone.b, 0.2)
            Text {
                id: confidenceLabel
                anchors.centerIn: parent
                text: line.confidence
                color: HudPalette.text
                font.pointSize: HudPalette.fs(0.75)
                font.bold: true
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: 0
            visible: line.renewal !== ""
            text: line.renewal
            color: HudPalette.muted
            font.pointSize: HudPalette.fs(0.85)
            wrapMode: Text.Wrap
        }
    }
    Text {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.preferredWidth: 0
        visible: line.sourceText !== ""
        text: line.sourceText
        color: HudPalette.muted
        font.pointSize: HudPalette.fs(0.85)
        wrapMode: Text.Wrap
    }
}
