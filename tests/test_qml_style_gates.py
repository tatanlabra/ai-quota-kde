"""Reglas de estilo del QML como gates, con el caso rojo observado en cada docstring.

Los tests que sustituyen comparaban cadenas literales del fuente con su indentacion
exacta (`'iconIsMask: true\\n            iconMaskColor: "#57ff8d"'`), asi que cualquier
reordenacion los rompia sin que nada estuviera mal, y en cambio no detectaban ninguno
de los defectos que si importaban. Estos comprueban propiedades del arbol.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "plasmoid/org.tatan.aiquota/contents/ui"
CONFIG = ROOT / "plasmoid/org.tatan.aiquota/contents/config"
PALETTE = UI / "components/HudPalette.qml"

# El de /usr/bin es el de Qt5: se identifica "qmllint 1.0", no conoce --json y sale 0
# con cualquier fichero, incluso uno que no sea QML. Un gate apoyado en el saldria
# siempre verde.
QMLLINT = Path("/usr/lib/qt6/bin/qmllint")

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
ABSOLUTE_SIZE = re.compile(
    r"font\.pixelSize:\s*[0-9]"
    r"|implicit(?:Width|Height):\s*(?:[3-9][0-9]|[0-9]{3,})\b"
    r"|^\s*(?:width|height):\s*[0-9]{2,}",
    re.MULTILINE,
)


def qml_files() -> list[Path]:
    return sorted(list(UI.rglob("*.qml")) + list(CONFIG.rglob("*.qml")))


def test_only_the_palette_names_a_colour():
    """Un color escrito en siete ficheros no se puede cambiar de una vez, ni auditar.

    falsified_by: 2026-09-06, medido. Sobre v0.2.0-hud-pre-refactor este test
    encuentra 108 colores en 8 ficheros: main.qml 29, FullRepresentation 29,
    CompactRepresentation 14, DonutGauge 13, QuotaTooltip 9, ProviderCard 7,
    MetricLine 5 y ProgressBar 2. Reproducible extrayendo el arbol de ese tag con
    `git archive v0.2.0-hud-pre-refactor plasmoid`.
    """
    offenders = {}
    for path in qml_files():
        if path == PALETTE:
            continue
        hits = HEX_COLOR.findall(path.read_text(encoding="utf-8"))
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, offenders
    # Y la paleta si tiene colores: un gate que pasara con la paleta vacia no probaria nada.
    assert len(HEX_COLOR.findall(PALETTE.read_text(encoding="utf-8"))) >= 20


def test_no_size_is_written_in_absolute_pixels():
    """Un tamano en pixeles no crece con la pantalla ni con la fuente del sistema.

    falsified_by: 2026-09-06, medido. Sobre v0.2.0-hud-pre-refactor salen 32
    coincidencias: FullRepresentation 15, QuotaTooltip 10, ProviderCard 5 y
    MetricLine 2. Y en ejecucion: reponiendo `implicitWidth: 620` en el popup, la
    identidad popupW == gridUnit * 30 pasa de cierta (540 == 18 * 30) a falsa
    (620 != 540), con el mismo gridUnit.
    """
    offenders = {}
    for path in qml_files():
        hits = ABSOLUTE_SIZE.findall(path.read_text(encoding="utf-8"))
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, offenders


def test_the_singleton_is_not_called_palette():
    """`Palette` es un tipo de QtQuick y eclipsa al singleton sin que nada falle al cargar.

    falsified_by: 2026-09-06, en ejecucion. Con el singleton llamado `Palette`, el
    plasmoide cargaba y el journal repetia
    `TypeError: Property 'deepOf' of object QtQuick/Palette is not a function`:
    `import QtQuick` gana, todos los colores quedan undefined y el HUD se dibuja gris.
    qmllint no lo detecta, porque resuelve el nombre contra el tipo de QtQuick.
    """
    assert PALETTE.exists()
    assert not (UI / "components/Palette.qml").exists()
    qmldir = (UI / "components/qmldir").read_text(encoding="utf-8")
    assert "singleton HudPalette 1.0 HudPalette.qml" in qmldir
    for path in qml_files():
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?<![.\w])Palette\.", text), path.name


def test_the_qmldir_lists_every_type_in_its_directory():
    """Un tipo ausente del qmldir deja de resolverse desde fuera del directorio."""
    components = UI / "components"
    declared = {
        line.split()[-1]
        for line in (components / "qmldir").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    on_disk = {path.name for path in components.glob("*.qml")}
    assert on_disk == declared, on_disk ^ declared


@pytest.mark.skipif(not QMLLINT.exists(), reason=f"{QMLLINT} no esta instalado")
def test_qmllint_is_clean_except_for_i18n():
    """qmllint de Qt6 sin avisos, salvo los de i18n, que no declara ningun modulo.

    falsified_by: 2026-09-06. Sobre v0.2.0-hud-pre-refactor quedan 5 avisos que no
    son de i18n: tres Quick.layout-positioning en FullRepresentation.qml lineas 62 y
    146, y dos accesos sin cualificar en QuotaTooltip.qml linea 49.
    """
    offenders = {}
    for path in qml_files():
        proc = subprocess.run(
            [str(QMLLINT), "-I", "/usr/lib/qt6/qml", str(path)],
            capture_output=True, text=True, check=False,
        )
        output = proc.stdout + proc.stderr
        lines = output.splitlines()
        for index, line in enumerate(lines):
            if "Warning:" not in line and "Error:" not in line:
                continue
            # El aviso trae debajo la linea del fuente; si es una llamada a i18n no cuenta.
            context = lines[index + 1] if index + 1 < len(lines) else ""
            if "i18n" in context:
                continue
            offenders.setdefault(path.name, []).append(line.strip())
    assert offenders == {}, offenders
