import QtQuick
import QtQuick3D

Node {
    id: root

    // Public API
    property string bodyState: "idle"
    property real modelScale: 1.0
    property bool showChestBadge: true

    scale: Qt.vector3d(modelScale, modelScale, modelScale)

    readonly property color stateGlow:
        bodyState === "alert" ? "#FF9A4A"
        : bodyState === "approval" ? "#FFD166"
        : bodyState === "success" ? "#6EE7A8"
        : bodyState === "listening" ? "#62DAFF"
        : "#78B7FF"

    readonly property bool sleeping: bodyState === "sleeping"

    PrincipledMaterial {
        id: shellMaterial
        baseColor: "#ECEFF3"
        roughness: 0.24
        metalness: 0.08
    }

    PrincipledMaterial {
        id: shellShadowMaterial
        baseColor: "#C8CDD5"
        roughness: 0.30
        metalness: 0.14
    }

    PrincipledMaterial {
        id: darkMaterial
        baseColor: "#10141B"
        roughness: 0.20
        metalness: 0.20
    }

    PrincipledMaterial {
        id: visorMaterial
        baseColor: "#02060B"
        roughness: 0.08
        metalness: 0.15
    }

    PrincipledMaterial {
        id: glowMaterial
        baseColor: root.stateGlow
        emissiveFactor: Qt.vector3d(
            root.stateGlow.r * 2.2,
            root.stateGlow.g * 2.2,
            root.stateGlow.b * 2.2
        )
        roughness: 0.18
    }

    PrincipledMaterial {
        id: warmEarMaterial
        baseColor: "#FFF0DC"
        emissiveFactor: Qt.vector3d(1.5, 1.0, 0.65)
        roughness: 0.18
    }

    Texture {
        id: badgeTexture
        sourceItem: Rectangle {
            width: 256
            height: 256
            color: "#111720"
            radius: 40

            Text {
                anchors.centerIn: parent
                text: "K"
                color: root.stateGlow
                font.pixelSize: 148
                font.weight: Font.DemiBold
            }
        }
    }

    PrincipledMaterial {
        id: badgeMaterial
        baseColorMap: badgeTexture
        roughness: 0.15
    }

    // Animated body. Root remains free for your parent scene to position.
    Node {
        id: floatNode

        SequentialAnimation on y {
            running: root.bodyState !== "working"
            loops: Animation.Infinite

            NumberAnimation {
                to: -4
                duration: 1450
                easing.type: Easing.InOutSine
            }

            NumberAnimation {
                to: 4
                duration: 1450
                easing.type: Easing.InOutSine
            }
        }

        // HEAD
        Node {
            id: head
            y: 26

            Model {
                source: "#Sphere"
                scale: Qt.vector3d(1.30, 1.05, 0.90)
                materials: [ shellMaterial ]
            }

            Model {
                source: "#Cylinder"
                y: -53
                scale: Qt.vector3d(0.48, 0.12, 0.48)
                materials: [ darkMaterial ]
            }

            Model {
                source: "#Sphere"
                z: 39
                y: -1
                scale: Qt.vector3d(1.06, 0.76, 0.15)
                materials: [ visorMaterial ]
            }

            Node {
                id: face

                Model {
                    x: -26
                    y: root.sleeping ? -3 : 7
                    z: 48
                    source: "#Sphere"
                    scale: Qt.vector3d(
                        0.27,
                        root.sleeping ? 0.035 : 0.085,
                        0.035
                    )
                    eulerRotation.z:
                        root.bodyState === "thinking" ? -8
                        : root.bodyState === "alert" ? -14
                        : 8
                    materials: [ glowMaterial ]
                }

                Model {
                    x: 26
                    y: root.sleeping ? -3 : 7
                    z: 48
                    source: "#Sphere"
                    scale: Qt.vector3d(
                        0.27,
                        root.sleeping ? 0.035 : 0.085,
                        0.035
                    )
                    eulerRotation.z:
                        root.bodyState === "thinking" ? 8
                        : root.bodyState === "alert" ? 14
                        : -8
                    materials: [ glowMaterial ]
                }

                Model {
                    visible:
                        root.bodyState === "idle"
                        || root.bodyState === "success"
                    y: -20
                    z: 48
                    source: "#Sphere"
                    scale: Qt.vector3d(0.18, 0.035, 0.028)
                    materials: [ glowMaterial ]
                }
            }

            // Side sensor/audio rings
            Node {
                x: -69

                Model {
                    source: "#Cylinder"
                    scale: Qt.vector3d(0.40, 0.105, 0.40)
                    eulerRotation.z: 90
                    materials: [ darkMaterial ]
                }

                Model {
                    x: -6
                    source: "#Cylinder"
                    scale: Qt.vector3d(0.30, 0.038, 0.30)
                    eulerRotation.z: 90
                    materials: [ glowMaterial ]
                }
            }

            Node {
                x: 69

                Model {
                    source: "#Cylinder"
                    scale: Qt.vector3d(0.40, 0.105, 0.40)
                    eulerRotation.z: 90
                    materials: [ darkMaterial ]
                }

                Model {
                    x: 6
                    source: "#Cylinder"
                    scale: Qt.vector3d(0.30, 0.038, 0.30)
                    eulerRotation.z: 90
                    materials: [ glowMaterial ]
                }
            }

            // Ears
            Node {
                x: -45
                y: 58
                z: -4
                eulerRotation.z: root.bodyState === "listening" ? -9 : -18

                Behavior on eulerRotation.z {
                    NumberAnimation {
                        duration: 160
                        easing.type: Easing.OutCubic
                    }
                }

                Model {
                    source: "#Sphere"
                    scale: Qt.vector3d(0.25, 0.62, 0.18)
                    materials: [ darkMaterial ]
                }

                Model {
                    z: 10
                    y: 2
                    source: "#Sphere"
                    scale: Qt.vector3d(0.065, 0.30, 0.035)
                    materials: [ warmEarMaterial ]
                }
            }

            Node {
                x: 45
                y: 58
                z: -4
                eulerRotation.z: root.bodyState === "listening" ? 9 : 18

                Behavior on eulerRotation.z {
                    NumberAnimation {
                        duration: 160
                        easing.type: Easing.OutCubic
                    }
                }

                Model {
                    source: "#Sphere"
                    scale: Qt.vector3d(0.25, 0.62, 0.18)
                    materials: [ darkMaterial ]
                }

                Model {
                    z: 10
                    y: 2
                    source: "#Sphere"
                    scale: Qt.vector3d(0.065, 0.30, 0.035)
                    materials: [ warmEarMaterial ]
                }
            }
        }

        // BODY
        Node {
            id: body
            y: -73

            Model {
                source: "#Sphere"
                scale: Qt.vector3d(0.72, 0.64, 0.62)
                materials: [ shellMaterial ]
            }

            Model {
                y: -33
                source: "#Sphere"
                scale: Qt.vector3d(0.54, 0.20, 0.49)
                materials: [ darkMaterial ]
            }

            Model {
                visible: root.showChestBadge
                y: 7
                z: 31
                source: "#Cube"
                scale: Qt.vector3d(0.32, 0.32, 0.055)
                materials: [ badgeMaterial ]
            }

            Node {
                x: -49
                y: 2

                Model {
                    source: "#Sphere"
                    scale: Qt.vector3d(0.27, 0.37, 0.27)
                    eulerRotation.z: -10
                    materials: [ shellShadowMaterial ]
                }

                Model {
                    x: -4
                    y: -18
                    source: "#Sphere"
                    scale: Qt.vector3d(0.22, 0.31, 0.22)
                    eulerRotation.z: -12
                    materials: [ darkMaterial ]
                }
            }

            Node {
                x: 49
                y: 2

                Model {
                    source: "#Sphere"
                    scale: Qt.vector3d(0.27, 0.37, 0.27)
                    eulerRotation.z: 10
                    materials: [ shellShadowMaterial ]
                }

                Model {
                    x: 4
                    y: -18
                    source: "#Sphere"
                    scale: Qt.vector3d(0.22, 0.31, 0.22)
                    eulerRotation.z: 12
                    materials: [ darkMaterial ]
                }
            }

            // Rear status bar
            Model {
                y: 5
                z: -31
                source: "#Cube"
                scale: Qt.vector3d(0.26, 0.07, 0.035)
                materials: [ glowMaterial ]
            }
        }

        // Soft floating glow
        Model {
            y: -125
            source: "#Sphere"
            scale: Qt.vector3d(0.62, 0.025, 0.26)
            opacity: 0.28
            materials: [ glowMaterial ]
        }

        SequentialAnimation on eulerRotation.z {
            running: root.bodyState === "thinking"
            loops: Animation.Infinite

            NumberAnimation {
                to: -2.2
                duration: 460
                easing.type: Easing.InOutSine
            }

            NumberAnimation {
                to: 2.2
                duration: 460
                easing.type: Easing.InOutSine
            }
        }
    }
}