"""Ejecuta las funciones JS reales de main.qml contra el esquema del proveedor.

No reimplementa la lógica en Python: extrae del propio main.qml el texto de las funciones
que deciden qué anillo pinta qué ventana y las corre en Node. Una reimplementación probaría
la copia, no el QML que se instala; y el mapeo anillo→ventana es justo lo que se puede
invertir sin que ningún test de Python se entere.

Se omite (skip) si no hay `node` en el sistema.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from ai_quota_monitor.providers import gemini
from ai_quota_monitor.schema import StatusReport
from test_antigravity_quota import USAGE_MEDIDO

ROOT = Path(__file__).resolve().parents[1]
MAIN_QML = ROOT / "plasmoid/org.tatan.aiquota/contents/ui/main.qml"

# Funciones puras de main.qml que deciden el mapeo anillo -> ventana.
FUNCIONES = (
    "getProviderByKey",
    "getWindowByKey",
    "windowOf",
    "metricKind",
    "remainingFraction",
    "gaugeWindows",
    "gaugeOuterFraction",
    "gaugeInnerFraction",
    "gaugeSingleRing",
)


def _extraer_funcion(texto: str, nombre: str) -> str:
    """Recorta `function nombre(...) { ... }` balanceando llaves."""
    inicio = texto.index(f"function {nombre}(")
    i = texto.index("{", inicio)
    profundidad = 0
    for j in range(i, len(texto)):
        if texto[j] == "{":
            profundidad += 1
        elif texto[j] == "}":
            profundidad -= 1
            if profundidad == 0:
                return texto[inicio : j + 1]
    raise AssertionError(f"llaves sin balancear en {nombre}")


def _extraer_lista(texto: str, propiedad: str) -> list[str]:
    inicio = texto.index(f"readonly property var {propiedad}")
    cuerpo = texto[inicio : texto.index("]", inicio)]
    return re.findall(r'"([^"]+)"', cuerpo)


def _shim_js(texto: str) -> str:
    cuerpos = "\n".join(_extraer_funcion(texto, nombre) for nombre in FUNCIONES)
    gauge_order = json.dumps(_extraer_lista(texto, "gaugeOrder"))
    # `root` y `gaugeOrder` son las únicas referencias al contexto QML que usan estas
    # funciones; todo lo demás es JS puro tomado literal del archivo.
    return (
        "import {readFileSync} from 'node:fs';\n"
        "const report = JSON.parse(readFileSync(process.argv[2],'utf8'));\n"
        "const root = { report: report };\n"
        f"const gaugeOrder = {gauge_order};\n"
        f"{cuerpos}\n"
        "const out = {\n"
        "  ids: gaugeWindows('gemini'),\n"
        "  outer: gaugeOuterFraction('gemini'),\n"
        "  inner: gaugeInnerFraction('gemini'),\n"
        "  single: gaugeSingleRing('gemini'),\n"
        "};\n"
        "console.log(JSON.stringify(out));\n"
    )


@pytest.fixture()
def reporte_gemini(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(gemini, "_run_agy_usage", lambda: USAGE_MEDIDO)
    monkeypatch.setattr(
        gemini,
        "_run_helper",
        lambda: {
            "agy_requests": 4,
            "cli_requests": 0,
            "agy_observed": True,
            "cli_observed": False,
            "agy_sources": 1,
            "cli_sources": 0,
        },
    )
    provider = gemini.collect({}, allow_network=True)
    destino = tmp_path / "status.json"
    destino.write_text(StatusReport(providers=[provider]).model_dump_json(), encoding="utf-8")
    return destino


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_el_qml_real_mapea_gemini_afuera_y_los_terceros_adentro(reporte_gemini, tmp_path):
    script = tmp_path / "gauge.mjs"
    script.write_text(_shim_js(MAIN_QML.read_text(encoding="utf-8")), encoding="utf-8")

    proc = subprocess.run(
        ["node", str(script), str(reporte_gemini)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    resultado = json.loads(proc.stdout)

    # Dos anillos, no uno: es la condición que hacía imposible la dona doble antes.
    assert resultado["single"] is False
    assert resultado["ids"] == [
        "antigravity_gemini_weekly",
        "antigravity_claude_gpt_weekly",
    ]

    # Anillo EXTERNO = modelos propios de Google (gemini-weekly), 0.0 libre = agotado.
    assert resultado["outer"] == 0.0
    # Anillo INTERNO = modelos de terceros (3p-weekly), 0.9067 libre.
    assert round(resultado["inner"], 4) == 0.9067

    # Y no al revés: invertir el orden en gaugeOrder tiene que romper este test.
    assert resultado["outer"] != resultado["inner"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_sin_cuota_el_qml_no_dibuja_anillos_falsos(monkeypatch, tmp_path):
    monkeypatch.setattr(gemini, "_run_agy_usage", lambda: None)
    monkeypatch.setattr(gemini, "_run_helper", lambda: {"error": "jq_not_found"})
    provider = gemini.collect({}, allow_network=True)
    reporte = tmp_path / "status.json"
    reporte.write_text(StatusReport(providers=[provider]).model_dump_json(), encoding="utf-8")

    script = tmp_path / "gauge.mjs"
    script.write_text(_shim_js(MAIN_QML.read_text(encoding="utf-8")), encoding="utf-8")
    proc = subprocess.run(
        ["node", str(script), str(reporte)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    resultado = json.loads(proc.stdout)

    # -1 es el contrato de DonutGauge para "sin datos": pista gris, ningún arco.
    assert resultado["ids"] == []
    assert resultado["outer"] == -1
    assert resultado["inner"] == -1
    assert resultado["single"] is True
