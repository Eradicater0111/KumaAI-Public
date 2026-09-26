import QtQuick
import QtQuick3D

Item {
    id: root

    width: 180
    height: 190

    property string bodyState: "idle"
    property real phase: 0.0

    property real hoverAmount: {
        if (bodyState === "happy")
            return 7.0

        if (bodyState === "alert")
            return 2.0

        if (bodyState === "focused")
            return 2.0

        if (bodyState === "sleep")
            return 2.0

        return 4.0
    }

    property real hoverOffset:
        Math.sin(phase) * hoverAmount

    property real idleBlink: {
        if (bodyState !== "idle")
            return 1.0

        return (
            Math.sin(phase * 1.9) > 0.985
            ? 0.12
            : 1.0
        )
    }

    property real eyeHeight: {
        if (bodyState === "sleep")
            return 0.018

        if (bodyState === "thinking")
            return 0.028

        if (bodyState === "focused")
            return 0.038

        if (bodyState === "happy")
            return 0.045

        if (bodyState === "listening")
            return 0.095

        return 0.067 * idleBlink
    }

    property real eyeWidth: {
        if (bodyState === "listening")
            return 0.105

        if (bodyState === "observing")
            return 0.095

        return 0.13
    }

    property real eyeTracking: {
        if (bodyState !== "observing")
            return 0.0

        return Math.sin(
            phase * 1.35
        ) * 5.0
    }

    NumberAnimation on phase {
        from: 0.0
        to: Math.PI * 2.0
        duration: 2600
        loops: Animation.Infinite
    }

    // =====================================================
    // FLOOR SHADOW
    // =====================================================

    Rectangle {
        width: 76
        height: 10

        radius: 5

        color: "#30000000"

        anchors.horizontalCenter:
            parent.horizontalCenter

        y: 161

        scale: (
            1.0
            - Math.abs(
                root.hoverOffset
            ) * 0.008
        )
    }

    // =====================================================
    // 3D VIEWPORT
    // =====================================================

    View3D {
        id: viewport

        anchors.fill: parent

        environment: SceneEnvironment {
            backgroundMode:
                SceneEnvironment.Transparent

            antialiasingMode:
                SceneEnvironment.MSAA

            antialiasingQuality:
                SceneEnvironment.High

            aoStrength: 75
            aoDistance: 18
            aoSoftness: 35
        }

        PerspectiveCamera {
            id: camera

            position:
                Qt.vector3d(
                    0,
                    3,
                    265
                )

            clipNear: 1
            clipFar: 1000
        }

        // ---------------------------------------------
        // LIGHTING
        // ---------------------------------------------

        DirectionalLight {
            eulerRotation:
                Qt.vector3d(
                    -28,
                    -32,
                    0
                )

            brightness: 1.25
        }

        PointLight {
            position:
                Qt.vector3d(
                    -130,
                    130,
                    220
                )

            brightness: 120
        }

        PointLight {
            position:
                Qt.vector3d(
                    130,
                    60,
                    180
                )

            brightness: 65

            color: "#8bbcff"
        }

        // ---------------------------------------------
        // MATERIALS
        // ---------------------------------------------

        PrincipledMaterial {
            id: shellMaterial

            baseColor: "#dfe2e7"

            metalness: 0.68
            roughness: 0.22
        }

        PrincipledMaterial {
            id: darkMetalMaterial

            baseColor: "#545965"

            metalness: 0.8
            roughness: 0.2
        }

        PrincipledMaterial {
            id: faceMaterial

            baseColor: "#030711"

            metalness: 0.32
            roughness: 0.08
        }

        PrincipledMaterial {
            id: warmLightMaterial

            baseColor: "#fff0d8"

            emissiveFactor:
                Qt.vector3d(
                    0.55,
                    0.38,
                    0.20
                )

            roughness: 0.18
        }

        PrincipledMaterial {
            id: eyeMaterial

            baseColor: (
                root.bodyState === "alert"
                ? "#ff626a"
                : "#70b5ff"
            )

            emissiveFactor: (
                root.bodyState === "alert"
                ? Qt.vector3d(
                    1.0,
                    0.08,
                    0.08
                )
                : Qt.vector3d(
                    0.18,
                    0.55,
                    1.0
                )
            )

            roughness: 0.08
        }

        PrincipledMaterial {
            id: badgeMaterial

            baseColor: "#090d15"

            metalness: 0.35
            roughness: 0.18
        }

        // =================================================
        // KUMA RIG ROOT
        // =================================================

        Node {
            id: kuma

            y: root.hoverOffset

            // BODY-2B3D presentation scale.
            //
            // One global scale keeps all head/body/ear/arm
            // proportions and state animations identical.
            scale:
                Qt.vector3d(
                    1.45,
                    1.45,
                    1.45
                )

            eulerRotation: {
                var tilt = 0.0

                if (
                    root.bodyState
                    === "thinking"
                ) {
                    tilt = -5.0
                }
                else if (
                    root.bodyState
                    === "happy"
                ) {
                    tilt = (
                        Math.sin(
                            root.phase * 2.0
                        )
                        * 2.5
                    )
                }
                else if (
                    root.bodyState
                    === "idle"
                ) {
                    tilt = (
                        Math.sin(
                            root.phase * 0.55
                        )
                        * 1.4
                    )
                }

                return Qt.vector3d(
                    0,
                    0,
                    tilt
                )
            }

            // =============================================
            // TORSO
            // =============================================

            Model {
                source: "#Sphere"

                position:
                    Qt.vector3d(
                        0,
                        -53,
                        0
                    )

                scale:
                    Qt.vector3d(
                        0.43,
                        0.49,
                        0.31
                    )

                materials: [
                    shellMaterial
                ]
            }

            // Left arm
            Model {
                source: "#Sphere"

                position:
                    Qt.vector3d(
                        -35,
                        -52,
                        0
                    )

                eulerRotation:
                    Qt.vector3d(
                        0,
                        0,
                        (
                            root.bodyState
                            === "happy"
                            ? -12
                            : -4
                        )
                    )

                scale:
                    Qt.vector3d(
                        0.17,
                        0.31,
                        0.18
                    )

                materials: [
                    darkMetalMaterial
                ]
            }

            // Right arm
            Model {
                source: "#Sphere"

                position:
                    Qt.vector3d(
                        35,
                        -52,
                        0
                    )

                eulerRotation:
                    Qt.vector3d(
                        0,
                        0,
                        (
                            root.bodyState
                            === "happy"
                            ? 12
                            : 4
                        )
                    )

                scale:
                    Qt.vector3d(
                        0.17,
                        0.31,
                        0.18
                    )

                materials: [
                    darkMetalMaterial
                ]
            }

            // Chest badge
            Model {
                source: "#Cube"

                position:
                    Qt.vector3d(
                        0,
                        -48,
                        29
                    )

                scale:
                    Qt.vector3d(
                        0.18,
                        0.16,
                        0.035
                    )

                materials: [
                    badgeMaterial
                ]
            }

            // =============================================
            // HEAD RIG
            // =============================================

            Node {
                id: head

                position:
                    Qt.vector3d(
                        0,
                        22,
                        0
                    )

                eulerRotation: {
                    var pitch = 0.0
                    var yaw = 0.0

                    if (
                        root.bodyState
                        === "thinking"
                    ) {
                        pitch = 3.0
                        yaw = -4.0
                    }
                    else if (
                        root.bodyState
                        === "observing"
                    ) {
                        yaw = (
                            Math.sin(
                                root.phase * 1.15
                            )
                            * 5.5
                        )
                    }
                    else if (
                        root.bodyState
                        === "listening"
                    ) {
                        pitch = -2.5
                    }
                    else if (
                        root.bodyState
                        === "idle"
                    ) {
                        yaw = (
                            Math.sin(
                                root.phase * 0.45
                            )
                            * 1.8
                        )
                    }

                    return Qt.vector3d(
                        pitch,
                        yaw,
                        0
                    )
                }

                // -----------------------------------------
                // OUTER HEAD SHELL
                // -----------------------------------------

                Model {
                    source: "#Sphere"

                    scale:
                        Qt.vector3d(
                            0.96,
                            0.72,
                            0.61
                        )

                    materials: [
                        shellMaterial
                    ]
                }

                // -----------------------------------------
                // GLOSSY FACE GLASS
                // -----------------------------------------

                Model {
                    source: "#Sphere"

                    position:
                        Qt.vector3d(
                            0,
                            -2,
                            27
                        )

                    scale:
                        Qt.vector3d(
                            0.78,
                            0.52,
                            0.14
                        )

                    materials: [
                        faceMaterial
                    ]
                }

                // -----------------------------------------
                // HEADPHONE PODS
                // -----------------------------------------

                Model {
                    source: "#Sphere"

                    position:
                        Qt.vector3d(
                            -51,
                            -1,
                            0
                        )

                    scale:
                        Qt.vector3d(
                            0.22,
                            0.33,
                            0.22
                        )

                    materials: [
                        darkMetalMaterial
                    ]
                }

                Model {
                    source: "#Sphere"

                    position:
                        Qt.vector3d(
                            51,
                            -1,
                            0
                        )

                    scale:
                        Qt.vector3d(
                            0.22,
                            0.33,
                            0.22
                        )

                    materials: [
                        darkMetalMaterial
                    ]
                }

                // Pod lighting
                Model {
                    source: "#Sphere"

                    position:
                        Qt.vector3d(
                            -53,
                            -1,
                            14
                        )

                    scale:
                        Qt.vector3d(
                            0.12,
                            0.22,
                            0.035
                        )

                    materials: [
                        warmLightMaterial
                    ]
                }

                Model {
                    source: "#Sphere"

                    position:
                        Qt.vector3d(
                            53,
                            -1,
                            14
                        )

                    scale:
                        Qt.vector3d(
                            0.12,
                            0.22,
                            0.035
                        )

                    materials: [
                        warmLightMaterial
                    ]
                }

                // -----------------------------------------
                // EARS
                // -----------------------------------------

                Model {
                    source: "#Cone"

                    position:
                        Qt.vector3d(
                            -37,
                            54,
                            0
                        )

                    eulerRotation:
                        Qt.vector3d(
                            0,
                            0,
                            (
                                root.bodyState
                                === "listening"
                                ? -11
                                : -7
                            )
                        )

                    scale:
                        Qt.vector3d(
                            0.13,
                            0.30,
                            0.10
                        )

                    materials: [
                        shellMaterial
                    ]
                }

                Model {
                    source: "#Cone"

                    position:
                        Qt.vector3d(
                            37,
                            54,
                            0
                        )

                    eulerRotation:
                        Qt.vector3d(
                            0,
                            0,
                            (
                                root.bodyState
                                === "listening"
                                ? 11
                                : 7
                            )
                        )

                    scale:
                        Qt.vector3d(
                            0.13,
                            0.30,
                            0.10
                        )

                    materials: [
                        shellMaterial
                    ]
                }

                // Ear inner glow
                Model {
                    source: "#Cone"

                    position:
                        Qt.vector3d(
                            -37,
                            55,
                            8
                        )

                    eulerRotation:
                        Qt.vector3d(
                            0,
                            0,
                            -7
                        )

                    scale:
                        Qt.vector3d(
                            0.055,
                            0.21,
                            0.025
                        )

                    materials: [
                        warmLightMaterial
                    ]
                }

                Model {
                    source: "#Cone"

                    position:
                        Qt.vector3d(
                            37,
                            55,
                            8
                        )

                    eulerRotation:
                        Qt.vector3d(
                            0,
                            0,
                            7
                        )

                    scale:
                        Qt.vector3d(
                            0.055,
                            0.21,
                            0.025
                        )

                    materials: [
                        warmLightMaterial
                    ]
                }

                // =========================================
                // EXPRESSIVE EYES
                // =========================================

                Node {
                    id: leftEye

                    position:
                        Qt.vector3d(
                            -20
                            + root.eyeTracking,
                            2,
                            39
                        )

                    eulerRotation:
                        Qt.vector3d(
                            0,
                            0,
                            (
                                root.bodyState
                                === "focused"
                                || root.bodyState
                                === "alert"
                                ? -13
                                : (
                                    root.bodyState
                                    === "happy"
                                    ? 10
                                    : 0
                                )
                            )
                        )

                    Model {
                        source: "#Sphere"

                        scale:
                            Qt.vector3d(
                                root.eyeWidth,
                                root.eyeHeight,
                                0.025
                            )

                        materials: [
                            eyeMaterial
                        ]
                    }
                }

                Node {
                    id: rightEye

                    position:
                        Qt.vector3d(
                            20
                            + root.eyeTracking,
                            2,
                            39
                        )

                    eulerRotation:
                        Qt.vector3d(
                            0,
                            0,
                            (
                                root.bodyState
                                === "focused"
                                || root.bodyState
                                === "alert"
                                ? 13
                                : (
                                    root.bodyState
                                    === "happy"
                                    ? -10
                                    : 0
                                )
                            )
                        )

                    Model {
                        source: "#Sphere"

                        scale:
                            Qt.vector3d(
                                root.eyeWidth,
                                root.eyeHeight,
                                0.025
                            )

                        materials: [
                            eyeMaterial
                        ]
                    }
                }
            }
        }
    }

    // =====================================================
    // CHEST "K"
    // =====================================================

    Text {
        text: "K"

        color: "#eaf2ff"

        font.bold: true
        font.pixelSize: 11

        anchors.horizontalCenter:
            parent.horizontalCenter

        y:
            133
            - root.hoverOffset
    }

    // =====================================================
    // THINKING DOTS
    // =====================================================

    Row {
        visible:
            root.bodyState
            === "thinking"

        spacing: 3

        x: 140
        y: 48

        Repeater {
            model: 3

            Rectangle {
                width: 4
                height: 4

                radius: 2

                color: "#9fcaff"

                opacity:
                    0.4
                    + (
                        (
                            index
                            + root.phase
                        )
                        % 3
                    ) * 0.2
            }
        }
    }

    // =====================================================
    // ALERT SYMBOL
    // =====================================================

    Text {
        visible:
            root.bodyState
            === "alert"

        text: "!"

        color: "#ff656d"

        font.bold: true
        font.pixelSize: 22

        x: 145
        y: 39
    }

    // =====================================================
    // SLEEP SYMBOL
    // =====================================================

    Text {
        visible:
            root.bodyState
            === "sleep"

        text: "Zᶻ"

        color: "#87b9ff"

        font.bold: true
        font.pixelSize: 14

        x: 140
        y: 38
    }
}
