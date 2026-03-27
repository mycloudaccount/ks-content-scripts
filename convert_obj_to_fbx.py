import bpy
import bmesh
import os
import sys

# ============================================================
# CLI ARGUMENTS (after --)
# ============================================================

if len(sys.argv) < 3:
    raise SystemExit(
        "Usage: blender -b -P convert_obj_to_fbx.py -- <input.obj> <output.fbx>"
    )

INPUT_OBJ_PATH = sys.argv[-2]
OUTPUT_FBX_PATH = sys.argv[-1]

# ============================================================
# VALIDATION
# ============================================================

in_obj = os.path.abspath(INPUT_OBJ_PATH)
out_fbx = os.path.abspath(OUTPUT_FBX_PATH)

if not os.path.exists(in_obj):
    raise SystemExit(f"Input OBJ not found: {in_obj}")

os.makedirs(os.path.dirname(out_fbx), exist_ok=True)

# ============================================================
# UTILITIES (BLENDER 5.0 + HEADLESS SAFE)
# ============================================================


def force_object_mode():
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')


def deselect_all():
    for o in bpy.context.selected_objects:
        o.select_set(False)


def set_active(obj):
    bpy.context.view_layer.objects.active = obj


def select_all_in_edit():
    bpy.ops.mesh.select_all(action='SELECT')


def mesh_stats(label, obj):
    mesh = obj.data
    print(
        f"{label}: "
        f"{len(mesh.polygons):,} faces | "
        f"{len(mesh.edges):,} edges | "
        f"{len(mesh.vertices):,} verts"
    )

# ============================================================
# MATERIAL SANITIZATION (BLENDER 5.0 SAFE)
# ============================================================


def force_opaque_material(mat):
    """
    Prevent alpha / transparency bugs in FBX → glTF.
    Blender 5.0 compatible.
    """
    mat.use_backface_culling = False
    mat.blend_method = 'OPAQUE'

    if not mat.use_nodes:
        return

    bsdf = None
    for node in mat.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            bsdf = node
            break

    if not bsdf:
        return

    # Force solid alpha
    bsdf.inputs['Alpha'].default_value = 1.0

    # Remove alpha texture links
    for link in list(mat.node_tree.links):
        if link.to_socket == bsdf.inputs['Alpha']:
            mat.node_tree.links.remove(link)


def sanitize_object_materials(obj):
    for mat in obj.data.materials:
        if mat:
            force_opaque_material(mat)

# ============================================================
# SCENE CLEAN
# ============================================================


force_object_mode()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# ============================================================
# IMPORT OBJ (MagicaVoxel)
# ============================================================

bpy.ops.wm.obj_import(filepath=in_obj)

mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not mesh_objs:
    raise SystemExit("No mesh objects were imported from the OBJ.")

# Join meshes (materials preserved)
deselect_all()
for o in mesh_objs:
    o.select_set(True)

set_active(mesh_objs[0])
bpy.ops.object.join()

obj = bpy.context.view_layer.objects.active
obj.name = "MV_Character"

mesh_stats("After import + join", obj)

# ============================================================
# TRANSFORMS (MIXAMO SAFE)
# ============================================================

bpy.ops.object.transform_apply(
    location=False,
    rotation=True,
    scale=True
)

# ============================================================
# GEOMETRY CLEANUP + OPTIMIZATION
# ============================================================

bpy.ops.object.mode_set(mode='EDIT')

bm = bmesh.from_edit_mesh(obj.data)
bmesh.ops.remove_doubles(
    bm,
    verts=bm.verts,
    dist=0.0001
)
bmesh.update_edit_mesh(obj.data)

select_all_in_edit()
bpy.ops.mesh.normals_make_consistent(inside=False)

bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.mesh.select_interior_faces()
bpy.ops.mesh.delete(type='FACE')

bpy.ops.object.mode_set(mode='OBJECT')
mesh_stats("After hollowing", obj)

# ============================================================
# PLANAR DISSOLVE
# ============================================================

bpy.ops.object.mode_set(mode='EDIT')

select_all_in_edit()
bpy.ops.mesh.dissolve_limited(
    angle_limit=0.0,
    delimit={'NORMAL', 'MATERIAL', 'SHARP'}
)

# ============================================================
# TRIANGLES → QUADS
# ============================================================

select_all_in_edit()
bpy.ops.mesh.tris_convert_to_quads(
    face_threshold=0.698,
    shape_threshold=0.698
)

select_all_in_edit()
bpy.ops.mesh.delete_loose()
select_all_in_edit()
bpy.ops.mesh.normals_make_consistent(inside=False)

bpy.ops.object.mode_set(mode='OBJECT')

mesh_stats("Final optimized mesh", obj)

# ============================================================
# SHADING
# ============================================================

for poly in obj.data.polygons:
    poly.use_smooth = False

if obj.data.materials:
    sanitize_object_materials(obj)
    print("✔ Materials sanitized (opaque, alpha stripped)")
else:
    print("⚠️ No materials found")

# ============================================================
# EXPORT FBX (MIXAMO READY)
# ============================================================

deselect_all()
obj.select_set(True)
set_active(obj)

bpy.ops.export_scene.fbx(
    filepath=out_fbx,
    use_selection=True,
    object_types={'MESH'},
    apply_unit_scale=True,
    bake_space_transform=False,
    add_leaf_bones=False,
    mesh_smooth_type='FACE',
    use_mesh_modifiers=True,
    path_mode='COPY',
    embed_textures=True
)

print("==============================================")
print("✔ Export complete (Blender 5.0 safe, opaque)")
print(out_fbx)
print("==============================================")
