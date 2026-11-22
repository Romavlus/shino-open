import AppKit
import WebKit

extension Pet {
    @MainActor func verifyModelPicker() async {
        func require(_ value:Bool,_ description:String) throws {
            if !value {throw NSError(domain:"ModelPicker",code:1,userInfo:[NSLocalizedDescriptionKey:description])}
        }
        func waitFor(_ condition:()->Bool) async throws{
            let until=now+12
            while !condition(){
                try require(now<until,"Timed out loading "+selectedModel.title)
                try await Task.sleep(nanoseconds:50_000_000)
            }
        }
        func run(_ view:WKWebView,_ script:String,_ args:[String:Any]=[:]) async throws -> Bool{
            try await view.callAsyncJavaScript(script,arguments:args,in:nil,contentWorld:.page) as? Bool == true
        }
        func selectInMenu(_ choice:PetModel)throws{
            let items=menu().item(withTitle:tr("Персонаж"))?.submenu
            guard let items,let index=items.items.firstIndex(where:{$0.representedObject as? String==choice.rawValue}) else{
                try require(false,"Missing menu entry "+choice.title);return
            }
            items.performActionForItem(at:index)
        }
        do{
            let bundled:[PetModel]=[.shino,.shinoCherry,.shinoCardigan]
            let choices=models.choices
            try require(choices==bundled,"Installed wardrobe")
            openStudio(false)
            try await waitFor{self.galleryReady && self.ready}
            settings.frequency="manual";walkEnabled=false;applySettings()
            let prepare="""
            const row=previews.find(r=>r.key==='highfive');
            await pet.prepare(row.clip);choose(row);pet.play(row.clip,0,true,.58);
            if(!closeUp)el('portrait').click();
            pet.restoreCamera(true,[.30,.05,.72]);
            if(!stopped)el('pause').click();
            return el('character').options.length===count && pet.check().model==='shino';
            """
            let started=try await run(galleryWeb!,prepare,["count":choices.count])
            try require(started,"Initial preview controls")
            let bodyIndices=try await galleryWeb!.callAsyncJavaScript("return pet.check(true).bodyIndices",arguments:[:],in:nil,contentWorld:.page) as? Int ?? 0
            try require(bodyIndices>1000,"Full Shino body")
            for (index,choice) in (Array(choices.dropFirst())+[.shino]).enumerated(){
                let scene=clipID("chilly"),length=durations[scene]
                perform(scene);phaseStart=now-0.33*length;deadline=now+0.67*length
                js("pet.play(\(scene),0,true,0.33)")
                let behavior=index%2==1
                _ = try await run(galleryWeb!,"el(options?'showOptions':'showLibrary').click();return true",["options":behavior])
                if index%2==0{
                    let clicked=try await run(galleryWeb!,"el('character').value=id;el('character').dispatchEvent(new Event('change'));return true",["id":choice.rawValue])
                    try require(clicked,"Studio model command")
                }else{try selectInMenu(choice)}
                try await waitFor{self.selectedModel==choice && self.ready && self.galleryReady}
                let preview=try await run(galleryWeb!,"""
                const state=studioSnapshot(), check=pet.check();
                return el('character').value===id && check.file===file && petModel.family===family && state.settings===options &&
                  check.dress===(id==='shinoCardigan') &&
                  state.key==='highfive' && state.paused && state.portrait && Math.abs(state.phase-.58)<.025 &&
                  state.camera.every((n,i)=>Math.abs(n-[.30,.05,.72][i])<.008);
                """,["id":choice.rawValue,"file":choice.file,"options":behavior,"family":"shino"])
                try require(preview,"Preview/pose/camera mismatch for "+choice.title)
                let desktop=try await run(web,"const x=pet.check(),s=pet.previewState();return x.model===id && x.file===file && x.triangles>100 && x.transparent && s.key==='chilly' && s.phase>.30 && s.phase<.79",["id":choice.rawValue,"file":choice.file])
                try require(desktop,"Desktop mismatch for "+choice.title)
                let marked=menu().item(withTitle:tr("Персонаж"))?.submenu?.items.filter{$0.state == .on}
                try require(marked?.count==1 && marked?.first?.title==choice.title,"Menu checkmark")
                let takes=try await run(galleryWeb!,"""
                const looks=previews.slice();
                for(const row of looks){
                    await pet.prepare(row.clip);pet.sample(row.clip,pet.durations[row.clip]*.44);
                    const x=pet.check();
                    if(x.active!==row.clip || !Number.isFinite(x.knee) || x.triangles<100)throw Error(row.label);
                }
                if(petModel.family==='shino'){
                    async function wrists(key,phase){
                        const row=previews.find(r=>r.key===key);
                        await pet.prepare(row.clip);pet.sample(row.clip,pet.durations[row.clip]*phase);
                        return pet.check(true).wrists;
                    }
                    const rest=await wrists('stand',.5);
                    const distance=(wrist,side)=>Math.hypot(...wrist.map((v,i)=>v-rest[side][i]));
                    for(const scene of looks.filter(row=>row.role==='scene')){
                        for(const phase of [0,.999]){
                            const hands=await wrists(scene.key,phase);
                            if(!hands.every((w,i)=>distance(w,i)<.035))throw Error(scene.key+' lost its relaxed return pose');
                        }
                    }
                    for(const [key,free] of [['look',[0,1]],['think',[1]],['wait',[0]]]){
                        for(const phase of [0,.22,.52,.78,.99]){
                            const hands=await wrists(key,phase);
                            for(const side of free){
                                if(!(distance(hands[side],side)<.035))throw Error(key+' lost its resting arm');
                            }
                            if(free.length===1 && phase===.52){
                                const raised=1-free[0];
                                if(!(hands[raised][1]-rest[raised][1]>.30))throw Error(key+' lost its hand gesture');
                            }
                        }
                    }
                }
                const saved=previews.find(r=>r.key==='highfive');
                pet.sample(saved.clip,pet.durations[saved.clip]*.58);
                return looks.filter(r=>r.role==='scene').length===20;
                """)
                try require(takes,"Motion library for "+choice.title)
                if choice == .shinoCardigan {
                    let drapes=try await run(galleryWeb!,"""
                    const stand=previews.find(r=>r.key==='stand');
                    await pet.prepare(stand.clip);pet.sample(stand.clip,pet.durations[stand.clip]*.56);
                    const fit=pet.check(true);
                    if(fit.bodyIndices!==baseCount || fit.cloth.kneeFront>.185)return false;
                    for(const key of ['walk','hop','plane']){
                        const row=previews.find(r=>r.key===key);
                        await pet.prepare(row.clip);
                        let travel=0, ribbon=0;
                        for(const phase of [.18,.36,.54,.73,.92]){
                            pet.sample(row.clip,pet.durations[row.clip]*phase);
                            const cloth=pet.check(true).cloth;
                            if(cloth.waist>.0001 || cloth.ties.length!==6 || !Number.isFinite(cloth.hem))return false;
                            travel=Math.max(travel,cloth.hem);
                            ribbon=Math.max(ribbon,...cloth.ties);
                        }
                        if(!(travel>.018 && travel<.78 && ribbon>.0001))return false;
                    }
                    const saved=previews.find(r=>r.key==='highfive');
                    pet.sample(saved.clip,pet.durations[saved.clip]*.58);
                    return true;
                    """,["baseCount":bodyIndices])
                    try require(drapes,"Complete body, standing silhouette and moving cloth")
                }
                print("PASS",choice.title,"on desktop and in fitting room, 20 scenes; phase, portrait, orbit and pause")
            }
            // Only the last request can install its view and assets.
            selectModel(.shinoCardigan,preview:savedPreview);selectModel(.shino,preview:savedPreview);selectModel(.shinoCherry,preview:savedPreview)
            try await waitFor{self.selectedModel == .shinoCherry && self.ready && self.galleryReady}
            let last=try await run(web,"return pet.check().model==='shinoCherry' && pet.check().file==='ShinoCherry.gltf'")
            try require(last,"Rapid selection")
            gallery?.close()
            let screen=(panel.screen ?? NSScreen.main)!.visibleFrame
            panel.setFrameOrigin(CGPoint(x:screen.midX-panel.frame.width/2,y:panel.frame.minY))
            for (dir,yaw) in [(1,0.96),(-1,-0.91)]{
                idle();viewAngles=NSPoint(x:yaw,y:0.64);sendView()
                direction=CGFloat(dir)
                let origin=panel.frame.origin
                beginWalk(at:now)
                try await Task.sleep(nanoseconds:85_000_000)
                try require(facingSince != nil && panel.frame.origin==origin,"Travel began before turning")
                try await waitFor{self.facingSince==nil && self.current==self.startClip}
                let aligned=try await run(web,"return d*pet.check(true).screenRight>.993",["d":dir])
                try require(aligned,"Screen-relative heading after a manual orbit")
                try await waitFor{CGFloat(dir)*(self.panel.frame.minX-origin.x)>2}
                grab(NSPoint(x:300,y:200),rotating:true)
                moveGrab(NSPoint(x:355,y:217))
                let held=panel.frame.origin,saved=viewAngles
                release()
                try await Task.sleep(nanoseconds:50_000_000)
                try require(facingSince != nil && panel.frame.origin==held,"Walk resumed before facing the screen edge")
                try await waitFor{self.facingSince==nil}
                let resumed=try await run(web,"return d*pet.check(true).screenRight>.993",["d":dir])
                try require(resumed && viewAngles==saved,"Heading and saved orbit after mid-stride rotation")
            }
            idle();resetView()
            if let display=panel.screen {
                let bottom=clamp(NSPoint(x:display.frame.midX-panel.frame.width/2,y:display.frame.minY-panel.frame.height),to:display)
                panel.setFrameOrigin(bottom)
                let suite="ShinoOpenPlacement-"+UUID().uuidString
                let prefs=UserDefaults(suiteName:suite)!
                defer {prefs.removePersistentDomain(forName:suite)}
                saveSpot(defaults:prefs)
                panel.setFrameOrigin(NSPoint(x:bottom.x+45,y:bottom.y+90))
                restoreSpot(defaults:prefs)
                try require(hypot(panel.frame.minX-bottom.x,panel.frame.minY-bottom.y)<1.5,"Preferred placement")
                var spot=prefs.dictionary(forKey:"desktopSpot")!
                spot["display"]="disconnected";prefs.set(spot,forKey:"desktopSpot")
                restoreSpot(defaults:prefs)
                try require(panel.screen != nil,"Disconnected display fallback")
                panel.setFrameOrigin(bottom)
                let initialY=panel.frame.minY
                try require(abs(initialY+panel.frame.height*Pet.floorFraction-display.frame.minY-1)<1.1,"Floor placement")
                for key in ["plane","hop","stop"]{
                    perform(clipID(key));translate(4);idle()
                    try require(abs(panel.frame.minY-initialY)<0.01,"Floor drift after "+key)
                }
                resize(to:75)
                try require(abs(panel.frame.minY+panel.frame.height*Pet.floorFraction-display.frame.minY-1)<1.1,"Floor after resize")
            }
            print("PASS turn in place before screen-space travel, in both directions and after an in-stride orbit")
            settings.visits=Visits(enabled:true,period:40,duration:3)
            visitOrigin=Date().addingTimeInterval(-7);updateVisit(at:Date())
            hiddenSince=Date().addingTimeInterval(-2);updateVisit(at:Date())
            try require(away && web==nil,"Desktop should be unloaded")
            selectModel(.shinoCardigan)
            try require(away && web==nil && selectedModel == .shinoCardigan,"Switching should respect scheduled absence")
            visitOrigin=Date().addingTimeInterval(-36.6);tick()
            try await waitFor{self.ready && !self.away && self.panel.isVisible}
            let woke=try await run(web,"return pet.check().model==='shinoCardigan' && pet.check().dress")
            try require(woke,"Scheduled appearance with selected model")
            print("PASS rapid switching and scheduled return");exit(0)
        }catch{print("Model verification failed:",error);exit(1)}
    }
}
