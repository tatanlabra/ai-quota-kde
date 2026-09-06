# HUD visual and interaction validation

## Follow-up to visual feedback

The geometry-only correction below did not resolve five visual problems reported
on the installed widget. This iteration changes the panel as well as its previews.

| Reported problem | Result |
|---|---|
| Copilot showed an exclamation mark | Bundled official Octicons SVG and its MIT licence |
| Claude logo crossed the inner ring | All icon corners fit inside the calculated ring aperture |
| Tooltip was too small | One hovered provider, larger metric fonts and a wider preview |
| Popup was crowded and hid providers | Five pinned selectors; complete selected details in a scroll area |
| Panel donuts had not improved | Shared gauge geometry, thinner separated rings, margins, hover and keyboard focus |

Qt runtime tests cover 15 combinations of panel/popup/tooltip, widths, and
100%, 125%, 200% scaling. They check text bounds, native clicks on all five
selectors, nonempty icons contained in the aperture, and metric fonts at least
10 pt with an 11 pt desktop font. The complete suite passed **91 tests**; after
extending the public-path check to README and PO/POT, its **9 tests** passed again.

A temporary negative control replaced aperture-based icon sizing with 72% of the
gauge diameter. All five icons violated the containment assertion. The unmodified
source passes. Temporary copies and synthetic samples never replace the live cache.

The first expanded test run exposed two test problems: a stale assertion requiring
the Copilot warning glyph, and a PySide/QtTest introspection abort. The assertion now
requires the bundled icon; native mouse events exercise the buttons without QtTest.
These failures were test defects, not evidence of visual acceptance.

Native Wayland/RHI captures of panel, tooltip and popup were inspected with the
real QML formatting functions and five-provider sample JSON. Software rendering
alone did not show SVG mask colours faithfully. The preview fixture does not load
the Spanish catalogue; the installed catalogue has **55 translated messages**.

The package was upgraded and Plasma reloaded. Source and installed package are
byte-identical. Plasma is active, the quota timer is active/waiting, and the last
collector run succeeded. An eight-second `plasmawindowed` smoke produced no QML
messages (intentional timeout exit 124). The focused post-reload journal query
found no HUD component messages; it does not certify the whole desktop journal.

Limit: this is author verification, not independent review or proof of visual
perfection on every panel size, font, translation and monitor. Scroll reachability
for arbitrary future provider payloads is not exhaustively tested. API balances,
estimates and unavailable data retain their existing collector semantics.

To undo this iteration, restore the package from `38716a6` in a separate checkout,
compile its translations and reinstall it. No credentials or cache migration is
involved. Do not reset unrelated working-tree changes.

## Earlier geometry-only correction (`38716a6`, superseded)

The popup and tooltip allowed natural text widths to expand their layouts past
available space. The popup now uses equal, responsive columns with a useful
minimum width including column spacing; extra rows remain reachable by scrolling.
Provider names and status/reset summaries wrap inside their column. The tooltip
subtitle has its own row, and shared metric labels yield space to values.

Validation on Qt 6.11.2, using synthetic data only:

| Probe, 125% scale | Before (`1a7c8d5`) | After |
|---|---:|---:|
| Popup, 612 logical px, 84 text nodes | 34 nodes beyond an ancestor's horizontal bounds | 0 |
| Tooltip, 360 logical px, 99 text nodes | 67 nodes beyond an ancestor's horizontal bounds | 0 |

`tests/test_qml_layout_runtime.py` renders the actual QML with Fira Sans 11 and
long synthetic labels at 100%, 125%, and 200%. Twelve cases check text bounds;
an empty view cannot pass. The whole suite passed: **88 tests**. The prior QML
was extracted into a temporary directory for the negative cases; no live package
was perturbed. This is author validation of geometry, not proof of optimal design
or pixel-perfect placement of a Plasma popup on every monitor.

The installed package matched the source byte for byte. Plasma was reloaded and
`plasmawindowed org.tatan.aiquota` ran without output/errors for eight seconds,
then was stopped by the deliberate smoke timeout (exit 124). The desktop journal
also contained unrelated Panel Colorizer/rendering warnings; it was not globally
clean. Screenshots from the geometry fixture were inspected locally.

The translation builder now extracts relative source references. Its regression
was observed red with the previous absolute references, then green after repair.
All 60 Spanish translations remain compiled and complete.

Reproduce the suite with `PYTHONPATH=src python -m pytest -q`; the native geometry
cases need PySide6 and the Plasma/Kirigami QML modules. Without PySide6 they are
explicitly skipped. To revert the layout, restore the three changed view files
from `1a7c8d5`, rebuild the catalogue and reinstall the package; backend/cache
and user configuration were not modified by this correction.
