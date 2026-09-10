"""El teaser tiene que mostrar el producto real, no una ilustracion parecida.

El teaser anterior era una ilustracion con CUATRO donas, sin Copilot, y con iconos que
no son los del widget: un `</>` donde va el starburst de Claude. Un teaser asi promete
algo que el widget no es, y no hay forma de que un gate de codigo lo note. Estos
criterios lo notan: exigen los cinco acentos y las dos variantes coherentes entre si.

Por defecto mira `build/teaser`, que es donde escribe scripts/render_teaser.sh; se puede
apuntar a otro sitio con TEASER_DIR para verificar lo publicado.
"""

from __future__ import annotations

import collections
import importlib.util
import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PALETTE = ROOT / "plasmoid/org.tatan.aiquota/contents/ui/components/HudPalette.qml"
TEASER_DIR = pathlib.Path(os.environ.get("TEASER_DIR", ROOT / "build/teaser"))
MASTER = TEASER_DIR / "teaser-ai-quota-hud.webp"
MOBILE = TEASER_DIR / "teaser-ai-quota-hud-640.webp"

# Tolerancia por canal. El teaser pasa por WebP con perdida (calidad 86) sobre un fondo
# muy oscuro, asi que un acento puro se desplaza unos pocos niveles. Medido: el maximo
# desplazamiento observado en los cinco acentos es de 3 niveles.
CHANNEL_TOLERANCE = 10
# Cada acento tiene que aparecer en cantidad, no como un pixel perdido de compresion.
MIN_PIXELS_PER_ACCENT = 200

pytestmark = [
    pytest.mark.skipif(importlib.util.find_spec("PIL") is None, reason="Pillow no instalado"),
    pytest.mark.skipif(
        not MASTER.exists(),
        reason=f"no hay teaser en {TEASER_DIR}; generalo con scripts/render_teaser.sh",
    ),
]


def _accents() -> dict[str, tuple[int, int, int]]:
    text = PALETTE.read_text(encoding="utf-8")
    out = {}
    for key, accent in re.findall(r'"(\w+)":\s*\{\s*accent:\s*"#([0-9a-fA-F]{6})"', text):
        out[key] = (int(accent[0:2], 16), int(accent[2:4], 16), int(accent[4:6], 16))
    assert len(out) == 5
    return out


def test_the_two_variants_have_the_legacy_dimensions() -> None:
    """falsified_by: 2026-09-09. Un render a otra escala cambia el tamano y reprueba.
    Los nombres y las medidas son heredados a proposito: el blog tiene
    assets/images/teasers/teaser-ai-quota-hud-640.webp hardcodeado en
    scripts/verify_site_artifact.rb:34, y el tema deriva el sufijo -640 en
    _includes/archive-single.html. Cambiarlos romperia el gate de artefacto y las
    tarjetas sociales ya servidas.
    """
    from PIL import Image

    assert Image.open(MASTER).size == (1280, 720)
    assert Image.open(MOBILE).size == (640, 360)


def test_every_provider_accent_is_present() -> None:
    """falsified_by: 2026-09-09. Contra el teaser anterior
    (git -C ../3cucharadas show HEAD:assets/images/teasers/teaser-ai-quota-hud.webp)
    reprueba con los conteos medidos: claude 0 px cerca de #ff7518, copilot 0 de
    #c084fc, codex 6 de #57ff8d, deepseek 98 de #fff36d; solo gemini llegaba a 1615.
    O sea: la ilustracion no solo le faltaba Copilot, es que ninguno de sus colores era
    el del widget. El teaser nuevo da 1771 / 1922 / 1792 / 2661 / 3239, entre 9 y 16
    veces el umbral. Ningun gate de codigo podia ver esto.
    """
    from PIL import Image

    image = Image.open(MASTER).convert("RGB")
    hist: collections.Counter = collections.Counter(image.get_flattened_data())
    for provider, accent in _accents().items():
        count = sum(
            n
            for colour, n in hist.items()
            if max(abs(a - b) for a, b in zip(colour, accent)) <= CHANNEL_TOLERANCE
        )
        assert count >= MIN_PIXELS_PER_ACCENT, (
            f"{provider}: solo {count} px cerca de "
            f"#{accent[0]:02x}{accent[1]:02x}{accent[2]:02x}; minimo {MIN_PIXELS_PER_ACCENT}"
        )


def test_the_mobile_variant_is_a_reduction_of_the_master() -> None:
    """Las dos variantes no pueden derivar por separado.

    falsified_by: 2026-09-09. Si la de 640 se renderiza aparte en vez de reducirse del
    maestro, la diferencia media supera el umbral. Es el fallo que muestran las marcas
    de tiempo del par teaser-multiagentes-memoria-640 / -gobernada-640x360 del blog,
    regeneradas en momentos distintos.
    """
    from PIL import Image, ImageChops, ImageStat

    reduced = Image.open(MASTER).convert("RGB").resize((640, 360), Image.LANCZOS)
    actual = Image.open(MOBILE).convert("RGB")
    diff = ImageChops.difference(reduced, actual)
    mean = sum(ImageStat.Stat(diff).mean) / 3
    assert mean <= 4.0, f"diferencia media {mean:.2f} niveles frente al maestro reducido"


def test_the_teaser_is_dark_but_not_empty() -> None:
    """Un lienzo negro pasaria los criterios de dimension: este lo descarta.

    falsified_by: 2026-09-09. Un PNG negro de 1280x720 da luminancia media 0,0 y
    reprueba por el minimo; el teaser real mide 0,09.
    """
    from PIL import Image, ImageStat

    grey = Image.open(MASTER).convert("L")
    mean = ImageStat.Stat(grey).mean[0] / 255
    assert 0.03 <= mean <= 0.30, f"luminancia media {mean:.3f} fuera del rango del disenio"


def test_no_alpha_channel_survives() -> None:
    """Una tarjeta social con alfa se compone contra un fondo desconocido.

    falsified_by: 2026-09-09. Quitar `-alpha remove -alpha off` de render_teaser.sh
    deja el modo en RGBA y esto reprueba.
    """
    from PIL import Image

    for path in (MASTER, MOBILE):
        assert Image.open(path).mode == "RGB", f"{path.name} tiene canal alfa"
