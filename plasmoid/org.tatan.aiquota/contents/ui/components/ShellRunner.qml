pragma ComponentBehavior: Bound

import QtQuick
import org.kde.plasma.plasma5support as Plasma5Support

// Ejecuta un comando y devuelve su resultado por callback. Una sola orden en
// vuelo: el refresco manual arranca la unidad systemd, que tarda entre 9 y 20
// segundos, y solaparlas es justo lo que hay que evitar.
Item {
    id: runner

    property bool running: false
    property string lastCommand: ""

    signal finished(int exitCode, string stdout, string stderr)

    Plasma5Support.DataSource {
        id: source
        engine: "executable"
        connectedSources: []

        onNewData: function(sourceName, data) {
            disconnectSource(sourceName)
            runner.running = false
            runner.finished(Number(data["exit code"] || 0),
                            String(data["stdout"] || ""),
                            String(data["stderr"] || ""))
        }
    }

    // Si el comando no vuelve nunca, la interfaz no puede quedarse en «ocupado».
    Timer {
        interval: 90000
        running: runner.running
        onTriggered: {
            source.connectedSources = []
            runner.running = false
            runner.finished(-1, "", "tiempo agotado")
        }
    }

    function run(command) {
        if (runner.running)
            return false
        runner.running = true
        runner.lastCommand = command
        source.connectSource(command)
        return true
    }
}
