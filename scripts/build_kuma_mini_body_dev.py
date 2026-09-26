from __future__ import annotations

from pathlib import Path
import math
import shutil

import numpy as np
import trimesh


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

SOURCE_PARTS = (
    ROOT
    / "app"
    / "ui"
    / "assets"
    / "kuma_mini"
    / "models"
    / "parts"
)

REFERENCE_PARTS = (
    ROOT
    / "app"
    / "ui"
    / "assets"
    / "kuma_mini"
    / "models"
    / "body_dev"
    / "parts"
)

REFERENCE_PARTS.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# MATERIALS
# =========================================================

def pbr(
    *,
    name,
    color,
    metallic,
    roughness,
    emissive=None,
):
    kwargs = {
        "name": name,
        "baseColorFactor": color,
        "metallicFactor": metallic,
        "roughnessFactor": roughness,
    }

    if emissive is not None:
        kwargs["emissiveFactor"] = emissive

    return trimesh.visual.material.PBRMaterial(
        **kwargs
    )


WHITE_SHELL = pbr(
    name="KUMA_Reference_WhiteShell",
    color=[
        242,
        243,
        246,
        255,
    ],
    metallic=0.26,
    roughness=0.16,
)

DARK_METAL = pbr(
    name="KUMA_Reference_DarkMetal",
    color=[
        27,
        31,
        39,
        255,
    ],
    metallic=0.76,
    roughness=0.15,
)

VISOR_GLASS = pbr(
    name="KUMA_Reference_Visor",
    color=[
        1,
        2,
        4,
        255,
    ],

    # The visor is glossy black glass/plastic, not metallic.
    #
    # A near-zero roughness combined with the old blue fill
    # light caused the entire curved visor to behave like a
    # blue mirror. Preserve a premium highlight while keeping
    # the body of the visor visually black.
    metallic=0.0,
    roughness=0.22,
)

BLUE_EMISSIVE = pbr(
    name="KUMA_Reference_BlueRing",
    color=[
        90,
        166,
        255,
        255,
    ],
    metallic=0.02,
    roughness=0.10,
    emissive=[
        0.20,
        0.58,
        1.0,
    ],
)

WARM_EMISSIVE = pbr(
    name="KUMA_Reference_EarGlow",
    color=[
        255,
        226,
        184,
        255,
    ],
    metallic=0.01,
    roughness=0.08,
    emissive=[
        1.0,
        0.46,
        0.13,
    ],
)


def apply_material(
    mesh,
    material,
):
    mesh.visual = (
        trimesh.visual.TextureVisuals(
            material=material
        )
    )

    return mesh


# =========================================================
# SUPERELLIPSOID
# =========================================================

def signed_power(
    value,
    power,
):
    value = np.asarray(
        value,
        dtype=float,
    )

    return (
        np.sign(value)
        * np.power(
            np.abs(value),
            power,
        )
    )


def superellipsoid(
    radii,
    material,
    *,
    vertical_power,
    horizontal_power,
    latitude_steps=40,
    longitude_steps=80,
):
    rx, ry, rz = (
        float(v)
        for v in radii
    )

    vertices = [
        (
            0.0,
            -ry,
            0.0,
        )
    ]

    for lat in range(
        1,
        latitude_steps,
    ):
        phi = (
            -math.pi / 2.0
            + math.pi
            * lat
            / latitude_steps
        )

        cp = signed_power(
            math.cos(phi),
            vertical_power,
        )

        sp = signed_power(
            math.sin(phi),
            vertical_power,
        )

        for lon in range(
            longitude_steps
        ):
            theta = (
                2.0
                * math.pi
                * lon
                / longitude_steps
            )

            ct = signed_power(
                math.cos(theta),
                horizontal_power,
            )

            st = signed_power(
                math.sin(theta),
                horizontal_power,
            )

            vertices.append(
                (
                    rx * cp * ct,
                    ry * sp,
                    rz * cp * st,
                )
            )

    top = len(
        vertices
    )

    vertices.append(
        (
            0.0,
            ry,
            0.0,
        )
    )

    faces = []

    # Bottom cap.
    for lon in range(
        longitude_steps
    ):
        nxt = (
            lon + 1
        ) % longitude_steps

        faces.append(
            (
                0,
                1 + nxt,
                1 + lon,
            )
        )

    ring_count = (
        latitude_steps - 1
    )

    for ring in range(
        ring_count - 1
    ):
        current = (
            1
            + ring
            * longitude_steps
        )

        following = (
            current
            + longitude_steps
        )

        for lon in range(
            longitude_steps
        ):
            nxt = (
                lon + 1
            ) % longitude_steps

            a = current + lon
            b = current + nxt
            c = following + lon
            d = following + nxt

            faces.append(
                (
                    a,
                    b,
                    d,
                )
            )

            faces.append(
                (
                    a,
                    d,
                    c,
                )
            )

    last_ring = (
        1
        + (
            ring_count - 1
        )
        * longitude_steps
    )

    for lon in range(
        longitude_steps
    ):
        nxt = (
            lon + 1
        ) % longitude_steps

        faces.append(
            (
                last_ring + lon,
                last_ring + nxt,
                top,
            )
        )

    mesh = trimesh.Trimesh(
        vertices=np.asarray(
            vertices,
            dtype=float,
        ),
        faces=np.asarray(
            faces,
            dtype=np.int64,
        ),
        process=True,
    )

    try:
        mesh.fix_normals()
    except Exception:
        pass

    return apply_material(
        mesh,
        material,
    )


# =========================================================
# CYLINDER ALONG X — SIDE PODS
# =========================================================

def x_cylinder(
    *,
    radius,
    length,
    material,
    sections=96,
):
    mesh = trimesh.creation.cylinder(
        radius=radius,
        height=length,
        sections=sections,
    )

    mesh.apply_transform(
        trimesh.transformations.rotation_matrix(
            math.radians(
                90
            ),
            (
                0,
                1,
                0,
            ),
        )
    )

    return apply_material(
        mesh,
        material,
    )


# =========================================================
# SWEPT EAR FIN
# =========================================================

def swept_ear(
    *,
    side,
):
    """
    Broad swept KUMA ear derived from the turnaround.

    side:
        -1 left
        +1 right
    """

    sections = [
        # y, half-width-x, half-depth-z, outward shift
        (
            -20.0,
            14.5,
            9.0,
            0.0,
        ),
        (
            -3.0,
            11.5,
            7.5,
            1.5,
        ),
        (
            18.0,
            8.5,
            6.0,
            5.0,
        ),
        (
            42.0,
            5.5,
            4.8,
            12.0,
        ),
    ]

    vertices = []

    for (
        y,
        half_x,
        half_z,
        outward,
    ) in sections:

        center_x = (
            side
            * outward
        )

        vertices.extend(
            [
                (
                    center_x - half_x,
                    y,
                    -half_z,
                ),
                (
                    center_x + half_x,
                    y,
                    -half_z,
                ),
                (
                    center_x + half_x,
                    y,
                    half_z,
                ),
                (
                    center_x - half_x,
                    y,
                    half_z,
                ),
            ]
        )

    faces = []

    # Bottom.
    faces.extend(
        [
            (
                0,
                2,
                1,
            ),
            (
                0,
                3,
                2,
            ),
        ]
    )

    section_count = len(
        sections
    )

    for section in range(
        section_count - 1
    ):
        a = section * 4
        b = (
            section + 1
        ) * 4

        for edge in range(
            4
        ):
            nxt = (
                edge + 1
            ) % 4

            faces.append(
                (
                    a + edge,
                    a + nxt,
                    b + nxt,
                )
            )

            faces.append(
                (
                    a + edge,
                    b + nxt,
                    b + edge,
                )
            )

    top = (
        section_count - 1
    ) * 4

    faces.extend(
        [
            (
                top,
                top + 1,
                top + 2,
            ),
            (
                top,
                top + 2,
                top + 3,
            ),
        ]
    )

    mesh = trimesh.Trimesh(
        vertices=np.asarray(
            vertices,
            dtype=float,
        ),
        faces=np.asarray(
            faces,
            dtype=np.int64,
        ),
        process=True,
    )

    return apply_material(
        mesh,
        DARK_METAL,
    )


def ear_glow_strip(
    *,
    side,
):
    """
    Narrow emissive bar embedded into the dark ear.
    """

    mesh = superellipsoid(
        (
            2.4,
            8.0,
            1.25,
        ),
        WARM_EMISSIVE,
        vertical_power=0.55,
        horizontal_power=0.52,
        latitude_steps=22,
        longitude_steps=40,
    )

    mesh.apply_translation(
        (
            side * 2.6,
            1.0,
            5.4,
        )
    )

    return mesh



# =========================================================
# BODY-DEV ROUNDED SWEPT EAR FIN
# =========================================================

def rounded_swept_fin_ear(
    *,
    side,
):
    """
    Build KUMA's dark outer ear as one connected,
    watertight rounded swept fin.

    Coordinate system:
        X = left/right thickness
        Y = vertical
        Z = front/back

    Negative Z sweeps the upper ear toward the rear
    of KUMA's helmet.

    `side` adds a subtle outward X sweep so the ears
    retain presence in the front view:
        -1 = left
        +1 = right

    Construction strategy:
        1. build several rounded ellipsoidal volumes,
        2. taper them toward the tip,
        3. shift successive volumes rearward,
        4. take one convex hull.

    This avoids fragile hand-authored polygon topology.
    """

    if side not in (
        -1,
        1,
    ):
        raise ValueError(
            "side must be -1 or +1"
        )

    # -----------------------------------------------------
    # CONTROL VOLUMES
    # -----------------------------------------------------
    #
    # (center_x, center_y, center_z),
    # (radius_x, radius_y, radius_z)
    #
    # The lower volume remains broad enough to disappear
    # naturally into the helmet.
    #
    # Successive volumes become smaller and travel upward
    # and rearward, producing the KUMA swept-fin silhouette.
    # -----------------------------------------------------

    controls = (
        (
            (
                0.0,
                -9.0,
                1.0,
            ),
            (
                8.5,
                7.5,
                5.5,
            ),
        ),
        (
            (
                side * 3.0,
                -1.0,
                -0.5,
            ),
            (
                7.5,
                8.0,
                5.0,
            ),
        ),
        (
            (
                side * 6.0,
                8.0,
                -3.5,
            ),
            (
                5.5,
                6.5,
                4.0,
            ),
        ),
        (
            (
                side * 8.5,
                16.0,
                -6.5,
            ),
            (
                3.5,
                4.5,
                3.0,
            ),
        ),
    )

    volumes = []

    for (
        center,
        radii,
    ) in controls:

        mesh = trimesh.creation.icosphere(
            subdivisions=3,
            radius=1.0,
        )

        mesh.apply_scale(
            np.asarray(
                radii,
                dtype=float,
            )
        )

        mesh.apply_translation(
            np.asarray(
                center,
                dtype=float,
            )
        )

        volumes.append(
            mesh
        )

    combined = trimesh.util.concatenate(
        volumes
    )

    fin = combined.convex_hull

    fin.remove_unreferenced_vertices()

    fin.fix_normals()

    if not fin.is_watertight:
        raise RuntimeError(
            "Generated KUMA swept ear is not watertight."
        )

    if not fin.is_volume:
        raise RuntimeError(
            "Generated KUMA swept ear does not form a valid volume."
        )

    return apply_material(
        fin,
        DARK_METAL,
    )


# =========================================================
# EXPORT HELPERS
# =========================================================

def export_scene(
    destination,
    parts,
):
    scene = trimesh.Scene()

    for (
        name,
        mesh,
    ) in parts:
        scene.add_geometry(
            mesh,
            node_name=name,
            geom_name=name,
        )

    destination.write_bytes(
        trimesh.exchange.gltf.export_glb(
            scene
        )
    )


def export_single(
    destination,
    name,
    mesh,
):
    export_scene(
        destination,
        [
            (
                name,
                mesh,
            )
        ],
    )


# =========================================================
# SEED NON-HEAD PARTS FROM PROVEN LIVING BODY
# =========================================================

head_files = {
    "head_shell.glb",
    "face_glass.glb",
    "ear_left.glb",
    "ear_right.glb",
    "pod_left.glb",
    "pod_right.glb",
    "torso.glb",
    "arm_left.glb",
    "arm_right.glb",
    "foot_left.glb",
    "foot_right.glb",
    "chest_badge.glb",
    "neck.glb",
    "body_bottom.glb",
    "rear_panel.glb",
    "rear_light.glb",
}

for source_path in SOURCE_PARTS.glob(
    "*.glb"
):
    if (
        source_path.name
        in head_files
    ):
        continue

    shutil.copy2(
        source_path,
        REFERENCE_PARTS
        / source_path.name,
    )



# =========================================================
# BODY-3A1 CANONICAL FLOATING BODY
# =========================================================
#
# Locked KUMA proportions:
#
# torso:
#     92 x 78 x 76
#
# arm:
#     27 x 51 x 30
#
# neck:
#     48 x 15 x 43
#
# chest badge:
#     29 x 31
#
# Feet are intentionally removed.
# =========================================================

for stale_name in (
    "foot_left.glb",
    "foot_right.glb",
):
    stale_path = (
        REFERENCE_PARTS
        / stale_name
    )

    stale_path.unlink(
        missing_ok=True
    )


# ---------------------------------------------------------
# TORSO SHELL
# ---------------------------------------------------------

torso = superellipsoid(
    (
        46.0,
        39.0,
        38.0,
    ),
    WHITE_SHELL,
    vertical_power=0.52,
    horizontal_power=0.44,
    latitude_steps=40,
    longitude_steps=80,
)

export_single(
    REFERENCE_PARTS
    / "torso.glb",
    "KUMA_Canonical_Torso",
    torso,
)


# ---------------------------------------------------------
# NECK / GIMBAL
# ---------------------------------------------------------

neck = superellipsoid(
    (
        24.0,
        7.5,
        21.5,
    ),
    DARK_METAL,
    vertical_power=0.58,
    horizontal_power=0.54,
    latitude_steps=28,
    longitude_steps=56,
)

export_single(
    REFERENCE_PARTS
    / "neck.glb",
    "KUMA_Canonical_Neck",
    neck,
)


# ---------------------------------------------------------
# FLOATING DARK UNDERSIDE
# ---------------------------------------------------------

body_bottom = superellipsoid(
    (
        31.0,
        12.0,
        29.0,
    ),
    DARK_METAL,
    vertical_power=0.52,
    horizontal_power=0.48,
    latitude_steps=30,
    longitude_steps=64,
)

export_single(
    REFERENCE_PARTS
    / "body_bottom.glb",
    "KUMA_Canonical_BodyBottom",
    body_bottom,
)


# ---------------------------------------------------------
# ARM PODS
# ---------------------------------------------------------

for arm_name in (
    "arm_left",
    "arm_right",
):
    arm = superellipsoid(
        (
            13.5,
            25.5,
            15.0,
        ),
        WHITE_SHELL,
        vertical_power=0.56,
        horizontal_power=0.52,
        latitude_steps=32,
        longitude_steps=64,
    )

    export_single(
        REFERENCE_PARTS
        / f"{arm_name}.glb",
        f"KUMA_Canonical_{arm_name}",
        arm,
    )


# ---------------------------------------------------------
# CHEST BADGE
# ---------------------------------------------------------

badge_base = superellipsoid(
    (
        14.5,
        15.5,
        3.8,
    ),
    DARK_METAL,
    vertical_power=0.42,
    horizontal_power=0.38,
    latitude_steps=28,
    longitude_steps=64,
)


def badge_stroke(
    *,
    extents,
    angle,
    position,
):
    mesh = trimesh.creation.box(
        extents=extents
    )

    mesh.visual = (
        trimesh.visual.TextureVisuals(
            material=BLUE_EMISSIVE
        )
    )

    if angle:
        mesh.apply_transform(
            trimesh.transformations.rotation_matrix(
                math.radians(angle),
                (
                    0.0,
                    0.0,
                    1.0,
                ),
            )
        )

    mesh.apply_translation(
        np.asarray(
            position,
            dtype=float,
        )
    )

    return mesh


badge_k_vertical = badge_stroke(
    extents=(
        2.8,
        18.0,
        1.2,
    ),
    angle=0.0,
    position=(
        -3.5,
        0.0,
        4.2,
    ),
)

badge_k_upper = badge_stroke(
    extents=(
        2.6,
        11.0,
        1.2,
    ),
    angle=-45.0,
    position=(
        2.0,
        4.0,
        4.2,
    ),
)

badge_k_lower = badge_stroke(
    extents=(
        2.6,
        11.0,
        1.2,
    ),
    angle=45.0,
    position=(
        2.0,
        -4.0,
        4.2,
    ),
)

export_scene(
    REFERENCE_PARTS
    / "chest_badge.glb",
    [
        (
            "KUMA_Canonical_Badge",
            badge_base,
        ),
        (
            "KUMA_K_Vertical",
            badge_k_vertical,
        ),
        (
            "KUMA_K_Upper",
            badge_k_upper,
        ),
        (
            "KUMA_K_Lower",
            badge_k_lower,
        ),
    ],
)


# ---------------------------------------------------------
# REAR STATUS PANEL
# ---------------------------------------------------------

rear_panel = superellipsoid(
    (
        24.0,
        16.0,
        2.5,
    ),
    DARK_METAL,
    vertical_power=0.40,
    horizontal_power=0.34,
    latitude_steps=28,
    longitude_steps=64,
)

export_single(
    REFERENCE_PARTS
    / "rear_panel.glb",
    "KUMA_Canonical_RearPanel",
    rear_panel,
)


# ---------------------------------------------------------
# REAR BLUE STATUS STRIP
# ---------------------------------------------------------

rear_light = superellipsoid(
    (
        17.0,
        2.8,
        1.5,
    ),
    BLUE_EMISSIVE,
    vertical_power=0.36,
    horizontal_power=0.32,
    latitude_steps=20,
    longitude_steps=48,
)

export_single(
    REFERENCE_PARTS
    / "rear_light.glb",
    "KUMA_Canonical_RearLight",
    rear_light,
)


# =========================================================
# REFERENCE HEAD SHELL
# =========================================================
#
# Front:
#     wide rounded-square.
#
# Side:
#     substantial white rear volume.
#
# Back:
#     smooth bulbous shell.
# =========================================================

head = superellipsoid(
    (
        64.0,
        47.5,
        51.0,
    ),
    WHITE_SHELL,
    vertical_power=0.48,
    horizontal_power=0.36,
)


export_single(
    REFERENCE_PARTS
    / "head_shell.glb",
    "KUMA_Reference_HeadShell",
    head,
)


# =========================================================
# DEEP CURVED VISOR
# =========================================================

visor = superellipsoid(
    (
        51.0,
        36.0,
        12.5,
    ),
    VISOR_GLASS,
    vertical_power=0.38,
    horizontal_power=0.30,
    latitude_steps=36,
    longitude_steps=88,
)


export_single(
    REFERENCE_PARTS
    / "face_glass.glb",
    "KUMA_Reference_VisorGlass",
    visor,
)


# =========================================================
# EARS
# =========================================================

for (
    side,
    name,
) in (
    (
        -1,
        "ear_left",
    ),
    (
        1,
        "ear_right",
    ),
):

    outer = rounded_swept_fin_ear(
        side=side
    )

    glow = ear_glow_strip(
        side=side
    )

    export_scene(
        REFERENCE_PARTS
        / f"{name}.glb",
        [
            (
                f"{name}_outer",
                outer,
            ),
            (
                f"{name}_glow",
                glow,
            ),
        ],
    )


# =========================================================
# SIDE PODS
# =========================================================

def build_pod(
    *,
    side,
):
    outer_shell = x_cylinder(
        radius=25.0,
        length=18.5,
        material=WHITE_SHELL,
    )

    inner_housing = x_cylinder(
        radius=20.0,
        length=20.0,
        material=DARK_METAL,
    )

    blue_ring = x_cylinder(
        radius=17.0,
        length=3.0,
        material=BLUE_EMISSIVE,
    )

    dark_center = x_cylinder(
        radius=11.3,
        length=3.2,
        material=DARK_METAL,
    )

    outward = (
        side * 10.0
    )

    blue_ring.apply_translation(
        (
            outward,
            0,
            0,
        )
    )

    dark_center.apply_translation(
        (
            side * 10.7,
            0,
            0,
        )
    )

    return [
        (
            "outer_shell",
            outer_shell,
        ),
        (
            "inner_housing",
            inner_housing,
        ),
        (
            "blue_ring",
            blue_ring,
        ),
        (
            "dark_center",
            dark_center,
        ),
    ]


export_scene(
    REFERENCE_PARTS
    / "pod_left.glb",
    build_pod(
        side=-1
    ),
)

export_scene(
    REFERENCE_PARTS
    / "pod_right.glb",
    build_pod(
        side=1
    ),
)


# =========================================================
# VALIDATION
# =========================================================

required = (
    "head_shell.glb",
    "face_glass.glb",
    "ear_left.glb",
    "ear_right.glb",
    "pod_left.glb",
    "pod_right.glb",
    "torso.glb",
    "arm_left.glb",
    "arm_right.glb",
    "chest_badge.glb",
    "neck.glb",
    "body_bottom.glb",
    "rear_panel.glb",
    "rear_light.glb",
)

for name in required:

    target = (
        REFERENCE_PARTS
        / name
    )

    if not target.is_file():
        raise RuntimeError(
            f"Missing reference part: {name}"
        )

    loaded = trimesh.load(
        target,
        force="scene",
    )

    if not loaded.geometry:
        raise RuntimeError(
            f"Empty reference part: {name}"
        )

    print(
        "PASS",
        name,
        "geometry=",
        len(
            loaded.geometry
        ),
        "bytes=",
        target.stat().st_size,
    )


print()
print(
    "PASS — BODY-3A1 canonical floating KUMA body built."
)
