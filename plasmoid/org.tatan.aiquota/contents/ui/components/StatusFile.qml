pragma ComponentBehavior: Bound

import QtQuick
import QtCore
import Qt.labs.folderlistmodel
import org.kde.plasma.plasma5support as Plasma5Support

// Lector de la cache que el timer systemd escribe. Cero red y cero Python: el
// subcomando de consulta del CLI solo hacia `cat` de este mismo fichero, pero
// arrancando el venv con typer, rich y pydantic en cada tick.
//
// La cache se escribe de forma atomica (security.py: `status.tmp` -> rename a
// `status.json`), asi que el directorio cambia dos veces por refresco. Se vigilan
// LOS DOS nombres a proposito: `dataChanged` solo llega si el modelo compara
// `fileModified`, cosa que no se puede afirmar leyendo el plugin; en cambio la
// aparicion y desaparicion de `status.tmp` mueve filas siempre. El timer de
// respaldo acota el peor caso a un ciclo del colector aunque fallen ambos.
Item {
    id: watcher

    readonly property url cacheDir: StandardPaths.writableLocation(StandardPaths.HomeLocation) + "/.cache/ai-quota-monitor"
    readonly property string catCmd: 'cat -- "$HOME/.cache/ai-quota-monitor/status.json"'
    readonly property int backupInterval: 300000

    property string rawJson: ""
    property bool debug: false

    signal loaded(string raw)
    signal failed(string message)

    FolderListModel {
        id: folder
        folder: watcher.cacheDir
        nameFilters: ["status.json", "status.tmp"]
        showDirs: false
        showOnlyReadable: true
        sortField: FolderListModel.Name
    }

    Connections {
        target: folder
        function onDataChanged() { debounce.restart() }
        function onRowsInserted() { debounce.restart() }
        function onRowsRemoved() { debounce.restart() }
        function onModelReset() { debounce.restart() }
    }

    // El rename atomico produce varias senales seguidas; una sola lectura basta.
    Timer {
        id: debounce
        interval: 250
        onTriggered: watcher.read()
    }

    Timer {
        interval: watcher.backupInterval
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: watcher.read()
    }

    Plasma5Support.DataSource {
        id: shell
        engine: "executable"
        connectedSources: []

        onNewData: function(sourceName, data) {
            disconnectSource(sourceName)
            const out = String(data["stdout"] || "")
            const code = Number(data["exit code"] || 0)
            if (code !== 0 || !out.trim()) {
                watcher.failed(String(data["stderr"] || "").trim() || ("cat salio " + code))
                return
            }
            // Sin cambio real no se despiertan los ~100 bindings del HUD.
            if (out === watcher.rawJson)
                return
            watcher.rawJson = out
            watcher.loaded(out)
        }
    }

    function read() {
        if (shell.connectedSources.indexOf(watcher.catCmd) !== -1)
            return
        shell.connectSource(watcher.catCmd)
    }
}
