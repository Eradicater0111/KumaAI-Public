import QtQuick
import QtQuick3D

Item {
    id: root

    width: 180
    height: 180

    property alias bodyState: kuma.bodyState
    property alias modelScale: kuma.modelScale
    property bool draggable: true
    property real yaw: 0
    property real pitch: 0
    signal activated()

    View3D {
        id: view
        anchors.fill: parent

        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Transparent
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }

        PerspectiveCamera {
            id: camera
            z: 250
            y: -25
            clipNear: 1
            clipFar: 2000
        }

        DirectionalLight {
            eulerRotation.x: -35
            eulerRotation.y: -35
            brightness: 1.15
        }

        DirectionalLight {
            eulerRotation.x: 25
            eulerRotation.y: 145
            brightness: 0.45
        }

        Node {
            id: turntable
            eulerRotation.y: root.yaw
            eulerRotation.x: root.pitch

            KumaMini3D {
                id: kuma
                modelScale: 1.00
            }
        }
    }

    MouseArea {
        id: interaction
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true
        drag.target: root
        drag.axis: Drag.XAndYAxis
        drag.minimumX: 0
        drag.minimumY: 0
        drag.maximumX: root.parent ? Math.max(0, root.parent.width - root.width) : 0
        drag.maximumY: root.parent ? Math.max(0, root.parent.height - root.height) : 0
        enabled: root.draggable

        onDoubleClicked: root.activated()
    }
}
