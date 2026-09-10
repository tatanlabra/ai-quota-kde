#!/usr/bin/env python3
"""Rechaza una captura que no salio por RHI, o a la escala equivocada, o con desborde.

Existe porque el fallo que dejo cuatro logotipos negros en el blog era INVISIBLE:
la sonda salia 0, los 93 tests seguian verdes y el PNG parecia bien salvo que se
mirara el color de un pixel. Un render por software no es un aviso, es un
artefacto que no se puede publicar; de ahi que aborte en vez de advertir.
"""

import json
import sys


def main() -> int:
    report = json.load(open(sys.argv[1], encoding="utf-8"))
    scale = float(sys.argv[2])

    if report["graphics_api"] == "Software" or report["platform"] == "offscreen":
        print(
            f"ERROR: render por {report['platform']}/{report['graphics_api']}: los "
            "logotipos enmascarados saldrian negros. No se publica.",
            file=sys.stderr,
        )
        return 1
    if abs(report["dpr"] - scale) > 1e-6:
        print(
            f"ERROR: dpr {report['dpr']} != escala pedida {scale}",
            file=sys.stderr,
        )
        return 1
    if report["overflow"]:
        print(
            f"ERROR: desborde de texto a esta escala: {report['overflow']}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
