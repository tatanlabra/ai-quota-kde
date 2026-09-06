from __future__ import annotations

import json

from ai_quota_monitor import collector
from ai_quota_monitor.collector import merge_preserving
from ai_quota_monitor.providers import gemini
from ai_quota_monitor.schema import Provider, ProviderWindow, StatusReport


# Payload real de `agy -p "/usage" --output-format json`, medido el 2026-08-17.
# remaining_fraction es la fracción RESTANTE (no la usada) y reset_time es RFC3339
# absoluto en UTC. Los dos grupos renuevan en fechas distintas: eso es justamente
# lo que hace que un solo número por proveedor sea inservible.
USAGE_MEDIDO = {
    "status": "SUCCESS",
    "usage": {"total_tokens": 0},
    "command": {
        "name": "usage",
        "data": {
            "groups": [
                {
                    "name": "Gemini Models",
                    "buckets": [
                        {
                            "id": "gemini-weekly",
                            "name": "Weekly Limit Remaining",
                            "window": "weekly",
                            "remaining_fraction": 0.0,
                            "reset_time": "2026-08-23T13:56:21Z",
                            "description": "You have hit your weekly limit.",
                        }
                    ],
                },
                {
                    "name": "Claude and GPT models",
                    "buckets": [
                        {
                            "id": "3p-weekly",
                            "name": "Weekly Limit Remaining",
                            "window": "weekly",
                            "remaining_fraction": 0.9067,
                            "reset_time": "2026-08-21T01:08:08Z",
                            "description": "You have used some of your weekly limit.",
                        }
                    ],
                },
            ]
        },
    },
}


def _win(provider: Provider, window_id: str) -> ProviderWindow | None:
    return next((w for w in provider.windows if w.id == window_id), None)


def _collect_online(monkeypatch, usage: dict | None) -> Provider:
    """Recolecta con la red permitida, sin helper local ni subprocess real."""
    monkeypatch.setattr(gemini, "_run_agy_usage", lambda: usage)
    monkeypatch.setattr(
        gemini,
        "_run_helper",
        lambda: {
            "agy_requests": 0,
            "cli_requests": 0,
            "agy_observed": True,
            "cli_observed": True,
            "agy_sources": 1,
            "cli_sources": 1,
        },
    )
    return gemini.collect({}, allow_network=True)


# ── 1. La inversión, con los dos valores reales medidos ───────────────────────

def test_remaining_fraction_se_invierte_a_usado(monkeypatch):
    """agy da lo RESTANTE; `percent` del esquema es lo USADO.

    Sin invertir, el grupo agotado (0.0 restante) se pintaría como intacto: es el modo
    de fallo más caro posible, porque el widget diría "hay cuota" justo cuando no hay.
    """
    provider = _collect_online(monkeypatch, USAGE_MEDIDO)

    agotada = _win(provider, "antigravity_gemini_weekly")
    holgada = _win(provider, "antigravity_claude_gpt_weekly")

    # gemini-weekly: 0.0 restante -> 100% usado
    assert agotada.percent == 1.0
    assert agotada.used == 100.0
    # 3p-weekly: 0.9067 restante -> 9.33% usado
    assert holgada.percent == 1.0 - 0.9067
    assert holgada.used == 9.33
    assert holgada.limit == 100.0

    # Y el consumidor que reconstruye "libre" recupera el valor original de agy.
    assert round(1.0 - agotada.percent, 4) == 0.0
    assert round(1.0 - holgada.percent, 4) == 0.9067


def test_fraccion_fuera_de_rango_se_recorta_sin_reventar(monkeypatch):
    payload = json.loads(json.dumps(USAGE_MEDIDO))
    payload["command"]["data"]["groups"][0]["buckets"][0]["remaining_fraction"] = 1.0000001
    payload["command"]["data"]["groups"][1]["buckets"][0]["remaining_fraction"] = -0.2

    provider = _collect_online(monkeypatch, payload)
    assert _win(provider, "antigravity_gemini_weekly").percent == 0.0
    assert _win(provider, "antigravity_claude_gpt_weekly").percent == 1.0


# ── 2. metric_kind debe ser cuota, nunca actividad ───────────────────────────

def test_ventanas_nuevas_son_quota_y_no_actividad(monkeypatch):
    """metric_kind="activity" haría que collector no preserve el valor tras un fallo."""
    provider = _collect_online(monkeypatch, USAGE_MEDIDO)

    for window_id in ("antigravity_gemini_weekly", "antigravity_claude_gpt_weekly"):
        win = _win(provider, window_id)
        assert win is not None, window_id
        assert win.metric_kind == "quota"
        assert win.renewal_kind == "rolling"
        assert win.cycle_days == 7
        assert win.confidence == "official"
        assert win.source == "agy /usage"

    # Incluso el placeholder de fallo tiene que declararse como cuota, o el merge
    # lo dejaría pasar sin preservar el valor previo.
    degradado = gemini.collect({}, allow_network=False)
    for window_id in ("antigravity_gemini_weekly", "antigravity_claude_gpt_weekly"):
        win = _win(degradado, window_id)
        assert win.metric_kind == "quota"
        assert win.confidence == "unknown"
        assert win.source == "unavailable"
        assert win.percent is None


def test_las_etiquetas_distinguen_el_claude_de_antigravity(monkeypatch):
    """3p-weekly ES Claude, pero facturado por Google: otra ventana que la de Claude.

    Si ambas se llamaran igual, el tablero mostraría dos "Claude semanal" con números
    y relojes distintos y nadie sabría cuál mira.
    """
    provider = _collect_online(monkeypatch, USAGE_MEDIDO)
    tercero = _win(provider, "antigravity_claude_gpt_weekly")

    assert "Antigravity" in tercero.label
    assert "Claude" in tercero.label
    assert tercero.label != "Weekly (7d)"          # la etiqueta de la cuota directa
    assert tercero.id != "weekly"


# ── 3. Un fetch fallido preserva el valor anterior ───────────────────────────

def test_fetch_fallido_preserva_la_cuota_en_vez_de_ponerla_en_cero(monkeypatch):
    bueno = _collect_online(monkeypatch, USAGE_MEDIDO)
    # Segundo ciclo del timer: la red falla y `agy /usage` no devuelve nada.
    caido = _collect_online(monkeypatch, None)

    prev = StatusReport(generated_at="2026-08-17T21:00:00-04:00", providers=[bueno])
    fresh = StatusReport(generated_at="2026-08-17T21:05:00-04:00", providers=[caido])

    merged = merge_preserving(prev, fresh)
    preservada = _win(merged.providers[0], "antigravity_claude_gpt_weekly")

    assert preservada.percent == 1.0 - 0.9067        # NO 0.0 ni None
    assert preservada.confidence == "official"
    assert preservada.stale_since == "2026-08-17T21:00:00-04:00"
    assert preservada.reset_at == "2026-08-21T01:08:08Z"


def test_fetch_fallido_no_inventa_cuota_cuando_no_habia_previa(monkeypatch):
    monkeypatch.setattr(gemini, "_run_agy_usage", lambda: None)
    caido = gemini.collect({}, allow_network=True)
    merged = merge_preserving(None, StatusReport(providers=[caido]))
    win = _win(merged.providers[0], "antigravity_gemini_weekly")
    assert win.percent is None and win.limit is None
    assert win.confidence == "unknown"


# ── 4. reset_at llega al caché como RFC3339 absoluto, sin recalcular ─────────

def test_reset_at_se_propaga_literal_hasta_el_json_del_cache(monkeypatch):
    """El reloj no se recalcula desde el "refreshes in N days" de la descripción.

    Ese texto es relativo al instante del fetch y envejece dentro de la caché; el único
    dato estable es reset_time. Los dos grupos tienen relojes distintos, así que además
    hay que comprobar que no se colapsan en uno.
    """
    provider = _collect_online(monkeypatch, USAGE_MEDIDO)
    report = StatusReport(providers=[provider])

    # Round-trip por el mismo serializador que escribe ~/.cache/.../status.json.
    recargado = StatusReport.model_validate_json(report.model_dump_json())
    windows = {w.id: w for w in recargado.providers[0].windows}

    assert windows["antigravity_gemini_weekly"].reset_at == "2026-08-23T13:56:21Z"
    assert windows["antigravity_claude_gpt_weekly"].reset_at == "2026-08-21T01:08:08Z"
    assert (
        windows["antigravity_gemini_weekly"].reset_at
        != windows["antigravity_claude_gpt_weekly"].reset_at
    )


def test_reset_time_no_string_no_se_convierte_en_fecha_inventada(monkeypatch):
    payload = json.loads(json.dumps(USAGE_MEDIDO))
    payload["command"]["data"]["groups"][0]["buckets"][0]["reset_time"] = None
    provider = _collect_online(monkeypatch, payload)
    assert _win(provider, "antigravity_gemini_weekly").reset_at is None
    # y la otra ventana no se contamina
    assert _win(provider, "antigravity_claude_gpt_weekly").reset_at == "2026-08-21T01:08:08Z"


# ── 5. La llamada externa solo ocurre en el camino online ────────────────────

def test_el_modo_offline_no_llama_a_agy(monkeypatch):
    """Este workspace ya se comió un HTTP 429 por recolectar cuota en vivo."""
    llamadas = {"n": 0}

    def contar():
        llamadas["n"] += 1
        return USAGE_MEDIDO

    monkeypatch.setattr(gemini, "_run_agy_usage", contar)
    monkeypatch.setattr(gemini, "_run_helper", lambda: {"error": "jq_not_found"})

    gemini.collect({}, allow_network=False)
    assert llamadas["n"] == 0

    gemini.collect({}, allow_network=True)
    assert llamadas["n"] == 1


def test_collect_all_offline_no_consulta_la_cuota_de_antigravity(monkeypatch):
    llamadas = {"n": 0}
    monkeypatch.setattr(gemini, "_run_agy_usage", lambda: (llamadas.update(n=llamadas["n"] + 1), USAGE_MEDIDO)[1])
    monkeypatch.setattr(gemini, "_run_helper", lambda: {"error": "jq_not_found"})

    cfg = {
        "general": {"prefer_offline": True, "network_enabled": False},
        "providers": {
            "claude": {"enabled": False},
            "codex": {"enabled": False},
            "gemini": {"enabled": True},
            "deepseek": {"enabled": False},
        },
    }
    collector.collect_all(cfg)
    assert llamadas["n"] == 0

    collector.collect_all(cfg, online=True)
    assert llamadas["n"] == 1


def test_helper_local_caido_no_borra_la_cuota_oficial(monkeypatch):
    """Fuentes independientes: que el conteo local falle no invalida un /usage bueno."""
    monkeypatch.setattr(gemini, "_run_agy_usage", lambda: USAGE_MEDIDO)
    monkeypatch.setattr(gemini, "_run_helper", lambda: None)

    provider = gemini.collect({}, allow_network=True)
    assert provider.status == "ok"
    assert provider.error is None
    assert _win(provider, "antigravity_gemini_weekly").confidence == "official"


# ── 6. La dona doble: el orden de los anillos ───────────────────────────────

def test_el_orden_de_anillos_pone_los_modelos_propios_fuera(monkeypatch):
    """DonutGauge ya soporta anillo doble: ids[0]=externo, ids[1]=interno.

    gaugeOrder de main.qml es lo que decide el mapeo, así que el contrato se fija aquí
    en vez de confiar en el orden accidental de las ventanas.
    """
    from pathlib import Path

    main_qml = (
        Path(__file__).resolve().parents[1]
        / "plasmoid/org.tatan.aiquota/contents/ui/main.qml"
    ).read_text(encoding="utf-8")

    inicio = main_qml.index("readonly property var gaugeOrder")
    gauge_order = main_qml[inicio : main_qml.index("]", inicio)]
    externo = gauge_order.index('"antigravity_gemini_weekly"')
    interno = gauge_order.index('"antigravity_claude_gpt_weekly"')
    assert externo < interno, "el anillo externo debe ser el grupo de modelos propios"

    # El componente que los pinta sigue siendo el de doble anillo.
    donut = (
        Path(__file__).resolve().parents[1]
        / "plasmoid/org.tatan.aiquota/contents/ui/components/DonutGauge.qml"
    ).read_text(encoding="utf-8")
    assert "property real outerFraction" in donut
    assert "property real innerFraction" in donut
    assert "gauge.innerFraction, gauge.innerColor" in donut

    # Y el proveedor entrega las dos ventanas con percent, que es la condición que
    # gaugeWindows() exige para dibujar dos anillos en vez de uno.
    provider = _collect_online(monkeypatch, USAGE_MEDIDO)
    con_percent = [
        w.id
        for w in provider.windows
        if w.metric_kind == "quota" and w.percent is not None
    ]
    assert con_percent == ["antigravity_gemini_weekly", "antigravity_claude_gpt_weekly"]
