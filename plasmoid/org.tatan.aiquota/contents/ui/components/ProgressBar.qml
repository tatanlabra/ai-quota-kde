import QtQuick

Item {
    id: bar
    property real value: 0.0   // 0.0 – 1.0
    property color fillColor: "#00d4ff"

    height: 6
    clip: true

    Rectangle {
        anchors.fill: parent
        color: "#1a1a2e"
        radius: 3
    }
    Rectangle {
        width: Math.max(0, Math.min(1, bar.value)) * parent.width
        height: parent.height
        color: bar.fillColor
        radius: 3
        Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
    }
}
