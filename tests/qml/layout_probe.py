"""Render the real HUD views with synthetic data; never read the user cache."""

import os, pathlib, sys, json

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# El renderizador software es correcto SOLO offscreen: es determinista, rapido y no
# exige sesion grafica, que es lo que la suite de geometria necesita. Pero
# Kirigami.Icon con isMask NO tine bajo QSGSoftwareRenderer --su IconMaterial solo
# existe como material RHI, sin el fallback que si tiene ShadowedRectangle--, asi que
# una captura para publicar tiene que salir por RHI o los cuatro logotipos
# enmascarados salen negros (codex, blanco). Medido el 2026-09-09; ya estaba
# registrado en docs/layout-validation-2026-09-06.md:31-34 y se perdio en 74bd40a.
# Por eso el default va condicionado: pedir una plataforma con GPU basta para
# desactivarlo, sin tener que acordarse de una segunda variable.
if os.environ["QT_QPA_PLATFORM"].split(";")[0] == "offscreen":
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
# El DPI logico se fija a 96 para que la geometria no dependa del monitor de la
# maquina ni de la plataforma Qt. Medido el 2026-09-09: offscreen reporta 96, pero
# eglfs deriva 100 del panel real (1920x1080 a 143,91 DPI fisico) y con ello el
# tooltip pasaba de 310 a 318 px logicos --y la imagen publicada de 1260x930 a
# 1260x954-- sin que cambiara una linea de QML. Con 96 las dos plataformas dan el
# mismo alto, asi que lo que miden los tests es lo que se publica.
os.environ.setdefault("QT_FONT_DPI", "96")
from PySide6.QtCore import QUrl, QTimer, QPointF, QObject, Qt, QEvent, QCoreApplication
from PySide6.QtGui import QGuiApplication, QFont, QMouseEvent
from PySide6.QtQml import QQmlEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem, QQuickWindow

app = QGuiApplication([])
app.setFont(QFont("Fira Sans", 11))
engine = QQmlEngine()
ui = QUrl.fromLocalFile(sys.argv[1]).toString()
surface = sys.argv[2]
width = int(sys.argv[3])
# Alto del lienzo. El fixture usa 650 para que un desborde tenga sitio donde asomar y
# el test lo detecte; una captura para publicar quiere el alto real de la vista, sin
# el fondo muerto que sobra debajo del contenido.
height = 40 if surface == "compact" else 650
if "--height" in sys.argv:
    height = int(sys.argv[sys.argv.index("--height") + 1])
funcs = {
    "windowOf": "({})",
    "confidenceText": '"API"',
    "renewalText": '"renueva 13 septiembre · en siete días"',
    "windowSourceText": '"estimación con nota de fuente considerablemente larga para comprobar desbordes"',
    "windowShortName": '"AI Credits / Premium requests"',
    "metricValueText": '"128/200 requests"',
    "metricTone": '"white"',
    "confidenceColor": '"blue"',
    "localTimeText": '"18:39"',
    "refreshButtonText": '"Refresh"',
    "providerDisplayName": 'k === "gemini" ? "ANTIGRAVITY / GEMINI" : k.toUpperCase()',
    "providerStatusText": '"⚠ sin registro local compatible"',
    "nextQuotaResetSummary": '"renueva en 6 días y 15 horas"',
    "detailWindows": '["weekly", "session", "activity"]',
    "gaugeWindows": '["weekly", "session"]',
    "gaugeSingleRing": "false",
    "providerStale": "true",
    "gaugeOuterFraction": "0.42",
    "gaugeInnerFraction": "0.65",
    "hasUsableDetailData": "true",
    "resetDaysRemaining": "6",
    "donutCenterText": '"42%"',
    "donutCenterColor": '"white"',
    "providerAccent": '"cyan"',
    "providerGlyph": '"A"',
    "providerGlyphColor": '"white"',
    "providerIconSource": '""',
    "providerIconIsMask": "false",
    "providerIconColor": '"white"',
    "providerInnerColor": '"blue"',
    "getProviderByKey": "({})",
    "requestManualRefresh": "null",
}
mock = "\n".join(
    "function " + k + "(k, w) { return " + v + "; }" for k, v in funcs.items()
)
sample_report = None
sample_properties = ""
if "--sample" in sys.argv:
    import re
    import tempfile
    from pathlib import Path
    from typer.testing import CliRunner

    project = Path(sys.argv[1]).resolve().parents[3]
    sys.path.insert(0, str(project / "src"))
    from ai_quota_monitor import cli

    # Only the synthetic sample command runs; all writes go to this temporary folder.
    with tempfile.TemporaryDirectory(prefix="hud-preview-") as folder:
        cli.CACHE_DIR = Path(folder)
        cli.STATUS_JSON = Path(folder) / "status.json"
        result = CliRunner().invoke(cli.app, ["sample", "--write-cache"])
        assert result.exit_code == 0, result.stdout
        sample_report = cli.STATUS_JSON.read_text()

    # Reloj fijo, para que dos corridas den los mismos bytes.
    #
    # Por que hace falta: `sample` deriva generated_at y todos los reset_at de
    # datetime.now(), y main.qml compara esas fechas contra Date.now() para calcular
    # las cuentas atras Y los arcos. Dos renders separados por un minuto producen
    # imagenes distintas, asi que un video no se puede regenerar identico ni se puede
    # tener un gate de determinismo. Medido el 2026-09-09.
    #
    # Se descarto libfaketime: su sintaxis `x0` la rechaza la version instalada
    # (0.9.13) y `@<fecha>` fija el INICIO pero el reloj sigue avanzando, asi que el
    # render de 40 s podia cruzar un minuto igualmente. Y ralentizar el reloj cuelga
    # cualquier sleep, porque espera segundos falsos.
    #
    # En su lugar: se desplazan TODAS las marcas de tiempo del informe por el mismo
    # delta, de modo que el informe queda tal como `sample` lo habria escrito en el
    # instante congelado, y se sustituye la fuente de tiempo de los cuerpos inyectados
    # por ese mismo instante. El informe sigue siendo el que genera el CLI real: solo
    # se traslada en el tiempo.
    if "--frozen-now" in sys.argv:
        import datetime as _dt
        import json as _json_frozen

        frozen_iso = sys.argv[sys.argv.index("--frozen-now") + 1]
        frozen = _dt.datetime.fromisoformat(frozen_iso)
        if frozen.tzinfo is None:
            frozen = frozen.replace(tzinfo=_dt.timezone.utc)
        report_obj = _json_frozen.loads(sample_report)
        base = _dt.datetime.fromisoformat(report_obj["generated_at"])
        delta = frozen - base

        def _shift(value):
            if isinstance(value, dict):
                return {k: _shift(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_shift(v) for v in value]
            if isinstance(value, str):
                try:
                    stamp = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return value
                if stamp.tzinfo is None:
                    return value
                moved = stamp + delta
                return (
                    moved.astimezone(_dt.timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                    if value.endswith("Z")
                    else moved.isoformat()
                )
            return value

        sample_report = _json_frozen.dumps(_shift(report_obj))
        FROZEN_MS = int(frozen.timestamp() * 1000)
    main = (Path(sys.argv[1]) / "main.qml").read_text()
    bodies = []
    for match in re.finditer(r"^    function (\w+)\(", main, re.MULTILINE):
        name = match.group(1)
        if name in ("requestManualRefresh", "refreshButtonText"):
            continue
        opening = main.index("{", match.start())
        depth = 0
        for end in range(opening, len(main)):
            if main[end] == "{":
                depth += 1
            elif main[end] == "}":
                depth -= 1
                if depth == 0:
                    body = main[match.start() : end + 1].replace("root.", "pi.")
                    if "--frozen-now" in sys.argv:
                        # La fuente de tiempo se sustituye SOLO en los cuerpos
                        # inyectados al fixture; el QML instalado no se toca.
                        body = body.replace("Date.now()", "pi.frozenNow")
                        body = body.replace("new Date()", "new Date(pi.frozenNow)")
                    bodies.append(body)
                    break
    mock = "\n".join(bodies) + '\nfunction refreshButtonText() { return "Refresh"; }'
    for name in ("gaugeOrder", "detailOrder"):
        values = re.search(
            r"readonly property var " + name + r": (\[.*?\])", main, re.S
        ).group(1)
        sample_properties += "property var " + name + ": " + values + "\n"

component = {
    "popup": "HUD.FullRepresentation",
    "tooltip": "C.QuotaTooltip",
    "compact": "HUD.CompactRepresentation",
    # El escenario del video: las tres vistas en un solo lienzo, compartiendo el mismo
    # objeto de estado. Es una superficie mas para la sonda, asi que reutiliza el
    # fixture entero --datos ficticios en tempdir, catalogo .po, cuerpos reales de
    # main.qml-- en vez de duplicarlo en un renderizador aparte que podria derivar.
    "stage": "D.DemoStage",
}[surface]
# Catalogo de traduccion opcional. El fixture resuelve i18n como identidad, que basta
# para medir layout pero rinde los msgid en ingles. Una captura para un post en espanol
# tiene que salir en espanol, asi que --lang carga po/<lang>.po y lo inyecta como tabla.
catalog = "({})"
if "--lang" in sys.argv:
    import json as _json
    import re as _re
    from pathlib import Path as _Path

    lang = sys.argv[sys.argv.index("--lang") + 1]
    # Qt no toma el locale del entorno para los nombres de dia y mes de
    # Qt.formatDate: con LC_ALL=es_CL.UTF-8 seguia rindiendo "Mon 14 Sep". Si se pide
    # el catalogo de un idioma, sus fechas van en ese idioma o la captura sale mestiza.
    from PySide6.QtCore import QLocale

    QLocale.setDefault(QLocale(lang))
    po = _Path(sys.argv[1]).resolve().parents[3] / "po" / f"{lang}.po"
    # El ingles es el idioma fuente: sus cadenas SON los msgid y no hay catalogo. Aun
    # asi hace falta fijar el locale, o las fechas saldrian en el idioma del sistema.
    text = po.read_text(encoding="utf-8") if po.exists() else ""

    # Solo estas cuatro secuencias aparecen en un .po. `unicode_escape` seria mas
    # corto y esta mal: interpreta los bytes como latin-1, asi que "mañana" sale
    # "maÃ±ana" y el mojibake acaba publicado en la captura.
    _ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}

    def _unquote(block):
        joined = "".join(
            _re.sub(r'^"|"$', "", line.strip())
            for line in block.strip().splitlines()
        )
        return _re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), joined)

    table = {}
    entries = _re.split(r"\n\n+", text)
    for entry in entries:
        if entry.lstrip().startswith("#~") or "msgid" not in entry:
            continue
        ctx = _re.search(r'^msgctxt ((?:"[^"]*"\s*)+)', entry, _re.M)
        mid = _re.search(r'^msgid ((?:"[^"]*"\s*)+)', entry, _re.M)
        mstr = _re.search(r'^msgstr(?:\[0\])? ((?:"[^"]*"\s*)+)', entry, _re.M)
        if not mid or not mstr:
            continue
        source, target = _unquote(mid.group(1)), _unquote(mstr.group(1))
        if not source or not target:
            continue
        table[source] = target
        if ctx:
            table[_unquote(ctx.group(1)) + "\u0004" + source] = target
    # Dos cuidados con el literal que se inserta en el QML. ensure_ascii deja el
    # separador de contexto U+0004 y los acentos como escapes \uXXXX, porque un control
    # char literal no sobrevive al fuente. Y los parentesis no son adorno: en un binding
    # QML, `{}` se lee como bloque de codigo vacio y la propiedad queda undefined, asi
    # que con un catalogo vacio --el ingles, que es el idioma fuente-- la vista se
    # rendia sin valores ni insignias.
    catalog = "(" + _json.dumps(table) + ")"

probe_dir = QUrl.fromLocalFile(str(pathlib.Path(__file__).resolve().parent)).toString()
# Sin --frozen-now el fixture usa el reloj real, que es lo correcto para los tests de
# geometria: no dependen de la hora y no hace falta fijarla.
frozen_property = str(FROZEN_MS) if "--frozen-now" in sys.argv else "Date.now()"
qml = f'''import QtQuick
import "{ui}" as HUD
import "{ui}/components" as C
import "{ui}/components"
import "{probe_dir}" as D
Item {{
 width: {width}; height: {height}
 readonly property var catalog: {catalog}
 function i18n(s) {{var args = arguments; var t = catalog[s] || s
     return t.replace(/%([1-9])/g, function(m,n) {{return n < args.length ? args[n] : m}})}}
 function i18nc(c, s) {{var args = Array.prototype.slice.call(arguments, 1)
     args[0] = catalog[c + "\u0004" + s] || catalog[s] || s
     return i18n.apply(null, args)}}
 function i18np(s, p, n) {{var args = Array.prototype.slice.call(arguments, 2)
     args.unshift(catalog[n === 1 ? s : p] || (n === 1 ? s : p))
     return i18n.apply(null, args)}}
 function i18ncp(c, s, p, n) {{return i18np.apply(null, Array.prototype.slice.call(arguments, 1))}}
 QtObject {{ id: pi
 objectName: "fixtureState"
 property int compactMode: 0
 property string worstProvider: "claude"
 property bool expanded: false
 property var visibleProviders: ["claude","codex","gemini","copilot","deepseek"]
 property var report: ({sample_report or '{generated_at:"2026-09-06",warnings:[],network_used:false}'})
 {sample_properties}
 property string selectedProvider: "claude"
 property string hoveredProvider: "gemini"
 property bool canRefresh: false
 property string refreshHint: ""
 property string lastError: ""
 property real amberThreshold: 0.3
 property real redThreshold: 0.1
 property bool showResetRing: true
 property real frozenNow: {frozen_property}
 {mock}
 }}
 {component} {{ objectName: "surface"; plasmoidItem: pi; width: parent.width; height: {"implicitHeight" if surface == "tooltip" else "parent.height"} }}
}}'''
c = QQmlComponent(engine)
c.setData(qml.encode(), QUrl.fromLocalFile(str(__file__)))
root = c.create()
if root is None:
    print([e.toString() for e in c.errors()])
    sys.exit(2)
window = QQuickWindow()
window.setGeometry(0, 0, width, height)
root.setParentItem(window.contentItem())
# show() sin banderas ni opacidad, a proposito, y las tres platformas de captura lo
# toleran. Dos intentos de "mejorarlo" fallaron el 2026-09-09 y quedan aqui para que
# nadie los repita: (1) setOpacity(0) hace que el compositor no renderice la ventana,
# asi que grabToImage() devuelve un puntero NULO --"Attempt to retrieve 'ready' from
# null object"-- y el proceso se cuelga sin guardar nada; (2) Qt.ToolTip sin padre
# corre el mismo riesgo de no mapearse en Wayland. La captura publicada va por
# QT_QPA_PLATFORM=eglfs con EGL_PLATFORM=surfaceless, que no abre ventana en absoluto
# y por eso funciona incluso con la pantalla bloqueada.
window.show()


def grab_now(item, path, timeout_ms=4000):
    """Un grab sincrono. grabToImage() es asincrono y devuelve None si el item no se
    esta renderizando; un bucle anidado con vigilante convierte las dos cosas en un
    fallo ruidoso en vez de un cuelgue silencioso, que es como se perdieron dos horas
    el 2026-09-09 con setOpacity(0)."""
    from PySide6.QtCore import QEventLoop

    grab = item.grabToImage()
    if grab is None:
        raise RuntimeError(f"grabToImage() devolvio nulo en {path.name}")
    loop = QEventLoop()
    grab.ready.connect(loop.quit)
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(loop.quit)
    watchdog.start(timeout_ms)
    loop.exec()
    if not watchdog.isActive():
        raise RuntimeError(f"el grab agoto el vigilante en {path.name}")
    watchdog.stop()
    image = grab.image()
    if image.isNull():
        raise RuntimeError(f"imagen nula en {path.name}")
    if not grab.saveToFile(str(path)):
        raise RuntimeError(f"no se pudo escribir {path}")
    return image.width(), image.height()


def find_in(root_item, container_name, target_name):
    """Busca `target_name` DENTRO del subarbol `container_name`.

    Hace falta porque en el escenario hay tres instancias de cada dona --barra, visor y
    popup-- y una busqueda global devolveria la primera en orden de arbol, que es un
    detalle de como esta escrito el QML y no algo en lo que se pueda confiar."""

    def walk(item, name):
        if item.objectName() == name:
            return item
        for child in item.childItems():
            found = walk(child, name)
            if found is not None:
                return found
        return None

    container = walk(root_item, container_name)
    return None if container is None else walk(container, target_name)


def render_sequence(root_item, surf, state):
    """Renderiza el guion completo a PNG, en un solo proceso.

    Un proceso por fotograma costaria ~1,5 s de arranque x 486 = 12 min; con el engine
    vivo son decenas de milisegundos por fotograma. Y mas importante: el estado se muta
    con EVENTOS REALES --MouseMove sobre la celda, press+release sobre el selector--, no
    escribiendo las propiedades finales, asi que lo que se ve en el video son los
    manejadores del widget reaccionando de verdad. Cada fotograma comprueba que el
    estado que pedia el guion es el que quedo; si un clic no prende, el render falla en
    voz alta en vez de producir un video donde el selector nunca cambia."""
    import hashlib
    import pathlib as _pathlib

    sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
    import demo_storyboard as sb

    dest = _pathlib.Path(sys.argv[sys.argv.index("--sequence") + 1])
    dest.mkdir(parents=True, exist_ok=True)
    only = None
    if "--frames" in sys.argv:
        only = {int(n) for n in sys.argv[sys.argv.index("--frames") + 1].split(",")}

    def send_mouse(kind, point, buttons):
        QCoreApplication.sendEvent(
            window, QMouseEvent(kind, point, point, Qt.LeftButton, buttons, Qt.NoModifier)
        )

    def centre(item):
        return item.mapToScene(QPointF(item.width() / 2, item.height() / 2))

    # Precalentado: cada Canvas del HUD usa renderStrategy Cooperative, asi que el
    # primer fotograma tras aparecer una capa puede salir con el arco viejo. Se visitan
    # todos los estados una vez antes de grabar nada.
    for provider in ("claude", "codex", "gemini", "copilot", "deepseek"):
        state.setProperty("selectedProvider", provider)
        state.setProperty("hoveredProvider", provider)
        for name, value in (("tooltipOpacity", 1.0), ("popupOpacity", 1.0)):
            surf.setProperty(name, value)
        app.processEvents()

    rows = []
    frames = sb.total_frames()
    for index in range(frames):
        want = sb.state_at(index)
        surf.setProperty("tooltipOpacity", want.tooltip_opacity)
        surf.setProperty("tooltipLift", want.tooltip_lift)
        surf.setProperty("popupOpacity", want.popup_opacity)
        surf.setProperty("popupLift", want.popup_lift)

        if want.hover is not None:
            cell = find_in(root_item, "stageCompact", "gauge-" + want.hover)
            if cell is None:
                raise RuntimeError(f"no existe gauge-{want.hover} en la barra compacta")
            send_mouse(QEvent.MouseMove, centre(cell), Qt.NoButton)
        else:
            QCoreApplication.sendEvent(window, QEvent(QEvent.Leave))

        if want.click is not None:
            button = find_in(root_item, "stagePopup", want.click)
            if button is None:
                raise RuntimeError(f"no existe {want.click} en el popup")
            point = centre(button)
            send_mouse(QEvent.MouseButtonPress, point, Qt.LeftButton)
            send_mouse(QEvent.MouseButtonRelease, point, Qt.NoButton)
        elif want.select is not None and want.popup_opacity > 0.99:
            state.setProperty("selectedProvider", want.select)

        app.processEvents()
        if want.ease is not None:
            # Dos pases en las transiciones: la primera pasada aplica el cambio de
            # geometria y la segunda deja que el Canvas cooperativo lo pinte.
            app.processEvents()

        if want.hover is not None:
            got = state.property("hoveredProvider")
            if got != want.hover:
                raise RuntimeError(
                    f"fotograma {index}: se pidio hover {want.hover} y quedo {got}: "
                    "el MouseMove no llego al manejador"
                )
        if want.select is not None and want.popup_opacity > 0.99:
            got = state.property("selectedProvider")
            if got != want.select:
                raise RuntimeError(
                    f"fotograma {index}: se pidio seleccion {want.select} y quedo {got}"
                )

        if only is not None and index not in only:
            continue
        path = dest / f"frame-{index:04d}.png"
        w, h = grab_now(surf, path)
        expected = (sb.STAGE_WIDTH * sb.SCALE, sb.STAGE_HEIGHT * sb.SCALE)
        if (w, h) != expected:
            raise RuntimeError(f"{path.name}: {w}x{h}, se esperaba {expected[0]}x{expected[1]}")
        rows.append(
            {
                "name": path.name,
                "shot": want.shot,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "width": w,
                "height": h,
            }
        )

    manifest = {
        "frames": frames,
        "rendered": len(rows),
        "fps": sb.FPS,
        "stage": [sb.STAGE_WIDTH, sb.STAGE_HEIGHT],
        "scale": sb.SCALE,
        "platform": app.platformName(),
        "graphics_api": window.rendererInterface().graphicsApi().name,
        "rows": rows,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"secuencia: {len(rows)}/{frames} fotogramas en {dest}", file=sys.stderr)
    app.exit(0)


def done():
    if "--no-hover" in sys.argv:
        # El puntero virtual de una plataforma sin raton arranca en (0,0), que cae
        # DENTRO de la primera celda de la barra compacta: su MouseArea reporta
        # containsMouse y la celda se dibuja con fondo HudPalette.panel, o sea un
        # recuadro mas claro detras de un solo proveedor. Medido el 2026-09-09: 37 745
        # pixeles de #0e1120 a escala 6. No es el foco de teclado --activeFocusItem()
        # es el contentItem de la ventana, no la celda--, es el hover.
        #
        # En una figura de documentacion ese recuadro es informacion legitima (asi se
        # ve al pasar el raton); en un teaser destaca uno de los cinco proveedores sin
        # motivo y se lee como un error de composicion. La bandera lo quita solo ahi.
        QCoreApplication.sendEvent(window, QEvent(QEvent.Leave))
        app.processEvents()
    errors = []
    texts = []
    icons = []
    metric_fonts = []
    selected_visits = []
    state = root.findChild(QObject, "fixtureState")
    surf = root.findChild(QQuickItem, "surface")

    def find_visual(item, name):
        if item.objectName() == name:
            return item
        for child in item.childItems():
            found = find_visual(child, name)
            if found is not None:
                return found
        return None

    if surface == "popup":
        for key in ("claude", "codex", "gemini", "copilot", "deepseek"):
            button = find_visual(root, "select-" + key)
            if button is None:
                continue
            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
            if point.x() < 0 or point.x() >= surf.width() or point.y() >= surf.height():
                errors.append(["provider button outside viewport", key])
            for event_type, buttons in (
                (QEvent.MouseButtonPress, Qt.LeftButton),
                (QEvent.MouseButtonRelease, Qt.NoButton),
            ):
                event = QMouseEvent(
                    event_type, point, point, Qt.LeftButton, buttons, Qt.NoModifier
                )
                QCoreApplication.sendEvent(window, event)
            app.processEvents()
            selected_visits.append(surf.property("activeProvider"))
        state.setProperty("selectedProvider", "claude")
        app.processEvents()

    def walk(item):
        if not item.isVisible():
            return
        if item.objectName() == "providerIcon":
            parent = item.parentItem()
            # rect_px es el recuadro del icono en el sistema de coordenadas del PNG:
            # el grab se hace sobre `surf`, asi que mapToItem(surf, .) por el dpr da
            # exactamente donde cae el icono en el fichero. Es lo que permite medir
            # su color sin coordenadas magicas escritas a mano.
            origin = item.mapToItem(surf, QPointF(0, 0))
            dpr = window.devicePixelRatio()
            icons.append(
                {
                    "source": item.property("source").toString(),
                    "width": item.width(),
                    "height": item.height(),
                    "aperture": parent.property("apertureRadius"),
                    "provider": parent.objectName().replace("gauge-", ""),
                    "mask": bool(parent.property("iconIsMask")),
                    "tint": parent.property("iconMaskColor").name(),
                    "rect_px": [
                        round(origin.x() * dpr),
                        round(origin.y() * dpr),
                        round(item.width() * dpr),
                        round(item.height() * dpr),
                    ],
                }
            )
        if item.objectName() in ("metricLabel", "metricValue"):
            metric_fonts.append(item.property("font").pointSizeF())
        if item.metaObject().indexOfProperty(
            "text"
        ) >= 0 and item.metaObject().className().startswith("QQuickText"):
            t = item.property("text")
            p = item.parentItem()
            if t:
                texts.append(
                    [t, round(item.x(), 1), round(item.width(), 1), round(p.width(), 1)]
                )
                ancestor = p
                while ancestor and ancestor != root:
                    x = item.mapToItem(ancestor, QPointF(0, 0)).x()
                    if x < -1 or x + item.width() > ancestor.width() + 1:
                        errors.append(texts[-1])
                        break
                    ancestor = ancestor.parentItem()
        for child in item.childItems():
            walk(child)

    walk(root)
    surf = root.findChild(QQuickItem, "surface")
    window.resize(width, int(surf.height()))
    print(
        json.dumps(
            {
                "surface": surface,
                "width": width,
                "height": surf.height(),
                "platform": app.platformName(),
                "backend": QQuickWindow.sceneGraphBackend(),
                "graphics_api": window.rendererInterface().graphicsApi().name,
                "dpr": window.devicePixelRatio(),
                "text_count": len(texts),
                "overflow": errors,
                "selected_visits": selected_visits,
                "icons": icons,
                "metric_fonts": metric_fonts,
            },
            ensure_ascii=False,
        )
    )

    if "--sequence" in sys.argv:
        # Una excepcion dentro de un slot de Qt NO termina el proceso: Python la imprime
        # y el bucle de eventos sigue corriendo, asi que el comando se cuelga hasta el
        # timeout y parece que el render tarda cuando en realidad ya fallo. Medido el
        # 2026-09-09 con un AttributeError. De ahi este try/except explicito.
        try:
            render_sequence(root, surf, state)
        except Exception as exc:  # noqa: BLE001 - hay que salir con codigo, no propagar
            import traceback

            traceback.print_exc()
            print(f"SECUENCIA FALLIDA: {exc}", file=sys.stderr)
            app.exit(2)
        return

    def finish():
        if "--image" in sys.argv:
            # Capture only the scene item, avoiding native frame/DPR resize artifacts.
            grab = surf.grabToImage()

            def save():
                grab.saveToFile(sys.argv[sys.argv.index("--image") + 1])
                app.exit(1 if errors else 0)

            grab.ready.connect(save)
            window._grab = grab
        else:
            app.exit(1 if errors else 0)

    QTimer.singleShot(250, finish)


QTimer.singleShot(900, done)
sys.exit(app.exec())
