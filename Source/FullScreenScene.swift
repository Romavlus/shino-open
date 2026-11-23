import AppKit

enum SceneBackdrop: String, CaseIterable {
    case mist, pearl, sage, apricot, dusk, starlake, harbor, garden

    var title: String {
        switch self {
        case .mist: return "Утренняя дымка"
        case .pearl: return "Жемчужный"
        case .sage: return "Мягкий шалфей"
        case .apricot: return "Тёплый песок"
        case .dusk: return "Синие сумерки"
        case .starlake: return "Озеро под звёздами"
        case .harbor: return "Гавань на закате"
        case .garden: return "Сад после дождя"
        }
    }
    var colors: [NSColor] {
        let stops: [Int]
        switch self {
        case .mist: stops = [0xA4B2D2,0xBFB4BC,0xC39E95]
        case .pearl: stops = [0xDADDE4,0xEAE8E7,0xCFCCD2]
        case .sage: stops = [0xACBDB9,0xCDD3C6,0xAEB9A6]
        case .apricot: stops = [0xE5D5C8,0xF0E2D1,0xCEB09D]
        case .dusk, .starlake: stops = [0x323B54,0x535971,0x776878]
        case .harbor: stops = [0x8FA7C4,0xE6AF89,0x987464]
        case .garden: stops = [0xA4BBC6,0x839A7B,0xB2A596]
        }
        return stops.map { n in NSColor(srgbRed:CGFloat(n >> 16)/255,
            green:CGFloat((n >> 8) & 255)/255,blue:CGFloat(n & 255)/255,alpha:1) }
    }
    var illustrated:Bool {self == .starlake || self == .harbor || self == .garden}
    func resource(_ suffix:String="")->URL? {
        Bundle.main.url(forResource:rawValue+suffix,withExtension:"jpg",subdirectory:"Scenery")
    }
    private static let thumbnails:[Self:NSImage]=Dictionary(uniqueKeysWithValues:allCases.filter{$0.illustrated}.compactMap{ choice in
        guard let url=choice.resource("-menu"),let image=NSImage(contentsOf:url) else{return nil}
        image.size=NSSize(width:26,height:15);return (choice,image)
    })
    var swatch: NSImage {
        if let thumbnail=Self.thumbnails[self]{return thumbnail}
        return NSImage(size:NSSize(width:22,height:15),flipped:false) { rect in
            NSBezierPath(roundedRect:rect,xRadius:3,yRadius:3).addClip()
            NSGradient(colors:self.colors)?.draw(in:rect,angle:-90)
            return true
        }
    }
}

extension NSScreen {
    var sceneID: String {
        let id=(deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? 0
        if let uuid=CGDisplayCreateUUIDFromDisplayID(id)?.takeRetainedValue() {
            return CFUUIDCreateString(nil,uuid) as String
        }
        return String(id)
    }
}

/// The same WebKit view and gesture overlay live in either the desktop panel or the scene.
final class ActorSurface: NSView {
    weak var actor: Pet?
    override func hitTest(_ point: NSPoint) -> NSView? {
        if let actor,actor.onStage,let parent=superview,let window {
            let mouse=window.convertPoint(toScreen:parent.convert(point,to:nil))
            guard !actor.away,actor.hit(mouse) else {return nil}
        }
        return super.hitTest(point)
    }
}

private final class SceneWindow: NSWindow {
    weak var root: Pet?
    override var canBecomeKey: Bool {true}
    override func constrainFrameRect(_ frameRect:NSRect,to screen:NSScreen?) -> NSRect {frameRect}
    override func keyDown(with event:NSEvent) {
        if event.keyCode==53 {root?.closeFullScreenScene()} else {super.keyDown(with:event)}
    }
    override func cancelOperation(_ sender:Any?) {root?.closeFullScreenScene()}
}

final class SceneCanvas: NSView {
    weak var root: Pet?
    private let gradient=CAGradientLayer()
    private let landscape=CALayer()
    private var current:SceneBackdrop?
    // Points on bright stars in the painting, measured from its lower left.
    private let stars:[(CGFloat,CGFloat)]=[(0.1059,0.9054),(0.2213,0.8268),(0.3146,0.9065),
        (0.4205,0.7875),(0.5484,0.8629),(0.6591,0.9341),(0.7368,0.7556),(0.8565,0.9054),(0.933,0.7811)]
    private var starLayers:[CALayer]=[]
    init(root:Pet,backdrop:SceneBackdrop) {
        super.init(frame:.zero)
        self.root=root
        wantsLayer=true;layer?.masksToBounds=true
        gradient.startPoint=CGPoint(x:0.5,y:1);gradient.endPoint=CGPoint(x:0.5,y:0)
        gradient.locations=[0,0.54,1];layer?.insertSublayer(gradient,at:0)
        gradient.addSublayer(landscape);gradient.masksToBounds=true
        NSWorkspace.shared.notificationCenter.addObserver(self,selector:#selector(updateStars),name:NSWorkspace.accessibilityDisplayOptionsDidChangeNotification,object:nil)
        setBackdrop(backdrop)
    }
    required init?(coder:NSCoder) {nil}
    override func layout() {
        super.layout()
        CATransaction.begin();CATransaction.setDisableActions(true)
        gradient.frame=bounds
        if let picture=landscape.contents as? NSImage {
            let scale=max(bounds.width/picture.size.width,bounds.height/picture.size.height)
            let size=NSSize(width:picture.size.width*scale,height:picture.size.height*scale)
            landscape.frame=NSRect(x:(bounds.width-size.width)/2,y:0,width:size.width,height:size.height)
            for (star,point) in zip(starLayers,stars){star.position=CGPoint(x:point.0*size.width,y:point.1*size.height)}
        }
        CATransaction.commit()
    }
    func setBackdrop(_ value:SceneBackdrop) {
        CATransaction.begin();CATransaction.setDisableActions(true)
        gradient.colors=value.colors.map{$0.cgColor}
        current=value
        landscape.contents=value.illustrated ? value.resource().flatMap{NSImage(contentsOf:$0)} : nil
        updateStars();needsLayout=true;CATransaction.commit()
    }
    @objc private func updateStars(){
        for star in starLayers {star.removeFromSuperlayer()}
        starLayers.removeAll()
        guard current == .starlake,!NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else{return}
        for i in stars.indices {
            let star=CALayer(),diameter=CGFloat(i%3+3)
            star.bounds=CGRect(x:0,y:0,width:diameter,height:diameter);star.cornerRadius=diameter/2
            star.backgroundColor=NSColor.white.cgColor;star.opacity=0
            star.shadowColor=NSColor.white.cgColor;star.shadowOpacity=0.85;star.shadowRadius=2;star.shadowOffset = .zero
            landscape.addSublayer(star);starLayers.append(star)
            let pulse=CABasicAnimation(keyPath:"opacity")
            pulse.fromValue=0;pulse.toValue=0.60;pulse.autoreverses=true;pulse.repeatCount = .infinity
            pulse.duration=2.6+Double(i%4)*0.7;pulse.timeOffset=Double(i)*1.7
            pulse.timingFunction=CAMediaTimingFunction(name:.easeInEaseOut);star.add(pulse,forKey:"twinkle")
        }
        needsLayout=true
    }
    override func acceptsFirstMouse(for event:NSEvent?) -> Bool {true}
    override func rightMouseDown(with event:NSEvent) {
        if let root {NSMenu.popUpContextMenu(root.stageMenu(),with:event,for:self)}
    }
    override func mouseDown(with event:NSEvent) {
        if event.modifierFlags.contains(.control){rightMouseDown(with:event)}
        else{window?.makeFirstResponder(self)}
    }
    override var acceptsFirstResponder: Bool {true}
}

final class FullScreenScene {
    private weak var root: Pet?
    let canvas: SceneCanvas
    let window: NSWindow
    private(set) var screen: NSScreen
    private struct DesktopPlace {let rect:NSRect;let screenID:String?;let percent:Int}
    private var desktop: [Int:DesktopPlace]=[:]

    init(_ root:Pet,on screen:NSScreen) {
        self.root=root;self.screen=screen
        canvas=SceneCanvas(root:root,backdrop:root.backdrop)
        let stage=SceneWindow(contentRect:screen.frame,styleMask:.borderless,backing:.buffered,defer:false)
        stage.root=root;stage.title="Сино — полноэкранная сцена"
        stage.isReleasedWhenClosed=false;stage.hasShadow=false;stage.isMovable=false
        stage.level=NSWindow.Level(rawValue:NSWindow.Level.mainMenu.rawValue+1)
        stage.collectionBehavior=[.canJoinAllSpaces,.fullScreenAuxiliary,.stationary,.ignoresCycle]
        stage.contentView=canvas;stage.setFrame(screen.frame,display:false)
        window=stage
    }
    func open() {
        guard let root else{return}
        let cast=root.actors.sorted{$0.slot<$1.slot}
        for (i,actor) in cast.enumerated(){mount(actor,at:(CGFloat(i)+0.5)/CGFloat(cast.count))}
        NSApp.activate(ignoringOtherApps:true);window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(canvas)
        let hint=NSTextField(labelWithString:"Esc — на рабочий стол     ·     Правый клик — экран и фон")
        hint.font = .systemFont(ofSize:13,weight:.medium);hint.textColor = .white
        hint.alignment = .center;hint.backgroundColor=NSColor.black.withAlphaComponent(0.58)
        hint.drawsBackground=true;hint.sizeToFit()
        hint.frame.size.width+=24;hint.frame.size.height+=8
        hint.frame.origin=NSPoint(x:(canvas.bounds.width-hint.frame.width)/2,y:canvas.bounds.height-64)
        hint.autoresizingMask=[.minXMargin,.maxXMargin,.minYMargin];canvas.addSubview(hint)
        DispatchQueue.main.asyncAfter(deadline:.now()+4){[weak hint] in hint?.removeFromSuperview()}
    }
    func add(_ actor:Pet) {
        let locations=([0]+(root?.actors.filter{$0.onStage}.map{($0.actorFrame.midX-screen.frame.minX)/screen.frame.width} ?? [])+[1]).sorted()
        var widest:CGFloat = -1, middle:CGFloat = 0.5
        for (left,right) in zip(locations,locations.dropFirst()) where right-left>widest {
            widest=right-left;middle=(right+left)/2
        }
        mount(actor,at:middle)
    }
    private func mount(_ actor:Pet,at fraction:CGFloat) {
        let original=actor.panel.frame
        desktop[actor.slot]=DesktopPlace(rect:original,screenID:actor.panel.screen?.sceneID,percent:actor.sizePercent)
        actor.panel.orderOut(nil);actor.panel.contentView=nil
        let fitted=Pet.dimensions(at:min(actor.sizePercent,Pet.maximumSize(in:screen.frame)))
        actor.surface.autoresizingMask=[];actor.surface.frame=NSRect(origin:.zero,size:fitted)
        canvas.addSubview(actor.surface)
        let requested=NSPoint(x:screen.frame.minX+screen.frame.width*fraction-fitted.width/2,
            y:screen.frame.minY+1-Pet.floorFraction*fitted.height)
        actor.relocate(to:actor.clamp(requested,to:screen),from:original)
        actor.surface.isHidden=actor.away;actor.syncSize()
    }
    func remove(_ actor:Pet,restore:Bool) {
        guard let place=desktop.removeValue(forKey:actor.slot) else{return}
        let staged=actor.actorFrame
        actor.surface.removeFromSuperview();actor.surface.isHidden=false
        actor.panel.contentView=actor.surface
        actor.surface.autoresizingMask=[.width,.height]
        guard restore,let target=NSScreen.screens.first(where:{$0.sceneID==place.screenID}) ?? NSScreen.main else{return}
        let percent=min(actor.sizePercent,Pet.maximumSize(in:target.visibleFrame))
        let size=percent==place.percent ? place.rect.size : Pet.dimensions(at:percent)
        actor.sizePercent=percent
        let origin=NSPoint(x:place.rect.midX-size.width/2,y:place.rect.minY+(place.rect.height-size.height)*Pet.floorFraction)
        let originalScreenIsPresent=target.sceneID==place.screenID
        let rect=NSRect(origin:origin,size:size)
        let destination=originalScreenIsPresent && target.frame.intersects(rect) ? origin : actor.clamp(origin,to:target,size:size)
        actor.panel.setContentSize(size)
        actor.relocate(to:destination,from:staged)
        if !actor.away {actor.panel.orderFrontRegardless()}
        actor.syncSize()
    }
    func move(to next:NSScreen) {
        let before=window.frame
        let placements=(root?.actors ?? []).filter{$0.onStage}.map{($0,$0.actorFrame)}
        screen=next;window.setFrame(next.frame,display:true)
        for (actor,old) in placements {
            let fx=(old.midX-before.minX)/max(1,before.width)
            let feet=(old.minY+old.height*Pet.floorFraction-before.minY)/max(1,before.height)
            let fitted=Pet.dimensions(at:min(actor.sizePercent,Pet.maximumSize(in:next.frame)))
            actor.surface.setFrameSize(fitted)
            let p=NSPoint(x:next.frame.minX+next.frame.width*fx-fitted.width/2,
                y:next.frame.minY+next.frame.height*feet-fitted.height*Pet.floorFraction)
            actor.relocate(to:actor.clamp(p,to:next),from:old)
            actor.syncSize()
        }
    }
    func close() {
        for actor in root?.actors ?? [] {
            remove(actor,restore:true);actor.gallery?.level = .normal
        }
        window.orderOut(nil);window.close()
    }
}

extension Pet {
    var onStage: Bool {primary.stage.map{$0.canvas===surface.superview} ?? false}
    var actorScreen: NSScreen? {onStage ? primary.stage?.screen : (panel.screen ?? NSScreen.main)}
    var actorFrame: NSRect {
        guard onStage,let stage=primary.stage else{return panel.frame}
        return surface.frame.offsetBy(dx:stage.window.frame.minX,dy:stage.window.frame.minY)
    }
    func setActorFrame(_ rect:NSRect) {
        if onStage,let stage=primary.stage {
            surface.frame=rect.offsetBy(dx:-stage.window.frame.minX,dy:-stage.window.frame.minY)
        }else{panel.setFrame(rect,display:true)}
    }
    func moveActor(to point:NSPoint) {
        if onStage {setActorFrame(NSRect(origin:point,size:surface.frame.size))}
        else{panel.setFrameOrigin(point)}
    }
    func relocate(to point:NSPoint,from old:NSRect) {
        endRotation();picked=nil;dragged=false;strideRemainder=0
        moveActor(to:point)
        if let home=sceneHome,let screen=actorScreen {
            sceneHome=clamp(NSPoint(x:home+point.x-old.minX,y:point.y),to:screen).x
        }
    }
    func showActor() {if onStage{surface.isHidden=false}else{panel.orderFrontRegardless()}}
    func hideActor() {if onStage{surface.isHidden=true}else{panel.orderOut(nil)}}

    func stageMenu() -> NSMenu {
        let root=primary,menu=NSMenu(),screens=NSScreen.screens
        if root.stage==nil,let preferred=root.preferredSceneScreen {
            let open=menu.addItem(withTitle:"Открыть сцену",action:#selector(selectStageScreen(_:)),keyEquivalent:"")
            open.target=root;open.representedObject=preferred.sceneID
            menu.addItem(.separator())
        }
        menu.addItem(withTitle:"Открыть на мониторе",action:nil,keyEquivalent:"")
        for (i,display) in screens.enumerated() {
            let name=screens.filter{$0.localizedName==display.localizedName}.count>1 ? "\(display.localizedName) · \(i+1)" : display.localizedName
            let item=menu.addItem(withTitle:name,action:#selector(selectStageScreen(_:)),keyEquivalent:"")
            item.target=root;item.representedObject=display.sceneID
            item.state=root.stage?.screen.sceneID==display.sceneID ? .on:.off
        }
        menu.addItem(.separator())
        let backgrounds=NSMenu()
        for choice in SceneBackdrop.allCases {
            if choice == .starlake{backgrounds.addItem(.separator())}
            let item=backgrounds.addItem(withTitle:choice.title,action:#selector(selectBackdrop(_:)),keyEquivalent:"")
            item.representedObject=choice.rawValue;item.target=root;item.image=choice.swatch
            item.state=choice==root.backdrop ? .on:.off
        }
        menu.setSubmenu(backgrounds,for:menu.addItem(withTitle:"Фон",action:nil,keyEquivalent:""))
        if root.stage != nil {
            let done=menu.addItem(withTitle:"Вернуться на рабочий стол",action:#selector(closeFullScreenScene),keyEquivalent:"")
            done.target=root
        }
        return menu
    }
    var preferredSceneScreen:NSScreen? {
        let screens=NSScreen.screens,last=UserDefaults.standard.string(forKey:"sceneDisplay")
        if let saved=screens.first(where:{$0.sceneID==last}) {return saved}
        let occupied=Dictionary(grouping:actors.compactMap{$0.actorScreen?.sceneID},by:{$0})
        return screens.max{(occupied[$0.sceneID]?.count ?? 0)<(occupied[$1.sceneID]?.count ?? 0)} ?? actorScreen
    }
    @objc func selectStageScreen(_ item:NSMenuItem) {
        guard let id=item.representedObject as? String,let target=NSScreen.screens.first(where:{$0.sceneID==id}) else{return}
        openFullScreenScene(on:target)
    }
    func openFullScreenScene(on display:NSScreen) {
        for actor in actors {actor.gallery?.level = .normal}
        if let stage {
            if stage.screen.sceneID != display.sceneID {stage.move(to:display)}
            NSApp.activate(ignoringOtherApps:true);stage.window.makeKeyAndOrderFront(nil)
        }else{
            let next=FullScreenScene(self,on:display);stage=next;next.open()
        }
        if savesPreferences {UserDefaults.standard.set(display.sceneID,forKey:"sceneDisplay")}
        refreshMenus()
    }
    @objc func selectBackdrop(_ item:NSMenuItem) {
        guard let id=item.representedObject as? String,let value=SceneBackdrop(rawValue:id) else{return}
        applyBackdrop(value)
    }
    func applyBackdrop(_ value:SceneBackdrop) {
        backdrop=value
        if savesPreferences {UserDefaults.standard.set(value.rawValue,forKey:"sceneBackdrop")}
        stage?.canvas.setBackdrop(value);refreshMenus()
        for actor in actors where actor.galleryReady {actor.syncBackdrop()}
    }
    func syncBackdrop(){
        let choices=SceneBackdrop.allCases.map{["id":$0.rawValue,"title":$0.title]}
        galleryWeb?.callAsyncJavaScript("window.setBackdrop(value,choices)",arguments:["value":primary.backdrop.rawValue,"choices":choices],in:nil,in:.page){_ in}
    }
    @objc func closeFullScreenScene() {stage?.close();stage=nil;refreshMenus()}
    @objc func stageDisplaysChanged(_ note:Notification) {
        guard let stage else{refreshMenus();return}
        guard let current=NSScreen.screens.first(where:{$0.sceneID==stage.screen.sceneID}) else{closeFullScreenScene();return}
        if current.frame != stage.window.frame {stage.move(to:current)}
        refreshMenus()
    }
}
