"""Render the real HUD views with synthetic data; never read the user cache."""

import os, sys, json

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
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
                    bodies.append(main[match.start() : end + 1].replace("root.", "pi."))
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
}[surface]
qml = f'''import QtQuick
import "{ui}" as HUD
import "{ui}/components" as C
import "{ui}/components"
Item {{
 width: {width}; height: {40 if surface == "compact" else 650}
 function i18n(s) {{var args = arguments; return s.replace(/%([1-9])/g,
     function(m,n) {{return n < args.length ? args[n] : m}})}}
 function i18nc() {{return i18n.apply(null, Array.prototype.slice.call(arguments,1))}}
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
window.setGeometry(0, 0, width, 650)
root.setParentItem(window.contentItem())
window.show()


def done():
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
            icons.append(
                {
                    "source": item.property("source").toString(),
                    "width": item.width(),
                    "height": item.height(),
                    "aperture": parent.property("apertureRadius"),
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
                "text_count": len(texts),
                "overflow": errors,
                "selected_visits": selected_visits,
                "icons": icons,
                "metric_fonts": metric_fonts,
            },
            ensure_ascii=False,
        )
    )

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
