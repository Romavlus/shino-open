import Foundation
import WebKit

enum PetModel: String, CaseIterable {
    case shino, shinoCherry, shinoCardigan, shinoRider, shinoMarine, shinoBordeaux
    var name: String {"Сино"}

    static func savedChoice(_ key:String,in defaults:UserDefaults = .standard) -> PetModel? {
        guard let id=defaults.string(forKey:key) else{return nil}
        if let model=PetModel(rawValue:id){return model}
        // Keep the slot and its personal profile when upgrading an older outfit.
        guard ["honey","forest","dress"].contains(id) else{return nil}
        defaults.set(PetModel.shino.rawValue,forKey:key)
        return .shino
    }
    var title: String {
        switch self {
        case .shino: return "Сино"
        case .shinoCherry: return "Сино — Вишнёвая форма"
        case .shinoCardigan: return "Сино — Платье с кардиганом"
        case .shinoRider: return "25C · Чёрная косуха"
        case .shinoMarine: return "29 · Морской бриз"
        case .shinoBordeaux: return "33C · Коралловый шёлк"
        }
    }
    var file: String {
        switch self {
        case .shino: return "Shino.vrm"
        case .shinoCherry: return "ShinoCherry.gltf"
        case .shinoCardigan: return "ShinoCardigan.gltf"
        case .shinoRider: return "ShinoRider.gltf"
        case .shinoMarine: return "ShinoMarine.gltf"
        case .shinoBordeaux: return "ShinoBordeaux.gltf"
        }
    }
}

final class ModelLibrary {
    let resources:URL
    let catalog:[Motion]
    let choices=PetModel.allCases

    init(resources:URL) {
        self.resources=resources
        let data=try! Data(contentsOf:resources.appendingPathComponent("catalog.json"))
        catalog=try! JSONDecoder().decode([Motion].self,from:data)
    }
    func configuration(for model:PetModel,preview:[String:Any]?,slots:[String]) -> String {
        var data:[String:Any]=["slots":slots,"id":model.rawValue,"name":model.name,"file":model.file,
                               "choices":choices.map{["id":$0.rawValue,"title":$0.title]}]
        if let preview,JSONSerialization.isValidJSONObject(preview){data["preview"]=preview}
        let encoded=try! JSONSerialization.data(withJSONObject:data)
        return "window.petModelConfig="+String(decoding:encoded,as:UTF8.self)+";"
    }
}

final class Assets: NSObject, WKURLSchemeHandler {
    let resources:URL
    init(resources:URL){self.resources=resources}
    func webView(_ webView:WKWebView,start task:WKURLSchemeTask){
        guard let url=task.request.url,url.host=="local",url.pathComponents.count==2 else{
            task.didFailWithError(URLError(.badURL));return
        }
        let name=url.lastPathComponent
        do{
            let data=try Data(contentsOf:resources.appendingPathComponent(name),options:.mappedIfSafe)
            let mime=["html":"text/html; charset=utf-8","js":"text/javascript","gltf":"model/gltf+json","png":"image/png"]
            let info=HTTPURLResponse(url:url,statusCode:200,httpVersion:"HTTP/1.1",headerFields:[
                "Content-Type":mime[url.pathExtension] ?? "application/octet-stream","Access-Control-Allow-Origin":"*"])!
            task.didReceive(info);task.didReceive(data);task.didFinish()
        }catch{task.didFailWithError(error)}
    }
    func webView(_ webView:WKWebView,stop task:WKURLSchemeTask){}
}
