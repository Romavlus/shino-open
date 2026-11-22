"""Package the two Shino looks using the signed model as their shared glTF buffer."""
import copy
import json
import shutil
import struct


def external_model(base):
    with base.open('rb') as f:
        f.seek(12)
        size, kind = struct.unpack('<II', f.read(8))
        assert kind == 0x4e4f534a
        model = json.loads(f.read(size))
    model['buffers'] = [dict(uri=base.name, byteLength=base.stat().st_size)]
    for view in model['bufferViews']:
        view['byteOffset'] = view.get('byteOffset', 0) + 28 + size
    return model


def replace_image(model, name, filename):
    image = next(i for i in model['images'] if i['name'] == name)
    image.pop('bufferView')
    image.pop('mimeType', None)
    image['uri'] = filename


def cherry(model):
    for name, image in [('EyeIris_00','iris'), ('Body_00','stockings'), ('Tops_01','shirt'),
                        ('Accessory_01','bow'), ('Bottoms_01','plaid'), ('Shoes_01','loafers')]:
        prefix = 'F00_001_' if name in ('Tops_01','Accessory_01','Bottoms_01','Shoes_01') else 'F00_000_'
        replace_image(model, prefix + name, 'cherry-' + image + '.png')
    for material, toon in zip(model['materials'], model['extensions']['VRM']['materialProperties']):
        name = toon['name']
        if 'HairBack' in name or name.endswith('HAIR_01'):
            color, shadow, emission = [.245,.126,.159,1], [.32,.19,.25,1], [.36,.235,.26,1]
        elif 'FaceBrow' in name:
            color, shadow, emission = [.27,.15,.18,1], [.29,.18,.22,1], [0,0,0,1]
        else:
            continue
        toon['vectorProperties'].update(_Color=color, _ShadeColor=shadow, _EmissionColor=emission)
        material['pbrMetallicRoughness']['baseColorFactor'] = color


def dress(model, pattern):
    nodes, skins = model['nodes'], model['skins']
    body = next(n for n in nodes if n.get('name') == 'Body')
    mesh = model['meshes'][body['mesh']]
    skin = skins[body['skin']]
    hips = next(b['node'] for b in model['extensions']['VRM']['humanoid']['humanBones'] if b['bone']=='hips')
    indices_by_name = {node['name']: i for i, node in enumerate(nodes)}
    for name, parent in pattern['guides']:
        index = len(nodes)
        nodes[indices_by_name[parent]].setdefault('children', []).append(index)
        nodes.append(dict(name=name))
        indices_by_name[name] = index
        skin['joints'].append(index)
    nodes[hips].setdefault('extras', {})['wrapDress'] = pattern['fit']
    base_view, base_accessor = len(model['bufferViews']), len(model['accessors'])
    model['buffers'].append(dict(uri='cardigan-cut.bin', byteLength=pattern['bytes']))
    model['bufferViews'].extend(dict(view,buffer=1) for view in pattern['views'])
    model['accessors'].extend(dict(a,bufferView=a['bufferView']+base_view) for a in pattern['accessors'])
    skin['inverseBindMatrices'] = base_accessor + pattern['bind']
    replace_image(model, 'F00_000_Body_00', 'cardigan-skin.png')
    skin_part = next(p for p in mesh['primitives'] if model['materials'][p['material']]['name'].endswith('Body_00_SKIN'))
    skin_part['attributes'].update({k:v+base_accessor for k,v in pattern['skinAttributes'].items()})
    mesh['primitives'] = [p for p in mesh['primitives'] if p is skin_part or 'HairBack' in model['materials'][p['material']]['name']]
    vrm = model['extensions']['VRM']
    skin_shader = vrm['materialProperties'][skin_part['material']]
    skin_shader['floatProperties'].update(_OutlineWidth=0, _OutlineWidthMode=0)
    skin_shader['keywordMap'] = {k:v for k,v in skin_shader['keywordMap'].items() if not k.startswith('MTOON_OUTLINE')}
    vrm['secondaryAnimation']['boneGroups'] = [g for g in vrm['secondaryAnimation']['boneGroups'] if g['comment'] != 'Skirt']
    for piece in pattern['pieces']:
        name = piece['name']
        material = dict(name=name, doubleSided=True, pbrMetallicRoughness=dict(
            metallicFactor=piece.get('metal',0), roughnessFactor=piece['roughness']))
        if piece.get('texture') == 'cardigan-knit.png':
            material['emissiveFactor'] = [.105,.091,.073]
        elif piece.get('texture') == 'cardigan-floral.png':
            material['emissiveFactor'] = [.003,.004,.008]
        if 'texture' in piece:
            s = len(model['samplers'])
            model['samplers'].append(dict(wrapS=10497,wrapT=10497,magFilter=9729,minFilter=9987))
            t = len(model['textures'])
            model['textures'].append(dict(sampler=s, source=len(model['images'])))
            model['images'].append(dict(name=name,uri=piece['texture']))
            material['pbrMetallicRoughness']['baseColorTexture'] = dict(index=t)
        mesh['primitives'].append(dict(material=len(model['materials']), indices=piece['indices']+base_accessor,
                                       attributes={k:v+base_accessor for k,v in piece['attributes'].items()}))
        model['materials'].append(material)
        vrm['materialProperties'].append(dict(name=name, shader='VRM_USE_GLTFSHADER', renderQueue=-1,
            floatProperties={}, vectorProperties={}, textureProperties={}, keywordMap={}, tagMap={}))


def package_wardrobe(assets, resources):
    common = external_model(resources/'Shino.vrm')
    pattern = json.loads((assets/'cardigan-cut.json').read_text())
    for name in ('Cherry','Cardigan'):
        model = copy.deepcopy(common)
        if name == 'Cherry':
            cherry(model)
        else:
            dress(model, pattern)
        for item in model['images'] + model['buffers'][1:]:
            if 'uri' in item:
                path = assets/item['uri']
                shutil.copy2(path, resources/path.name)
        (resources/('Shino'+name+'.gltf')).write_text(json.dumps(model,separators=(',',':')))
