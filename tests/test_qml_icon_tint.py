"""El acento del proveedor tiene que llegar al pixel del logotipo, no solo a la propiedad.

Por que existe este fichero: entre el 2026-09-06 y el 2026-09-09 se publicaron cuatro
imagenes del HUD con los logotipos en negro (codex, en blanco) y los 93 tests estaban
verdes. Una silueta negra tiene exactamente la misma anchura, altura y apertura que una
tenida, asi que ningun invariante de geometria podia verlo: la ausencia de una asercion
de color ES la razon de que el defecto pasara inadvertido durante dos dias y llegara al
blog. La causa era Kirigami.Icon con isMask: true, que no tine bajo QSGSoftwareRenderer
--su IconMaterial solo existe como material RHI, sin el fallback que si tiene
ShadowedRectangle-- combinado con un capture_previews.sh que imponia el backend software.

Este gate mide el ARTEFACTO que produce el script de publicacion, no un render paralelo:
si alguien vuelve a poner el backend software en capture_previews.sh, esto se pone rojo.
"""

from __future__ import annotations

import collections
import importlib.util
import json
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_previews.sh"
PALETTE = ROOT / "plasmoid/org.tatan.aiquota/contents/ui/components/HudPalette.qml"

SCALE = 3
# Recorte del recuadro del icono, en pixeles de dispositivo. Con iconScale: 1.0 las
# esquinas del recuadro caen sobre la circunferencia de apertura, que esta a 1 px logico
# (3 a escala 3) del borde interno de la tinta del anillo; recortar 3 px por lado aleja
# las esquinas 4,24 px en diagonal, asi que el antialias del anillo no entra en la
# medicion. Los logotipos son siluetas centradas, asi que el recorte no come tinta.
INSET = 3
# Un pixel cuenta como tenido si esta saturado. Los cinco acentos van de 120 a 231 de
# saturacion; el cromo del HUD no pasa de 25 (bg #08080f -> 7, panel #0e1120 -> 18,
# text #e6ecff -> 25), asi que 40 separa las dos poblaciones con holgura.
SATURATION_FLOOR = 40
# Tolerancia por canal. No es cero a proposito: codex.png es un PNG blanco de 256 px
# que se reduce con suavizado, asi que su alfa no llega a 1 en casi ningun pixel y la
# mascara compone #57fe8d en vez de #57ff8d en el popup. Medido el 2026-09-09; una
# desviacion de 1 no es un logotipo sin tenir, y 6 sigue descartando negro y blanco.
CHANNEL_TOLERANCE = 6
# Fraccion minima del recuadro recortado que debe llevar el color dominante. Margen
# medido: la cobertura real va del 13 % al 36 %, y en el caso roto es 0 %.
COVERAGE_FLOOR = 0.05

SURFACES = {"bar": 5, "tooltip": 1, "popup-hidpi": 5}
# gemini esta declarado mask: false a proposito y conserva el azul de su PNG. Es el
# control negativo que distingue "la mascara funciono" de "medi el anillo por error".
GEMINI_ICON_RGB = (0x42, 0x85, 0xF4)

HAS_RENDER_DEVICE = bool(list(pathlib.Path("/dev/dri").glob("renderD*"))) if pathlib.Path("/dev/dri").exists() else False

pytestmark = [
    pytest.mark.skipif(
        importlib.util.find_spec("PySide6") is None, reason="PySide6 no instalado"
    ),
    pytest.mark.skipif(
        importlib.util.find_spec("PIL") is None, reason="Pillow no instalado"
    ),
]


def _accents() -> dict[str, tuple[int, int, int]]:
    """Los acentos se leen de HudPalette.qml, no se copian aqui.

    Copiarlos crearia una segunda fuente de verdad que puede derivar en silencio: el
    gate seguiria verde midiendo contra un color que el widget ya no usa.
    """
    import re

    text = PALETTE.read_text(encoding="utf-8")
    out = {}
    for key, accent in re.findall(
        r'"(\w+)":\s*\{\s*accent:\s*"#([0-9a-fA-F]{6})"', text
    ):
        out[key] = (int(accent[0:2], 16), int(accent[2:4], 16), int(accent[4:6], 16))
    assert len(out) == 5, f"se esperaban 5 proveedores en HudPalette, hay {len(out)}: {out}"
    return out


def _dominant_saturated(image, rect: list[int]) -> tuple[tuple[int, int, int], int, int]:
    x, y, w, h = rect
    hist: collections.Counter = collections.Counter()
    for py in range(y + INSET, y + h - INSET):
        for px in range(x + INSET, x + w - INSET):
            if not (0 <= px < image.width and 0 <= py < image.height):
                continue
            pixel = image.getpixel((px, py))
            if pixel[3] < 250:
                continue
            if max(pixel[:3]) - min(pixel[:3]) < SATURATION_FLOOR:
                continue
            hist[pixel[:3]] += 1
    area = max((w - 2 * INSET) * (h - 2 * INSET), 1)
    if not hist:
        return (0, 0, 0), 0, area
    colour, count = hist.most_common(1)[0]
    return colour, count, area


@pytest.fixture(scope="module")
def captures(tmp_path_factory) -> pathlib.Path:
    if not HAS_RENDER_DEVICE:
        pytest.skip(
            "El tinte de mascara solo existe bajo RHI, y RHI necesita un dispositivo de "
            "render (/dev/dri/renderD*). Se salta explicitamente; NUNCA se aprueba por "
            "salida vacia: donde hay GPU este gate exige returncode 0, las 11 instancias "
            "de icono y graphics_api != Software."
        )
    dest = tmp_path_factory.mktemp("previews")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    run = subprocess.run(
        ["bash", str(SCRIPT), str(dest), "es", str(SCALE)],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )
    assert run.returncode == 0, f"capture_previews.sh salio {run.returncode}: {run.stderr}"
    return dest


@pytest.mark.parametrize("stem", sorted(SURFACES))
def test_the_render_is_the_one_we_think_it_is(captures: pathlib.Path, stem: str) -> None:
    """falsified_by: 2026-09-09. Con AIQ_CAPTURE_PLATFORM=offscreen el propio script
    aborta en scripts/assert_render_is_rhi.py y este test no llega a correr; con la
    guarda desactivada, graphics_api vale "Software" y la asercion reprueba.
    """
    report = json.loads((captures / f"{stem}.json").read_text(encoding="utf-8"))
    assert report["graphics_api"] != "Software", report
    assert report["platform"] != "offscreen", report
    assert report["dpr"] == pytest.approx(SCALE), report
    assert report["overflow"] == [], report
    assert len(report["icons"]) == SURFACES[stem], report


@pytest.mark.parametrize("stem", sorted(SURFACES))
def test_no_masked_logo_renders_as_pure_black_or_white(
    captures: pathlib.Path, stem: str
) -> None:
    """La firma del defecto, medida sobre la imagen completa.

    falsified_by: 2026-09-09. Sobre las imagenes publicadas el 8 de septiembre
    (activos/3cucharadas/assets/images/ai-quota-hud/), renderizadas con el backend
    software, y contados con el mismo umbral de alfa que usa este test (>250):
    bar.png tenia 1452 pixeles opacos exactamente #000000 y 299 #ffffff;
    popup-hidpi.png, 2597 y 6, igual que su gemelo en ingles. Tras el arreglo, cero
    de cada uno en las seis imagenes
    (tres superficies x dos idiomas). Los dos tooltip nunca tuvieron el defecto --su
    unico icono es gemini, declarado mask: false-- asi que ese par no lo demuestra.
    Lo justifica test_the_palette_declares_no_pure_
    black_or_white: si la paleta no los nombra, su aparicion solo puede venir de una
    mascara sin tenir.
    """
    from PIL import Image

    image = Image.open(captures / f"{stem}.png").convert("RGBA")
    pixels = list(image.get_flattened_data())
    black = sum(1 for p in pixels if p[3] > 250 and p[:3] == (0, 0, 0))
    white = sum(1 for p in pixels if p[3] > 250 and p[:3] == (255, 255, 255))
    assert black == 0, f"{stem}.png: {black} pixeles opacos negro puro"
    assert white == 0, f"{stem}.png: {white} pixeles opacos blanco puro"


@pytest.mark.parametrize("stem", sorted(SURFACES))
def test_every_logo_is_tinted_with_its_own_provider_accent(
    captures: pathlib.Path, stem: str
) -> None:
    """falsified_by: 2026-09-09. Medido sobre el bar.png publicado (backend software):
    claude 0 pixeles saturados en el recuadro y 184 negros; codex 0 saturados y 209
    blancos; copilot 0 y 224; deepseek 0 y 649. Los cuatro reprueban por cobertura y
    por color. gemini pasaba tambien entonces --es mask: false-- y ese verde es lo que
    prueba que el criterio puede pasar, o sea que los cuatro rojos no eran un artefacto.
    """
    from PIL import Image

    accents = _accents()
    report = json.loads((captures / f"{stem}.json").read_text(encoding="utf-8"))
    image = Image.open(captures / f"{stem}.png").convert("RGBA")

    for icon in report["icons"]:
        provider = icon["provider"]
        colour, count, area = _dominant_saturated(image, icon["rect_px"])
        expected = GEMINI_ICON_RGB if provider == "gemini" else accents[provider]
        drift = max(abs(a - b) for a, b in zip(colour, expected))
        assert drift <= CHANNEL_TOLERANCE, (
            f"{stem}/{provider}: dominante #{colour[0]:02x}{colour[1]:02x}{colour[2]:02x}, "
            f"esperado #{expected[0]:02x}{expected[1]:02x}{expected[2]:02x}"
        )
        assert count >= COVERAGE_FLOOR * area, (
            f"{stem}/{provider}: solo {count} de {area} px ({100 * count / area:.1f}%) "
            f"llevan el color dominante; minimo {100 * COVERAGE_FLOOR:.0f}%"
        )
        if provider == "gemini":
            # Control negativo: gemini conserva su azul propio y NO toma el acento.
            # Si ambos casaran, la medicion estaria mirando el anillo, no el logotipo.
            drift_accent = max(
                abs(a - b) for a, b in zip(colour, accents["gemini"])
            )
            assert drift_accent > CHANNEL_TOLERANCE, (
                "gemini casa con su acento y con su icono a la vez: el recuadro "
                "esta midiendo el anillo, no el logotipo"
            )


def test_the_capture_script_renders_with_rhi() -> None:
    """No necesita GPU: lee el script. Es la mitad estatica del gate.

    falsified_by: 2026-09-09. Contra la version en 74bd40a
    (git show 74bd40a:scripts/capture_previews.sh) las tres aserciones reprueban:
    tenia QT_QUICK_BACKEND=software, no tenia guarda de dispositivo de render y
    descartaba el JSON de la sonda con >/dev/null, asi que nadie podia comprobar
    con que se habia renderizado.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert "QT_QUICK_BACKEND=software" not in text
    assert "/dev/dri/renderD" in text
    assert "assert_render_is_rhi.py" in text


def test_the_palette_declares_no_pure_black_or_white() -> None:
    """Justifica el criterio de la firma del defecto.

    falsified_by: 2026-09-09. Anadir accent: "#000000" a cualquier proveedor pone rojo
    este test, y entonces el de la firma del defecto deja de ser concluyente: los dos
    fallan juntos y el mensaje dice que hay que decidir cual de los dos cambia.
    """
    text = PALETTE.read_text(encoding="utf-8").lower()
    assert "#000000" not in text
    assert "#ffffff" not in text
