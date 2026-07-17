pragma ComponentBehavior: Bound

import QtQuick
import org.kde.kirigami as Kirigami

// Dona de saldo: representa el % FALTANTE (remaining) como arco que se encoge al consumir.
//   Modo doble (default): dos anillos concéntricos.
//     innerFraction → ventana semanal/7d (anillo interno, color oscuro del proveedor)
//     outerFraction → ventana 5h/sesión  (anillo externo, color claro del proveedor)
//   Modo single (singleRing:true): un único anillo grueso usando outerFraction
//     (para proveedores con una sola métrica: DeepSeek saldo, Gemini diario).
// El arco arranca arriba (−90°) en sentido horario; su longitud = fraction·360°.
//   fraction == 1 → anillo completo (0% usado, todo libre).
//   0 < fraction < 1 → arco parcial.
//   fraction < 0 → SIN DATOS: solo pista gris + contenido atenuado.
// stale:true → arco punteado y atenuado (dato preservado de caché, fetch en vivo falló).
Item {
    id: gauge

    property real outerFraction: -1
    property real innerFraction: -1
    property bool singleRing: false
    property bool stale: false
    property string label: ""           // glifo del proveedor (fallback si no hay iconSource)
    property string centerText: ""      // valor grande al centro (ej. "82%"); vacío = ícono/glifo
    property url iconSource: ""          // logo del proveedor (PNG/SVG); tiene prioridad sobre label
    property bool iconIsMask: false      // true = recolorear (SVG monocromo); false = color original
    property color iconMaskColor: "#e6ecff"
    property real iconScale: 0.50         // tamaño del ícono como fracción del diámetro
    property string iconFontFamily: "Symbols Nerd Font"
    // Identidad de proveedor en dos tonos: interno oscuro / externo claro.
    property color innerColor: "#1a39ff"
    property color outerColor: "#36c8ff"
    property color trackColor: "#23233a"

    implicitWidth: 24
    implicitHeight: 24

    readonly property bool hasData: outerFraction >= 0 || (!singleRing && innerFraction >= 0)

    // Peor fracción libre visible (la más crítica) → color semántico de salud.
    readonly property real _minFrac: {
        var best = 2
        if (outerFraction >= 0 && outerFraction < best) best = outerFraction
        if (!singleRing && innerFraction >= 0 && innerFraction < best) best = innerFraction
        return best <= 1 ? best : -1
    }
    // Verde/blanco = holgado · ámbar ≤30% · rojo ≤10% · gris = sin datos.
    readonly property color _healthColor: {
        if (_minFrac < 0) return "#666688"
        if (_minFrac <= 0.10) return "#ff5555"
        if (_minFrac <= 0.30) return "#ffaa00"
        return "#e6ecff"
    }

    onOuterFractionChanged: canvas.requestPaint()
    onInnerFractionChanged: canvas.requestPaint()
    onSingleRingChanged: canvas.requestPaint()
    onStaleChanged: canvas.requestPaint()
    onInnerColorChanged: canvas.requestPaint()
    onOuterColorChanged: canvas.requestPaint()

    function _drawRing(ctx, cx: real, cy: real, r: real, lw: real, frac: real, col: color): void {
        if (r <= 0)
            return
        // Pista de fondo (anillo completo tenue) para ver la porción consumida.
        ctx.setLineDash([])
        ctx.beginPath()
        ctx.arc(cx, cy, r, 0, 2 * Math.PI)
        ctx.lineWidth = lw
        ctx.strokeStyle = gauge.trackColor
        ctx.globalAlpha = 1.0
        ctx.stroke()
        // Arco de faltante (nada si frac < 0 = sin datos).
        if (frac >= 0) {
            const start = -Math.PI / 2
            const end = start + Math.min(Math.max(frac, 0), 1) * 2 * Math.PI
            ctx.beginPath()
            if (gauge.stale) {
                ctx.lineCap = "butt"
                ctx.setLineDash([lw * 0.7, lw * 0.6])
                ctx.globalAlpha = 0.55
            } else {
                ctx.lineCap = "round"
                ctx.setLineDash([])
                ctx.globalAlpha = 1.0
            }
            ctx.arc(cx, cy, r, start, end, false)
            ctx.lineWidth = lw
            ctx.strokeStyle = col
            ctx.stroke()
            ctx.globalAlpha = 1.0
            ctx.setLineDash([])
        }
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: true

        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const cx = width / 2
            const cy = height / 2
            const maxR = Math.min(width, height) / 2
            if (gauge.singleRing) {
                const lw = Math.max(3, maxR * 0.26)
                const r = maxR - lw / 2 - 1
                gauge._drawRing(ctx, cx, cy, r, lw, gauge.outerFraction, gauge.outerColor)
            } else {
                const lw = Math.max(2, maxR * 0.20)
                const rOuter = maxR - lw / 2 - 1
                const rInner = rOuter - lw * 1.05
                gauge._drawRing(ctx, cx, cy, rOuter, lw, gauge.outerFraction, gauge.outerColor)
                gauge._drawRing(ctx, cx, cy, rInner, lw, gauge.innerFraction, gauge.innerColor)
            }
        }
    }

    // Centro, prioridad: número (popup) → logo del proveedor (compacto) → glifo (fallback).
    Text {
        visible: gauge.centerText !== ""
        anchors.fill: parent
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        text: gauge.centerText
        color: gauge._healthColor
        // Conteo "robótico": Iosevka pesada, más chica que antes.
        font.pixelSize: Math.max(10, gauge.height * 0.27)
        font.weight: Font.Black
        font.family: "IosevkaTerm Nerd Font"
        font.letterSpacing: 0.5
        renderType: Text.NativeRendering
    }

    Kirigami.Icon {
        visible: gauge.centerText === "" && String(gauge.iconSource) !== ""
        anchors.centerIn: parent
        width: Math.round(gauge.height * gauge.iconScale)
        height: width
        source: gauge.iconSource
        isMask: gauge.iconIsMask
        color: gauge.iconMaskColor
        opacity: gauge.hasData ? 1.0 : 0.45
        smooth: true
    }

    Text {
        visible: gauge.centerText === "" && String(gauge.iconSource) === ""
        anchors.fill: parent
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        text: gauge.label
        color: gauge.hasData ? (gauge._minFrac <= 0.30 ? gauge._healthColor : "#e6ecff") : "#555577"
        opacity: gauge.hasData ? 1.0 : 0.6
        font.pixelSize: Math.max(9, gauge.height * 0.42)
        font.family: gauge.iconFontFamily
        renderType: Text.NativeRendering
    }

    // Indicador de dato preservado (stale): punto tenue arriba a la derecha.
    Rectangle {
        visible: gauge.stale
        width: Math.max(4, gauge.height * 0.10)
        height: width
        radius: width / 2
        color: "#ffaa44"
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 1
    }
}
