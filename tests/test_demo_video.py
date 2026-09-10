"""El guion del video, y que el render sea reproducible.

Un video de demostracion tiene dos formas de mentir sin que nadie lo note: quedarse
congelado en un plano (y parecer que el widget no reacciona) o cambiar entre corridas
(y entonces no se puede regenerar identico, que es justo lo que el post promete). Estos
criterios cubren las dos.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests/qml/layout_probe.py"
UI = ROOT / "plasmoid/org.tatan.aiquota/contents/ui"
sys.path.insert(0, str(ROOT / "tests/qml"))

import demo_storyboard as sb  # noqa: E402

HAS_RENDER_DEVICE = (
    bool(list(pathlib.Path("/dev/dri").glob("renderD*")))
    if pathlib.Path("/dev/dri").exists()
    else False
)

# Muestra para el gate de determinismo: cuatro fotogramas que cubren los tres planos
# --reposo, visor y popup-- mas el ultimo, que es el que cierra el bucle. Renderizar los
# 486 dos veces costaria minutos sin anadir cobertura: el bucle es el mismo codigo.
SAMPLE = (0, 100, 380, sb.total_frames() - 1)


def test_the_storyboard_adds_up_to_what_it_claims() -> None:
    """falsified_by: 2026-09-09. Cambiar los frames de cualquier plano rompe la suma y
    la duracion; se vio al recortar el aire muerto inicial de 45 a 30 fotogramas, que
    bajo el total de 510 a 486.
    """
    assert sb.total_frames() == sum(shot.frames for shot in sb.SHOTS)
    assert sb.total_frames() == 486
    assert abs(sb.total_frames() / sb.FPS - 16.2) < 0.01


def test_the_loop_closes_on_the_same_state() -> None:
    """El primer y el ultimo fotograma tienen que ser el mismo estado.

    Con `autoplay loop` el salto ocurre en cada vuelta; si los dos extremos difieren, se
    ve un tiron. falsified_by: 2026-09-09. Poner layer="popup" en el plano rest-close
    deja popup_opacity en 1.0 en el ultimo fotograma y esto reprueba.
    """
    first = sb.state_at(0)
    last = sb.state_at(sb.total_frames() - 1)
    for field in ("hover", "select", "tooltip_opacity", "popup_opacity", "tooltip_lift", "popup_lift"):
        assert getattr(first, field) == getattr(last, field), field


def test_every_click_lands_on_the_first_frame_of_its_shot_with_the_popup_open() -> None:
    """Un clic sobre un selector invisible no demuestra nada.

    falsified_by: 2026-09-09. Mover un plano select-* a layer="tooltip" deja
    popup_opacity en 0 y esto reprueba; repetir el clic en varios fotogramas del plano
    tambien, porque el guion solo lo emite en el primero.
    """
    clicks = [sb.state_at(i) for i in range(sb.total_frames()) if sb.state_at(i).click]
    assert len(clicks) == 3, [c.shot for c in clicks]
    for state in clicks:
        assert state.popup_opacity > 0.99, state
        assert state.shot.startswith("select-"), state
    assert [c.click for c in clicks] == ["select-codex", "select-gemini", "select-deepseek"]


# El criterio va en SEGUNDOS y no en fotogramas: lo que decide si un video parece roto
# es cuanto tiempo lleva sin cambiar, no cuantos fotogramas caben en ese tiempo. 3,5 s
# es el limite: por debajo se lee como tiempo de lectura de un plano, por encima como
# congelado. Medido el 2026-09-09: la carrera mas larga es de 92 fotogramas (3,07 s) y
# la produce select-gemini + popup-hold-gemini, porque el clic no cambia el estado
# visual --Gemini ya estaba seleccionado-- y los dos planos se leen como uno. Es el
# plano de Antigravity con sus dos cuotas semanales, o sea la tesis del post, y merece
# ser el mas largo: son cuatro lineas de metrica que hay que poder leer.
MAX_FROZEN_SECONDS = 3.5
MIN_DISTINCT_STATES = 12
# Umbrales del gate de determinismo, con los dos extremos medidos el 2026-09-09:
# mismo instante congelado -> 1 nivel de desviacion y 0,03 % de pixeles distintos;
# instantes separados 60 s -> 179 niveles y 0,45 %. El limite va en medio y mucho mas
# cerca del suelo, porque lo que hay que cazar es el reloj colandose, no el antialias.
MAX_CHANNEL_DEVIATION = 2
MAX_DIFFERING_FRACTION = 0.002


def test_the_sequence_is_never_frozen_for_too_long() -> None:
    """Los planos de espera SON el contenido --hacen falta para leer-- pero un video que
    no cambia durante varios segundos parece roto.

    falsified_by: 2026-09-09. Subir popup-hold-gemini de 82 a 200 fotogramas lleva la
    carrera a 210 fotogramas (7,0 s) y esto reprueba. Y con el umbral anterior de 90
    FOTOGRAMAS reprobaba el guion real por 2 fotogramas, que es lo que delato que el
    criterio estaba escrito en la unidad equivocada.
    """
    states = [sb.state_at(i) for i in range(sb.total_frames())]
    keys = [
        (s.hover, s.select, round(s.tooltip_opacity, 3), round(s.popup_opacity, 3),
         round(s.tooltip_lift, 3), round(s.popup_lift, 3))
        for s in states
    ]
    run = best = 1
    for a, b in zip(keys, keys[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    seconds = best / sb.FPS
    assert seconds <= MAX_FROZEN_SECONDS, (
        f"{best} fotogramas seguidos sin cambio de estado ({seconds:.2f} s), "
        f"maximo {MAX_FROZEN_SECONDS} s"
    )
    assert len(set(keys)) >= MIN_DISTINCT_STATES, f"solo {len(set(keys))} estados distintos"


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 no instalado")
@pytest.mark.skipif(
    not HAS_RENDER_DEVICE,
    reason=(
        "El escenario se renderiza por RHI, que necesita /dev/dri/renderD*. Se salta "
        "explicitamente; donde hay GPU exige returncode 0 y hashes iguales entre corridas."
    ),
)
def test_the_render_is_deterministic(tmp_path: pathlib.Path) -> None:
    """Dos corridas tienen que dar la misma imagen.

    NO se exige igualdad byte a byte, y no es una concesion: el rasterizador de glifos
    no es bit-exacto entre procesos. Medido el 2026-09-09 con el mismo instante
    congelado: hasta 507 pixeles distintos (0,03 % de la imagen) y **1 nivel** de
    desviacion maxima por canal, todos en zonas de texto. Exigir bytes iguales daria un
    gate rojo por algo que no es un defecto.

    Lo que si discrimina es la desviacion maxima. falsified_by: 2026-09-09, midiendo el
    mismo guion con el reloj congelado en dos instantes separados 60 s: la desviacion
    maxima salta de **1 a 179** niveles y los pixeles distintos de 507 a 7713. Ese
    factor 89 es lo que separa "misma escena renderizada dos veces" de "se colo el
    reloj del sistema", que es el defecto real: sin --frozen-now, dos renders del video
    a distinta hora muestran cuentas atras distintas y no se puede regenerar.
    """
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "QT_QPA_PLATFORM": "eglfs",
            "EGL_PLATFORM": "surfaceless",
            "QT_SCALE_FACTOR": str(sb.SCALE),
        }
    )
    runs = []
    for run_index in (1, 2):
        dest = tmp_path / f"run{run_index}"
        run = subprocess.run(
            [
                sys.executable, str(PROBE), str(UI), "stage", str(sb.STAGE_WIDTH),
                "--height", str(sb.STAGE_HEIGHT), "--sample", "--lang", "es",
                "--frozen-now", sb.FROZEN_NOW,
                "--sequence", str(dest),
                "--frames", ",".join(str(n) for n in SAMPLE),
            ],
            capture_output=True, text=True, env=env, timeout=600, check=False,
        )
        assert run.returncode == 0, f"corrida {run_index}: {run.stderr[-800:]}"
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["graphics_api"] != "Software", manifest
        assert manifest["rendered"] == len(SAMPLE), manifest
        for row in manifest["rows"]:
            assert (row["width"], row["height"]) == (
                sb.STAGE_WIDTH * sb.SCALE,
                sb.STAGE_HEIGHT * sb.SCALE,
            ), row
            path = dest / row["name"]
            # El manifiesto declara el sha256 del fichero: se comprueba que no miente,
            # aunque la comparacion entre corridas se haga sobre los pixeles.
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        runs.append(dest)

    from PIL import Image, ImageChops

    def deviation(path_a, path_b):
        a = Image.open(path_a).convert("RGB")
        b = Image.open(path_b).convert("RGB")
        pixels = list(ImageChops.difference(a, b).get_flattened_data())
        differing = sum(1 for p in pixels if p != (0, 0, 0))
        return max(max(p) for p in pixels), differing / len(pixels)

    for index in SAMPLE:
        name = f"frame-{index:04d}.png"
        worst, fraction = deviation(runs[0] / name, runs[1] / name)
        assert worst <= MAX_CHANNEL_DEVIATION, (
            f"{name}: desviacion maxima {worst} niveles entre corridas; el limite es "
            f"{MAX_CHANNEL_DEVIATION} y un reloj que se cuela da 179"
        )
        assert fraction <= MAX_DIFFERING_FRACTION, (
            f"{name}: {100 * fraction:.4f}% de pixeles distintos entre corridas"
        )

    # El cierre del bucle, sobre los pixeles del primer y el ultimo fotograma.
    worst, fraction = deviation(
        runs[0] / f"frame-{SAMPLE[0]:04d}.png",
        runs[0] / f"frame-{SAMPLE[-1]:04d}.png",
    )
    assert worst == 0 and fraction == 0.0, (
        "el bucle no cierra: el primer y el ultimo fotograma no son la misma imagen "
        f"(desviacion {worst}, {100 * fraction:.4f}% de pixeles)"
    )
