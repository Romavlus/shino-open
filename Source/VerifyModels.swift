import AppKit
import WebKit

extension Pet {
    @MainActor func verifyModelPicker() async {
        func require(_ value:Bool,_ description:String) throws {
            if !value {throw NSError(domain:"ModelPicker",code:1,userInfo:[NSLocalizedDescriptionKey:description])}
        }
        func waitFor(_ condition:()->Bool) async throws{
            let until=now+25
            while !condition(){
                try require(now<until,"Timed out loading "+selectedModel.title)
                try await Task.sleep(nanoseconds:50_000_000)
            }
        }
        func run(_ view:WKWebView,_ script:String,_ args:[String:Any]=[:]) async throws -> Bool{
            try await view.callAsyncJavaScript(script,arguments:args,in:nil,contentWorld:.page) as? Bool == true
        }
        func selectInMenu(_ choice:PetModel)throws{
            let items=menu().item(withTitle:"Персонаж")?.submenu
            guard let items,let index=items.items.firstIndex(where:{$0.representedObject as? String==choice.rawValue}) else{
                try require(false,"Missing menu entry "+choice.title);return
            }
            items.performActionForItem(at:index)
        }
        do{
            let bundled:[PetModel]=[.shino,.shinoCherry,.shinoCardigan,.shinoRider,.shinoMarine,.shinoBordeaux]
            let choices=models.choices
            try require(choices==bundled,"Only the six Shino looks are offered")
            let suiteName="ShinoWardrobeQA-"+UUID().uuidString
            let migrated=UserDefaults(suiteName:suiteName)!
            defer{migrated.removePersistentDomain(forName:suiteName)}
            for (i,old) in ["honey","forest","dress","shinoBordeaux"].enumerated(){
                let key=i==0 ? "selectedModel":"companionModel"+String(i+1)
                migrated.set(old,forKey:key)
                let expected:PetModel=i==3 ? .shinoBordeaux:.shino
                try require(PetModel.savedChoice(key,in:migrated)==expected && migrated.string(forKey:key)==expected.rawValue,"Restore saved outfit")
            }
            try require(PetModel.savedChoice("companionModel9",in:migrated)==nil,"Empty slot stays empty")
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
                return el('character').value===id && check.file===file && state.settings===options &&
                  check.dress===['shinoCardigan','shinoRider','shinoBordeaux'].includes(id) &&
                  state.key==='highfive' && state.paused && state.portrait && Math.abs(state.phase-.58)<.025 &&
                  state.camera.every((n,i)=>Math.abs(n-[.30,.05,.72][i])<.008);
                """,["id":choice.rawValue,"file":choice.file,"options":behavior])
                try require(preview,"Preview/pose/camera mismatch for "+choice.title)
                let desktop=try await run(web,"const x=pet.check(),s=pet.previewState();return x.model===id && x.file===file && x.triangles>100 && x.transparent && s.key==='chilly' && s.phase>.30 && s.phase<.79",["id":choice.rawValue,"file":choice.file])
                try require(desktop,"Desktop mismatch for "+choice.title)
                let marked=menu().item(withTitle:"Персонаж")?.submenu?.items.filter{$0.state == .on}
                try require(marked?.count==1 && marked?.first?.title==choice.title,"Menu checkmark")
                let takes=try await run(galleryWeb!,"""
                const looks=previews.slice();
                for(const row of looks){
                    await pet.prepare(row.clip);pet.sample(row.clip,pet.durations[row.clip]*.44);
                    const x=pet.check();
                    if(x.active!==row.clip || !Number.isFinite(x.knee) || x.triangles<100)throw Error(row.label);
                }
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
                const saved=previews.find(r=>r.key==='highfive');
                pet.sample(saved.clip,pet.durations[saved.clip]*.58);
                return looks.filter(r=>r.role==='scene').length===20;
                """)
                try require(takes,"Motion library for "+choice.title)
                if [.shinoCardigan,.shinoRider,.shinoBordeaux].contains(choice) {
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
                            if(cloth.waist>.0001 || cloth.ties.length!==ties || !Number.isFinite(cloth.hem))return false;
                            travel=Math.max(travel,cloth.hem);
                            ribbon=Math.max(ribbon,...cloth.ties);
                        }
                        if(!(travel>.018 && travel<.78 && (!ties || ribbon>.0001)))return false;
                    }
                    const saved=previews.find(r=>r.key==='highfive');
                    pet.sample(saved.clip,pet.durations[saved.clip]*.58);
                    return true;
                    """,["baseCount":bodyIndices,"ties":choice == .shinoRider ? 0:6])
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
            sceneHome=nil
            walkEnabled=false
            openStudio(false)
            try await waitFor{self.galleryReady}
            func setSlot(_ n:Int,_ model:PetModel?) async throws{
                let ok=try await run(galleryWeb!,"const p=slotPickers[n-1];p.value=id;p.dispatchEvent(new Event('change'));return p.value===id",["n":n,"id":model?.rawValue ?? ""])
                try require(ok,"Studio slot choice")
            }
            let limits=try await run(galleryWeb!,"el('slotCount').value=0;el('slotCount').dispatchEvent(new Event('change'));return true")
            try require(limits,"Roster input")
            try await waitFor{self.slotCount==1}
            let plus=try await run(galleryWeb!,"if(!el('fewer').disabled)return false;el('more').click();return true")
            try require(plus,"Roster stepper")
            try await waitFor{self.slotCount==2}
            let grow=try await run(galleryWeb!,"el('more').click();return true")
            try require(grow,"Third picker")
            try await waitFor{self.slotCount==3}
            let empty=try await run(galleryWeb!,"return slotPickers[1].value==='' && slotPickers[2].value===''")
            try require(empty,"Empty companion slots")
            try await setSlot(3,.shino)
            try await waitFor{self.companions.count==1 && self.companions[0].slot==3 && self.companions[0].ready}
            try await setSlot(3,.shinoCherry)
            try await waitFor{self.companions[0].selectedModel == .shinoCherry && self.companions[0].ready}
            try await setSlot(3,nil)
            try await waitFor{self.companions.isEmpty}
            try await setSlot(2,models.choices.last!)
            try await setSlot(3,.shino)
            try await waitFor{self.companions.count==2 && self.companions.allSatisfy{$0.ready}}
            try require(menu().item(withTitle:"Добавить персонажа") != nil,"Room for further companions")
            func control(_ id:String,_ value:String) async throws{
                let applied=try await run(galleryWeb!,"const c=el(id);c.value=value;c.dispatchEvent(new Event('change'));return true",["id":id,"value":value])
                try require(applied,"Profile setting "+id)
            }
            try await control("frequency","rare")
            try await waitFor{self.actors.allSatisfy{$0.settings.frequency=="rare"}}
            try await control("mode","personal")
            try await waitFor{self.profiles.individual}
            try await control("target","2")
            try await waitFor{self.profileTarget.slot==2}
            try await control("frequency","often")
            try await waitFor{self.profileTarget.settings.frequency=="often"}
            try require(settings.frequency=="rare" && companions.last?.settings.frequency=="rare","Isolated personal edit")
            try await control("mode","shared")
            try await waitFor{self.actors.allSatisfy{$0.settings.frequency=="rare"}}
            try await control("mode","personal")
            try await waitFor{self.profileTarget.settings.frequency=="often"}
            try await control("mode","shared")
            try await waitFor{!self.profiles.individual}
            let actors=[self,companions[0]]
            var places:[NSPoint]=[]
            for (i,actor) in actors.enumerated(){
                actor.settings.frequency="manual";actor.walkEnabled=false;actor.scheduleScene()
                let frame=actor.panel.screen!.visibleFrame
                actor.panel.setFrameOrigin(NSPoint(x:frame.minX+frame.width*(i==0 ? 0.25:0.65),y:frame.minY+20))
                places.append(actor.panel.frame.origin)
                actor.perform(actor.clipID("sneak"))
            }
            try await waitFor{actors.allSatisfy{$0.walkingHome}}
            for (actor,place) in zip(actors,places){
                try require(abs(actor.panel.frame.minX-place.x)>2,"Scene moved before return")
            }
            try await waitFor{actors.allSatisfy{$0.sceneHome==nil && !$0.walkingHome}}
            for (actor,place) in zip(actors,places){
                try require(actor.panel.frame.origin==place && !actor.walkEnabled,"Walked back to scene origin")
            }
            try await control("slotCount","10")
            try await waitFor{self.slotCount == 10}
            for n in 4...10{
                let choice=bundled[(n-4)%bundled.count]
                try await setSlot(n,choice)
                try await waitFor{self.companions.contains{$0.slot==n && $0.ready}}
            }
            try require(self.actors.count==10 && self.actors.allSatisfy{$0.ready && $0.panel.isVisible},"Ten rendered desktop windows")
            for actor in self.actors{
                let drawn=try await run(actor.web,"return pet.check().rendered>0 && pet.check().model===id",["id":actor.selectedModel.rawValue])
                try require(drawn,"Live renderer "+String(actor.slot))
            }
            try require(menu().item(withTitle:"Добавить персонажа")==nil,"Full ten-slot menu")
            let tenthModel=self.selectedCompanions[10]
            try await control("slotCount","5")
            try await waitFor{self.actors.count==5}
            let five=try await run(galleryWeb!,"return slotPickers.length===5 && el('character6')===null")
            try require(five,"Five visible pickers")
            if let display=NSScreen.screens.last {
                let cast=self.actors
                let desktopFrames=cast.map{$0.panel.frame},views=cast.map{$0.web},priorBackdrop=backdrop
                let picked=try await run(galleryWeb!,"const p=el('backdrop');p.value='starlake';p.dispatchEvent(new Event('change'));return p.options.length===8")
                try require(picked,"Eight fitting-room backgrounds")
                try await waitFor{self.backdrop == .starlake}
                let studioOpened=try await run(galleryWeb!,"el('openScene').click();return true")
                try require(studioOpened,"Fitting-room full-screen button")
                try await waitFor{self.stage != nil}
                let menu=stageMenu()
                guard let entry=menu.items.lastIndex(where:{$0.representedObject as? String==display.sceneID}) else {
                    throw CocoaError(.coderValueNotFound)
                }
                menu.performActionForItem(at:entry)
                try require(stage?.window.frame==display.frame && cast.allSatisfy{$0.onStage && !$0.panel.isVisible && !$0.surface.isHidden},"One full monitor and five mounted actors")
                for color in SceneBackdrop.allCases {
                    let colors=stageMenu().item(withTitle:"Фон")!.submenu!
                    colors.performActionForItem(at:colors.indexOfItem(withTitle:color.title))
                    try require(backdrop==color,"Scene backdrop "+color.title)
                }
                let actor=cast[1],before=actor.actorFrame
                actor.translate(8)
                try require(actor.actorFrame.minX>before.minX+5 && actor.actorScreen?.sceneID==display.sceneID,"Local stage travel")
                actor.hideActor();try require(actor.surface.isHidden,"Stage absence");actor.showActor()
                for (mounted,original) in zip(cast,views) {
                    try require(mounted.web===original && mounted.web.window===stage?.window,"Mounted renderer "+String(mounted.slot))
                    let script="""
                    const initial=pet.check().rendered;
                    for(let attempt=0;attempt<25;attempt++){
                        await new Promise(resolve=>setTimeout(resolve,80));
                        if(!document.hidden && pet.check().rendered>initial)return 'live';
                    }
                    return [document.visibilityState,initial,pet.check().rendered,innerWidth,innerHeight].join('/');
                    """
                    let progress=try await mounted.web!.callAsyncJavaScript(script,arguments:[:],in:nil,contentWorld:.page) as? String
                    try require(progress=="live","Scene playback in slot "+String(mounted.slot)+" "+(progress ?? "missing"))
                }
                if let other=NSScreen.screens.first(where:{$0.sceneID != display.sceneID}){
                    openFullScreenScene(on:other)
                    try require(cast.allSatisfy{other.frame.contains(NSPoint(x:$0.actorFrame.midX,y:$0.actorFrame.midY))},"Move the whole cast between monitors")
                }
                let finish=stageMenu();finish.performActionForItem(at:finish.indexOfItem(withTitle:"Вернуться на рабочий стол"))
                try require(stage==nil && zip(cast,desktopFrames).allSatisfy{$0.panel.frame==$1 && $0.panel.isVisible && $0.surface.window===$0.panel},"Original desktop layout after exit")
                backdrop=priorBackdrop
                print("PASS full-screen cast, eight backgrounds, travel, visibility, monitor selection and exact desktop return")
            }
            func pressRound(_ actor:Pet,stop:Bool=false)throws{
                let title=stop ? "Остановить показ сценок" : "Показать все сценки"
                let m=actor.menu(),index=m.indexOfItem(withTitle:title)
                try require(index>=0,"Missing group menu command "+title)
                m.performActionForItem(at:index)
            }
            let visitor=self.actors.last!,previousBehavior=visitor.settings
            visitor.settings.visits=Visits(enabled:true,period:600,duration:5)
            visitor.visitOrigin=Date().addingTimeInterval(-25)
            visitor.updateVisit(at:Date());visitor.hiddenSince=Date().addingTimeInterval(-3)
            visitor.updateVisit(at:Date())
            try require(visitor.away && visitor.web==nil,"Cold scheduled slot")
            try pressRound(self);try pressRound(visitor,stop:true)
            try require(self.sceneRound==nil,"Cancel pending loads for all slots")
            let homes=Dictionary(uniqueKeysWithValues:self.actors.map{($0.slot,$0.panel.frame.origin)})
            try pressRound(self)
            guard let round=self.sceneRound else{throw CocoaError(.coderValueNotFound)}
            let ordered=self.catalog.filter{$0.role=="scene"}.map(\.key)
            var seen:[String]=[],worstPhaseError=0.0
            for (index,key) in ordered.enumerated(){
                try await waitFor{
                    guard self.sceneRound===round,round.index==index,let start=round.start else{return false}
                    return self.now>=start+round.duration*0.33
                }
                let epoch=(Date().timeIntervalSince1970+(round.start!-self.now))*1000
                for actor in self.actors{
                    try require(actor.ready && actor.panel.isVisible && actor.panel.frame.origin==homes[actor.slot],"Stationary visible slot "+String(actor.slot))
                    let error=try await actor.web!.callAsyncJavaScript("""
                    const s=pet.previewState();
                    if(s.key!==key)throw Error('Expected '+key+', got '+s.key);
                    return Math.abs(s.phase*duration-(Date.now()-epoch)/1000);
                    """,arguments:["key":key,"duration":round.duration,"epoch":epoch],in:nil,contentWorld:.page) as? Double
                    worstPhaseError=max(worstPhaseError,error ?? .infinity)
                }
                seen.append(key)
                if index==1{
                    let changing=self.companions.first{$0.slot==4}!
                    changing.selectModel(.shinoBordeaux)
                    try await waitFor{changing.ready && round.members[changing.slot]?.state == .playing}
                    let joined=try await run(changing.web,"const s=pet.previewState();return s.key===key && s.phase>0.2",["key":key])
                    try require(joined,"Replacement model joined the running scene")
                }
            }
            try await waitFor{self.sceneRound==nil}
            try require(seen==ordered && worstPhaseError<0.18,"Scene ordering or on-screen clock drift: "+String(worstPhaseError))
            try require(visitor.away && self.menu().item(withTitle:"Показать все сценки") != nil,"End of round restores schedule and menu")
            visitor.settings=previousBehavior;visitor.applySettings()
            print("PASS one synchronized round:",seen.count,"scenes on five live models; max sampled timing error",Int(worstPhaseError*1000),"ms")

            try await control("slotCount","10")
            try await waitFor{self.actors.count==10 && self.actors.allSatisfy{$0.ready}}
            try require(self.actors.first(where:{$0.slot==10})?.selectedModel==tenthModel,"Hidden choices restored")
            try pressRound(self.companions.last!)
            try await waitFor{self.sceneRound?.members.values.filter{$0.state == .playing}.count==10}
            try await Task.sleep(nanoseconds:400_000_000)
            for actor in self.actors{
                let playing=try await run(actor.web,"return pet.previewState().key==='hello' && pet.previewState().phase>0")
                try require(playing,"Scene comparison in slot "+String(actor.slot))
            }
            try pressRound(self,stop:true)
            try require(self.sceneRound==nil && self.actors.allSatisfy{$0.showcase==nil},"One stop for all ten slots")

            try await control("mode","personal");try await waitFor{self.profiles.individual}
            try await control("target","10");try await waitFor{self.profileTarget.slot==10}
            try await control("frequency","rare");try await waitFor{self.profileTarget.settings.frequency=="rare"}
            try await control("mode","shared");try await waitFor{!self.profiles.individual}
            try await control("slotCount","3")
            try await waitFor{self.actors.count==3 && self.slotCount==3}
            print("PASS ten live desktop characters, numeric roster, shrink/restore, per-character control through slot ten")
            try await setSlot(2,nil);try await setSlot(3,nil)
            try await waitFor{self.companions.isEmpty}
            gallery?.close()
            try require(companions.isEmpty && web != nil,"Independent companion removal")
            print("PASS three simultaneous characters, animated returns in both directions, independent removal")
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
