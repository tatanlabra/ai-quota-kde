"""El catálogo de traducción, como gate.

Las cadenas fuente están en inglés y el español vive en `po/es.po`. Es la condición que
la persona usuaria puso para publicar el repositorio, junto con HiDPI.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "plasmoid/org.tatan.aiquota/contents/ui"
CONFIG = ROOT / "plasmoid/org.tatan.aiquota/contents/config"
DOMAIN = "plasma_applet_org.tatan.aiquota"
PO = ROOT / "po" / "es.po"
POT = ROOT / "po" / f"{DOMAIN}.pot"
MO = ROOT / f"plasmoid/org.tatan.aiquota/contents/locale/es/LC_MESSAGES/{DOMAIN}.mo"

# Palabras que solo pueden aparecer traducidas, nunca en el fuente.
SPANISH_SENTINELS = (
    "libre", "renueva", "hoy", "mañana", "sin dato", "caché", "actualizado",
    "reinicio", "saldo", "cuota", "espera", "limitado", "proveedor", "solic",
)


def qml_files() -> list[Path]:
    return sorted(list(UI.rglob("*.qml")) + list(CONFIG.rglob("*.qml")))


def source_without_i18n_payloads(text: str) -> str:
    """El texto del fichero con el contenido de cada i18n vaciado.

    Lo que queda son las cadenas que llegarían a pantalla SIN pasar por el catálogo.
    """
    return re.sub(r'i18n[cnp]*\((?:"[^"]*",\s*)?"[^"]*"', 'i18n(""', text)


def test_the_catalogue_is_complete_and_the_compiled_file_is_fresh():
    """Un `.mo` viejo se instala igual de silenciosamente que uno al día.

    falsified_by: 2026-09-06. Editar un `msgstr` de `po/es.po` sin recompilar deja el
    `.mo` versionado distinto del que produce `msgfmt`, y `cmp` lo detecta. Se observó
    al revés durante el desarrollo: el catálogo decía «51 traducidos, 9 sin traducir»
    mientras el widget ya mostraba texto, porque el `.mo` compilado era anterior.
    """
    assert MO.exists(), MO
    stats = subprocess.run(
        ["msgfmt", "--check", "--statistics", "--output-file=/dev/null", str(PO)],
        capture_output=True, text=True, check=True,
    )
    output = stats.stdout + stats.stderr
    assert "sin traducir" not in output and "untranslated" not in output, output

    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "fresh.mo"
        subprocess.run(["msgfmt", "--output-file", str(fresh), str(PO)], check=True)
        assert fresh.read_bytes() == MO.read_bytes(), (
            "el .mo versionado no coincide con el que produce msgfmt: "
            "ejecuta scripts/build_locale.sh"
        )


def test_every_message_of_the_template_has_an_entry():
    """`msgcmp` compara plantilla y catálogo en las dos direcciones."""
    result = subprocess.run(["msgcmp", str(PO), str(POT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_spanish_string_reaches_the_screen_outside_the_catalogue():
    """Las cadenas fuente son inglesas; el español solo existe dentro de `po/es.po`.

    falsified_by: 2026-09-06. Antes de este trabajo, la interfaz entera estaba escrita
    en español y sin una sola llamada a i18n: este test encuentra 33 líneas sobre
    `git show v0.2.0-hud-pre-refactor:…`, y ese es el motivo por el que el repositorio
    seguía sin publicarse.
    """
    offenders = {}
    for path in qml_files():
        stripped = source_without_i18n_payloads(path.read_text(encoding="utf-8"))
        for number, line in enumerate(stripped.splitlines(), 1):
            code = line.split("//")[0]
            for match in re.finditer(r'"([^"]{2,})"', code):
                value = match.group(1)
                if any(re.search(rf"\b{word}\b", value, re.IGNORECASE) for word in SPANISH_SENTINELS):
                    offenders.setdefault(path.name, []).append(f"{number}: {value[:60]}")
    assert offenders == {}, offenders


def test_the_context_notes_are_written_for_whoever_translates():
    """Un `%1` sin explicar es una traducción a ciegas.

    Cada cadena con marcador posicional tiene que llegar al catálogo con su contexto,
    o quien traduzca no sabe si `%1` es una hora, un porcentaje o un nombre.
    """
    template = POT.read_text(encoding="utf-8")
    entries = re.findall(
        r'(?:msgctxt "((?:[^"\\]|\\.)*)"\n)?msgid "((?:[^"\\]|\\.)*)"', template
    )
    missing = [
        msgid for context, msgid in entries
        if "%1" in msgid and not context and msgid not in ("%1 tok",)
    ]
    assert missing == [], missing


def test_the_installer_compiles_the_catalogue_before_packaging():
    """kpackagetool6 copia el arbol tal cual: un .mo sin compilar se instala vacio.

    Se compara contra la INVOCACION que empaqueta (`-t Plasma/Applet -i` o `-u`), no
    contra la primera mencion del binario: la guarda `command -v kpackagetool6` lo
    nombra antes con toda razon, y un test que no distinga las dos cosas se pone rojo
    por un orden que es correcto.

    falsified_by: 2026-09-06. Moviendo la llamada a build_locale.sh detras de
    `kpackagetool6 -t Plasma/Applet -u`, esta asercion falla; y sin la llamada, la
    primera.
    """
    installer = (ROOT / "scripts/install-user.sh").read_text(encoding="utf-8")
    assert "build_locale.sh" in installer
    packaging = re.search(r"kpackagetool6 -t Plasma/Applet -[iu]\b", installer)
    assert packaging is not None, "el instalador ya no empaqueta el plasmoide"
    assert installer.index("build_locale.sh") < packaging.start()


def test_catalogue_source_references_are_relative():
    """Source locations must be portable between checkout directories.

    falsified_by: 2026-09-06, prior generator emitted absolute checkout paths
    in both tracked catalogues; this test failed before switching extraction cwd.
    """
    for catalogue in (PO, POT):
        references = re.findall(r'^#: (.+)$', catalogue.read_text(), re.MULTILINE)
        assert references, catalogue
        assert all(not Path(ref.rsplit(':', 1)[0]).is_absolute()
                   for line in references for ref in line.split()), catalogue


def test_dates_are_formatted_through_the_desktop_locale():
    """Qt.formatDate con un formato de texto ignora el locale y rinde en ingles.

    Es la trampa que dejo el widget medio traducido sin que ningun gate lo notara: los
    porcentajes y las etiquetas salian en espanol y las fechas en ingles, porque
    Qt.formatDate(d, "ddd d MMM") usa el locale C. Medido con QLocale("es_CL") sobre la
    misma fecha: `Qt.formatDate` devuelve "Sat 12 Sep" y `toLocaleDateString(Qt.locale(),
    ...)` devuelve "sab 12 sept".

    falsified_by: 2026-09-08. Reponiendo cualquiera de las dos llamadas originales de
    main.qml --lineas 244 y 264 antes del arreglo-- este test falla. Se observo primero
    en una captura para el post, con el resto de la interfaz ya en espanol.
    """
    offenders = {}
    for path in qml_files():
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            code = line.split("//")[0]
            # Con un enum Locale.ShortFormat si respeta el locale; el problema es el
            # formato escrito a mano.
            if re.search(r'Qt\.format(?:Date|DateTime)\s*\([^)]*"', code):
                offenders.setdefault(path.name, []).append(f"{number}: {code.strip()[:70]}")
    assert offenders == {}, offenders

    # Y la via correcta esta en uso, para que el test no pase por ausencia de fechas.
    main = (UI / "main.qml").read_text(encoding="utf-8")
    assert "toLocaleDateString(Qt.locale()" in main
    assert "toLocaleTimeString(Qt.locale()" in main


def test_no_translation_is_left_marked_as_a_guess():
    """`msgmerge` adivina, y una marca `#, fuzzy` borrada en bloque publica su adivinanza.

    falsified_by: 2026-09-08, ocurrido de verdad. Al anadir `Antigravity (today)`,
    msgmerge la caso por parecido con una entrada vieja y propuso «Antigravity /
    Gemini», que no es su traduccion; limpiar los marcadores con una regex la acepto en
    silencio y quedo en el catalogo compilado. Este gate no distingue una traduccion
    buena de una mala --ninguno puede-- pero obliga a que ninguna llegue al .mo sin que
    una persona la haya mirado: tras cada `msgmerge`, o se corrige o el test esta rojo.
    """
    text = PO.read_text(encoding="utf-8")
    fuzzy = [
        number
        for number, line in enumerate(text.splitlines(), 1)
        if line.startswith("#, ") and "fuzzy" in line
    ]
    assert fuzzy == [], f"entradas marcadas como adivinanza en las lineas {fuzzy}"
    # No se exige que no haya entradas obsoletas (`#~`). Son de donde msgmerge saca sus
    # casamientos falsos, si, pero tambien es su razon de ser: si una cadena retirada
    # vuelve, recupera su traduccion en vez de perderla. El control correcto no es
    # borrar el historial sino que ninguna adivinanza pase sin revisar, que es lo que
    # comprueba la asercion de arriba.
