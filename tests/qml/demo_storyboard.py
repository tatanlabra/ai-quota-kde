"""El guion del video de demostracion, como dato.

Cada fotograma es funcion PURA de su indice: no hay animaciones en QML, ni timers, ni
reloj del que desincronizarse. Dos corridas del renderizador producen los mismos bytes,
y eso es lo que permite tener un gate de determinismo en vez de mirar el video a ojo.

Solo se interpolan dos cosas, y las calcula Python: la opacidad y el desplazamiento
vertical de las dos capas flotantes. Todo lo demas es corte duro, porque en el widget
real el cambio de proveedor ES instantaneo: interpolarlo seria mentir sobre el producto.
"""

from __future__ import annotations

from dataclasses import dataclass

FPS = 30
STAGE_WIDTH = 736
STAGE_HEIGHT = 576
SCALE = 2                     # -> 1472x1152 px reales, sin reescalado posterior
TOOLTIP_LIFT = 14.0
POPUP_LIFT = 18.0

# Instante congelado del render. Sin el, `sample` deriva sus fechas de datetime.now() y
# main.qml las compara contra Date.now(), asi que dos renders separados por un minuto dan
# imagenes distintas y el video no se puede regenerar identico. Medido el 2026-09-09: con
# el mismo instante congelado dos procesos difieren como maximo 1 nivel por canal; con 60
# segundos de diferencia, 179. Esa es la senal que distingue "misma escena" de "reloj que
# se colo", y el umbral del gate va en medio.
#
# La fecha es la de la revision del post, no una futura: las cuentas atras que se ven en
# el video tienen que ser plausibles para quien lo mire el dia de la publicacion.
FROZEN_NOW = "2026-09-09T23:00:00-03:00"


def smoothstep(u: float) -> float:
    u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
    return u * u * (3.0 - 2.0 * u)


@dataclass(frozen=True)
class Shot:
    name: str
    frames: int
    layer: str                 # "rest" | "tooltip" | "popup"
    hover: str | None          # proveedor bajo el puntero
    select: str | None         # proveedor seleccionado en el popup
    click: str | None          # objectName de un boton a pulsar, solo primer fotograma
    ease: str | None           # None | "tooltip-in" | "popup-in" | "popup-out"


# El orden replica el de las figuras del post y el de la interaccion real:
# barra -> visor al pasar el raton -> vista detallada -> recorrido de selectores.
SHOTS: tuple[Shot, ...] = (
    Shot("rest",                   30, "rest",    None,      None,       None, None),
    Shot("tooltip-in",             12, "tooltip", "claude",  None,       None, "tooltip-in"),
    Shot("tooltip-hold-claude",    54, "tooltip", "claude",  None,       None, None),
    Shot("tooltip-swap",            8, "tooltip", "copilot", None,       None, None),
    Shot("tooltip-hold-copilot",   46, "tooltip", "copilot", None,       None, None),
    Shot("popup-in",               14, "popup",   "copilot", "claude",   None, "popup-in"),
    Shot("popup-hold-claude",      76, "popup",   None,      "claude",   None, None),
    Shot("select-codex",           10, "popup",   None,      "codex",    "select-codex", None),
    Shot("popup-hold-codex",       50, "popup",   None,      "codex",    None, None),
    Shot("select-gemini",          10, "popup",   None,      "gemini",   "select-gemini", None),
    Shot("popup-hold-gemini",      82, "popup",   None,      "gemini",   None, None),
    Shot("select-deepseek",        10, "popup",   None,      "deepseek", "select-deepseek", None),
    Shot("popup-hold-deepseek",    50, "popup",   None,      "deepseek", None, None),
    Shot("popup-out",              14, "popup",   None,      "deepseek", None, "popup-out"),
    Shot("rest-close",             20, "rest",    None,      None,       None, None),
)


@dataclass(frozen=True)
class FrameState:
    index: int
    shot: str
    hover: str | None
    select: str | None
    click: str | None
    tooltip_opacity: float
    tooltip_lift: float
    popup_opacity: float
    popup_lift: float
    ease: str | None


def total_frames() -> int:
    return sum(shot.frames for shot in SHOTS)


def _shot_at(index: int) -> tuple[Shot, int]:
    cursor = 0
    for shot in SHOTS:
        if index < cursor + shot.frames:
            return shot, index - cursor
        cursor += shot.frames
    raise IndexError(f"fotograma {index} fuera de un guion de {total_frames()}")


def state_at(index: int) -> FrameState:
    shot, offset = _shot_at(index)
    progress = (offset + 1) / shot.frames

    tooltip_opacity = 1.0 if shot.layer == "tooltip" else 0.0
    tooltip_lift = 0.0 if shot.layer == "tooltip" else TOOLTIP_LIFT
    popup_opacity = 1.0 if shot.layer == "popup" else 0.0
    popup_lift = 0.0 if shot.layer == "popup" else POPUP_LIFT

    if shot.ease == "tooltip-in":
        eased = smoothstep(progress)
        tooltip_opacity = eased
        tooltip_lift = TOOLTIP_LIFT * (1.0 - eased)
    elif shot.ease == "popup-in":
        eased = smoothstep(progress)
        popup_opacity = eased
        popup_lift = POPUP_LIFT * (1.0 - eased)
        # El tooltip sale a la vez que entra el popup: es el gesto real, primero se
        # posa el puntero y luego se hace clic, no dos acciones sin relacion.
        tooltip_opacity = 1.0 - eased
        tooltip_lift = TOOLTIP_LIFT * eased
    elif shot.ease == "popup-out":
        eased = smoothstep(progress)
        popup_opacity = 1.0 - eased
        popup_lift = POPUP_LIFT * eased

    # NO hay atenuado ni crossfade al cambiar de proveedor, a proposito: en el widget
    # real el cambio es instantaneo, y fingir una transicion seria mentir sobre el
    # producto en la pieza que sirve para ensenarlo.

    return FrameState(
        index=index,
        shot=shot.name,
        hover=shot.hover,
        select=shot.select,
        click=shot.click if offset == 0 else None,
        tooltip_opacity=tooltip_opacity,
        tooltip_lift=tooltip_lift,
        popup_opacity=popup_opacity,
        popup_lift=popup_lift,
        ease=shot.ease,
    )
