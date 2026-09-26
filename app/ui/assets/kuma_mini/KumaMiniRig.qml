import QtQuick
import QtQuick3D
import QtQuick3D.AssetUtils

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
            return 1.5

        if (bodyState === "sleep")
            return 1.5

        return 3.5
    }

    property real hoverOffset:
        Math.sin(phase) * hoverAmount

    // =====================================================
    // AUTONOMOUS MICRO-BEHAVIOR
    // =====================================================
    //
    // Presentation-level body language only.
    // Kuma's existing personality / reasoning remains the brain.
    // These values produce small creature-like spontaneous motion.
    // =====================================================

    property bool blinkClosed: false

    property real curiosityYaw: 0.0
    property real curiosityPitch: 0.0

    property real leftEarTwitch: 0.0
    property real rightEarTwitch: 0.0

    property real idleBreath:
        Math.sin(
            phase * 0.72
        )

    property real happyBounce:
        Math.max(
            0,
            Math.sin(
                phase * 2.0
            )
        )

    property real blinkScale: {
        if (bodyState === "sleep")
            return 0.10

        if (bodyState === "thinking")
            return 0.35

        if (bodyState === "focused")
            return 0.48

        if (
            bodyState === "idle"
            && Math.sin(phase * 2.7) > 0.985
        )
            return 0.10

        return 1.0
    }

    property real eyeTrack: {
        if (bodyState !== "observing")
            return 0.0

        return Math.sin(
            phase * 1.35
        ) * 4.5
    }

    Timer {
        id: blinkTimer

        interval: 2400
        repeat: false
        running: true

        onTriggered: {
            if (
                root.bodyState !== "sleep"
                && root.bodyState !== "alert"
            ) {
                root.blinkClosed = true
                blinkOpenTimer.start()
            }

            interval =
                1800
                + Math.random() * 4200

            restart()
        }
    }

    Timer {
        id: blinkOpenTimer

        interval: 115
        repeat: false

        onTriggered: {
            root.blinkClosed = false
        }
    }

    Timer {
        id: curiosityTimer

        interval: 3300
        repeat: false
        running: true

        onTriggered: {
            if (
                root.bodyState === "idle"
            ) {
                root.curiosityYaw =
                    -5.0
                    + Math.random() * 10.0

                root.curiosityPitch =
                    -2.5
                    + Math.random() * 5.0

                if (
                    Math.random() > 0.63
                ) {
                    if (
                        Math.random() > 0.5
                    ) {
                        root.leftEarTwitch = -6.0
                        leftEarResetTimer.restart()
                    }
                    else {
                        root.rightEarTwitch = 6.0
                        rightEarResetTimer.restart()
                    }
                }
            }

            else {
                root.curiosityYaw = 0.0
                root.curiosityPitch = 0.0
            }

            interval =
                2200
                + Math.random() * 4200

            restart()
        }
    }

    Timer {
        id: leftEarResetTimer

        interval: 240

        onTriggered: {
            root.leftEarTwitch = 0.0
        }
    }

    Timer {
        id: rightEarResetTimer

        interval: 240

        onTriggered: {
            root.rightEarTwitch = 0.0
        }
    }

    Behavior on curiosityYaw {
        NumberAnimation {
            duration: 650
            easing.type:
                Easing.InOutQuad
        }
    }

    Behavior on curiosityPitch {
        NumberAnimation {
            duration: 650
            easing.type:
                Easing.InOutQuad
        }
    }

    Behavior on leftEarTwitch {
        NumberAnimation {
            duration: 160
            easing.type:
                Easing.OutQuad
        }
    }

    Behavior on rightEarTwitch {
        NumberAnimation {
            duration: 160
            easing.type:
                Easing.OutQuad
        }
    }

    NumberAnimation on phase {
        from: 0
        to: Math.PI * 2
        duration: 2700
        loops: Animation.Infinite
    }

    // =====================================================
    // DESKTOP SHADOW / FLOAT RING
    // =====================================================

    Rectangle {
        width: 88
        height: 11

        radius: 6

        anchors.horizontalCenter:
            parent.horizontalCenter

        y: 162

        color: "#25000000"

        scale:
            1.0
            - Math.abs(
                root.hoverOffset
            ) * 0.008
    }

    Rectangle {
        width: 84
        height: 14

        radius: 7

        anchors.horizontalCenter:
            parent.horizontalCenter

        y: 157

        color: "transparent"

        border.width: 1
        border.color: "#77ffc56d"

        opacity:
            0.38
            + Math.sin(
                root.phase
            ) * 0.07
    }

    // =====================================================
    // 3D WORLD
    // =====================================================

    View3D {
        anchors.fill: parent

        environment: SceneEnvironment {
            backgroundMode:
                SceneEnvironment.Transparent

            antialiasingMode:
                SceneEnvironment.MSAA

            antialiasingQuality:
                SceneEnvironment.High

            aoStrength: 90
            aoDistance: 20
            aoSoftness: 45
        }

        PerspectiveCamera {
            position:
                Qt.vector3d(
                    0,
                    0,
                    220
                )

            clipNear: 1
            clipFar: 1000
        }

        // -------------------------------------------------
        // LIVE DIGITAL VISOR MATERIAL
        // -------------------------------------------------

        Texture {
            id: faceDisplayTexture

            sourceItem:
                faceTextureSource

            generateMipmaps: false
        }

        PrincipledMaterial {
            id: faceDisplayMaterial

            baseColor: "#ffffff"

            baseColorMap:
                faceDisplayTexture

            emissiveMap:
                faceDisplayTexture

            emissiveFactor:
                Qt.vector3d(
                    1.0,
                    1.0,
                    1.0
                )

            metalness: 0.0
            roughness: 0.05

            alphaMode:
                PrincipledMaterial.Blend
        }

        // -------------------------------------------------
        // LIGHTS
        // -------------------------------------------------

        DirectionalLight {
            eulerRotation:
                Qt.vector3d(
                    -28,
                    -34,
                    0
                )

            brightness: 1.45
        }

        PointLight {
            position:
                Qt.vector3d(
                    -120,
                    130,
                    180
                )

            brightness: 125
        }

        PointLight {
            position:
                Qt.vector3d(
                    120,
                    50,
                    170
                )

            brightness: 78

            color: "#86baff"
        }

        // -------------------------------------------------
        // KUMA WARM EAR / POD ACCENT LIGHTS
        // -------------------------------------------------

        PointLight {
            position:
                Qt.vector3d(
                    -72,
                    72,
                    115
                )

            color: "#ffd7a1"
            brightness: 18
        }

        PointLight {
            position:
                Qt.vector3d(
                    72,
                    72,
                    115
                )

            color: "#ffd7a1"
            brightness: 18
        }

        // =================================================
        // WHOLE KUMA RIG
        // =================================================

        Node {
            id: kumaRig

            y:
                root.hoverOffset
                + (
                    root.bodyState === "happy"
                    ? root.happyBounce * 3.0
                    : 0.0
                )

            scale:
                Qt.vector3d(
                    1.10,
                    1.10,
                    1.10
                )

            eulerRotation: {
                var roll = 0.0

                if (root.bodyState === "idle") {
                    roll =
                        Math.sin(
                            root.phase * 0.55
                        ) * 1.2
                }
                else if (
                    root.bodyState
                    === "happy"
                ) {
                    roll =
                        Math.sin(
                            root.phase * 2.0
                        ) * 2.3
                }

                return Qt.vector3d(
                    0,
                    0,
                    roll
                )
            }

            // =============================================
            // TORSO
            // =============================================

            Node {
                id: torsoNode

                position:
                    Qt.vector3d(
                        0,
                        -48,
                        1
                    )

                scale:
                    Qt.vector3d(
                        1.0,
                        (
                            root.bodyState === "sleep"
                            ? 1.0
                              + root.idleBreath * 0.025
                            : (
                                root.bodyState === "idle"
                                ? 1.0
                                  + root.idleBreath * 0.012
                                : 1.0
                            )
                        ),
                        1.0
                    )

                RuntimeLoader {
                    source:
                        "models/parts/torso.glb"
                }
            }

            // Chest badge
            Node {
                position:
                    Qt.vector3d(
                        0,
                        -40,
                        29
                    )

                RuntimeLoader {
                    source:
                        "models/parts/chest_badge.glb"
                }
            }

            // =============================================
            // ARMS
            // =============================================

            Node {
                id: leftArm

                position:
                    Qt.vector3d(
                        -45,
                        -44,
                        4
                    )

                eulerRotation:
                    Qt.vector3d(
                        0,
                        0,
                        (
                            root.bodyState
                            === "happy"
                            ? (
                                -25
                                - root.happyBounce * 7
                            )
                            : (
                                root.bodyState
                                === "alert"
                                ? -10
                                : -7
                            )
                        )
                    )

                RuntimeLoader {
                    source:
                        "models/parts/arm_left.glb"
                }
            }

            Node {
                id: rightArm

                position:
                    Qt.vector3d(
                        45,
                        -44,
                        4
                    )

                eulerRotation:
                    Qt.vector3d(
                        0,
                        0,
                        (
                            root.bodyState
                            === "happy"
                            ? (
                                25
                                + root.happyBounce * 7
                            )
                            : (
                                root.bodyState
                                === "alert"
                                ? 10
                                : 7
                            )
                        )
                    )

                RuntimeLoader {
                    source:
                        "models/parts/arm_right.glb"
                }
            }

            // =============================================
            // FEET
            // =============================================

            Node {
                position:
                    Qt.vector3d(
                        -19,
                        -76,
                        10
                    )

                eulerRotation:
                    Qt.vector3d(
                        18,
                        0,
                        -8
                    )

                RuntimeLoader {
                    source:
                        "models/parts/foot_left.glb"
                }
            }

            Node {
                position:
                    Qt.vector3d(
                        19,
                        -76,
                        10
                    )

                eulerRotation:
                    Qt.vector3d(
                        18,
                        0,
                        8
                    )

                RuntimeLoader {
                    source:
                        "models/parts/foot_right.glb"
                }
            }

            // =============================================
            // HEAD RIG
            // =============================================

            Node {
                id: headRig

                position:
                    Qt.vector3d(
                        0,
                        24,
                        0
                    )

                eulerRotation: {
                    var pitch = 0.0
                    var yaw = 0.0
                    var roll = 0.0

                    if (
                        root.bodyState
                        === "thinking"
                    ) {
                        pitch = 4.0
                        roll = -5.0
                    }

                    else if (
                        root.bodyState
                        === "observing"
                    ) {
                        yaw =
                            Math.sin(
                                root.phase * 1.15
                            ) * 7.0
                    }

                    else if (
                        root.bodyState
                        === "listening"
                    ) {
                        pitch = -3.0
                    }

                    else if (
                        root.bodyState
                        === "idle"
                    ) {
                        yaw =
                            root.curiosityYaw
                            + Math.sin(
                                root.phase * 0.45
                            ) * 1.2

                        pitch =
                            root.curiosityPitch
                    }

                    return Qt.vector3d(
                        pitch,
                        yaw,
                        roll
                    )
                }

                // -----------------------------------------
                // SHELL
                // -----------------------------------------

                RuntimeLoader {
                    source:
                        "models/parts/head_shell.glb"
                }

                // -----------------------------------------
                // FACE GLASS
                // -----------------------------------------

                Node {
                    position:
                        Qt.vector3d(
                            0,
                            -3,
                            43.5
                        )

                    RuntimeLoader {
                        source:
                            "models/parts/face_glass.glb"
                    }
                }

                // =========================================
                // LIVE DIGITAL VISOR DISPLAY
                // =========================================
                //
                // Attached to headRig, therefore head yaw,
                // pitch and roll carry Kuma's expression with it.
                // =========================================

                Model {
                    id: digitalFaceDisplay

                    source: "#Rectangle"

                    position:
                        Qt.vector3d(
                            0,
                            -3,
                            56.5
                        )

                    scale:
                        Qt.vector3d(
                            0.82,
                            0.43,
                            1.0
                        )

                    materials: [
                        faceDisplayMaterial
                    ]
                }

                // =========================================
                // EARS
                // =========================================

                Node {
                    id: leftEar

                    position:
                        Qt.vector3d(
                            -46,
                            48,
                            -4
                        )

                    eulerRotation:
                        Qt.vector3d(
                            0,
                            0,
                            (
                                root.bodyState
                                === "listening"
                                ? -17
                                : (
                                    -8
                                    + root.leftEarTwitch
                                )
                            )
                        )

                    RuntimeLoader {
                        source:
                            "models/parts/ear_left.glb"
                    }
                }

                Node {
                    id: rightEar

                    position:
                        Qt.vector3d(
                            46,
                            48,
                            -4
                        )

                    eulerRotation:
                        Qt.vector3d(
                            0,
                            0,
                            (
                                root.bodyState
                                === "listening"
                                ? 17
                                : (
                                    8
                                    + root.rightEarTwitch
                                )
                            )
                        )

                    RuntimeLoader {
                        source:
                            "models/parts/ear_right.glb"
                    }
                }

                // =========================================
                // SIDE PODS
                // =========================================

                Node {
                    position:
                        Qt.vector3d(
                            -73,
                            -4,
                            0
                        )

                    RuntimeLoader {
                        source:
                            "models/parts/pod_left.glb"
                    }
                }

                Node {
                    position:
                        Qt.vector3d(
                            73,
                            -4,
                            0
                        )

                    RuntimeLoader {
                        source:
                            "models/parts/pod_right.glb"
                    }
                }

                // =========================================
                // EXPRESSIVE EYES
                // =========================================

                Node {
                    id: leftEye

                    visible: false

                    position:
                        Qt.vector3d(
                            -25
                            + root.eyeTrack,
                            -3,
                            50
                        )

                    scale:
                        Qt.vector3d(
                            1,
                            root.blinkScale,
                            1
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
                                ? -14
                                : (
                                    root.bodyState
                                    === "happy"
                                    ? 11
                                    : 0
                                )
                            )
                        )

                    RuntimeLoader {
                        source:
                            "models/parts/eye_left.glb"
                    }
                }

                Node {
                    id: rightEye

                    visible: false

                    position:
                        Qt.vector3d(
                            25
                            + root.eyeTrack,
                            -3,
                            50
                        )

                    scale:
                        Qt.vector3d(
                            1,
                            root.blinkScale,
                            1
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
                                ? 14
                                : (
                                    root.bodyState
                                    === "happy"
                                    ? -11
                                    : 0
                                )
                            )
                        )

                    RuntimeLoader {
                        source:
                            "models/parts/eye_right.glb"
                    }
                }
            }
        }
    }

    // =====================================================
    // KUMA DIGITAL VISOR SOURCE
    // =====================================================
    //
    // This Canvas is no longer drawn directly over the desktop.
    // It is rendered off-screen and used as a live texture on a
    // 3D plane attached to headRig.
    // =====================================================

    Item {
        id: faceTextureSource

        width: 256
        height: 128

        // Remain renderable for Texture.sourceItem but stay
        // completely outside the visible floating window.
        x: -1000
        y: -1000

        Canvas {
            id: kumaFaceTexture

            anchors.fill: parent

            antialiasing: true

            onPaint: {
                var ctx = getContext("2d")

                ctx.clearRect(
                    0,
                    0,
                    width,
                    height
                )

                var alert =
                    root.bodyState === "alert"

                var eyeColor =
                    alert
                    ? "#ff626c"
                    : "#74b9ff"

                ctx.strokeStyle = eyeColor
                ctx.fillStyle = eyeColor

                ctx.lineWidth = 13
                ctx.lineCap = "round"
                ctx.lineJoin = "round"

                var track = 0

                if (
                    root.bodyState
                    === "observing"
                ) {
                    track =
                        Math.sin(
                            root.phase * 1.35
                        )
                        * 10
                }

                var left = 72
                var right = 184
                var centerY = 67

                function happyEye(cx) {
                    ctx.beginPath()

                    ctx.moveTo(
                        cx - 28,
                        centerY + 9
                    )

                    ctx.quadraticCurveTo(
                        cx,
                        centerY - 25,
                        cx + 28,
                        centerY + 9
                    )

                    ctx.stroke()
                }

                function flatEye(cx) {
                    ctx.beginPath()

                    ctx.moveTo(
                        cx - 25,
                        centerY
                    )

                    ctx.lineTo(
                        cx + 25,
                        centerY
                    )

                    ctx.stroke()
                }

                function sleepEye(cx) {
                    ctx.beginPath()

                    ctx.moveTo(
                        cx - 27,
                        centerY - 4
                    )

                    ctx.quadraticCurveTo(
                        cx,
                        centerY + 20,
                        cx + 27,
                        centerY - 4
                    )

                    ctx.stroke()
                }

                function openEye(cx) {
                    ctx.beginPath()

                    ctx.ellipse(
                        cx + track,
                        centerY,
                        13,
                        23,
                        0,
                        0,
                        Math.PI * 2
                    )

                    ctx.fill()
                }

                function focusedLeft(cx) {
                    ctx.beginPath()

                    ctx.moveTo(
                        cx - 27,
                        centerY - 15
                    )

                    ctx.lineTo(
                        cx + 25,
                        centerY + 10
                    )

                    ctx.stroke()
                }

                function focusedRight(cx) {
                    ctx.beginPath()

                    ctx.moveTo(
                        cx - 25,
                        centerY + 10
                    )

                    ctx.lineTo(
                        cx + 27,
                        centerY - 15
                    )

                    ctx.stroke()
                }

                // Natural idle blink.
                var blinking =
                    root.blinkClosed

                if (blinking) {
                    flatEye(left)
                    flatEye(right)
                }

                else if (
                    root.bodyState === "idle"
                    || root.bodyState === "happy"
                ) {
                    happyEye(left)
                    happyEye(right)
                }

                else if (
                    root.bodyState === "thinking"
                ) {
                    flatEye(left)
                    flatEye(right)
                }

                else if (
                    root.bodyState === "focused"
                    || root.bodyState === "alert"
                ) {
                    focusedLeft(left)
                    focusedRight(right)
                }

                else if (
                    root.bodyState === "sleep"
                ) {
                    sleepEye(left)
                    sleepEye(right)
                }

                else {
                    openEye(left)
                    openEye(right)
                }
            }

            Connections {
                target: root

                function onBodyStateChanged() {
                    kumaFaceTexture.requestPaint()
                }

                function onPhaseChanged() {
                    kumaFaceTexture.requestPaint()
                }
            }
        }
    }

    // =====================================================
    // CHEST K
    // =====================================================

    Text {
        text: "K"

        color: "#e9f2ff"

        font.bold: true
        font.pixelSize: 11

        anchors.horizontalCenter:
            parent.horizontalCenter

        y:
            132
            - root.hoverOffset
    }

    // =====================================================
    // THINKING
    // =====================================================

    Row {
        visible:
            root.bodyState
            === "thinking"

        spacing: 3

        x: 142
        y: 43

        Repeater {
            model: 3

            Rectangle {
                width: 4
                height: 4

                radius: 2

                color: "#9cc8ff"

                opacity:
                    0.40
                    + index * 0.18
            }
        }
    }

    // =====================================================
    // ALERT
    // =====================================================

    Text {
        visible:
            root.bodyState
            === "alert"

        text: "!"

        color: "#ff656d"

        font.bold: true
        font.pixelSize: 22

        x: 147
        y: 37
    }

    // =====================================================
    // SLEEP
    // =====================================================

    Text {
        visible:
            root.bodyState
            === "sleep"

        text: "Zᶻ"

        color: "#88baff"

        font.bold: true
        font.pixelSize: 14

        x: 139
        y: 36
    }
}
