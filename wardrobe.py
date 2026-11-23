"""Package the wardrobe, sharing the base mesh, rig, facial expressions and animation library."""
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


def set_hair_color(model,index,rgba,shadow,emission):
    mat=model['materials'][index]
    mat['pbrMetallicRoughness']['baseColorFactor']=[*((v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4) for v in rgba),1]
    toon=model['extensions']['VRM']['materialProperties'][index]
    toon['vectorProperties'].update(_Color=[*rgba,1],_ShadeColor=[*shadow,1],_EmissionColor=[*emission,1])


def hairstyle(model,kind,pattern,base_accessor):
    vrm=model['extensions']['VRM']
    node=next(n for n in model['nodes'] if n['name']=='Hair001')
    mesh=model['meshes'][node['mesh']]
    strands,barrette=mesh['primitives']
    colors={'rider':([.89,.218,.46],[.65,.18,.38],[.69,.34,.49]),
            'bordeaux':([.34,.16,.24],[.28,.14,.22],[.37,.24,.30])}
    if kind in colors:
        for idx in (14,15):set_hair_color(model,idx,*colors[kind])
        set_hair_color(model,4,[.14,.046,.074],[.17,.07,.10],[0,0,0])
    parts=[]
    for row in pattern['groups']:
        part=dict(strands,indices=base_accessor+row['indices'])
        if 'position' in row:part['attributes']=dict(part['attributes'],POSITION=base_accessor+row['position'])
        if row['role']=='teal':
            idx=len(model['materials']);part['material']=idx
            mat=copy.deepcopy(model['materials'][15]);toon=copy.deepcopy(vrm['materialProperties'][15])
            mat['name']=toon['name']='Deep teal underlayer HAIR'
            model['materials'].append(mat);vrm['materialProperties'].append(toon)
            set_hair_color(model,idx,[.067,.64,.66],[.069,.39,.47],[.11,.54,.58])
        parts.append(part)
    if pattern['clip']:parts.append(barrette)
    if parts:mesh['primitives']=parts
    else:
        # Keep the indexed mesh resource valid while removing its visible instance.
        node.pop('mesh');node.pop('skin')
    if kind in ('marine','bordeaux'):replace_image(model,'F00_000_EyeIris_00',kind+'-iris.png')
    if kind=='marine':replace_image(model,'F00_001_Shoes_01','marine-loafers.png')


def dress(model, pattern, stem):
    nodes, skins = model['nodes'], model['skins']
    body = next(n for n in nodes if n.get('name') == 'Body')
    mesh = model['meshes'][body['mesh']]
    skin = skins[body['skin']]
    hips = next(b['node'] for b in model['extensions']['VRM']['humanoid']['humanBones'] if b['bone']=='hips')
    indices_by_name = {node['name']: i for i, node in enumerate(nodes)}
    for name, parent, *pivot in pattern['guides']:
        index = len(nodes)
        nodes[indices_by_name[parent]].setdefault('children', []).append(index)
        nodes.append(dict(name=name,**(dict(translation=pivot[0]) if pivot else {})))
        indices_by_name[name] = index
        skin['joints'].append(index)
    if pattern['fit']:nodes[hips].setdefault('extras', {})['wrapDress'] = pattern['fit']
    base_view, base_accessor = len(model['bufferViews']), len(model['accessors'])
    model['buffers'].append(dict(uri=stem+'-cut.bin', byteLength=pattern['bytes']))
    model['bufferViews'].extend(dict(view,buffer=1) for view in pattern['views'])
    model['accessors'].extend(dict(a,bufferView=a['bufferView']+base_view) for a in pattern['accessors'])
    skin['inverseBindMatrices'] = base_accessor + pattern['bind']
    replace_image(model,'F00_000_Body_00','cardigan-skin.png' if stem=='cardigan' else 'atelier-skin.png')
    if stem!='cardigan':replace_image(model,'F00_001_01_Body_00_nml','atelier-skin-n.png')
    skin_part = next(p for p in mesh['primitives'] if model['materials'][p['material']]['name'].endswith('Body_00_SKIN'))
    if 'visibleBody' in pattern:skin_part['indices']=base_accessor+pattern['visibleBody']
    skin_part['attributes'].update({k:v+base_accessor for k,v in pattern['skinAttributes'].items()})
    mesh['primitives'] = [p for p in mesh['primitives'] if p is skin_part or (p['material']==14 and stem!='bordeaux') or (stem=='marine' and p['material']==13)]
    vrm = model['extensions']['VRM']
    skin_shader = vrm['materialProperties'][skin_part['material']]
    skin_shader['floatProperties'].update(_OutlineWidth=0, _OutlineWidthMode=0)
    skin_shader['keywordMap'] = {k:v for k,v in skin_shader['keywordMap'].items() if not k.startswith('MTOON_OUTLINE')}
    vrm['secondaryAnimation']['boneGroups'] = [g for g in vrm['secondaryAnimation']['boneGroups'] if g['comment'] != 'Skirt']
    if 'hair' in pattern:
        hairstyle(model,stem,pattern['hair'],base_accessor)
        if stem in ('rider','bordeaux'):
            vrm['secondaryAnimation']['boneGroups']=[g for g in vrm['secondaryAnimation']['boneGroups'] if g['comment']=='Bust']
        for g in pattern['springGroups']:
            vrm['secondaryAnimation']['boneGroups'].append(dict(g,bones=[indices_by_name[n] for n in g['bones']]))
    file_textures={}
    def texture(filename):
        if filename not in file_textures:
            if not file_textures:model['samplers'].append(dict(wrapS=10497,wrapT=10497,magFilter=9729,minFilter=9987))
            file_textures[filename]=len(model['textures'])
            model['textures'].append(dict(sampler=len(model['samplers'])-1,source=len(model['images'])))
            model['images'].append(dict(name=filename,uri=filename))
        return file_textures[filename]
    for piece in pattern['pieces']:
        name = piece['name']
        material = dict(name=name, doubleSided=True, pbrMetallicRoughness=dict(
            metallicFactor=piece.get('metal',0), roughnessFactor=piece['roughness']))
        if name=='Antique silver zip and snaps':material['emissiveFactor']=[.065,.062,.063]
        if piece.get('texture') == 'cardigan-knit.png':
            material['emissiveFactor'] = [.105,.091,.073]
        elif piece.get('texture') == 'cardigan-floral.png':
            material['emissiveFactor'] = [.003,.004,.008]
        if 'texture' in piece:
            material['pbrMetallicRoughness']['baseColorTexture'] = dict(index=texture(piece['texture']))
        if 'normal' in piece:material['normalTexture']=dict(index=texture(piece['normal']),scale=piece['normalScale'])
        if 'alphaCutoff' in piece:
            material.update(alphaMode='MASK',alphaCutoff=piece['alphaCutoff'])
        if 'anisotropy' in piece:
            ext='KHR_materials_anisotropy'
            if ext not in model['extensionsUsed']:model['extensionsUsed'].append(ext)
            material.setdefault('extensions',{})[ext]=dict(anisotropyStrength=piece['anisotropy'],anisotropyRotation=1.5707963)
        if 'sheen' in piece:
            ext='KHR_materials_sheen'
            if ext not in model['extensionsUsed']:model['extensionsUsed'].append(ext)
            material.setdefault('extensions',{})[ext]=dict(sheenColorFactor=piece['sheen'],sheenRoughnessFactor=piece.get('sheenRoughness',.61))
        mesh['primitives'].append(dict(material=len(model['materials']), indices=piece['indices']+base_accessor,
                                       attributes={k:v+base_accessor for k,v in piece['attributes'].items()}))
        model['materials'].append(material)
        vrm['materialProperties'].append(dict(name=name, shader='VRM_USE_GLTFSHADER', renderQueue=-1,
            floatProperties={}, vectorProperties={}, textureProperties={}, keywordMap={}, tagMap={}))


def package_wardrobe(assets, resources):
    common = external_model(resources/'Shino.vrm')
    for name in ('Cherry','Cardigan','Rider','Marine','Bordeaux'):
        model = copy.deepcopy(common)
        if name == 'Cherry':
            cherry(model)
        else:
            stem=name.lower()
            dress(model,json.loads((assets/(stem+'-cut.json')).read_text()),stem)
        for item in model['images'] + model['buffers'][1:]:
            if 'uri' in item:
                path = assets/item['uri']
                shutil.copy2(path, resources/path.name)
        (resources/('Shino'+name+'.gltf')).write_text(json.dumps(model,separators=(',',':')))
