import AppKit

extension Pet {
    private func displayID(_ screen:NSScreen)->String {
        guard let id=screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber,
              let uuid=CGDisplayCreateUUIDFromDisplayID(id.uint32Value) else{return ""}
        return CFUUIDCreateString(nil,uuid.takeRetainedValue()) as String
    }

    func saveSpot(defaults:UserDefaults = .standard){
        guard let screen=panel.screen else{return}
        let frame=panel.frame,bounds=screen.frame
        let floor=frame.minY+frame.height*Pet.floorFraction
        defaults.set(["display":displayID(screen),"x":(frame.midX-bounds.minX)/bounds.width,
                                   "y":(floor-bounds.minY-1)/bounds.height],forKey:"desktopSpot")
    }

    func restoreSpot(defaults:UserDefaults = .standard){
        guard let spot=defaults.dictionary(forKey:"desktopSpot"),
              let x=spot["x"] as? Double,let y=spot["y"] as? Double,x.isFinite,y.isFinite,
              let screen=NSScreen.screens.first(where:{displayID($0)==spot["display"] as? String}) ?? NSScreen.main else{return}
        let f=screen.frame,size=panel.frame.size
        let pos=NSPoint(x:f.minX+x*f.width-size.width/2,y:f.minY+1+y*f.height-size.height*Pet.floorFraction)
        panel.setFrameOrigin(clamp(pos,to:screen))
    }

    @objc func dismissWelcome(){welcome?.orderOut(nil);welcome=nil}
    @objc func tryMotions(){dismissWelcome();openStudio(false)}

    func showWelcome(){
        guard let screen=panel.screen ?? NSScreen.main else{return}
        let window=NSPanel(contentRect:NSRect(x:0,y:0,width:285,height:106),styleMask:[.borderless,.nonactivatingPanel],backing:.buffered,defer:false)
        window.isReleasedWhenClosed=false;window.level = .floating
        let card=NSVisualEffectView(frame:window.contentView!.bounds)
        card.material = .popover;card.state = .active;card.wantsLayer=true;card.layer?.cornerRadius=12
        let hint=NSTextField(wrappingLabelWithString:tr("Перетащи меня мышью. Удерживай ⌘, чтобы повернуть."))
        hint.frame=NSRect(x:14,y:48,width:257,height:46)
        let tryButton=NSButton(title:tr("Попробовать движения"),target:self,action:#selector(tryMotions))
        let close=NSButton(title:tr("Понятно"),target:self,action:#selector(dismissWelcome))
        tryButton.sizeToFit();close.sizeToFit()
        tryButton.setFrameOrigin(NSPoint(x:10,y:12));close.setFrameOrigin(NSPoint(x:tryButton.frame.maxX+4,y:12))
        for v in [hint,tryButton,close]{card.addSubview(v)}
        window.contentView=card;window.isOpaque=false;window.backgroundColor = .clear
        let bounds=screen.visibleFrame,pet=panel.frame
        let x=pet.midX>bounds.midX ? pet.minX-window.frame.width : pet.maxX
        window.setFrameOrigin(NSPoint(x:max(bounds.minX,min(x,bounds.maxX-window.frame.width)),
                                      y:max(bounds.minY,min(pet.midY,bounds.maxY-window.frame.height))))
        welcome=window;window.orderFrontRegardless()
        DispatchQueue.main.asyncAfter(deadline:.now()+15){[weak self,weak window] in
            if self?.welcome===window{self?.dismissWelcome()}
        }
    }
}
