import bpy
import os
import sys
import bmesh
import mathutils
import tempfile
import shutil

# ============================================================
# CONFIG
# ============================================================
INPUT_DIR = None
OUTPUT_GLB = None
FPS = 30

# ============================================================
# CLI ARGS
# ============================================================
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []

if len(argv) < 2:
    raise SystemExit(
        "Usage:\n"
        "  blender -b -P merge_fbxs.py -- <input_dir> <output.glb>"
    )

INPUT_DIR = os.path.abspath(argv[0])
OUTPUT_GLB = os.path.abspath(argv[1])

if not os.path.isdir(INPUT_DIR):
    raise SystemExit(f"Input directory not found: {INPUT_DIR}")

os.makedirs(os.path.dirname(OUTPUT_GLB), exist_ok=True)

# ============================================================
# RESET SCENE
# ============================================================
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS

# ============================================================
# HELPERS
# ============================================================


def import_fbx(path):
    bpy.ops.import_scene.fbx(filepath=path)


def get_armatures():
    return [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]


def bone_signature(armature):
    return [b.name for b in armature.data.bones]


def action_name_from_file(path):
    return os.path.splitext(os.path.basename(path))[0].lower()


def cleanup_except(keep_armature):
    keep = {keep_armature}
    for obj in bpy.context.scene.objects:
        if obj.parent == keep_armature:
            keep.add(obj)
    for obj in list(bpy.context.scene.objects):
        if obj not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)

# ============================================================
# MATERIAL SANITIZER (THE FIX)
# ============================================================


def sanitize_material(mat):
    """
    Force a glTF-safe opaque PBR material.
    This is the critical fix.
    """
    mat.use_backface_culling = False
    mat.blend_method = 'OPAQUE'

    if not mat.use_nodes:
        return

    nt = mat.node_tree

    bsdf = None
    for n in nt.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            bsdf = n
            break

    if not bsdf:
        return

    # Force solid alpha
    bsdf.inputs["Alpha"].default_value = 1.0

    # Remove ANY alpha links
    for link in list(nt.links):
        if link.to_socket == bsdf.inputs["Alpha"]:
            nt.links.remove(link)

    # Safety: ensure Base Color is connected or solid
    if not bsdf.inputs["Base Color"].is_linked:
        bsdf.inputs["Base Color"].default_value = (1, 1, 1, 1)


def sanitize_object_materials(obj):
    for mat in obj.data.materials:
        if mat:
            sanitize_material(mat)

# ============================================================
# NORMALS (SAFE)
# ============================================================


def fix_mesh_normals(mesh_obj):
    bpy.context.view_layer.objects.active = mesh_obj
    mesh_obj.select_set(True)

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    sanitize_object_materials(mesh_obj)
    mesh_obj.select_set(False)

# ============================================================
# IMPORT + ACTIONS
# ============================================================


armature = None
reference_bones = None

for file in sorted(os.listdir(INPUT_DIR)):
    if not file.lower().endswith(".fbx"):
        continue

    path = os.path.join(INPUT_DIR, file)
    print(f"📥 Importing {file}")
    import_fbx(path)

    armatures = get_armatures()
    if not armatures:
        raise RuntimeError(f"No armature found in {file}")

    current = armatures[-1]

    if armature is None:
        armature = current
        reference_bones = bone_signature(armature)
    else:
        if bone_signature(current) != reference_bones:
            raise RuntimeError(f"Bone mismatch in {file}")

    if not current.animation_data or not current.animation_data.action:
        raise RuntimeError(f"No animation in {file}")

    current.animation_data.action.name = action_name_from_file(path)
    cleanup_except(armature)

# ============================================================
# FIX MESHES
# ============================================================

for obj in bpy.context.scene.objects:
    if obj.type == "MESH" and obj.parent == armature:
        fix_mesh_normals(obj)

# ============================================================
# PREVIEW RENDER (PROVES CORRECTNESS)
# ============================================================


def render_preview(path):
    cam = bpy.data.cameras.new("PreviewCam")
    cam_obj = bpy.data.objects.new("PreviewCam", cam)
    scene.collection.objects.link(cam_obj)

    light = bpy.data.lights.new("PreviewLight", type='AREA')
    light_obj = bpy.data.objects.new("PreviewLight", light)
    scene.collection.objects.link(light_obj)

    cam_obj.location = (0, -2.5, 1.0)
    cam_obj.rotation_euler = (1.2, 0, 0)
    light_obj.location = (0, -1.0, 2.0)
    light.energy = 1500

    scene.camera = cam_obj
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path

    bpy.ops.render.render(write_still=True)


preview_path = os.path.join(os.path.dirname(OUTPUT_GLB), "preview.png")
render_preview(preview_path)
print(f"🖼️ Preview rendered: {preview_path}")

# ============================================================
# EXPORT GLB (CLEAN)
# ============================================================

bpy.ops.export_scene.gltf(
    filepath=OUTPUT_GLB,
    export_format="GLB",
    export_animations=True,
    export_animation_mode="ACTIONS",
    export_force_sampling=True,
    export_skins=True,
    export_apply=False,
    export_normals=True,
)

print(f"✅ Export complete: {OUTPUT_GLB}")
