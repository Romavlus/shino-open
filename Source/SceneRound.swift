import AppKit
import WebKit

/// A desktop comparison uses one cue per scene, even when the models have different takes.
final class SceneRound {
    enum State { case loading, prepared, playing }
    struct Member {
        let view:WKWebView
        var state:State
    }
    let clips:[Int]
    var index:Int
    var start:TimeInterval?
    var duration:TimeInterval=0
    var members:[Int:Member]=[:]
    init(_ clips:[Int],at index:Int=0){self.clips=clips;self.index=index}
    var clip:Int {clips[index]}
}

extension Pet {
    @objc func toggleSceneShowcase(){
        let root=primary
        if root.sceneRound != nil {root.stopSceneRound()}
        else if root.companions.isEmpty {root.toggleShowcase(.scenes)}
        else {root.beginSceneRound(root.allowed("scene",manual:true))}
    }

    func beginSceneRound(_ clips:[Int],at index:Int=0){
        guard slot==1,clips.indices.contains(index) else{return}
        sceneRound=SceneRound(clips,at:index)
        for actor in actors{
            actor.cancelFacing()
            actor.showcase=nil;actor.showcaseRequest+=1
            actor.afterLoad=nil;actor.resumeDesktop=nil;actor.manualWake=false
            actor.moving=false;actor.walkingHome=false;actor.lastReaction = -1
            actor.deadline = .infinity
            actor.showPanel()
        }
        refreshMenus()
        prepareSceneRound()
    }

    func prepareSceneRound(){
        guard let round=sceneRound else{return}
        for actor in actors{
            guard let view=actor.web,actor.ready else{actor.loadDesktop();continue}
            let slot=actor.slot,index=round.index
            if round.members[slot]?.view===view{continue}
            round.members[slot]=SceneRound.Member(view:view,state:.loading)
            view.callAsyncJavaScript("await pet.prepare(i);return true",arguments:["i":round.clip],in:nil,in:.page){[weak self,weak actor,weak round] result in
                guard let self,let actor,let round,self.sceneRound===round,round.index==index,
                      actor.web===view,round.members[slot]?.view===view else{return}
                guard (try? result.get()) as? Bool == true else{
                    NSLog("Could not prepare scene %@ for slot %d",actor.catalog[round.clip-actor.catalogStart].key,slot)
                    self.stopSceneRound();return
                }
                round.members[slot]?.state = .prepared
                self.cueSceneRound(round)
            }
        }
        cueSceneRound(round)
    }

    private func cueSceneRound(_ round:SceneRound){
        let cast=actors
        if round.start==nil{
            guard cast.allSatisfy({round.members[$0.slot]?.state == .prepared && $0.ready}) else{return}
            round.duration=durations[round.clip]
            round.start=now+0.10
        }
        guard let start=round.start else{return}
        // One instant across WebKit processes. Each renderer converts it to its
        // monotonic clock and samples its own clip at the shared normalized phase.
        let epoch=(Date().timeIntervalSince1970+(start-now))*1000
        for actor in cast where round.members[actor.slot]?.state == .prepared{
            round.members[actor.slot]?.state = .playing
            actor.current=round.clip;actor.activeDirection=0;actor.phaseStart=start
            actor.lastReaction=round.clip;actor.lastScene=round.clip;actor.deadline = .infinity
            actor.js("pet.cueScene(\(round.clip),\(epoch),\(round.duration))")
            if round.index+1<round.clips.count{actor.js("pet.prefetch(\(round.clips[round.index+1]))")}
        }
    }

    func advanceSceneRound(at time:Double){
        guard let round=sceneRound,let start=round.start,time>=start+round.duration else{return}
        guard round.index+1<round.clips.count else{stopSceneRound();return}
        round.index+=1;round.start=nil;round.members.removeAll(keepingCapacity:true)
        prepareSceneRound()
    }

    func stopSceneRound(){
        guard sceneRound != nil else{return}
        sceneRound=nil
        for actor in actors{
            actor.js("window.pet?.endSceneRound()")
            if actor.ready{actor.idle();actor.scheduleScene()}
            actor.shownCycle=nil;actor.updateVisit(at:Date())
        }
        refreshMenus()
    }
}
