// Escenario del video de demostracion: las tres vistas del HUD en un solo lienzo.
//
// Vive aqui y NO en contents/ui/ por dos razones concretas. (1) Necesita colores
// literales y tamanos absolutos --un panel de escritorio falso, posiciones fijas-- que
// tests/test_qml_style_gates.py prohibe con razon en el arbol que se empaqueta.
// (2) No es parte del widget: nadie deberia instalarlo. Los gates de estilo solo
// recorren contents/ui y contents/config, asi que este fichero queda fuera por diseno,
// no por descuido.
//
// Las tres superficies comparten EL MISMO objeto plasmoidItem, asi que hoveredProvider
// y selectedProvider se propagan igual que en el widget real: lo que se ve en el video
// son los manejadores de verdad reaccionando, no una animacion dibujada aparte.
import QtQuick
import "../../plasmoid/org.tatan.aiquota/contents/ui" as HUD
import "../../plasmoid/org.tatan.aiquota/contents/ui/components" as C
import "../../plasmoid/org.tatan.aiquota/contents/ui/components"

Item {
    id: stage
    required property var plasmoidItem

    // El guion los fija por fotograma desde Python. Nada se anima en QML a proposito:
    // el fotograma es funcion pura de su indice, asi que no hay reloj del que
    // desincronizarse y dos corridas dan los mismos bytes.
    property real tooltipOpacity: 0
    property real tooltipLift: 14
    property real popupOpacity: 0
    property real popupLift: 18

    // Fondo: el mismo aire que el teaser, para que las dos piezas se lean como una.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#0b0d18" }
            GradientStop { position: 1.0; color: "#04050b" }
        }
    }

    // Franja de panel de escritorio, a la altura real de un panel de 40 px.
    Rectangle {
        id: panelStrip
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 40
        color: "#1b1e2b"
        Rectangle {
            anchors { left: parent.left; right: parent.right; top: parent.top }
            height: 1
            color: "#2b3150"
        }
        Text {
            anchors { left: parent.left; leftMargin: 24; verticalCenter: parent.verticalCenter }
            text: "AI QUOTA HUD  ·  datos ficticios"
            color: "#6c718b"
            font.pixelSize: 11
            font.letterSpacing: 1.4
        }
    }

    // La barra, en su sitio del panel: a la derecha, como una bandeja del sistema.
    HUD.CompactRepresentation {
        objectName: "stageCompact"
        x: stage.width - width - 24
        y: stage.height - height
        width: 216
        height: 40
        plasmoidItem: stage.plasmoidItem
    }

    // El visor al posarse sobre una dona. Sale del panel hacia arriba.
    C.QuotaTooltip {
        objectName: "stageTooltip"
        x: 300
        y: 216 + stage.tooltipLift
        implicitWidth: 420
        opacity: stage.tooltipOpacity
        visible: stage.tooltipOpacity > 0.01
        plasmoidItem: stage.plasmoidItem
    }

    // La vista detallada del clic. Tapa el tooltip cuando entra.
    HUD.FullRepresentation {
        objectName: "stagePopup"
        x: 80
        y: 22 + stage.popupLift
        width: 640
        height: 500
        opacity: stage.popupOpacity
        visible: stage.popupOpacity > 0.01
        plasmoidItem: stage.plasmoidItem
    }
}
