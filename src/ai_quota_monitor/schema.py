from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Confidence = Literal["official", "local_observed", "configured_estimate", "unknown"]


class ProviderWindow(BaseModel):
    id: str
    label: str
    used: float
    limit: float | None = None
    unit: str  # tokens | usd_estimated | requests
    percent: float | None = None  # 0.0-1.0; None = no limit configured
    reset_at: str | None = None
    confidence: Confidence = "unknown"
    source: str = "unknown"
    note: str = ""
    # Si este valor proviene de una caché preservada (el fetch fresco falló),
    # guarda el generated_at del reporte previo. None = dato fresco de esta corrida.
    stale_since: str | None = None


class Provider(BaseModel):
    id: str
    label: str
    status: Literal["ok", "error", "degraded"] = "ok"
    windows: list[ProviderWindow] = Field(default_factory=list)
    error: str | None = None
    # Ventanas canónicas que el upstream, respondiendo OK, declara inexistentes para
    # este plan (p.ej. Codex 'prolite' ya no tiene ventana de 5h). No son un fallo
    # transitorio: dejaron de existir, así que el merge NO debe preservarlas.
    absent_windows: list[str] = Field(default_factory=list)


class StatusReport(BaseModel):
    schema_version: str = "0.1.0"
    generated_at: str = Field(default_factory=lambda: datetime.now().astimezone().isoformat())
    network_used: bool = False
    providers: list[Provider] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
