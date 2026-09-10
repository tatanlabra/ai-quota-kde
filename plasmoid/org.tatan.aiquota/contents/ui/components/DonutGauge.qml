pragma ComponentBehavior: Bound

import QtQuick
import org.kde.kirigami as Kirigami
import "."

// Dona de saldo: representa el % FALTANTE (remaining) como arco que se encoge al consumir.
//   Modo doble (default): dos anillos concéntricos.
//     innerFraction → ventana semanal/7d (anillo interno, color oscuro del proveedor)
//     outerFraction → ventana 5h/sesión  (anillo externo, color claro del proveedor)
//   Modo single (singleRing:true): un único anillo grueso usando outerFraction.
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
    // Mantiene la identidad legible para actividad o saldo sin porcentaje.
    property bool hasAuxiliaryData: false
    property string label: ""           // glifo del proveedor (fallback si no hay iconSource)
    // QML `color` cannot use an empty string as a sentinel: Plasma 6 rejects
    // the whole component before the HUD can load. Keep an explicit nullable
    // value instead; consumers may still assign a concrete provider color.
    property var centerGlyphColor: null
    property string centerText: ""      // valor grande al centro (ej. "82%"); vacío = ícono/glifo
    property color centerTextColor: _healthColor
    property url iconSource: ""          // logo del proveedor (PNG/SVG); tiene prioridad sobre label
    property bool iconIsMask: false      // true = recolorear (SVG monocromo); false = color original
    property color iconMaskColor: HudPalette.text
    // Fracción del cuadrado inscrito en la apertura central. 1.0 es el máximo
    // geométrico: la semidiagonal del recuadro del icono dividida por
    // apertureRadius vale exactamente iconScale, así que con 1.0 la esquina cae
    // sobre la circunferencia de apertura y no queda holgura oculta. Aún así no
    // roza el anillo: apertureRadius ya descuenta ringWidth/2 - 1, y los logos
    // son siluetas centradas que no llenan sus esquinas.
    property real iconScale: 1.0
    property string iconFontFamily: HudPalette.glyphFont
    // Identidad de proveedor en dos tonos: interno oscuro / externo claro.
    property color innerColor: HudPalette.fallbackAccent
    property color outerColor: HudPalette.accent
    property color trackColor: HudPalette.track
    // Tercer anillo temporal independiente del porcentaje. Cada segmento blanco
    // representa un día hasta el próximo reinicio de cuota (máximo siete).
    // Los umbrales de salud vienen de la configuracion del plasmoide; estaban
    // fijos en 0.30 y 0.10 dentro del calculo del color.
    property real amberThreshold: 0.30
    property real redThreshold: 0.10
    property bool showResetRing: true
    property int resetDaysRemaining: -1
    property int resetSegmentCount: 7
    property color resetSegmentColor: HudPalette.text

    implicitWidth: Kirigami.Units.iconSizes.smallMedium
    implicitHeight: Kirigami.Units.iconSizes.smallMedium

    readonly property bool hasData: outerFraction >= 0 || (!singleRing && innerFraction >= 0) || hasAuxiliaryData

    // Peor fracción libre visible (la más crítica) → color semántico de salud.
    readonly property real _minFrac: {
        var best = 2
        if (outerFraction >= 0 && outerFraction < best) best = outerFraction
        if (!singleRing && innerFraction >= 0 && innerFraction < best) best = innerFraction
        return best <= 1 ? best : -1
    }
    // Verde/blanco = holgado · ámbar ≤30% · rojo ≤10% · gris = sin datos.
    readonly property color _healthColor: {
        if (_minFrac < 0) return HudPalette.noData
        if (_minFrac <= gauge.redThreshold) return HudPalette.danger
        if (_minFrac <= gauge.amberThreshold) return HudPalette.warning
        return HudPalette.text
    }

    // One geometry for the painted rings and the content aperture. Icons are
    // fitted in the inscribed square, so even their corners cannot touch a ring.
    readonly property real diameter: Math.min(width, height)
    readonly property bool hasResetRing: showResetRing && resetDaysRemaining >= 0
    // Trazo ligeramente mas ancho para que el arco se lea de un vistazo en el panel,
    // donde la dona mide unos 34 px. Ensanchar el anillo encoge la apertura central y
    // con ella el icono, asi que el hueco se recupera apretando el gap entre anillos:
    // linea +9 %, icono +3 % y los dos anillos siguen distinguiendose.
    readonly property real resetWidth: Math.max(1, diameter * 0.032)
    readonly property real ringWidth: Math.max(1.2, diameter * 0.060)
    readonly property real ringGap: Math.max(1, diameter * 0.032)
    readonly property real outerRadius: diameter / 2 - 1 - ringWidth / 2
        - (hasResetRing ? resetWidth + ringGap : 0)
    readonly property real innerRadius: outerRadius - ringWidth - ringGap
    readonly property real apertureRadius: Math.max(0,
        (singleRing ? outerRadius : innerRadius) - ringWidth / 2 - 1)
    readonly property real contentSize: apertureRadius * Math.SQRT2

    // Una sola clave de repintado: el Canvas se redibuja cuando cambia algo que se ve,
    // no cada vez que un binding se reevalua. Con nueve manejadores sueltos, releer la
    // cache repintaba las quince donas aunque el JSON fuera identico.
    readonly property string paintKey: [
        gauge.outerFraction, gauge.innerFraction, gauge.singleRing, gauge.stale,
        gauge.showResetRing, gauge.resetDaysRemaining, gauge.resetSegmentCount,
        gauge.innerColor, gauge.outerColor, gauge.trackColor, gauge.resetSegmentColor,
        gauge.width, gauge.height
    ].join("|")

    onPaintKeyChanged: canvas.requestPaint()

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
        if (frac > 0) {
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

    function _drawResetRing(ctx, cx: real, cy: real, r: real, lw: real): void {
        if (!showResetRing || resetDaysRemaining < 0 || r <= 0 || resetSegmentCount <= 0)
            return
        const remaining = Math.min(Math.max(resetDaysRemaining, 0), resetSegmentCount)
        const slice = (2 * Math.PI) / resetSegmentCount
        const gap = Math.min(slice * 0.28, 0.12)
        ctx.setLineDash([])
        ctx.lineCap = "butt"
        ctx.lineWidth = lw
        for (let i = 0; i < resetSegmentCount; i++) {
            const start = -Math.PI / 2 + i * slice + gap / 2
            const end = -Math.PI / 2 + (i + 1) * slice - gap / 2
            ctx.beginPath()
            ctx.arc(cx, cy, r, start, end, false)
            ctx.strokeStyle = i < remaining ? resetSegmentColor : HudPalette.trackSpent
            ctx.globalAlpha = gauge.stale ? (i < remaining ? 0.55 : 0.40) : 1.0
            ctx.stroke()
        }
        ctx.globalAlpha = 1.0
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: true
        // Image rasteriza al device pixel ratio real. FramebufferObject no garantiza
        // multimuestreo con escala fraccional en Wayland, y aqui todo son arcos.
        renderTarget: Canvas.Image
        renderStrategy: Canvas.Cooperative

        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const cx = width / 2
            const cy = height / 2
            if (gauge.hasResetRing)
                gauge._drawResetRing(ctx, cx, cy,
                    gauge.diameter / 2 - 1 - gauge.resetWidth / 2, gauge.resetWidth)
            gauge._drawRing(ctx, cx, cy, gauge.outerRadius, gauge.ringWidth,
                gauge.outerFraction, gauge.outerColor)
            if (!gauge.singleRing)
                gauge._drawRing(ctx, cx, cy, gauge.innerRadius, gauge.ringWidth,
                    gauge.innerFraction, gauge.innerColor)
        }
    }

    // Centro, prioridad: número (popup) → logo del proveedor (compacto) → glifo (fallback).
    Text {
        visible: gauge.centerText !== ""
        anchors.centerIn: parent
        width: gauge.contentSize
        height: width
        fontSizeMode: Text.Fit
        minimumPixelSize: 4
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        text: gauge.centerText
        color: gauge.centerTextColor
        // Conteo "robótico": Iosevka pesada, más chica que antes.
        // Relativo al diametro de la dona, con un piso en la letra pequena del tema.
        font.pixelSize: Math.max(Kirigami.Units.gridUnit * 0.7, gauge.height * 0.27)
        font.weight: Font.Black
        font.family: "IosevkaTerm Nerd Font"
        font.letterSpacing: 0.5
        renderType: Text.NativeRendering
    }

    Kirigami.Icon {
        visible: gauge.centerText === "" && String(gauge.iconSource) !== ""
        anchors.centerIn: parent
        objectName: "providerIcon"
        // Sin Math.min: ese techo silencioso recortaba cualquier valor > 1 sin
        // avisar, y con ello desactivaba el propio invariante que protege la
        // contención (hypot(w,h)/2 <= apertureRadius, en test_qml_layout_runtime).
        // Un iconScale: 1.10 salía verde. Ahora pone rojas las 15 combinaciones.
        width: gauge.contentSize * gauge.iconScale
        height: width
        source: gauge.iconSource
        isMask: gauge.iconIsMask
        color: gauge.iconMaskColor
        opacity: gauge.hasData ? 1.0 : 0.45
        smooth: true
    }

    Text {
        visible: gauge.centerText === "" && String(gauge.iconSource) === ""
        anchors.centerIn: parent
        width: gauge.contentSize
        height: width
        fontSizeMode: Text.Fit
        minimumPixelSize: 4
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        text: gauge.label
        color: gauge.centerGlyphColor !== null ? gauge.centerGlyphColor
            : gauge.hasData ? (gauge._minFrac <= gauge.amberThreshold ? gauge._healthColor : HudPalette.text) : HudPalette.confidenceUnknown
        opacity: gauge.hasData ? 1.0 : 0.6
        font.pixelSize: Math.max(Kirigami.Units.gridUnit * 0.6, gauge.height * 0.42)
        font.family: gauge.iconFontFamily
        renderType: Text.NativeRendering
    }

    // Indicador de dato preservado (stale): punto tenue arriba a la derecha.
    Rectangle {
        visible: gauge.stale
        width: Math.max(Kirigami.Units.smallSpacing, gauge.height * 0.10)
        height: width
        radius: width / 2
        color: HudPalette.caution
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 1
    }

}
