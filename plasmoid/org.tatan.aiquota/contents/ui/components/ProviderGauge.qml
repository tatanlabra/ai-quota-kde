pragma ComponentBehavior: Bound

import QtQuick
import "."

// Shared identity and data bindings for panel, tooltip and overview.
DonutGauge {
    id: providerGauge
    required property var pi
    required property string providerKey
    objectName: "gauge-" + providerKey
    label: HudPalette.glyphOf(providerKey)
    centerGlyphColor: HudPalette.glyphColorOf(providerKey)
    iconSource: HudPalette.iconOf(providerKey)
    iconIsMask: HudPalette.iconIsMaskOf(providerKey)
    iconMaskColor: HudPalette.iconColorOf(providerKey)
    innerColor: HudPalette.deepOf(providerKey)
    outerColor: HudPalette.accentOf(providerKey)
    amberThreshold: pi.amberThreshold
    redThreshold: pi.redThreshold
    singleRing: pi.gaugeSingleRing(providerKey)
    outerFraction: pi.gaugeOuterFraction(providerKey)
    innerFraction: pi.gaugeInnerFraction(providerKey)
    hasAuxiliaryData: pi.hasUsableDetailData(providerKey)
    showResetRing: pi.showResetRing && providerKey !== "deepseek"
    resetDaysRemaining: pi.resetDaysRemaining(providerKey)
    stale: pi.providerStale(providerKey)
    Accessible.role: Accessible.Graphic
    Accessible.name: pi.providerDisplayName(providerKey)
}
