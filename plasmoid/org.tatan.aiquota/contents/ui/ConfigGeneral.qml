import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kcmutils as KCM
import org.kde.kirigami as Kirigami

KCM.SimpleKCM {
    property alias cfg_showClaude: claudeCheck.checked
    property alias cfg_showCodex: codexCheck.checked
    property alias cfg_showGemini: geminiCheck.checked
    property alias cfg_showCopilot: copilotCheck.checked
    property alias cfg_showDeepseek: deepseekCheck.checked
    property alias cfg_amberThreshold: amberSpin.value
    property alias cfg_redThreshold: redSpin.value
    property alias cfg_compactMode: compactCombo.currentIndex
    property alias cfg_showResetRing: resetRingCheck.checked

    Kirigami.FormLayout {
        anchors.fill: parent

        QQC2.CheckBox {
            id: claudeCheck
            Kirigami.FormData.label: i18n("Providers:")
            text: i18n("Claude")
        }
        QQC2.CheckBox { id: codexCheck; text: i18n("Codex") }
        QQC2.CheckBox { id: geminiCheck; text: i18n("Antigravity / Gemini") }
        QQC2.CheckBox { id: copilotCheck; text: i18n("Copilot") }
        QQC2.CheckBox { id: deepseekCheck; text: i18n("DeepSeek") }

        Item { Kirigami.FormData.isSection: true }

        QQC2.ComboBox {
            id: compactCombo
            Kirigami.FormData.label: i18n("In the panel:")
            model: [i18n("One donut per provider"), i18n("Only the tightest one")]
        }
        QQC2.CheckBox {
            id: resetRingCheck
            Kirigami.FormData.label: i18n("Reset ring:")
            text: i18n("Show the days until the next reset")
        }

        Item { Kirigami.FormData.isSection: true }

        QQC2.SpinBox {
            id: amberSpin
            Kirigami.FormData.label: i18n("Amber warning below (%):")
            from: 2
            to: 90
            stepSize: 5
        }
        QQC2.SpinBox {
            id: redSpin
            Kirigami.FormData.label: i18n("Red alarm below (%):")
            from: 1
            // El rojo nunca puede quedar por encima del ámbar: si lo hiciera, el color
            // de alarma se comería el de aviso y el ámbar no se vería nunca.
            to: Math.max(1, amberSpin.value - 1)
            stepSize: 1
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            font: Kirigami.Theme.smallFont
            text: i18n("The refresh cadence is set by the ai-quota-monitor.timer unit, not by this dialog.")
        }
    }
}
