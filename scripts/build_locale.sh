#!/usr/bin/env bash
# Extrae las cadenas del QML y compila el catalogo español.
#
# El dominio es plasma_applet_<KPlugin.Id> y el .mo va en contents/locale/<lang>/,
# que es donde KPackage lo busca. Precedente instalado en esta maquina:
# /usr/share/plasma/plasmoids/luisbocanegra.panel.colorizer/contents/locale/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$ROOT/plasmoid/org.tatan.aiquota"
DOMAIN="plasma_applet_org.tatan.aiquota"
POT="$ROOT/po/$DOMAIN.pot"

# Relative source references remain useful in any checkout or source archive.
cd "$ROOT"
mapfile -t SOURCES < <(find plasmoid/org.tatan.aiquota/contents -name '*.qml' | sort)

xgettext --from-code=UTF-8 --language=JavaScript \
    --keyword=i18n --keyword=i18nc:1c,2 --keyword=i18np:1,2 --keyword=i18ncp:1c,2,3 \
    --package-name="AI Quota HUD" --copyright-holder="tatan" \
    --add-comments --sort-by-file \
    -o "$POT" "${SOURCES[@]}"

for lang in es; do
    po="$ROOT/po/$lang.po"
    if [[ -f "$po" ]]; then
        msgmerge --quiet --update --backup=none "$po" "$POT"
    else
        msginit --no-translator --locale="$lang" --input="$POT" --output="$po"
    fi
    dest="$PKG/contents/locale/$lang/LC_MESSAGES"
    mkdir -p "$dest"
    msgfmt --check --output-file="$dest/$DOMAIN.mo" "$po"
done

echo "catalogo compilado: $(msgfmt --statistics --output-file=/dev/null "$ROOT/po/es.po" 2>&1)"
