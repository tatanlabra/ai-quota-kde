pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "."

Item {
    id: card

    property string providerLabel: "PROVIDER"
    property color accentColor: "#00d4ff"
    property var windows: []   // array of window objects from JSON

    implicitWidth: 220
    implicitHeight: col.implicitHeight + 16

    Rectangle {
        anchors.fill: parent
        color: "#0d0d14"
        radius: 6
        border.color: card.accentColor
        border.width: 1
        opacity: 0.95
    }

    ColumnLayout {
        id: col
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
        spacing: 8

        // Provider name header
        Text {
            text: card.providerLabel
            color: card.accentColor
            font.pixelSize: 13
            font.bold: true
            font.family: "monospace"
            font.letterSpacing: 2
        }

        // Window rows
        Repeater {
            model: card.windows
            delegate: WindowRow {
                required property var modelData
                Layout.fillWidth: true
                win: modelData
                accent: card.accentColor
            }
        }
    }
}

// ── Inline WindowRow component ────────────────────────────────────────────────
component WindowRow: ColumnLayout {
    id: row
    required property var win
    required property color accent

    readonly property real pctVal: {
        var w = row.win
        if (!w) return -1
        if (w.percent !== null && w.percent !== undefined) return w.percent
        return -1
    }
    readonly property string pctText: {
        var w = row.win
        if (!w) return "—"
        if (w.percent !== null && w.percent !== undefined) return Math.round(w.percent * 100) + "%"
        var u = w.used || 0
        if (u >= 1000000) return (u / 1000000).toFixed(1) + "M " + (w.unit || "")
        if (u >= 1000)    return (u / 1000).toFixed(0) + "k " + (w.unit || "")
        return String(Math.round(u)) + " " + (w.unit || "")
    }
    readonly property color barColor: {
        if (row.pctVal < 0) return "#555577"
        if (row.pctVal >= 0.9) return "#ff4444"
        if (row.pctVal >= 0.7) return "#ffaa00"
        return row.accent
    }

    spacing: 3

    RowLayout {
        Layout.fillWidth: true
        Text {
            text: row.win ? (row.win.label || "—") : "—"
            color: "#aaaacc"
            font.pixelSize: 10
            font.family: "monospace"
        }
        Item { Layout.fillWidth: true }
        Text {
            text: row.pctText
            color: row.barColor
            font.pixelSize: 14
            font.bold: true
            font.family: "monospace"
        }
    }

    ProgressBar {
        Layout.fillWidth: true
        value: row.pctVal >= 0 ? row.pctVal : 0
        fillColor: row.barColor
    }

    Text {
        visible: row.win && row.win.reset_at
        text: row.win && row.win.reset_at ? "reset: " + row.win.reset_at.substring(11, 16) + " UTC" : ""
        color: "#666688"
        font.pixelSize: 9
        font.family: "monospace"
    }
}
