"""Editable Blender file: the actual Shino meshes, a skinned rig and one action per take."""
import bpy, json, math, tempfile, shutil
import numpy as np
from pathlib import Path
from mathutils import Matrix, Vector, Euler
from rig import ROOT, read_glb, FPS

def save_workshop(rig,takes):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    gl,_=read_glb(ROOT/'Assets/Shino.vrm')
    names={}
    for entry in gl['extensions']['VRM']['humanoid']['humanBones']:
        n=entry['bone']
        if 'ThumbProximal' in n:n=n.replace('ThumbProximal','ThumbMetacarpal')
        elif 'ThumbIntermediate' in n:n=n.replace('ThumbIntermediate','ThumbProximal')
        names[n]=gl['nodes'][entry['node']]['name']
    with tempfile.TemporaryDirectory() as tmp:
        original=Path(tmp)/'Shino.glb'
        shutil.copyfile(ROOT/'Assets/Shino.vrm',original)
        bpy.ops.import_scene.gltf(filepath=str(original),bone_heuristic='TEMPERANCE',import_pack_images=True)
    armatures=[obj for obj in bpy.context.scene.objects if obj.type=='ARMATURE']
    if not armatures:raise ValueError('Shino armature missing')
    basis=(Matrix.Rotation(math.pi,3,'Z')@Matrix.Rotation(math.pi/2,3,'X')).to_quaternion()
    # Share actions between armatures with the same rest transforms (glTF may split skins).
    for number,arm in enumerate(armatures):
        arm.animation_data_create();arm.show_in_front=False
        bones={n:arm.pose.bones.get(raw) for n,raw in names.items()}
        bones={n:b for n,b in bones.items() if b is not None}
        if not bones:continue
        transforms={n:(arm.matrix_world@b.bone.matrix_local).to_quaternion().inverted()@basis for n,b in bones.items()}
        for key,frames in takes.items():
            action=bpy.data.actions.new(key if number==0 else key+' · '+arm.name)
            action.use_fake_user=True
            slot=action.slots.new('OBJECT',arm.name)
            arm.animation_data.action=action;arm.animation_data.action_slot=slot
            channelbag=action.layers.new('Сино').strips.new(type='KEYFRAME').channelbags.new(slot)
            def curve(data_path,table):
                for col in range(table.shape[1]):
                    f=channelbag.fcurves.new(data_path,index=col)
                    keys=f.keyframe_points;keys.add(len(table));co=np.column_stack([np.arange(1,len(table)+1),table[:,col]]).astype('f')
                    keys.foreach_set('co',co.ravel())
                    linear=bpy.types.Keyframe.bl_rna.properties['interpolation'].enum_items['LINEAR'].value
                    keys.foreach_set('interpolation',np.full(len(table),linear,dtype='i'));f.update()
            for n,bone in bones.items():
                if n in ('leftEye','rightEye','jaw'):continue
                bone.rotation_mode='QUATERNION';change=transforms[n];undo=change.inverted()
                coords=np.array([tuple(change@f.q[n]@undo) for f in frames])
                for i in range(1,len(coords)):
                    if coords[i-1]@coords[i]<0:coords[i]*=-1
                curve(bone.path_from_id('rotation_quaternion'),coords)
                if n=='hips':
                    curve(bone.path_from_id('location'),np.array([tuple(change@(f.hips-rig.rest['hips'])) for f in frames]))
            if key=='hello':arm['preview_action']=action.name
        arm.animation_data.action=bpy.data.actions[arm['preview_action']]
        arm.animation_data.action_slot=arm.animation_data.action.slots[0]
    scene=bpy.context.scene;scene.render.fps=FPS;scene.frame_start=1;scene.frame_end=len(takes['hello']);scene.frame_set(41)
    for obj in bpy.context.selected_objects:obj.select_set(False)
    bpy.context.view_layer.objects.active=armatures[0]
    for area in bpy.context.screen.areas:
        if area.type!='VIEW_3D':continue
        space=area.spaces.active;space.overlay.show_overlays=False;space.shading.type='SOLID'
        space.shading.color_type='TEXTURE';space.shading.light='STUDIO';space.shading.show_shadows=True
        view=space.region_3d;view.view_distance=2.7;view.view_location=(0,0,.86)
        view.view_rotation=Vector((.16,-1,-.05)).to_track_quat('-Z','Y')
        view.view_perspective='ORTHO'
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'MotionSource/Сино — анимации.blend'),compress=True)
