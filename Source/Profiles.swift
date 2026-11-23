import AppKit

struct CharacterProfile:Codable {
    var behavior:Behavior
    var size:Int
    var walking:Bool
    var gait:Int
}
struct ProfileStore:Codable {
    var individual=false
    var common:CharacterProfile?
    var personal:[Int:CharacterProfile]=[:]
}

extension Pet {
    var primary:Pet {owner ?? self}
    var actors:[Pet] {[primary]+primary.companions}
    var profile:CharacterProfile {CharacterProfile(behavior:settings,size:sizePercent,walking:walkEnabled,gait:walkClip)}

    func loadProfile(){
        if savesPreferences,let data=UserDefaults.standard.data(forKey:"characterProfiles"),
           let stored=try? JSONDecoder().decode(ProfileStore.self,from:data){profiles=stored}
        let root=primary
        if root.profiles.common==nil{root.profiles.common=root.profile}
        if let p=(root.profiles.individual ? root.profiles.personal[slot] : nil) ?? root.profiles.common{applyProfile(p)}
    }

    func applyProfile(_ p:CharacterProfile){
        let previous=settings,wasWalking=walkEnabled
        settings=p.behavior
        if sizePercent != p.size{resize(to:p.size)}
        walkEnabled=p.walking;walkClip=p.gait
        if ready {
            if previous != settings{applySettings(previous:previous)}
            if wasWalking != walkEnabled && primary.sceneRound==nil {
                if walkEnabled{requestWalk()}
                else if moving && !away{idle()}
            }
        }
    }
    func storeProfiles(){
        let root=primary
        if root.savesPreferences{UserDefaults.standard.set(try? JSONEncoder().encode(root.profiles),forKey:"characterProfiles")}
        root.refreshMenus()
        for actor in actors where actor.galleryReady{actor.syncProfile()}
    }
    func editProfile(_ edit:(inout CharacterProfile)->Void){
        let root=primary
        var p=profile
        edit(&p)
        if root.profiles.individual{
            root.profiles.personal[slot]=p;applyProfile(p)
        }else{
            root.profiles.common=p
            for actor in actors{actor.applyProfile(p)}
        }
        storeProfiles()
    }
    func setProfileMode(_ individual:Bool){
        let root=primary
        guard root.profiles.individual != individual else{return}
        root.profiles.individual=individual
        for actor in actors{
            if individual,root.profiles.personal[actor.slot]==nil{root.profiles.personal[actor.slot]=actor.profile}
            if let p=(individual ? root.profiles.personal[actor.slot] : nil) ?? root.profiles.common{actor.applyProfile(p)}
        }
        storeProfiles()
    }
    var profileTarget:Pet{
        guard primary.profiles.individual else{return primary}
        return actors.first{$0.slot==editingSlot} ?? self
    }
    func syncProfile(){
        let actor=profileTarget
        guard let data=try? JSONEncoder().encode(actor.settings),
              let prefs=try? JSONSerialization.jsonObject(with:data) else{return}
        let values:[String:Any]=["prefs":prefs,"individual":primary.profiles.individual,"target":actor.slot,
                                 "size":actor.sizePercent,"max":actor.maximumSize,"walk":actor.walkEnabled,"gait":actor.walkClip,"slots":slotValues()]
        galleryWeb?.callAsyncJavaScript("window.updateProfile(p)",arguments:["p":values],in:nil,in:.page){_ in}
    }
}
