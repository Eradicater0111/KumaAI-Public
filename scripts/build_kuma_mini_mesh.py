from __future__ import annotations

from pathlib import Path
import math

import numpy as np
import trimesh


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

MODEL_DIR = (
    ROOT
    / "app"
    / "ui"
    / "assets"
    / "kuma_mini"
    / "models"
)

PART_DIR = (
    MODEL_DIR
    / "parts"
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

PART_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# KUMA MATERIAL COLORS
# =========================================================

SHELL = (
    225,
    228,
    234,
    255,
)

SHELL_DARK = (
    118,
    124,
    136,
    255,
)

FACE_GLASS = (
    4,
    9,
    18,
    255,
)

DARK_METAL = (
    48,
    54,
    66,
    255,
)

BLUE_LIGHT = (
    96,
    174,
    255,
    255,
)

WARM_LIGHT = (
    255,
    219,
    171,
    255,
)

BADGE = (
    12,
    17,
    27,
    255,
)


def make_pbr_material(
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
        "metallicFactor": float(metallic),
        "roughnessFactor": float(roughness),
    }

    if emissive is not None:
        kwargs["emissiveFactor"] = emissive

    return (
        trimesh.visual.material.PBRMaterial(
            **kwargs
        )
    )


SHELL_MATERIAL = make_pbr_material(
    name="KUMA_Shell",
    color=(
        238,
        240,
        244,
        255,
    ),
    metallic=0.34,
    roughness=0.20,
)

SHELL_DARK_MATERIAL = make_pbr_material(
    name="KUMA_ShellDark",
    color=(
        53,
        58,
        68,
        255,
    ),
    metallic=0.58,
    roughness=0.22,
)

FACE_MATERIAL = make_pbr_material(
    name="KUMA_Visor",
    color=(
        3,
        7,
        15,
        255,
    ),
    metallic=0.46,
    roughness=0.055,
)

DARK_METAL_MATERIAL = make_pbr_material(
    name="KUMA_DarkMetal",
    color=(
        33,
        38,
        48,
        255,
    ),
    metallic=0.82,
    roughness=0.17,
)

BLUE_LIGHT_MATERIAL = make_pbr_material(
    name="KUMA_BlueLight",
    color=(
        75,
        154,
        255,
        255,
    ),
    metallic=0.05,
    roughness=0.12,
    emissive=(
        0.12,
        0.40,
        1.0,
    ),
)

WARM_LIGHT_MATERIAL = make_pbr_material(
    name="KUMA_WarmLight",
    color=(
        255,
        226,
        184,
        255,
    ),
    metallic=0.04,
    roughness=0.12,
    emissive=(
        1.0,
        0.48,
        0.15,
    ),
)

BADGE_MATERIAL = make_pbr_material(
    name="KUMA_Badge",
    color=(
        10,
        15,
        24,
        255,
    ),
    metallic=0.55,
    roughness=0.13,
)


def material_for_color(
    rgba,
):
    if tuple(rgba) == tuple(SHELL):
        return SHELL_MATERIAL

    if tuple(rgba) == tuple(SHELL_DARK):
        return SHELL_DARK_MATERIAL

    if tuple(rgba) == tuple(FACE_GLASS):
        return FACE_MATERIAL

    if tuple(rgba) == tuple(DARK_METAL):
        return DARK_METAL_MATERIAL

    if tuple(rgba) == tuple(BLUE_LIGHT):
        return BLUE_LIGHT_MATERIAL

    if tuple(rgba) == tuple(WARM_LIGHT):
        return WARM_LIGHT_MATERIAL

    if tuple(rgba) == tuple(BADGE):
        return BADGE_MATERIAL

    return None


def colorize(
    mesh: trimesh.Trimesh,
    rgba,
):
    material = material_for_color(
        rgba
    )

    if material is not None:
        mesh.visual = (
            trimesh.visual.TextureVisuals(
                material=material
            )
        )

        return mesh

    mesh.visual.face_colors = np.tile(
        np.asarray(
            rgba,
            dtype=np.uint8,
        ),
        (
            len(mesh.faces),
            1,
        ),
    )

    return mesh



def _signed_power(
    value,
    exponent,
):
    value = np.asarray(
        value,
        dtype=float,
    )

    return (
        np.sign(value)
        * np.power(
            np.abs(value),
            exponent,
        )
    )


def superellipsoid(
    radii,
    color,
    *,
    vertical_power=0.55,
    horizontal_power=0.50,
    latitude_steps=32,
    longitude_steps=64,
):
    """
    Rounded rectangular 3D form.

    power == 1.0:
        ordinary ellipsoid

    power < 1.0:
        progressively squarer / more KUMA-like

    Used for the premium rounded head shell, visor and torso.
    """

    a, b, c = (
        float(value)
        for value in radii
    )

    vertices = [
        (
            0.0,
            -b,
            0.0,
        )
    ]

    for latitude_index in range(
        1,
        latitude_steps,
    ):
        phi = (
            -math.pi / 2.0
            + (
                math.pi
                * latitude_index
                / latitude_steps
            )
        )

        cos_phi = _signed_power(
            math.cos(phi),
            vertical_power,
        )

        sin_phi = _signed_power(
            math.sin(phi),
            vertical_power,
        )

        for longitude_index in range(
            longitude_steps
        ):
            theta = (
                2.0
                * math.pi
                * longitude_index
                / longitude_steps
            )

            cos_theta = _signed_power(
                math.cos(theta),
                horizontal_power,
            )

            sin_theta = _signed_power(
                math.sin(theta),
                horizontal_power,
            )

            vertices.append(
                (
                    a
                    * cos_phi
                    * cos_theta,

                    b
                    * sin_phi,

                    c
                    * cos_phi
                    * sin_theta,
                )
            )

    top_index = len(
        vertices
    )

    vertices.append(
        (
            0.0,
            b,
            0.0,
        )
    )

    faces = []

    # Bottom pole.
    first_ring = 1

    for longitude_index in range(
        longitude_steps
    ):
        next_index = (
            longitude_index + 1
        ) % longitude_steps

        faces.append(
            (
                0,
                first_ring
                + next_index,
                first_ring
                + longitude_index,
            )
        )

    # Intermediate latitude rings.
    ring_count = (
        latitude_steps - 1
    )

    for ring_index in range(
        ring_count - 1
    ):
        current_start = (
            1
            + ring_index
            * longitude_steps
        )

        next_start = (
            current_start
            + longitude_steps
        )

        for longitude_index in range(
            longitude_steps
        ):
            next_longitude = (
                longitude_index + 1
            ) % longitude_steps

            a0 = (
                current_start
                + longitude_index
            )

            a1 = (
                current_start
                + next_longitude
            )

            b0 = (
                next_start
                + longitude_index
            )

            b1 = (
                next_start
                + next_longitude
            )

            faces.append(
                (
                    a0,
                    a1,
                    b1,
                )
            )

            faces.append(
                (
                    a0,
                    b1,
                    b0,
                )
            )

    # Top pole.
    final_ring = (
        1
        + (
            ring_count - 1
        )
        * longitude_steps
    )

    for longitude_index in range(
        longitude_steps
    ):
        next_index = (
            longitude_index + 1
        ) % longitude_steps

        faces.append(
            (
                final_ring
                + longitude_index,
                final_ring
                + next_index,
                top_index,
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

    return colorize(
        mesh,
        color,
    )


def premium_ear_fin(
    color,
):
    """
    Swept tapered ear fin rather than the old cone.

    Local Y is vertical.
    """

    lower_y = -18.0
    upper_y = 21.0

    lower_half_x = 12.0
    lower_half_z = 7.5

    upper_half_x = 5.5
    upper_half_z = 4.5

    upper_shift_x = 4.5
    upper_shift_z = -2.5

    vertices = np.asarray(
        [
            (
                -lower_half_x,
                lower_y,
                -lower_half_z,
            ),
            (
                lower_half_x,
                lower_y,
                -lower_half_z,
            ),
            (
                lower_half_x,
                lower_y,
                lower_half_z,
            ),
            (
                -lower_half_x,
                lower_y,
                lower_half_z,
            ),

            (
                -upper_half_x
                + upper_shift_x,
                upper_y,
                -upper_half_z
                + upper_shift_z,
            ),
            (
                upper_half_x
                + upper_shift_x,
                upper_y,
                -upper_half_z
                + upper_shift_z,
            ),
            (
                upper_half_x
                + upper_shift_x,
                upper_y,
                upper_half_z
                + upper_shift_z,
            ),
            (
                -upper_half_x
                + upper_shift_x,
                upper_y,
                upper_half_z
                + upper_shift_z,
            ),
        ],
        dtype=float,
    )

    faces = np.asarray(
        [
            (0, 2, 1),
            (0, 3, 2),

            (4, 5, 6),
            (4, 6, 7),

            (0, 1, 5),
            (0, 5, 4),

            (1, 2, 6),
            (1, 6, 5),

            (2, 3, 7),
            (2, 7, 6),

            (3, 0, 4),
            (3, 4, 7),
        ],
        dtype=np.int64,
    )

    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        process=True,
    )

    return colorize(
        mesh,
        color,
    )


def ellipsoid(
    radii,
    color,
    *,
    subdivisions=4,
):
    mesh = (
        trimesh.creation.icosphere(
            subdivisions=subdivisions,
            radius=1.0,
        )
    )

    mesh.apply_scale(
        radii
    )

    return colorize(
        mesh,
        color,
    )


def box(
    extents,
    color,
):
    mesh = trimesh.creation.box(
        extents=extents
    )

    return colorize(
        mesh,
        color,
    )


def x_cylinder(
    *,
    radius,
    length,
    color,
    sections=64,
):
    mesh = trimesh.creation.cylinder(
        radius=radius,
        height=length,
        sections=sections,
    )

    # Cylinder is created on Z.
    # Rotate its longitudinal axis onto X.
    mesh.apply_transform(
        trimesh.transformations.rotation_matrix(
            math.radians(
                90.0
            ),
            (
                0.0,
                1.0,
                0.0,
            ),
        )
    )

    return colorize(
        mesh,
        color,
    )


def ear_fin(
    color,
):
    mesh = trimesh.creation.cone(
        radius=1.0,
        height=1.0,
        sections=48,
    )

    # Center the cone before scaling.
    mesh.apply_translation(
        (
            0.0,
            0.0,
            -0.5,
        )
    )

    mesh.apply_scale(
        (
            11.5,
            8.0,
            29.0,
        )
    )

    # Point the cone upward on Qt Quick 3D's Y axis.
    mesh.apply_transform(
        trimesh.transformations.rotation_matrix(
            math.radians(
                -90.0
            ),
            (
                1.0,
                0.0,
                0.0,
            ),
        )
    )

    return colorize(
        mesh,
        color,
    )


def export_scene(
    scene,
    destination,
):
    data = (
        trimesh.exchange.gltf.export_glb(
            scene
        )
    )

    destination.write_bytes(
        data
    )


def export_mesh(
    mesh,
    destination,
    *,
    name,
):
    scene = trimesh.Scene()

    scene.add_geometry(
        mesh,
        node_name=name,
        geom_name=name,
    )

    export_scene(
        scene,
        destination,
    )


def transform_copy(
    mesh,
    *,
    translate=None,
    rotate_degrees=None,
):
    result = mesh.copy()

    if rotate_degrees is not None:
        rx, ry, rz = (
            math.radians(value)
            for value
            in rotate_degrees
        )

        matrix = (
            trimesh.transformations.euler_matrix(
                rx,
                ry,
                rz,
                axes="sxyz",
            )
        )

        result.apply_transform(
            matrix
        )

    if translate is not None:
        result.apply_translation(
            translate
        )

    return result


# =========================================================
# CANONICAL LOCAL PARTS — TURNAROUND REFERENCE
# =========================================================
#
# Geometry authority:
# - front / left / right / back KUMA Mini turnaround
#
# Style authority:
# - premium KUMA Mini concept sheet
#
# Proportion rules:
# - head dominates silhouette
# - visor occupies most of front face
# - side pods are integrated into head
# - torso is short, wide and rounded
# - arms are compact with dark joints
# - ears are broad swept fins, not horns
# =========================================================


# ---------------------------------------------------------
# HEAD
# ---------------------------------------------------------

head_shell = superellipsoid(
    (
        70.0,   # width
        52.0,   # height
        45.0,   # depth
    ),
    SHELL,
    vertical_power=0.52,
    horizontal_power=0.40,
    latitude_steps=36,
    longitude_steps=72,
)


# Deep glossy visor.
#
# Wider front face, but shallow enough that side views retain
# the white rear helmet volume shown in the reference.
face_glass = superellipsoid(
    (
        59.0,
        39.0,
        11.8,
    ),
    FACE_GLASS,
    vertical_power=0.43,
    horizontal_power=0.34,
    latitude_steps=32,
    longitude_steps=72,
)


# ---------------------------------------------------------
# EARS
# ---------------------------------------------------------

ear_left = premium_ear_fin(
    SHELL
)

ear_right = premium_ear_fin(
    SHELL
)


# ---------------------------------------------------------
# BODY
# ---------------------------------------------------------

torso = superellipsoid(
    (
        39.0,
        34.0,
        31.5,
    ),
    SHELL,
    vertical_power=0.72,
    horizontal_power=0.66,
    latitude_steps=30,
    longitude_steps=64,
)


# Rounded segmented arm shells.
arm_left = superellipsoid(
    (
        13.0,
        22.0,
        14.5,
    ),
    SHELL_DARK,
    vertical_power=0.78,
    horizontal_power=0.72,
    latitude_steps=24,
    longitude_steps=48,
)

arm_right = arm_left.copy()


# Compact lower dark feet / body caps.
foot_left = superellipsoid(
    (
        16.0,
        9.0,
        18.5,
    ),
    DARK_METAL,
    vertical_power=0.72,
    horizontal_power=0.70,
    latitude_steps=22,
    longitude_steps=44,
)

foot_right = foot_left.copy()


# Chest badge from the reference.
chest_badge = superellipsoid(
    (
        13.5,
        12.5,
        3.8,
    ),
    BADGE,
    vertical_power=0.34,
    horizontal_power=0.34,
    latitude_steps=24,
    longitude_steps=48,
)


# ---------------------------------------------------------
# REAR STATUS PANEL
# ---------------------------------------------------------

rear_panel = superellipsoid(
    (
        18.0,
        12.0,
        3.8,
    ),
    DARK_METAL,
    vertical_power=0.40,
    horizontal_power=0.40,
    latitude_steps=20,
    longitude_steps=40,
)

rear_status_light = superellipsoid(
    (
        10.5,
        2.5,
        1.4,
    ),
    BLUE_LIGHT,
    vertical_power=0.55,
    horizontal_power=0.45,
    latitude_steps=16,
    longitude_steps=32,
)


# Physical eye meshes remain available as a fallback.
# Live production expressions are rendered on the digital visor.
eye_left = ellipsoid(
    (
        9.0,
        3.8,
        2.2,
    ),
    BLUE_LIGHT,
    subdivisions=3,
)

eye_right = eye_left.copy()

# =========================================================
# PODS — REFERENCE CIRCULAR HEADPHONE MODULES
# =========================================================


def make_pod(
    *,
    side,
):
    """
    Three concentric pod layers:

        dark outer housing
        white/silver structural ring
        blue/warm luminous center ring

    Local longitudinal axis is X so the pods sit naturally
    against the sides of Kuma's head.
    """

    outer = x_cylinder(
        radius=22.0,
        length=16.5,
        color=DARK_METAL,
    )

    structural_ring = x_cylinder(
        radius=18.0,
        length=18.0,
        color=SHELL,
    )

    luminous_ring = x_cylinder(
        radius=14.0,
        length=2.8,
        color=BLUE_LIGHT,
    )

    dark_center = x_cylinder(
        radius=10.5,
        length=3.1,
        color=FACE_GLASS,
    )

    if side == "left":

        structural_ring.apply_translation(
            (
                -0.8,
                0.0,
                0.0,
            )
        )

        luminous_ring.apply_translation(
            (
                -9.4,
                0.0,
                0.0,
            )
        )

        dark_center.apply_translation(
            (
                -10.1,
                0.0,
                0.0,
            )
        )

    else:

        structural_ring.apply_translation(
            (
                0.8,
                0.0,
                0.0,
            )
        )

        luminous_ring.apply_translation(
            (
                9.4,
                0.0,
                0.0,
            )
        )

        dark_center.apply_translation(
            (
                10.1,
                0.0,
                0.0,
            )
        )

    return (
        outer,
        structural_ring,
        luminous_ring,
        dark_center,
    )


pod_left = make_pod(
    side="left"
)

pod_right = make_pod(
    side="right"
)

# =========================================================
# EXPORT INDIVIDUAL RIG PARTS
# =========================================================

simple_parts = {
    "head_shell": head_shell,
    "face_glass": face_glass,
    "ear_left": ear_left,
    "ear_right": ear_right,
    "torso": torso,
    "arm_left": arm_left,
    "arm_right": arm_right,
    "foot_left": foot_left,
    "foot_right": foot_right,
    "chest_badge": chest_badge,
    "eye_left": eye_left,
    "eye_right": eye_right,
    "rear_panel": rear_panel,
    "rear_status_light": rear_status_light,
}

for name, mesh in simple_parts.items():

    export_mesh(
        mesh,
        PART_DIR
        / f"{name}.glb",
        name=name,
    )


def export_pod(
    name,
    meshes,
):
    scene = trimesh.Scene()

    for index, mesh in enumerate(
        meshes
    ):
        scene.add_geometry(
            mesh,
            node_name=(
                f"{name}_{index}"
            ),
            geom_name=(
                f"{name}_{index}"
            ),
        )

    export_scene(
        scene,
        PART_DIR
        / f"{name}.glb",
    )


export_pod(
    "pod_left",
    pod_left,
)

export_pod(
    "pod_right",
    pod_right,
)


# =========================================================
# COMPLETE CANONICAL KUMA — REFERENCE ASSEMBLY
# =========================================================

scene = trimesh.Scene()


def add(
    name,
    mesh,
    *,
    position,
    rotation=None,
):
    geometry = transform_copy(
        mesh,
        translate=position,
        rotate_degrees=rotation,
    )

    scene.add_geometry(
        geometry,
        node_name=name,
        geom_name=name,
    )


# ---------------------------------------------------------
# HEAD + VISOR
# ---------------------------------------------------------

add(
    "HeadShell",
    head_shell,
    position=(
        0.0,
        24.0,
        0.0,
    ),
)

add(
    "FaceGlass",
    face_glass,
    position=(
        0.0,
        21.0,
        43.5,
    ),
)


# ---------------------------------------------------------
# EARS
# ---------------------------------------------------------

add(
    "Ear_L",
    ear_left,
    position=(
        -46.0,
        72.0,
        -4.0,
    ),
    rotation=(
        0.0,
        -5.0,
        -11.0,
    ),
)

add(
    "Ear_R",
    ear_right,
    position=(
        46.0,
        72.0,
        -4.0,
    ),
    rotation=(
        0.0,
        5.0,
        11.0,
    ),
)


# ---------------------------------------------------------
# PODS
# ---------------------------------------------------------

for index, mesh in enumerate(
    pod_left
):
    add(
        f"Pod_L_{index}",
        mesh,
        position=(
            -73.0,
            20.0,
            0.0,
        ),
    )

for index, mesh in enumerate(
    pod_right
):
    add(
        f"Pod_R_{index}",
        mesh,
        position=(
            73.0,
            20.0,
            0.0,
        ),
    )


# ---------------------------------------------------------
# FALLBACK EYES
# ---------------------------------------------------------

add(
    "Eye_L",
    eye_left,
    position=(
        -26.0,
        21.0,
        55.0,
    ),
)

add(
    "Eye_R",
    eye_right,
    position=(
        26.0,
        21.0,
        55.0,
    ),
)


# ---------------------------------------------------------
# TORSO
# ---------------------------------------------------------

add(
    "Torso",
    torso,
    position=(
        0.0,
        -48.0,
        1.0,
    ),
)


# ---------------------------------------------------------
# ARMS
# ---------------------------------------------------------

add(
    "Arm_L",
    arm_left,
    position=(
        -45.0,
        -44.0,
        4.0,
    ),
    rotation=(
        0.0,
        0.0,
        -8.0,
    ),
)

add(
    "Arm_R",
    arm_right,
    position=(
        45.0,
        -44.0,
        4.0,
    ),
    rotation=(
        0.0,
        0.0,
        8.0,
    ),
)


# ---------------------------------------------------------
# LOWER BODY
# ---------------------------------------------------------

add(
    "Foot_L",
    foot_left,
    position=(
        -19.0,
        -76.0,
        10.0,
    ),
    rotation=(
        16.0,
        0.0,
        -7.0,
    ),
)

add(
    "Foot_R",
    foot_right,
    position=(
        19.0,
        -76.0,
        10.0,
    ),
    rotation=(
        16.0,
        0.0,
        7.0,
    ),
)


# ---------------------------------------------------------
# REAR STATUS MODULE
# ---------------------------------------------------------

add(
    "RearPanel",
    rear_panel,
    position=(
        0.0,
        -47.0,
        -31.0,
    ),
    rotation=(
        0.0,
        180.0,
        0.0,
    ),
)

add(
    "RearStatusLight",
    rear_status_light,
    position=(
        0.0,
        -47.0,
        -35.0,
    ),
    rotation=(
        0.0,
        180.0,
        0.0,
    ),
)


# ---------------------------------------------------------
# FRONT CHEST BADGE
# ---------------------------------------------------------

add(
    "ChestBadge",
    chest_badge,
    position=(
        0.0,
        -46.0,
        33.0,
    ),
)


complete_path = (
    MODEL_DIR
    / "kuma_mini.glb"
)

export_scene(
    scene,
    complete_path,
)

# =========================================================
# VALIDATION
# =========================================================

expected = (
    complete_path,
    *sorted(
        PART_DIR.glob(
            "*.glb"
        )
    ),
)

for path in expected:

    loaded = trimesh.load(
        path,
        force="scene",
    )

    if not isinstance(
        loaded,
        trimesh.Scene,
    ):
        raise RuntimeError(
            f"Invalid GLB scene: {path}"
        )

    if not loaded.geometry:
        raise RuntimeError(
            f"Empty GLB scene: {path}"
        )

    print(
        "PASS",
        path.relative_to(
            ROOT
        ),
        "geometry=",
        len(
            loaded.geometry
        ),
        "bytes=",
        path.stat().st_size,
    )


print()
print(
    "PASS — canonical KUMA Mini GLB build complete."
)
