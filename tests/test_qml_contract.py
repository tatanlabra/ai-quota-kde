"""Contrato de la interfaz del HUD, comprobado por lo que hace y no por como esta escrito.

La version anterior de este fichero comparaba cadenas literales del fuente, con su
indentacion incluida:

    assert compact.count("DonutGauge {") == 5
    assert 'iconIsMask: true\\n            iconMaskColor: "#57ff8d"' in compact

Eso ataba doce tests a la forma del texto. Cuando los cinco bloques copiados pasaron a
ser un Repeater sobre una lista de proveedores --el mismo comportamiento, mejor
escrito-- cuatro se pusieron rojos sin que nada estuviera mal; y ninguno habria visto
el fallo real que si aparecio al ejecutarlo: el singleton llamado `Palette`, eclipsado
por el tipo homonimo de QtQuick.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

from ai_quota_monitor.schema import ProviderWindow

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "plasmoid/org.tatan.aiquota/contents/ui"
UI_FIXTURE = ROOT / "tests/fixtures/sanitized/ui_semantics.json"

PROVIDERS = ("claude", "codex", "gemini", "copilot", "deepseek")


def _fixture() -> dict:
    return json.loads(UI_FIXTURE.read_text(encoding="utf-8"))


def _read(*parts: str) -> str:
    return (UI.joinpath(*parts)).read_text(encoding="utf-8")


def _halo_segments(reset_at: str, now: str) -> int | None:
    delta = (datetime.fromisoformat(reset_at) - datetime.fromisoformat(now)).total_seconds()
    if delta < 0:
        return None
    return max(0, min(7, math.ceil(delta / 86_400)))


def test_third_white_reset_ring_uses_seven_segments_and_ceiling_days():
    donut = _read("components/DonutGauge.qml")
    main = _read("main.qml")

    assert "property int resetSegmentCount: 7" in donut
    assert "property int resetDaysRemaining: -1" in donut
    assert "property bool showResetRing: true" in donut
    assert "property string resetBadgeText" not in donut
    assert "function resetDaysRemaining(providerKey)" in main
    # DeepSeek solo expone saldo: un reloj de reinicio ahi seria inventado.
    assert 'if (providerKey === "deepseek") return -1' in main
    assert "Math.ceil(delta / (24 * 60 * 60 * 1000))" in main
    assert "Math.max(0, Math.min(7" in main
    assert "if (delta < 0) return -1" in main
    assert "nextQuotaReset(providerKey)" in main


def test_renewal_and_halo_fixtures_cover_today_tomorrow_weekly_and_zero_to_seven():
    fixture = _fixture()
    renewal = {case["id"]: case for case in fixture["renewal_cases"]}
    assert set(renewal) == {"today", "tomorrow", "weekly"}
    assert renewal["today"]["reset_at"].startswith("2026-07-19")
    assert renewal["tomorrow"]["reset_at"].startswith("2026-07-20")
    assert renewal["weekly"]["reset_at"].startswith("2026-07-22")

    actual = {
        case["expected_segments"]: _halo_segments(case["reset_at"], fixture["now"])
        for case in fixture["halo_cases"]
    }
    assert actual == {days: days for days in range(8)}


def test_activity_and_balance_fixture_cannot_claim_quota_or_renewal():
    fixture = _fixture()
    windows = {item["id"]: ProviderWindow.model_validate(item) for item in fixture["semantic_windows"]}
    agy = windows["antigravity_activity"]
    gemini = windows["gemini_cli_activity"]
    deepseek = windows["balance"]

    assert agy.metric_kind == gemini.metric_kind == "activity"
    assert agy.percent is gemini.percent is None
    assert agy.renewal_kind == gemini.renewal_kind == "calendar_cutoff"
    assert deepseek.metric_kind == "balance"
    assert deepseek.percent is None
    assert deepseek.renewal_kind == "none"


def test_custom_tooltip_reuses_metric_line_and_keeps_accessible_text():
    """El tooltip y el popup comparten MetricLine, para que no comuniquen fechas distintas."""
    main = _read("main.qml")
    assert "toolTipItem: QuotaTooltip" in main
    assert "toolTipSubText: root.accessibleSummary()" in main
    # Una sola instanciacion en cada superficie: el resto lo pone el Repeater.
    assert _read("components/QuotaTooltip.qml").count("MetricLine {") == 1
    assert _read("FullRepresentation.qml").count("MetricLine {") == 1


def test_the_five_providers_are_data_and_the_views_repeat_over_them():
    """Las tres superficies recorren la misma lista, en vez de repetir cinco bloques.

    falsified_by: 2026-09-06. Sobre v0.2.0-hud-pre-refactor no existe `providerOrder`
    y cada vista lleva sus cinco copias escritas a mano; anadir un proveedor obligaba
    a tocar tres ficheros y a mantener sincronizados quince literales de color.
    """
    main = _read("main.qml")
    order = re.search(r"readonly property var providerOrder: \[(.*?)\]", main, re.S)
    assert order is not None
    listed = re.findall(r'"([a-z]+)"', order.group(1))
    assert tuple(listed) == PROVIDERS

    # Cada vista recorre la lista visible, no una copia propia.
    for surface in ("CompactRepresentation.qml", "FullRepresentation.qml",
                    "components/QuotaTooltip.qml"):
        text = _read(*surface.split("/"))
        assert "Repeater {" in text, surface
        assert "visibleProviders" in text or "compact.shown" in text, surface

    # La rejilla se reparte por el ancho disponible en vez de fijar un numero de
    # columnas: con cinco proveedores y tres columnas fijas, la segunda fila quedaba
    # fuera del popup y solo se veian las tres primeras donas.
    full = _read("FullRepresentation.qml")
    assert "columns: 3" not in full
    # El reparto y los límites geométricos se ejercen en test_qml_layout_runtime.
    # Y el contenido va en un ScrollView, para que encogerlo no esconda nada.
    assert "PlasmaComponents.ScrollView" in full


def test_every_provider_has_a_complete_identity_in_one_place():
    """Color, logo y glifo de cada proveedor viven juntos, no repartidos por seis ficheros.

    falsified_by: 2026-09-06. Antes, `providerAccent`, `providerInnerColor`,
    `providerIconSource`, `providerIconIsMask`, `providerIconColor` y `providerGlyph`
    eran seis `switch` paralelos en main.qml, y los mismos valores aparecian otra vez
    escritos a mano en CompactRepresentation y en FullRepresentation. Bastaba cambiar
    uno para que las tres superficies dejaran de coincidir, y de hecho el comentario
    "Claude - azul neon" seguia sobre un naranja.
    """
    palette = _read("components/HudPalette.qml")
    entry = re.compile(
        r'"(?P<key>[a-z]+)":\s*\{[^}]*accent:\s*"(?P<accent>#[0-9a-fA-F]{6})"'
        r'[^}]*deep:\s*"(?P<deep>#[0-9a-fA-F]{6})"'
        r'[^}]*glyph:\s*"(?P<glyph>[^"\n]+)"'
    )
    found = {m.group("key"): m.groupdict() for m in entry.finditer(palette)}
    assert set(found) == set(PROVIDERS), set(found) ^ set(PROVIDERS)
    # Cada acento es distinto: dos proveedores del mismo color no se distinguen de un vistazo.
    accents = [v["accent"] for v in found.values()]
    assert len(set(accents)) == len(accents)
    assert found["claude"]["accent"] == "#ff7518"
    assert found["codex"]["accent"] == "#57ff8d"

    # Copilot is an SVG, not a font-dependent warning glyph.
    copilot = re.search(r'"copilot":\s*\{([^}]+)', palette).group(1)
    assert 'icon: "copilot.svg"' in copilot
    assert '\\uf06a' not in copilot
    assert (ROOT / "plasmoid/org.tatan.aiquota/contents/icons/copilot.svg").is_file()


def test_optional_center_glyph_color_uses_a_valid_qml_sentinel():
    """Regression for Plasma's observed component-load failure on 2026-08-29.

    Una cadena vacia no es un `color` QML valido y aborta el componente al cargar. El
    centinela ha de ser `null` sobre una propiedad `var`, y quien lo consuma tiene que
    compararlo contra `null`, no contra "".
    """
    donut = _read("components/DonutGauge.qml")
    assert "property var centerGlyphColor: null" in donut
    assert 'property color centerGlyphColor: ""' not in donut
    assert "gauge.centerGlyphColor !== null ? gauge.centerGlyphColor" in donut

    # Y la fuente del valor no puede devolver "" para los proveedores sin tinte.
    palette = _read("components/HudPalette.qml")
    assert "glyphColor: null" in palette
    assert 'glyphColor: ""' not in palette
    assert "function glyphColorOf(key)" in palette


def test_calendar_and_antigravity_resets_have_an_honest_countdown():
    """Un reinicio de calendario y uno rodante no se cuentan igual, y se dicen distinto.

    Las cadenas pasaron por i18n al traducir el widget: se comprueban los msgid en
    ingles, que es la fuente, y no el texto que ve quien lo usa, que depende del
    catalogo. La distincion que importa sigue siendo la misma: «observed reset» solo
    para una cuota con corte de calendario, «local cutoff» para lo demas.
    """
    main = _read("main.qml")
    assert "function nextQuotaReset(providerKey)" in main
    assert "function nextQuotaResetSummary(providerKey)" in main
    assert '"observed reset %1 · %2"' in main
    assert '"local cutoff %1 · %2"' in main
    assert '"renews %1 · %2"' in main
    # La cuenta atras cambia de unidad al pasar de un dia.
    assert '"in %1h %2m"' in main and '"in %1d %2h"' in main


def test_unknown_measurements_are_not_rendered_as_false_zeroes():
    main = _read("main.qml")
    helper = (ROOT / "scripts/helper_gemini_usage.sh").read_text(encoding="utf-8")

    assert 'if (win.confidence === "unknown") return i18n("no data")' in main
    assert "function hasUsableDetailData(providerKey)" in main
    assert "antigravity-cli" in helper
    assert '"agy_observed"' in helper and '"cli_observed"' in helper


def test_health_thresholds_are_configurable_and_amber_can_never_hide_red():
    """Los umbrales estaban fijos dentro del calculo del color y no habia forma de moverlos.

    falsified_by: 2026-09-06. Sobre v0.2.0-hud-pre-refactor, `_healthColor` compara
    contra 0.10 y 0.30 escritos en el cuerpo de la funcion, y el paquete no tiene
    siquiera un directorio `config/`: el dialogo de configuracion de Plasma aparecia
    vacio.
    """
    donut = _read("components/DonutGauge.qml")
    assert "property real amberThreshold: 0.30" in donut
    assert "property real redThreshold: 0.10" in donut
    assert "gauge.redThreshold" in donut and "gauge.amberThreshold" in donut

    kcfg = (ROOT / "plasmoid/org.tatan.aiquota/contents/config/main.xml").read_text(encoding="utf-8")
    declared = set(re.findall(r'<entry name="([^"]+)"', kcfg))
    assert {"amberThreshold", "redThreshold", "compactMode", "showResetRing"} <= declared

    # Cada clave declarada tiene que leerse en el QML y exponerse en el dialogo.
    main = _read("main.qml")
    compact = _read("CompactRepresentation.qml")
    form = _read("ConfigGeneral.qml")
    for key in declared:
        assert f"cfg_{key}" in form, key
        assert key in main or key in compact, key

    # El rojo no puede quedar por encima del ambar, o el ambar no se veria nunca.
    assert "to: Math.max(1, amberSpin.value - 1)" in form
