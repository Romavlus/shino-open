import AppKit
import WebKit
import ServiceManagement

final class Touch: NSView {
    weak var pet: Pet?
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    func screenPoint(_ event:NSEvent)->NSPoint {window?.convertPoint(toScreen:event.locationInWindow) ?? NSEvent.mouseLocation}
    override func mouseDown(with event: NSEvent) { pet?.grab(screenPoint(event),rotating:event.modifierFlags.contains(.command)) }
    override func mouseDragged(with event: NSEvent) { pet?.moveGrab(screenPoint(event)) }
    override func mouseUp(with event: NSEvent) { pet?.release() }
    override func rightMouseDown(with event: NSEvent) {
        guard let pet else { return }
        NSMenu.popUpContextMenu(pet.menu(), with: event, for: self)
    }
}

struct Motion:Decodable {
    let key:String, label:String, role:String, duration:Double
    let travel:[Double]?
    func distance(at phase:Double)->Double {
        guard let path=travel,path.count>1 else{return 0}
        let u=min(1,max(0,phase))*Double(path.count-1),i=Int(u)
        return path[i]+(path[min(i+1,path.count-1)]-path[i])*(u-Double(i))
    }
}
struct Visits:Codable,Equatable {
    var enabled=false, period=600, duration=20
    mutating func normalize(){
        period=min(86400,max(2,period))
        duration=min(period-1,max(1,duration))
    }
}
struct Behavior:Codable,Equatable {
    var frequency="normal",low=60,high=120,amount=100,gaze=true,disabled=[String]()
    // Older preferences predate scheduled visits and mean continuous display.
    var visits:Visits?
    var seconds:ClosedRange<Double>? {
        switch frequency {
        case "manual":return nil
        case "often":return 20...40
        case "rare":return 120...240
        case "fixed":return Double(low)...Double(low)
        case "custom":return Double(low)...Double(high)
        default:return 60...120
        }
    }
}
struct Showcase {
    enum Kind { case movements, scenes }
    let kind:Kind
    let clips:[Int]
    var position=0
}
final class Pet: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate, NSWindowDelegate, NSMenuDelegate {
    let verifyModels=CommandLine.arguments.contains("--verify-models")
    var testing:Bool { verifyModels || CommandLine.arguments.contains("--verify") }
    static let modelLibrary=ModelLibrary(resources:Bundle.main.resourceURL!)
    var models:ModelLibrary { Self.modelLibrary }
    static let dataStore=WKWebsiteDataStore.nonPersistent()
    var selectedModel:PetModel = .shino
    var catalog:[Motion] {models.catalog}
    var modelRequest=0,hasLoaded=false,galleryReady=false
    var savedPreview:[String:Any]?
    struct Playhead {
        let clip:Int, direction:Int, phase:Double, remaining:Double, walkRemaining:Double
    }
    var resumeDesktop:Playhead?,activeDirection=0
    var facingSince:Double?
    var plannedIdle:Int?,plannedScene:Int?,watchingMask:Bool?
    var settings=Behavior(),durations=[Double]()
    var visitOrigin:Date?, shownCycle:Int?, away=false
    var gallery:NSWindow?,galleryWeb:WKWebView?,showSettings=false
    var sceneRound:SceneRound?
    var showcase:Showcase?
    var showcaseRequest=0
    var current=0,lastIdle = -1,lastScene = -1
    var nextScene=Double.infinity,phaseStart=0.0,walkUntil=0.0,rootDistance=0.0
    var roomScale=1.0,lastCursor=NSPoint(x:-99999,y:-99999),nextGaze=0.0
    var glanceUntil=0.0,gazeSent=false,nextGlance=0.0
    static let panelHeight:CGFloat = 396
    static let coreHeight:CGFloat = 354
    static let floorFraction:CGFloat = 0.045
    let panel = NSPanel(contentRect: NSRect(x:0,y:0,width:238,height:Pet.panelHeight), styleMask:[.borderless,.nonactivatingPanel], backing:.buffered, defer:false)
    let surface=ActorSurface(frame:.zero)
    var stage:FullScreenScene?
    var backdrop:SceneBackdrop = .mist
    var web: WKWebView!
    var hiddenSince=Date(),manualWake=false
    var afterLoad:(()->Void)?
    let prewarm:TimeInterval=3
    var status: NSStatusItem!
    var timer: Timer?
    var ready = false
    var mask = [UInt8]()
    // Normalized bounds, with the origin at the bottom left as in AppKit.
    var silhouette = CGRect(x:0.25,y:0.035,width:0.50,height:0.89)
    func receiveMask(_ data:String){
        let next=Array(data.utf8)
        guard next.count==32*52 else{return}
        mask=next
        var left=32,right = -1,top=52,bottom = -1
        for i in next.indices where next[i]==49 {
            let x=i%32,y=i/32
            left=min(left,x);right=max(right,x);top=min(top,y);bottom=max(bottom,y)
        }
        if right>=left {
            silhouette=CGRect(x:CGFloat(left)/32,y:CGFloat(51-bottom)/52,
                width:CGFloat(right+1-left)/32,height:CGFloat(bottom+1-top)/52)
        }
    }
    var picked: NSPoint?
    let maximumPitch:CGFloat = 75 * .pi / 180
    var viewAngles=NSPoint.zero
    var rotationDrag:(mouse:NSPoint,angles:NSPoint,start:Double)?
    var startOrigin = NSPoint.zero
    var lastMove = 0.0
    var previousPointer=NSPoint.zero
    var pointerVelocity=NSPoint.zero
    var dragged = false
    var moving = false
    var direction: CGFloat = -1
    let sizes = [50, 75, 100, 125, 150, 200]
    var sizePercent = 100
    // The four base clips precede the catalog in the shared renderer.
    let catalogStart=4
    lazy var startClip:Int=clipID("start")
    lazy var stopClip:Int=clipID("stop")
    lazy var turnClip:Int=clipID("turn")
    func clipID(_ key:String)->Int {catalogStart+catalog.firstIndex{$0.key==key}!}
    var walkClip = 3
    var strideRemainder: CGFloat = 0
    var gaitRates: [Double] = []
    var travelScale=1.0
    var lastTick = 0.0
    var walkStart = 0.0
    var walkEnabled = true
    var deadline = 0.0
    var lastReaction = -1
    var profiles=ProfileStore(),editingSlot=1
    weak var owner:Pet?
    static let maximumSlots=10
    var slotCount=3
    var selectedCompanions:[Int:PetModel]=[:]
    var companions:[Pet]=[]
    var slot=1
    var sceneHome:CGFloat?
    var walkingHome=false
    var savesPreferences:Bool { !testing && slot==1 }

    func refreshMenus(){
        let primary=owner ?? self
        primary.status?.menu=primary.menu()
    }

    @objc func addCompanion(_ item:NSMenuItem){
        guard slot==1,let id=item.representedObject as? String,
              let model=PetModel(rawValue:id),models.choices.contains(model),
              let number=(2...Self.maximumSlots).first(where:{n in !companions.contains{$0.slot==n}}) else{return}
        if number>slotCount{
            selectedCompanions[number]=model
            setSlotCount(number)
        }else{createCompanion(model,slot:number)}
    }

    func setSlotCount(_ requested:Int){
        guard slot==1 else{return}
        let count=min(Self.maximumSlots,max(1,requested)),previous=slotCount
        guard count != previous else{return}
        slotCount=count
        if savesPreferences{UserDefaults.standard.set(count,forKey:"slotCount")}
        if count<previous{
            for child in companions where child.slot>count{child.removeCompanion(remember:true)}
        }else{
            for number in (previous+1)...count{
                if let model=selectedCompanions[number]{createCompanion(model,slot:number)}
            }
        }
        refreshMenus();syncSlotPickers()
    }

    func remember(_ model:PetModel,at number:Int){
        selectedCompanions[number]=model
        if savesPreferences{UserDefaults.standard.set(model.rawValue,forKey:"companionModel"+String(number))}
    }

    func createCompanion(_ model:PetModel,slot number:Int){
        guard slot==1,number>=2,number<=slotCount,!companions.contains(where:{$0.slot==number}) else{return}
        let child=Pet()
        child.slot=number
        child.editingSlot=number;child.owner=self;child.selectedModel=model;child.walkEnabled=walkEnabled;child.walkClip=walkClip
        companions.append(child)
        remember(model,at:number)
        child.start()
        if let solo=showcase,solo.kind == .scenes {
            beginSceneRound(solo.clips,at:solo.position)
        }
        if let display=panel.screen ?? NSScreen.main{
            let w=child.panel.frame.width
            let occupied=([self]+companions.filter{$0 !== child}).map{$0.panel.frame.midX}
            let places=(0...32).map{n in display.visibleFrame.minX+(display.visibleFrame.width-w)*CGFloat(n)/32}
            let x=places.max{a,b in
                occupied.map{abs(a+w/2-$0)}.min()! < occupied.map{abs(b+w/2-$0)}.min()!
            } ?? panel.frame.minX
            child.panel.setFrameOrigin(child.clamp(NSPoint(x:x,y:panel.frame.minY),to:display))
        }
        stage?.add(child)
        refreshMenus();syncSlotPickers()
    }

    func slotValues()->[String]{
        let root=owner ?? self
        return (1...root.slotCount).map{number in number==1 ? root.selectedModel.rawValue : root.selectedCompanions[number]?.rawValue ?? ""}
    }

    func syncSlotPickers(){
        let root=owner ?? self
        for actor in [root]+root.companions where actor.galleryReady{
            actor.syncProfile()
            actor.galleryWeb?.callAsyncJavaScript("window.setSlots(values)",arguments:["values":root.slotValues()],in:nil,in:.page){_ in}
        }
    }

    @objc func closeCompanion(){removeCompanion(remember:false)}

    func removeCompanion(remember:Bool){
        guard let primary=owner else{return}
        timer?.invalidate();timer=nil
        primary.stage?.remove(self,restore:false)
        gallery?.close();releaseDesktop();panel.orderOut(nil)
        primary.companions.removeAll{$0 === self};owner=nil
        if !remember{
            primary.selectedCompanions.removeValue(forKey:slot)
            if primary.savesPreferences{UserDefaults.standard.removeObject(forKey:"companionModel"+String(slot))}
        }
        primary.prepareSceneRound()
        primary.refreshMenus();primary.syncSlotPickers()
    }

    var now: Double { ProcessInfo.processInfo.systemUptime }
    func applicationDidFinishLaunching(_ notification: Notification) {
        if savesPreferences{
            let defaults=UserDefaults.standard
            backdrop=SceneBackdrop(rawValue:defaults.string(forKey:"sceneBackdrop") ?? "") ?? .mist
            if defaults.object(forKey:"slotCount") != nil{slotCount=min(Self.maximumSlots,max(1,defaults.integer(forKey:"slotCount")))}
            for number in 2...Self.maximumSlots{
                if let id=UserDefaults.standard.string(forKey:"companionModel"+String(number)),
                   let model=PetModel(rawValue:id),models.choices.contains(model){selectedCompanions[number]=model}
            }
        }
        NotificationCenter.default.addObserver(self,selector:#selector(stageDisplaysChanged(_:)),name:NSApplication.didChangeScreenParametersNotification,object:nil)
        start()
        for number in selectedCompanions.keys.sorted() where number<=slotCount{
            if let model=selectedCompanions[number]{createCompanion(model,slot:number)}
        }
    }
    func start(){
        if savesPreferences,let data=UserDefaults.standard.data(forKey:"behavior"),
           let stored=try? JSONDecoder().decode(Behavior.self,from:data) {settings=stored}
        if savesPreferences,let choice=PetModel.savedChoice("selectedModel"){selectedModel=choice}
        panel.title=selectedModel.name;panel.delegate=self;panel.isOpaque=false;panel.backgroundColor = .clear
        panel.hasShadow=false; panel.level = .floating; panel.hidesOnDeactivate=false
        panel.collectionBehavior=[.canJoinAllSpaces,.fullScreenAuxiliary,.stationary,.ignoresCycle]
        panel.isReleasedWhenClosed=false;panel.isMovableByWindowBackground=false;panel.isMovable=false
        let frame=NSScreen.main?.visibleFrame ?? CGRect(x:0,y:0,width:1024,height:768)
        panel.setFrameOrigin(CGPoint(x:frame.maxX-panel.frame.width-60,y:(NSScreen.main?.frame.minY ?? frame.minY)+1-Pet.floorFraction*panel.frame.height))
        if savesPreferences {
            let saved=UserDefaults.standard.integer(forKey:"sizePercent")
            if saved>0 { resize(to:saved) }
            if let view=UserDefaults.standard.array(forKey:"desktopView") as? [Double],view.count==2,view.allSatisfy({$0.isFinite}){
                viewAngles=NSPoint(x:view[0],y:max(-maximumPitch,min(maximumPitch,view[1])))
            }
            if let enabled=UserDefaults.standard.object(forKey:"walkEnabled") as? Bool {walkEnabled=enabled}
            let savedWalk=UserDefaults.standard.integer(forKey:"preferredGaitV2")
            if let gait=[1:1,12:2,13:3][savedWalk] {walkClip=gait}
        }
        loadProfile()
        let content=surface;surface.actor=self;content.frame=NSRect(origin:.zero,size:panel.frame.size)
        let touch=Touch(frame:content.bounds);touch.pet=self;touch.autoresizingMask=[.width,.height]
        content.addSubview(touch);panel.contentView=content;panel.ignoresMouseEvents=true
        if savesPreferences {
            status=NSStatusBar.system.statusItem(withLength:NSStatusItem.squareLength)
            let icon=NSImage(contentsOf:Bundle.main.url(forResource:"ShinoMenu",withExtension:"svg")!)!
            icon.isTemplate=true
            status.button?.image=icon;status.button?.imagePosition = .imageOnly
            status.button?.setAccessibilityLabel("Сино")
            status.button?.toolTip=selectedModel.title;status.menu=menu()
        }
        panel.orderFrontRegardless()
        loadDesktop()
        if savesPreferences && CommandLine.arguments.contains("--studio") { openStudio(false) }
        let clock=Timer(timeInterval:1/60.0,repeats:true){[weak self] _ in self?.tick()}
        RunLoop.main.add(clock,forMode:.common);timer=clock
        if testing && slot==1 { DispatchQueue.main.asyncAfter(deadline:.now()+(verifyModels ? 240:40)){ print("Verification timed out"); exit(1) } }
    }
    func makeView(_ frame:NSRect,preview:[String:Any]?=nil)->WKWebView{
        let cfg=WKWebViewConfiguration()
        cfg.websiteDataStore = Self.dataStore
        cfg.setURLSchemeHandler(Assets(resources:models.resources),forURLScheme:"shino")
        let config=models.configuration(for:selectedModel,preview:preview,slots:slotValues())
        cfg.userContentController.addUserScript(WKUserScript(source:config,injectionTime:.atDocumentStart,forMainFrameOnly:true))
        cfg.userContentController.add(self,name:"pet")
        let v=WKWebView(frame:frame,configuration:cfg);v.navigationDelegate=self
        return v
    }
    func loadDesktop(){
        guard web==nil else{return};let content=surface
        let v=makeView(content.bounds);web=v
        v.setValue(false,forKey:"drawsBackground");v.autoresizingMask=[.width,.height]
        content.addSubview(v,positioned:.below,relativeTo:content.subviews.first)
        watchingMask=nil
        plannedIdle=pickIdle()
        var scenes=allowed("scene")
        if scenes.count>1{scenes.removeAll{$0==lastScene}}
        if let visits=settings.visits,visits.enabled,settings.seconds != nil{
            let fitting=scenes.filter{catalog[$0-catalogStart].duration+1<=Double(visits.duration)}
            plannedScene=(fitting.isEmpty ? scenes:fitting).randomElement()
        }else{plannedScene=nil}
        let clips=[plannedIdle,plannedScene,resumeDesktop?.clip].compactMap{$0}.map{"&clip="+String($0)}.joined()
        v.load(URLRequest(url:URL(string:"shino://local/studio.html?desktop&core=\(Pet.coreHeight/Pet.panelHeight)&floor=\(Pet.floorFraction)"+clips)!))
    }
    func releaseDesktop(){
        guard let v=web else{return}
        cancelFacing()
        primary.sceneRound?.members.removeValue(forKey:slot)
        web=nil;ready=false;mask=[]
        v.navigationDelegate=nil;v.configuration.userContentController.removeScriptMessageHandler(forName:"pet")
        v.stopLoading();v.removeFromSuperview()
    }
    func applicationShouldHandleReopen(_ sender:NSApplication,hasVisibleWindows flag:Bool)->Bool { openStudio(false); return true }
    func webViewWebContentProcessDidTerminate(_ webView:WKWebView) { if webView===web {primary.sceneRound?.members.removeValue(forKey:slot);endRotation();ready=false;moving=false;picked=nil;mask=[];panel.ignoresMouseEvents=true};webView.reload() }
    func js(_ code:String) { web?.evaluateJavaScript(code,completionHandler:nil) }
    func userContentController(_ userContentController: WKUserContentController,didReceive message: WKScriptMessage) {
        guard let d=message.body as? [String:Any],let kind=d["type"] as? String else {return}
        guard message.webView===web || message.webView===galleryWeb else{return}
        if kind=="slotCount",message.webView===galleryWeb,let count=d["value"] as? Int{
            primary.setSlotCount(count);return
        }
        if kind=="slot",message.webView===galleryWeb,let number=d["slot"] as? Int,(1...primary.slotCount).contains(number),let id=d["value"] as? String{
            let root=owner ?? self
            let actor=number==1 ? root : root.companions.first(where:{$0.slot==number})
            if id.isEmpty && number>1{actor?.closeCompanion()}
            else if let model=PetModel(rawValue:id),models.choices.contains(model){
                if let actor{actor.selectModel(model,preview:actor===self ? d["preview"] as? [String:Any] : nil)}
                else{root.createCompanion(model,slot:number)}
            }
            return
        }
        if kind=="error",selectedModel != .shino,!testing{
            let failed=selectedModel.title
            NSLog("Model %@ could not open: %@",failed,String(describing:d["value"]))
            selectModel(.shino,preview:savedPreview ?? [:])
            if let gallery{
                let alert=NSAlert();alert.messageText="Не удалось открыть "+failed
                alert.informativeText="Открыт исходный образ Сино."
                alert.beginSheetModal(for:gallery)
            }
            return
        }
        if kind=="motionError"{
            NSLog("Motion could not load: %@",String(describing:d["value"]))
            if message.webView===web && ready{moving=false;lastReaction = -1;play(0);deadline=now+durations[0]}
            if message.webView===galleryWeb{galleryWeb?.evaluateJavaScript("el('caption').textContent='Не удалось загрузить движение. Нажми «Повтор».'")}
            return
        }
        if message.webView===galleryWeb {
            if kind=="backdrop",let id=d["value"] as? String,let choice=SceneBackdrop(rawValue:id){primary.applyBackdrop(choice);return}
            if kind=="openScene",let display=primary.preferredSceneScreen {primary.openFullScreenScene(on:display);return}
            if kind=="ready"{
                galleryReady=true;galleryWeb?.evaluateJavaScript("pet.enterStudio()");syncStudio()
                if gallery?.isMiniaturized==true{galleryWeb?.evaluateJavaScript("pet.visibility(false)")}
            }
            if kind=="mode",let value=d["value"] as? Bool{setProfileMode(value);return}
            if kind=="target",let n=d["value"] as? Int,actors.contains(where:{$0.slot==n}){editingSlot=n;syncProfile();return}
            let subject=profileTarget
            if kind=="walk",let value=d["value"] as? Bool{subject.editProfile{$0.walking=value}}
            if kind=="gait",let value=d["value"] as? Int,(1...3).contains(value){subject.editProfile{$0.gait=value}}
            if kind=="size",let value=d["value"] as? Int{subject.setUserSize(value)}
            if kind=="prefs",let value=d["value"],JSONSerialization.isValidJSONObject(value),
               let data=try? JSONSerialization.data(withJSONObject:value),var p=try? JSONDecoder().decode(Behavior.self,from:data) {
                p.low=min(86400,max(5,p.low));p.high=min(86400,max(p.low,p.high));p.amount=min(150,max(0,p.amount))
                p.visits?.normalize()
                subject.editProfile{$0.behavior=p}
            }
            if kind=="resetAngle"{for actor in primary.profiles.individual ? [subject]:actors {actor.resetView()}}
            if kind=="login"{primary.changeLogin()}
            if kind=="visitNow" {for actor in primary.profiles.individual ? [subject]:actors {actor.showNow()}}
            if kind=="error"{galleryWeb?.evaluateJavaScript("document.getElementById('caption').textContent='Не удалось загрузить модель. Закрой и снова открой примерочную.'");NSLog("Preview error: %@",String(describing:d["value"]))}
            return
        }
        guard message.webView===web else{return}
        if kind=="mask", let data=d["value"] as? String, data.utf8.count==32*52 {receiveMask(data)}
        if kind=="error" {
            let text=String(describing:d["value"] ?? "Ошибка модели")
            if testing {print(text);exit(1)}
            let alert=NSAlert();alert.messageText="Не удалось открыть Сино";alert.informativeText=text;alert.runModal();NSApp.terminate(nil)
        }
        if kind=="ready",let payload=d["value"] as? [String:[Double]],let rates=payload["rates"],let lengths=payload["durations"],rates.indices.contains(walkClip) {
            let first = !hasLoaded;hasLoaded=true
            gaitRates=rates;travelScale=payload["travelScale"]?.first ?? 1;lastTick=now
            durations=lengths;ready=true;sendView()
            let resumed=resumeDesktop
            resumeDesktop=nil
            if primary.sceneRound != nil{
                afterLoad=nil;manualWake=false
                js("pet.intensity(\(Double(settings.amount)/100))")
                showPanel();primary.prepareSceneRound()
            }else{
                if let state=resumed,!away {restoreDesktop(state)}else{idle()}
                if manualWake{manualWake=false;visitOrigin=Date();shownCycle=nil}
                if resumed == nil{applySettings()}else{js("pet.intensity(\(Double(settings.amount)/100))");updateVisit(at:Date())}
                let action=afterLoad;afterLoad=nil;action?()
                if showcase != nil && resumed == nil{startShowcaseClip()}
                if away {js("pet.paused(true)")}
            }
            let showBehavior=CommandLine.arguments.contains("--behavior")
            if first && savesPreferences && (showBehavior || CommandLine.arguments.contains("--studio") || !UserDefaults.standard.bool(forKey:"didIntroduceStudio")){
                openStudio(showBehavior);UserDefaults.standard.set(true,forKey:"didIntroduceStudio")
            }
            if first && testing && slot==1 {
                DispatchQueue.main.asyncAfter(deadline:.now()+0.35){
                    if self.verifyModels {Task { @MainActor in await self.verifyModelPicker() }}
                    else{self.verify()}
                }
            }
        }
    }
    func menu(includeStage:Bool=true)->NSMenu {
        let m=NSMenu();m.delegate=self
        for (name,action) in [
            ("Показать сейчас",#selector(showNow)),
            ("Примерочная движений…",#selector(library)),
            ("Поведение…",#selector(behavior)),
            (showcase?.kind == .movements ? "Остановить показ движений" : "Показать все движения подряд",#selector(toggleMovementShowcase)),
            (primary.sceneRound != nil || showcase?.kind == .scenes ? "Остановить показ сценок" : "Показать все сценки",#selector(toggleSceneShowcase))
        ] {
            let item=m.addItem(withTitle:name,action:action,keyEquivalent:"");item.target=self
        }
        if includeStage {m.setSubmenu(stageMenu(),for:m.addItem(withTitle:"Сцена во весь экран",action:nil,keyEquivalent:""))}
        m.addItem(.separator())
        let walk=m.addItem(withTitle:"Гулять по экрану",action:#selector(toggleWalk),keyEquivalent:"");walk.target=self;walk.state=walkEnabled ? .on:.off
        if models.choices.count>1{
            let list=NSMenu()
            for choice in models.choices{
                let item=list.addItem(withTitle:choice.title,action:#selector(chooseModel(_:)),keyEquivalent:"")
                item.representedObject=choice.rawValue;item.target=self;item.state=choice==selectedModel ? .on:.off
            }
            m.setSubmenu(list,for:m.addItem(withTitle:"Персонаж",action:nil,keyEquivalent:""))
        }
        let sizeMenu=NSMenu()
        for percent in Set(sizes.filter{$0<=maximumSize}+[sizePercent]).sorted() {
            let item=sizeMenu.addItem(withTitle:"\(percent) %",action:#selector(chooseSize(_:)),keyEquivalent:"")
            item.tag=percent; item.target=self; item.state=percent==sizePercent ? .on:.off
        }
        m.setSubmenu(sizeMenu,for:m.addItem(withTitle:"Размер",action:nil,keyEquivalent:""))
        let reset=m.addItem(withTitle:"Сбросить ракурс",action:#selector(resetView),keyEquivalent:"");reset.target=self
        let gaits=NSMenu()
        for (id,title) in [(3,"Мягкая прогулка"),(1,"Обычный шаг"),(2,"Сдержанный шаг")] {
            let item=gaits.addItem(withTitle:title,action:#selector(chooseGait(_:)),keyEquivalent:"")
            item.tag=id;item.target=self;item.state=id==walkClip ? .on:.off
        }
        m.setSubmenu(gaits,for:m.addItem(withTitle:"Походка",action:nil,keyEquivalent:""))
        let scenes=NSMenu()
        for i in catalog.indices where catalog[i].role=="scene" {
            let item=scenes.addItem(withTitle:catalog[i].label,action:#selector(choose(_:)),keyEquivalent:"")
            item.tag=catalogStart+i;item.target=self
        }
        m.setSubmenu(scenes,for:m.addItem(withTitle:"Сценки",action:nil,keyEquivalent:""))
        m.addItem(.separator())
        if slot>1 {
            let close=m.addItem(withTitle:"Убрать этого персонажа",action:#selector(closeCompanion),keyEquivalent:"")
            close.target=self
            return m
        }
        let add=NSMenu()
        for choice in models.choices{
            let item=add.addItem(withTitle:choice.title,action:#selector(addCompanion(_:)),keyEquivalent:"")
            item.target=self;item.representedObject=choice.rawValue
        }
        if companions.count<Self.maximumSlots-1 {m.setSubmenu(add,for:m.addItem(withTitle:"Добавить персонажа",action:nil,keyEquivalent:""))}
        for child in companions.sorted(by:{$0.slot<$1.slot}){
            m.setSubmenu(child.menu(includeStage:false),for:m.addItem(withTitle:"№\(child.slot) · "+child.selectedModel.title,action:nil,keyEquivalent:""))
        }
        m.addItem(.separator())
        let login=m.addItem(withTitle:"Запускать при входе в macOS",action:#selector(toggleLogin),keyEquivalent:"")
        login.target=self;refreshLogin(login)
        m.addItem(.separator());let quit=m.addItem(withTitle:"Закрыть программу",action:#selector(NSApplication.terminate(_:)),keyEquivalent:"q");quit.target=NSApp
        return m
    }
    func menuNeedsUpdate(_ menu:NSMenu){
        if let item=menu.items.first(where:{$0.action == #selector(toggleLogin)}){refreshLogin(item)}
    }
    func refreshLogin(_ item:NSMenuItem){
        let state=SMAppService.mainApp.status
        item.state=state == .enabled ? .on : state == .requiresApproval ? .mixed : .off
    }
    @objc func toggleLogin(_ item:NSMenuItem){changeLogin();refreshLogin(item)}
    func syncLogin(){
        let state=SMAppService.mainApp.status
        galleryWeb?.evaluateJavaScript("window.setLogin?.(\(state == .enabled),\(state == .requiresApproval))")
    }
    func changeLogin(){
        let service=SMAppService.mainApp
        do{
            if service.status == .enabled || service.status == .requiresApproval{try service.unregister()}
            else{
                try service.register()
                if service.status == .requiresApproval{SMAppService.openSystemSettingsLoginItems()}
            }
        }catch{NSAlert(error:error).runModal()}
        for actor in actors where actor.galleryReady{actor.syncLogin()}
        refreshMenus()
    }
    func play(_ index:Int,_ dir:Int=0) {
        guard ready else{return}
        cancelFacing()
        current=index;activeDirection=dir;phaseStart=now;rootDistance=0
        if dir==0{js("pet.play(\(index),0,true)")}
        else{faceTravel(resuming:false)}
    }
    func resumeTravelClock(){
        guard let start=facingSince else{return}
        let held=now-start
        phaseStart+=held;deadline+=held;walkUntil+=held;lastTick=now;facingSince=nil
    }
    func cancelFacing(){
        guard facingSince != nil else{return}
        resumeTravelClock()
        js("window.pet?.cancelPivot()")
    }
    func faceTravel(resuming:Bool){
        guard let view=web,ready,activeDirection != 0 else{return}
        let start=now
        facingSince=start
        view.callAsyncJavaScript("return await pet.faceTravel(i,d,resume?'current':null)",
            arguments:["i":current,"d":activeDirection,"resume":resuming],in:nil,in:.page){result in
            guard self.web===view,self.facingSince==start else{return}
            self.resumeTravelClock()
            if (try? result.get()) as? Bool != true{
                if self.showcase != nil{self.finishShowcase()}else{self.idle()}
            }
        }
    }
    func scheduleScene(){nextScene=settings.seconds.map{now+Double.random(in:$0)} ?? .infinity}
    func applySettings(previous:Behavior?=nil){
        js("pet.intensity(\(Double(settings.amount)/100))")
        if previous == nil || previous?.seconds != settings.seconds {scheduleScene()}
        if !settings.gaze{js("pet.gaze(0,0)")}
        updateVisit(at:Date())
    }
    @objc func showNow(){
        finishShowcase()
        if !ready{manualWake=true;loadDesktop();return}
        if settings.visits?.enabled==true {restartVisit()}
        showActor()
    }
    func restartVisit(){
        let date=Date()
        visitOrigin=date;shownCycle=nil
        updateVisit(at:date)
    }
    func updateVisit(at date:Date){
        guard showcase==nil,primary.sceneRound==nil else{return}
        guard let visits=settings.visits,visits.enabled else{
            if visitOrigin != nil {
                if !ready{loadDesktop();return}
                visitOrigin=nil;shownCycle=nil
                if away {showPanel()}
                idle();scheduleScene()
            }
            return
        }
        let origin=visitOrigin ?? date
        visitOrigin=origin
        let elapsed=max(0,date.timeIntervalSince(origin))
        let cycle=Int(elapsed)/visits.period
        let start=origin.addingTimeInterval(Double(cycle*visits.period))
        let remaining=Double(visits.duration)-date.timeIntervalSince(start)
        if remaining<=0 {
            if !away {
                hiddenSince=date;endRotation();cancelFacing();away=true;picked=nil;dragged=false;moving=false;lastReaction = -1
                panel.ignoresMouseEvents=true;hideActor()
                if let home=sceneHome{moveActor(to:NSPoint(x:home,y:actorFrame.minY))}
                sceneHome=nil;walkingHome=false
                js("pet.gaze(0,0);pet.paused(true)")
            }
            shownCycle=nil
            let next=start.addingTimeInterval(Double(visits.period))
            let warmAt=next.addingTimeInterval(-prewarm)
            var wake=next
            if manualWake{loadDesktop();return}
            if warmAt>date{
                if gallery != nil || visits.period-visits.duration>=30{
                    let discardAt=hiddenSince.addingTimeInterval(1)
                    if gallery != nil || date>=discardAt{releaseDesktop();wake=warmAt}
                    else{wake=min(discardAt,warmAt)}
                }
            }else{loadDesktop()}
            timer?.fireDate=wake
        }else if shownCycle != cycle {
            guard ready else{loadDesktop();timer?.fireDate=date.addingTimeInterval(0.15);return}
            shownCycle=cycle
            if away {showPanel()}
            if settings.seconds != nil && !allowed("scene").isEmpty {
                nextPerformance(manual:false,within:remaining)
            }else{idle();scheduleScene()}
        }
    }
    func showPanel(){
        away=false;lastTick=now;timer?.fireDate=Date()
        js("pet.paused(false)")
        showActor()
    }
    @objc func toggleMovementShowcase(){primary.stopSceneRound();toggleShowcase(.movements)}
    func toggleShowcase(_ kind:Showcase.Kind){
        if showcase?.kind==kind{finishShowcase();return}
        let clips:[Int]
        switch kind{
        case .movements:
            clips=[startClip,3,1,turnClip,2,stopClip]+catalog.indices.filter{catalog[$0].role != "travel"}.map{catalogStart+$0}
        case .scenes:
            clips=allowed("scene",manual:true)
        }
        guard !clips.isEmpty else{return}
        showcaseRequest+=1
        showcase=Showcase(kind:kind,clips:clips)
        afterLoad=nil;manualWake=false;deadline = .infinity
        refreshMenus()
        if ready{startShowcaseClip()}else{loadDesktop()}
    }
    func startShowcaseClip(){
        walkingHome=false
        guard let show=showcase,ready,let view=web else{return}
        if away{showPanel()}else{showActor()}
        moving=false;lastReaction = -1;deadline = .infinity
        let position=show.position,clip=show.clips[position]
        showcaseRequest+=1;let request=showcaseRequest
        view.callAsyncJavaScript("await pet.prepare(i);return true",arguments:["i":clip],in:nil,in:.page){result in
            guard self.web===view,self.ready,self.showcaseRequest==request else{return}
            guard (try? result.get()) as? Bool==true else{self.finishShowcase();return}
            if clip==self.startClip{
                guard let display=self.actorScreen else{return}
                let screen=display.frame
                self.direction=self.actorFrame.midX<screen.midX ? 1:-1
                let edge=self.clamp(NSPoint(x:self.direction>0 ? screen.maxX+self.actorFrame.width:screen.minX-self.actorFrame.width,y:self.actorFrame.minY),to:display)
                let distance=[3,1].reduce(0.0){$0+2*self.gaitRates[$1]*self.durations[$1]}
                let start=self.catalog[self.startClip-self.catalogStart].travel?.max() ?? 0
                let turn=self.catalog[self.turnClip-self.catalogStart].travel?.max() ?? 0
                self.roomScale=min(1,abs(edge.x-self.actorFrame.minX)/(self.actorFrame.height*(distance+(start+turn)*self.travelScale)))
                self.strideRemainder=0
            }
            if position>0 && show.clips[position-1]==self.turnClip{self.direction = -self.direction}
            if (1...3).contains(clip){
                self.moving=true
                self.play(clip,Int(self.direction));self.deadline=self.now+2*self.durations[clip]
            }else if self.catalog[clip-self.catalogStart].role=="travel"{
                self.lastReaction=clip;self.play(clip,Int(self.direction));self.deadline=self.now+self.durations[clip]
            }else{self.perform(clip)}
            if position+1<show.clips.count{self.js("pet.prefetch(\(show.clips[position+1]))")}
        }
    }
    func finishShowcase(){
        if primary.sceneRound != nil{primary.stopSceneRound();return}
        guard showcase != nil else{return}
        showcase=nil;showcaseRequest+=1;refreshMenus()
        if ready{idle();scheduleScene()}
        shownCycle=nil;updateVisit(at:Date())
    }
    @objc func chooseModel(_ item:NSMenuItem){
        if let id=item.representedObject as? String,let choice=PetModel(rawValue:id){selectModel(choice)}
    }
    func selectModel(_ choice:PetModel,preview:[String:Any]?=nil){
        guard models.choices.contains(choice) else{return}
        modelRequest+=1
        let request=modelRequest
        guard choice != selectedModel else{return}
        if preview==nil,galleryReady,let view=galleryWeb{
            view.evaluateJavaScript("window.studioSnapshot?.()"){[weak self] value,_ in
                guard let self,self.modelRequest==request else{return}
                self.changeModel(to:choice,preview:value as? [String:Any] ?? self.savedPreview)
            }
        }else{changeModel(to:choice,preview:preview ?? savedPreview)}
    }
    func captureDesktop()->Playhead?{
        guard ready,!away,deadline.isFinite,durations.indices.contains(current),durations[current]>0 else{return nil}
        let clock=facingSince ?? now
        let length=durations[current],progress=max(0,clock-phaseStart)/length
        let looping=current<catalogStart || catalog[current-catalogStart].role=="idle"
        return Playhead(clip:current,direction:activeDirection,
            phase:looping ? progress.truncatingRemainder(dividingBy:1):min(0.99999,progress),
            remaining:max(0,deadline-clock)/length,walkRemaining:max(0,walkUntil-clock))
    }
    func restoreDesktop(_ state:Playhead){
        guard durations.indices.contains(state.clip) else{idle();return}
        let length=durations[state.clip]
        current=state.clip;activeDirection=state.direction;phaseStart=now-state.phase*length
        deadline=now+state.remaining*length;walkUntil=now+state.walkRemaining
        let row=current-catalogStart
        rootDistance=catalog.indices.contains(row) ? catalog[row].distance(at:state.phase)*travelScale:0
        js("pet.play(\(current),\(state.direction),true,\(state.phase))")
    }
    func changeModel(to choice:PetModel,preview:[String:Any]?){
        endRotation();picked=nil;dragged=false;lastCursor=NSPoint(x:-99999,y:-99999)
        if ready && primary.sceneRound==nil{resumeDesktop=captureDesktop()}
        showcaseRequest+=1
        releaseDesktop();durations=[];gaitRates=[];strideRemainder=0
        panel.ignoresMouseEvents=true
        selectedModel=choice
        if savesPreferences{UserDefaults.standard.set(choice.rawValue,forKey:"selectedModel")}
        owner?.remember(choice,at:slot)
        syncSlotPickers()
        panel.title=choice.name;status?.button?.toolTip=choice.title;refreshMenus()
        if let window=gallery{
            savedPreview=preview;galleryReady=false
            if let options=preview?["settings"] as? Bool{showSettings=options}
            let bounds=window.contentView!.bounds
            if let old=galleryWeb{
                old.configuration.userContentController.removeScriptMessageHandler(forName:"pet")
                old.navigationDelegate=nil;old.stopLoading()
            }
            let next=makeView(bounds,preview:preview);galleryWeb=next;window.contentView=next
            window.title=studioTitle;loadGallery(next)
        }
        if !away || manualWake || showcase != nil || primary.sceneRound != nil{loadDesktop()}else{updateVisit(at:Date())}
    }
    var studioTitle:String {selectedModel.title+" — примерочная"}
    func loadGallery(_ view:WKWebView){
        view.load(URLRequest(url:URL(string:"shino://local/studio.html")!))
    }
    @objc func library(){openStudio(false)}
    @objc func behavior(){openStudio(true)}
    func openStudio(_ options:Bool){
        showSettings=options
        if gallery==nil{
            let w=NSWindow(contentRect:NSRect(x:0,y:0,width:800,height:680),styleMask:[.titled,.closable,.resizable,.miniaturizable],backing:.buffered,defer:false)
            w.title=studioTitle;w.minSize=NSSize(width:590,height:455);w.isReleasedWhenClosed=false;w.delegate=self
            savedPreview=nil;galleryReady=false
            let reuse=away && ready && web != nil
            let view=reuse ? web! : makeView(w.contentView!.bounds)
            if reuse{web=nil;ready=false;mask=[];view.removeFromSuperview()}
            view.frame=w.contentView!.bounds
            w.contentView=view;galleryWeb=view;gallery=w;w.center()
            if reuse{galleryReady=true;view.evaluateJavaScript("pet.enterStudio()");syncStudio()}
            else{loadGallery(view)}
            if away{updateVisit(at:Date())}
        }else{syncStudio()}
        if let gallery,let stage=primary.stage,gallery.screen?.sceneID==stage.screen.sceneID {gallery.level=NSWindow.Level(rawValue:stage.window.level.rawValue+1)}
        NSApp.activate(ignoringOtherApps:true);gallery?.makeKeyAndOrderFront(nil)
    }
    func syncStudio(){
        syncBackdrop()
        syncLogin()
        syncSlotPickers()
        guard let data=try? JSONEncoder().encode(settings),let json=String(data:data,encoding:.utf8) else{return}
        galleryWeb?.evaluateJavaScript("window.setupStudio?.(\(json),\(showSettings),\(sizePercent),\(maximumSize))")
        syncProfile()
    }
    func windowDidMiniaturize(_ note:Notification){
        if note.object as? NSWindow === gallery { galleryWeb?.evaluateJavaScript("window.pet?.visibility(false)") }
    }
    func windowDidDeminiaturize(_ note:Notification){
        if note.object as? NSWindow === gallery { galleryWeb?.evaluateJavaScript("window.pet?.visibility(true)") }
    }
    func windowWillClose(_ note:Notification){
        guard let window=note.object as? NSWindow,window===gallery else{return}
        galleryWeb?.configuration.userContentController.removeScriptMessageHandler(forName:"pet")
        galleryWeb=nil;gallery=nil;savedPreview=nil;galleryReady=false
    }
    func allowed(_ role:String,manual:Bool=false)->[Int]{
        catalog.indices.filter{catalog[$0].role==role && (manual || !settings.disabled.contains(catalog[$0].key))}.map{$0+catalogStart}
    }
    func pickIdle()->Int{
        var choices=allowed("idle")
        if choices.count>1{choices.removeAll{$0==lastIdle}}
        let weights=choices+choices.filter{$0<catalogStart+2}+choices.filter{$0<catalogStart+2}
        return weights.randomElement() ?? 0
    }
    func idle(){
        walkingHome=false
        moving=false;lastReaction = -1
        let id=plannedIdle.flatMap{allowed("idle").contains($0) ? $0:nil} ?? pickIdle()
        plannedIdle=nil;lastIdle=id;play(id)
        deadline=now+durations[id]
    }
    func nextPerformance(manual:Bool,within remaining:Double?=nil){
        var choices=allowed("scene",manual:manual)
        if let remaining {
            let fitting=choices.filter{durations[$0]+1<=remaining}
            if !fitting.isEmpty{choices=fitting}
        }
        if choices.count>1{choices.removeAll{$0==lastScene}}
        scheduleScene()
        let preferred=plannedScene;plannedScene=nil
        if let clip=preferred.flatMap({choices.contains($0) ? $0:nil}) ?? choices.randomElement(){
            perform(clip)
            if let remaining {
                // Leave time to settle into the stance even during a very short visit.
                let stanceTime=min(1,remaining/3)
                deadline=min(deadline,now+remaining-stanceTime)
            }
        }
    }
    func perform(_ clip:Int){
        guard ready else{return}
        moving=false;lastScene=clip;lastReaction=clip;roomScale=1
        let row=catalog.indices.contains(clip-catalogStart) ? catalog[clip-catalogStart]:nil
        walkingHome=false
        if let path=row?.travel {
            if !walkEnabled && row?.role=="scene" && sceneHome==nil {sceneHome=actorFrame.minX}
            guard let screen=actorScreen?.frame else{return}
            let roomLeft=actorFrame.minX-screen.minX,roomRight=screen.maxX-actorFrame.maxX
            direction=roomRight>=roomLeft ? 1:-1
            roomScale=min(1,max(0,max(roomLeft,roomRight))/(actorFrame.height*travelScale*max(0.01,path.map{abs($0)}.max() ?? 0.01)))
            play(clip,Int(direction))
        }else{play(clip)}
        deadline=now+durations[clip]
        let next=pickIdle();plannedIdle=next;js("pet.prefetch(\(next))")
    }
    @objc func toggleWalk(){
        editProfile{$0.walking.toggle()}
    }
    var maximumSize:Int{
        guard let display=actorScreen else{return 200}
        return Self.maximumSize(in:onStage ? display.frame : display.visibleFrame)
    }
    static func maximumSize(in area:NSRect)->Int{
        max(15,min(400,Int(100*min(area.height/panelHeight,area.width/238))))
    }
    static func dimensions(at percent:Int)->NSSize{
        let scale=CGFloat(percent)/100
        return NSSize(width:round(238*scale),height:round(panelHeight*scale))
    }
    func resize(to requested:Int) {
        guard let screen=actorScreen else{return}
        let percent=min(maximumSize,max(15,requested)),old=actorFrame
        let size=Self.dimensions(at:percent)
        let onFloor=abs(old.minY+Pet.floorFraction*old.height-screen.frame.minY-1)<2
        let y=onFloor ? screen.frame.minY+1-Pet.floorFraction*size.height : old.minY
        let origin=NSPoint(x:old.midX-size.width/2,y:y)
        setActorFrame(NSRect(origin:clamp(origin,to:screen,size:size),size:size))
        if let home=sceneHome{sceneHome=clamp(NSPoint(x:home+(old.width-size.width)/2,y:origin.y),to:screen,size:size).x}
        sizePercent=percent
    }
    func setUserSize(_ value:Int) {
        editProfile{$0.size=min(maximumSize,max(15,value))}
    }
    func syncSize(){if galleryReady{syncProfile()}}
    func windowDidChangeScreen(_ notification:Notification){
        guard let window=notification.object as? NSWindow,window===panel,!onStage else{return}
        if sizePercent>maximumSize{resize(to:maximumSize)}
        syncSize();refreshMenus()
    }
    @objc func chooseSize(_ item:NSMenuItem) {
        setUserSize(item.tag);syncSize()
    }
    func requestWalk(){
        sceneHome=nil;walkingHome=false
        finishShowcase()
        if !ready{
            afterLoad={ [weak self] in if let self{self.beginWalk(at:self.now)} }
            showNow();return
        }
        if away{restartVisit()}
        beginWalk(at:now)
    }
    @objc func chooseGait(_ item:NSMenuItem) {
        editProfile{$0.gait=item.tag;$0.walking=true}
        if !moving && facingSince==nil{requestWalk()}
    }
    @objc func choose(_ item:NSMenuItem){
        finishShowcase()
        let tag=item.tag
        if !ready{afterLoad={ [weak self] in self?.perform(tag) };showNow();return}
        if away{restartVisit()};perform(tag)
    }
    func clamp(_ pos:NSPoint,to screen:NSScreen,size:NSSize?=nil)->NSPoint {
        let windowSize=size ?? actorFrame.size
        let horizontal=screen.frame, vertical=onStage ? screen.frame : screen.visibleFrame
        let left=horizontal.minX+2-silhouette.minX*windowSize.width
        let right=horizontal.maxX-2-silhouette.maxX*windowSize.width
        let bottom=screen.frame.minY+1-Pet.floorFraction*windowSize.height
        let top=vertical.maxY-windowSize.height
        return NSPoint(x:max(left,min(right,pos.x)),y:max(bottom,min(top,pos.y)))
    }
    func sendView(){if ready{js("pet.desktopView(\(viewAngles.x),\(viewAngles.y))")}}
    func saveView(){if savesPreferences{UserDefaults.standard.set([Double(viewAngles.x),Double(viewAngles.y)],forKey:"desktopView")}}
    @objc func resetView(){viewAngles = .zero;saveView();sendView()}
    func endRotation(){
        guard let rotationDrag else{return}
        self.rotationDrag=nil
        if primary.sceneRound != nil{saveView();return}
        let held=now-rotationDrag.start
        phaseStart+=held;deadline+=held;walkUntil+=held;nextScene+=held
        saveView()
        if ready && !away {
            js("pet.paused(false)")
            if activeDirection != 0 {faceTravel(resuming:true)}
        }
    }
    func grab(_ mouse:NSPoint,rotating:Bool=false){
        guard ready && !away else{return}
        cancelFacing()
        if rotating{
            rotationDrag=(mouse,viewAngles,now)
            if primary.sceneRound==nil{js("pet.paused(true)")}
            return
        }
        if primary.sceneRound==nil{finishShowcase()};guard !away else{return}
        picked=mouse;startOrigin=actorFrame.origin;lastMove=now;previousPointer=mouse;pointerVelocity = .zero;dragged=false
        glanceUntil=0;js("pet.gaze(0,0)");moving=false
    }
    func moveGrab(_ mouse:NSPoint){
        if let rotationDrag{
            let rate=2*CGFloat.pi/max(160,actorFrame.width*1.45)
            let yaw=rotationDrag.angles.x-(mouse.x-rotationDrag.mouse.x)*rate
            let pitch=rotationDrag.angles.y-(mouse.y-rotationDrag.mouse.y)*rate*0.8
            viewAngles=NSPoint(x:atan2(sin(yaw),cos(yaw)),y:max(-maximumPitch,min(maximumPitch,pitch)))
            self.rotationDrag=(mouse,viewAngles,rotationDrag.start)
            sendView();return
        }
        guard let picked else{return}
        let dx=mouse.x-picked.x,dy=mouse.y-picked.y
        guard dragged || hypot(dx,dy)>3 else{return}
        if !dragged {sceneHome=nil;walkingHome=false;if primary.sceneRound==nil{play(0)}}
        dragged=true
        let screen=onStage ? actorScreen : (NSScreen.screens.first{$0.frame.contains(mouse)} ?? actorScreen)
        guard let screen else{return}
        let target=clamp(NSPoint(x:startOrigin.x+dx,y:startOrigin.y+dy),to:screen)
        moveActor(to:target)
        let time=now,elapsed=max(1.0/240,time-lastMove)
        let weight=1-exp(-elapsed/0.035)
        pointerVelocity.x+=weight*((mouse.x-previousPointer.x)/elapsed-pointerVelocity.x)
        pointerVelocity.y+=weight*((mouse.y-previousPointer.y)/elapsed-pointerVelocity.y)
        previousPointer=mouse;lastMove=time
        js("pet.drag(\(pointerVelocity.x),\(pointerVelocity.y))")
    }
    func release(){
        if rotationDrag != nil{endRotation();return}
        guard picked != nil else{return};picked=nil
        if primary.sceneRound==nil{if dragged {idle()}else {nextPerformance(manual:true)}}
    }
    func hit(_ mouse:NSPoint)->Bool {
        let rect=actorFrame
        guard rect.contains(mouse),mask.count==32*52 else{return false}
        let x=min(31,max(0,Int((mouse.x-rect.minX)/rect.width*32)))
        let y=min(51,max(0,Int((rect.maxY-mouse.y)/rect.height*52)))
        for row in max(0,y-1)...min(51,y+1) {
            for col in max(0,x-1)...min(31,x+1) where mask[row*32+col]==49 {return true}
        }
        return false
    }
    func beginWalk(at time:Double){
        js("pet.prefetch(\(walkClip));pet.prefetch(\(stopClip));pet.prefetch(\(turnClip))")
        moving=true;lastReaction = -1;strideRemainder=0;walkStart=time;roomScale=1
        guard let f=actorScreen?.frame else{return}
        if actorFrame.midX < f.minX+actorFrame.width {direction=1}
        if actorFrame.midX > f.maxX-actorFrame.width {direction = -1}
        play(startClip,Int(direction));deadline=time+durations[startClip];walkUntil=deadline+Double.random(in:5.5...9)
    }
    func cursor(_ mouse:NSPoint,_ time:Double){
        guard settings.gaze,time>=nextGaze else{return};nextGaze=time+0.09
        let center=NSPoint(x:actorFrame.midX,y:actorFrame.minY+actorFrame.height*0.78)
        let dx=mouse.x-center.x,dy=mouse.y-center.y,range=actorFrame.height*0.88
        if hypot(dx,dy)<range && hypot(mouse.x-lastCursor.x,mouse.y-lastCursor.y)>3 && time>=nextGlance{
            glanceUntil=time+1.5;nextGlance=time+3
        }
        lastCursor=mouse
        if time<glanceUntil && !moving{
            js("pet.gaze(\(max(-1,min(1,dx/(range*0.7)))),\(max(-1,min(1,dy/(range*0.65)))))");gazeSent=true
        }else if gazeSent{js("pet.gaze(0,0)");gazeSent=false}
    }
    func tick(){
        if sceneRound != nil{advanceSceneRound(at:now)}
        guard hasLoaded else{return}
        updateVisit(at:Date())
        if away || !ready || durations.isEmpty{return}
        let time=now,elapsed=min(0.10,time-lastTick);lastTick=time
        if picked != nil || rotationDrag != nil{return}
        if sceneHome==nil && facingSince==nil && showcase==nil && primary.sceneRound==nil && time>=nextScene && lastReaction<0{
            if allowed("scene").isEmpty{scheduleScene()}
            else{nextPerformance(manual:false)}
        }
        let mouse=NSEvent.mouseLocation
        let rect=actorFrame
        let nearPointer=rect.insetBy(dx:-36,dy:-36).contains(mouse)
        let bounds=CGRect(x:rect.minX+silhouette.minX*rect.width,y:rect.minY+silhouette.minY*rect.height,
                          width:silhouette.width*rect.width,height:silhouette.height*rect.height)
        let nearEdge=actorScreen.map{!$0.visibleFrame.insetBy(dx:16,dy:16).contains(bounds)} ?? false
        let watch=nearPointer || nearEdge
        if watchingMask != watch{watchingMask=watch;js("pet.watchMask(\(watch))")}
        panel.ignoresMouseEvents=testing || !hit(mouse);cursor(mouse,time)
        if primary.sceneRound != nil || facingSince != nil{return}
        if walkingHome,let target=sceneHome{
            let remaining=target-actorFrame.minX
            let step=max(0,gaitRates[current])*actorFrame.height*elapsed
            if abs(remaining)<=step+0.5 || step==0 {
                moveActor(to:NSPoint(x:target,y:actorFrame.minY))
                walkingHome=false;sceneHome=nil;moving=false;lastReaction = -1;strideRemainder=0
                if showcase==nil{idle();scheduleScene();return}
                deadline=time
            }else{
                translateHome(towards:target,step:step)
                return
            }
        }
        if moving || lastReaction>=0 {
            if catalog.indices.contains(current-catalogStart),let _=catalog[current-catalogStart].travel{
                let row=catalog[current-catalogStart],phase=(time-phaseStart)/durations[current]
                let distance=row.distance(at:phase)*travelScale
                translate(direction*(distance-rootDistance)*roomScale*actorFrame.height)
                rootDistance=distance
            }else if moving{
                let rate=showcase==nil ? gaitRates[walkClip] : gaitRates[current]*roomScale
                translate(direction*actorFrame.height*rate*elapsed)
            }
        }
        if time>=deadline,let home=sceneHome{
            if abs(home-actorFrame.minX)>0.5 {
                walkingHome=true;direction=home>actorFrame.minX ? 1:-1
                moving=true;strideRemainder=0;play(walkClip,Int(direction));deadline = .infinity
                return
            }
            sceneHome=nil
        }
        if let show=showcase{
            if time>=deadline{
                if show.position+1==show.clips.count{finishShowcase()}
                else{showcase?.position+=1;startShowcaseClip()}
            }
            return
        }
        if moving && current==walkClip,let screen=actorScreen{
            let limit=clamp(NSPoint(x:direction>0 ? screen.frame.maxX+actorFrame.width : screen.frame.minX-actorFrame.width,y:actorFrame.minY),to:screen)
            let clearance=abs(limit.x-actorFrame.minX)/actorFrame.height
            let turn=(catalog[turnClip-catalogStart].travel?.max() ?? 0.3)*travelScale
            if clearance<turn+0.08{play(turnClip,Int(direction));deadline=time+durations[turnClip];return}
        }
        guard time>=deadline else{return}
        if moving{
            if current==startClip || current==turnClip {
                if current==turnClip{direction = -direction;walkUntil=time+Double.random(in:3...6)}
                play(walkClip,Int(direction));deadline=walkUntil
            }else if current==stopClip{idle()}
            else{play(stopClip,Int(direction));deadline=time+durations[stopClip]}
        }else if lastReaction>=0{idle()}
        else if settings.visits?.enabled != true && walkEnabled && (lastIdle==0 || Bool.random()){beginWalk(at:time)}
        else{idle()}
    }
    func translateHome(towards target:CGFloat,step:CGFloat){
        let origin=actorFrame.origin
        let sign:CGFloat=target>origin.x ? 1:-1
        let distance=min(max(0,step+sign*strideRemainder),abs(target-origin.x))
        let x=origin.x+sign*distance
        moveActor(to:NSPoint(x:x,y:origin.y))
        strideRemainder=x-actorFrame.minX
    }
    func translate(_ step:CGFloat){
        guard step.isFinite,let screen=actorScreen else{return}
        let pos=actorFrame.origin
        let target=clamp(NSPoint(x:pos.x+step+strideRemainder,y:pos.y),to:screen)
        moveActor(to:NSPoint(x:target.x,y:pos.y));strideRemainder=target.x-actorFrame.minX
    }
    func verifySizes(_ sizes:[Int]){
        guard let percent=sizes.first else{verifyPointer();return}
        resize(to:percent);perform(clipID("peek"))
        DispatchQueue.main.asyncAfter(deadline:.now()+0.28){
            self.web.evaluateJavaScript("({width:innerWidth,triangles:pet.check().triangles})"){value,_ in
                guard let result=value as? [String:Any],let width=result["width"] as? Int,
                      self.sizePercent==min(percent,self.maximumSize),abs(Double(width)-self.panel.frame.width)<2,
                      abs(self.panel.frame.width-round(238*Double(self.sizePercent)/100))<1,(result["triangles"] as? Int ?? 0)>100 else{print("Scale failed",percent);exit(1)}
                self.verifySizes(Array(sizes.dropFirst()))
            }
        }
    }
    func verifyPointer(){
        resize(to:100)
        let origin=panel.frame.origin,clip=current
        func send(_ type:NSEvent.EventType,_ x:CGFloat,_ flags:NSEvent.ModifierFlags,y:CGFloat=110){
            let e=NSEvent.mouseEvent(with:type,location:NSPoint(x:x,y:y),modifierFlags:flags,
                timestamp:now,windowNumber:panel.windowNumber,context:nil,eventNumber:0,clickCount:1,pressure:1)!
            panel.sendEvent(e)
        }
        send(.leftMouseDown,110,.command);send(.leftMouseDragged,168,.command)
        send(.leftMouseUp,168,[])
        guard abs(viewAngles.x)>0.5,rotationDrag==nil,current==clip,panel.frame.origin==origin else{print("Command drag failed");exit(1)}
        send(.leftMouseDown,110,.command)
        send(.leftMouseDragged,110,.command,y:320)
        guard viewAngles.y == -maximumPitch else{print("Lower camera limit failed");exit(1)}
        send(.leftMouseDragged,110,.command,y:310)
        guard viewAngles.y > -maximumPitch else{print("Camera stuck at lower limit");exit(1)}
        send(.leftMouseDragged,110,.command,y:30);send(.leftMouseUp,110,[],y:30)
        guard viewAngles.y == maximumPitch else{print("Upper camera limit failed");exit(1)}
        let view=viewAngles
        send(.leftMouseDown,110,[]);send(.leftMouseDragged,138,[]);send(.leftMouseUp,138,[])
        guard viewAngles==view,panel.frame.origin != origin else{print("Move after rotation failed");exit(1)}
        resetView()
        verifyRendering()
    }
    func verifyRendering(){
        let script="""
        pet.paused(false);
        const samples=[], marks=[];
        await new Promise(done=>{
            function tick(t){
                marks.push(pet.check().rendered);
                samples.push(t);
                if(samples.length===91)done();else requestAnimationFrame(tick);
            }
            requestAnimationFrame(tick);
        });
        const ms=samples.slice(1).map((v,i)=>v-samples[i]).sort((a,b)=>a-b);
        pet.paused(true);
        const pausedAt=pet.check().rendered;
        await new Promise(r=>setTimeout(r,260));
        const held=pet.check().rendered;
        pet.desktopView(.72,.14);
        const orbited=pet.check().rendered;
        return {median:ms[45],p95:ms[85],frames:marks.at(-1)-marks[0],paused:held-pausedAt,orbited:orbited-held}
        """
        // Isolate this timing window from autonomous scene changes and cursor input.
        timer?.fireDate=Date.distantFuture
        web?.callAsyncJavaScript(script,arguments:[:],in:nil,in:.page){report in
            guard let m=(try? report.get()) as? [String:NSNumber],m["paused"]?.intValue==0,
                  (m["frames"]?.intValue ?? 0)>30,(m["orbited"]?.intValue ?? 0)>0 else{
                print("Frame scheduling failed",report);exit(1)
            }
            print("Native desktop timing",m)
            print("PASS desktop rotation, ordinary drag, exact size, gallery, gait, scene order and timed visits")
            exit(0)
        }
    }
    func verify(){
        let sceneKeys=Set(catalog.filter{$0.role=="scene"}.map(\.key))
        let newScenes:Set<String>=["curtsy","highfive","shrug","giggle","chilly","hairdo","swat","twist","duckdance","teapot","superhero","hummingbird"]
        guard catalog.filter({$0.role=="idle"}).count==4,newScenes.isSubset(of:sceneKeys),
              sceneKeys.isSuperset(of:["hello","peek","yawn","idea","plane","hop","sneak","dance"]),
              durations.count==catalogStart+catalog.count else{exit(1)}
        direction = -1;beginWalk(at:now)
        let initial=panel.frame.minX
        DispatchQueue.main.asyncAfter(deadline:.now()+2.45){
            guard self.current==self.walkClip,abs(initial-self.panel.frame.minX)>4 else{print("Travel failed",self.current);exit(1)}
            let screen=self.panel.screen!
            self.panel.setFrameOrigin(self.clamp(NSPoint(x:screen.frame.minX-self.panel.frame.width,y:self.panel.frame.minY),to:screen))
            self.tick()
            guard self.current==self.turnClip else{print("Turn failed");exit(1)}
            self.perform(self.clipID("peek"));self.openStudio(false)
            DispatchQueue.main.asyncAfter(deadline:.now()+2.3){
                self.galleryWeb?.evaluateJavaScript("document.querySelectorAll('#gait button').length===3 && document.querySelectorAll('#travel button').length===3 && document.querySelectorAll('#idle button').length===4 && document.querySelectorAll('#scene button').length===\(sceneKeys.count) && window.pet?.check().active===previews.find(r=>r.key==='hello').clip"){v,_ in
                    guard v as? Bool==true else{print("Gallery failed");exit(1)}
                    let script="""
                    await Promise.all([1,2,3].map(i=>pet.prepare(i)));
                    const gaitButtons=[...document.querySelectorAll('#gait button')];
                    const walks=gaitButtons.every(b=>{b.click();return pet.check().active===Number(b.dataset.clip) && el('autoOption').hidden});
                    const curtsy=previews.find(row=>row.key==='curtsy');await pet.prepare(curtsy.clip);
                    document.querySelector(`#scene button[data-clip="${curtsy.clip}"]`).click();
                    const sceneWorks=pet.check().active===curtsy.clip && !el('autoOption').hidden && el('caption').textContent===curtsy.label;
                    const cold=previews.find(row=>row.key==='chilly'),five=previews.find(row=>row.key==='highfive');
                    await Promise.all([pet.prepare(cold.clip),pet.prepare(five.clip)]);
                    for(const t of [2,4]){
                        pet.sample(cold.clip,t);
                        if(!pet.check(true).crossings.every(z=>z!==null && z<-.125))throw Error('Forearm inside bodice');
                    }
                    for(const t of [.55,.9,1.3]){
                        pet.sample(five.clip,t);
                        const pose=pet.check(true);
                        if(pose.chestPitch>.14 || pose.neckPitch>.17 || pose.headPitch>.36)throw Error('High five posture');
                    }
                    choose(previews.find(row=>row.key==='peek'));el('auto').click();el('showOptions').click();
                    el('scaleExact').value=67;el('scaleExact').dispatchEvent(new Event('input'));
                    el('frequency').value='custom';el('low').value=21;el('high').value=35;
                    el('amount').value=80;el('gaze').checked=false;save();
                    el('showLibrary').click();el('portrait').click();el('pause').click();
                    return walks && sceneWorks && stopped && closeUp && !el('auto').checked
                    """
                    self.galleryWeb?.callAsyncJavaScript(script,arguments:[:],in:nil,in:.page){result in
                        guard (try? result.get()) as? Bool==true else{print("Studio controls failed",result);exit(1)}
                        DispatchQueue.main.asyncAfter(deadline:.now()+0.15){
                            guard self.settings.low==21,self.settings.high==35,self.settings.amount==80,
                                  self.sizePercent==67,!self.settings.gaze,!self.allowed("scene").contains(self.clipID("peek")),
                                  self.settings.seconds==21...35 else{print("Preferences bridge failed");exit(1)}
                            self.verifyVisits()
                        }
                    }
                }
            }
        }
    }

    func verifyVisits(){
        let old = #"{"frequency":"custom","low":21,"high":35,"amount":80,"gaze":false,"disabled":["peek"]}"#
        guard let stored=try? JSONDecoder().decode(Behavior.self,from:Data(old.utf8)),
              stored.visits==nil,stored.disabled==["peek"] else{print("Legacy settings failed");exit(1)}
        let script="""
        el('showOptions').click();el('presence').value='visits';
        el('periodUnit').value='1';el('period').value=4;el('duration').value=2;
        el('frequency').value='fixed';el('low').value=6;save();
        """
        galleryWeb?.evaluateJavaScript(script){_,error in
            guard error==nil else{print("Visit form failed");exit(1)}
            DispatchQueue.main.asyncAfter(deadline:.now()+0.12){
                guard self.settings.visits==Visits(enabled:true,period:4,duration:2),
                      self.settings.seconds==6...6,self.panel.isVisible,
                      self.allowed("scene").contains(self.current) else{print("Arrival failed");exit(1)}
            }
            DispatchQueue.main.asyncAfter(deadline:.now()+1.7){
                guard self.allowed("idle").contains(self.current) else{print("Arrival stance failed");exit(1)}
            }
            DispatchQueue.main.asyncAfter(deadline:.now()+2.45){
                guard self.away,!self.panel.isVisible,self.gallery?.isVisible==true else{print("Visit did not hide");exit(1)}
            }
            DispatchQueue.main.asyncAfter(deadline:.now()+4.35){
                guard !self.away,self.panel.isVisible,self.shownCycle==1,self.allowed("scene").contains(self.current) else{print("Visit did not return");exit(1)}
                self.settings.frequency="manual";self.restartVisit()
                guard self.allowed("idle").contains(self.current) else{print("Manual arrival failed");exit(1)}
                self.updateVisit(at:self.visitOrigin!.addingTimeInterval(2.1))
                let menu=self.menu(),previousStart=self.visitOrigin
                guard self.away,menu.items.first?.title=="Показать сейчас" else{print("Missing show command");exit(1)}
                menu.performActionForItem(at:0)
                guard !self.away,self.panel.isVisible,self.visitOrigin != previousStart,self.shownCycle==0,
                      self.settings.visits==Visits(enabled:true,period:4,duration:2) else{print("Show from menu failed");exit(1)}
                self.updateVisit(at:self.visitOrigin!.addingTimeInterval(2.1))
                self.settings.visits?.enabled=false;self.applySettings()
                guard !self.away,self.panel.isVisible,self.visitOrigin==nil else{print("Continuous display failed");exit(1)}
                self.gallery?.close();self.verifyUnloading()
            }
        }
    }
    func verifyUnloading(){
        settings.visits=Visits(enabled:true,period:40,duration:3)
        visitOrigin=Date().addingTimeInterval(-6);updateVisit(at:Date())
        hiddenSince=Date().addingTimeInterval(-2);updateVisit(at:Date())
        guard away,web==nil else{print("Idle scene retained");exit(1)}
        // Move the next real timer deadline close enough to exercise preloading.
        visitOrigin=Date().addingTimeInterval(-36.5);updateVisit(at:Date())
        DispatchQueue.main.asyncAfter(deadline:.now()+2.4){
            guard self.away,self.ready,self.web != nil else{print("Preload failed");exit(1)}
            let previous=self.web
            self.openStudio(false)
            guard self.galleryWeb === previous,self.web !== previous else{print("Renderer not transferred");exit(1)}
            self.galleryWeb?.callAsyncJavaScript("const i=previews.find(r=>r.key==='hello').clip;await pet.prepare(i);return !document.documentElement.classList.contains('desktop') && pet.check().active===i",arguments:[:],in:nil,in:.page){result in
                guard (try? result.get()) as? Bool==true else{print("Transferred renderer failed");exit(1)}
            }
        }
        DispatchQueue.main.asyncAfter(deadline:.now()+4.5){
            guard self.ready,!self.away,self.panel.isVisible,self.gallery?.isVisible==true else{print("Scheduled return failed");exit(1)}
            self.gallery?.close();self.settings.visits?.enabled=false;self.applySettings()
            self.verifyShowcaseMenu()
            self.verifySizes([15,43,100,115,200])
        }
    }
    func verifyShowcaseMenu(){
        func select(_ title:String){
            let m=menu(),i=m.indexOfItem(withTitle:title)
            guard i>=0 else{print("Missing menu command",title);exit(1)}
            m.performActionForItem(at:i)
        }
        let scenes=menu().item(withTitle:"Сценки")?.submenu?.items.map(\.tag)
        select("Показать все движения подряд")
        guard showcase?.clips.first==startClip else{print("Movement showcase failed");exit(1)}
        select("Показать все сценки")
        guard let show=showcase,show.kind == .scenes,show.clips==scenes,
              show.clips.contains(clipID("peek")),!allowed("scene").contains(clipID("peek"))
        else{print("Scene showcase order or manual selection failed");exit(1)}
        select("Остановить показ сценок")
        guard showcase==nil else{print("Scene showcase did not stop");exit(1)}
    }
}
@main
struct DesktopApp {
    static func main(){
        let app=NSApplication.shared
        app.setActivationPolicy(.accessory)
        let delegate=Pet();app.delegate=delegate
        withExtendedLifetime(delegate){app.run()}
    }
}
