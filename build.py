"""Build a self-contained, signed macOS bundle entirely from this directory."""
from pathlib import Path
import argparse, hashlib, json, platform, plistlib, shutil, subprocess, tempfile
from optimize import optimize_model
from wardrobe import package_wardrobe
ROOT=Path(__file__).resolve().parent
BUNDLE_ID='org.shinoopen.desktop'
def run(*args):subprocess.run(args,check=True)
def build(output):
    output=output.expanduser().absolute()
    if output.exists():
        with (output/'Contents/Info.plist').open('rb') as cfg:existing=plistlib.load(cfg)
        if existing.get('CFBundleIdentifier')!=BUNDLE_ID:raise ValueError(f'Another application already occupies {output}')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.shino-build-') as tmp:
        app=Path(tmp)/'Shino Open.app'
        contents=app/'Contents';bin=contents/'MacOS';res=contents/'Resources'
        res.mkdir(parents=True);bin.mkdir()
        meta={'CFBundleName':'Shino Open','CFBundleDisplayName':'Shino Open','CFBundleExecutable':'Shino',
              'CFBundleIdentifier':BUNDLE_ID,'CFBundleVersion':'9','CFBundleShortVersionString':'1.3.0','CFBundleLocalizations':['ru','en'],'CFBundleDevelopmentRegion':'en',
              'CFBundleInfoDictionaryVersion':'6.0','CFBundlePackageType':'APPL','LSUIElement':True,
              'LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True}
        icon=ROOT/'Assets/Shino.icns'
        if icon.exists():meta['CFBundleIconFile']='Shino.icns';shutil.copy2(icon,res/icon.name)
        with (contents/'Info.plist').open('wb') as cfg:plistlib.dump(meta,cfg)
        model=ROOT/'Assets/Shino.vrm'
        if hashlib.sha256(model.read_bytes()).hexdigest()!='1e177c1a7b14f783a9c48395831db8616260d3bddd4154cb2784b779adca49b5':raise ValueError('Unexpected model')
        optimize_model(model,res/'Shino.vrm')
        package_wardrobe(ROOT/'Assets'/'Wardrobe',res)
        for name in ('en.json','studio.html','studio.js','pet.js','face.js','lighting.js','fit.js','arm-contacts.js','shino-drape.js','ShinoMenu.svg'):shutil.copy2(ROOT/'Source'/name,res/name)
        shutil.copy2(ROOT/'Vendor/runtime.js',res/'runtime.js')
        shutil.copytree(ROOT/'Licenses',res/'Licenses')
        shutil.copy2(ROOT/'LICENSE',res/'Licenses/LICENSE')
        motion=ROOT/'Motions'
        rows=json.loads((motion/'catalog.json').read_text());base=json.loads((motion/'base.json').read_text())
        seconds={f:r['duration'] for f,r in base.items()}
        seconds.update({r['file']:r['duration'] for r in rows})
        gait={f:r['cycleTravel'] for f,r in base.items() if r['cycleTravel']}
        for f in seconds:shutil.copy2(motion/f,res/f)
        catalog=json.dumps(rows,ensure_ascii=False,separators=(',',':'))
        (res/'catalog.json').write_text(catalog)
        (res/'catalog.js').write_text(f'const catalog={catalog};const clipSeconds={json.dumps(seconds)};const cycleTravel={json.dumps(gait)};')
        run('xcrun','swiftc','-O','-target',platform.machine()+'-apple-macosx13.0','-framework','WebKit','-framework','AppKit','-framework','ServiceManagement',str(ROOT/'Source/Pet.swift'),str(ROOT/'Source/Models.swift'),str(ROOT/'Source/Welcome.swift'),str(ROOT/'Source/VerifyModels.swift'),'-o',str(bin/'Shino'))
        run('codesign','--force','--sign','-','--identifier',BUNDLE_ID,str(app))
        run('codesign','--verify','--strict',str(app))
        previous=Path(tmp)/'previous.app'
        if output.exists():output.rename(previous)
        try:app.rename(output)
        except OSError:
            if previous.exists():previous.rename(output)
            raise
    if output.parent == Path.home() / "Desktop":
        run("xcrun", "swift", str(ROOT/"Source/DesktopIcon.swift"), str(output))
    print(output)
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'Shino Open.app')
    build(parser.parse_args().output)
