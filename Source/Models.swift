import Foundation
import WebKit

enum AppLanguage {
    static var preference:String { UserDefaults.standard.string(forKey:"interfaceLanguage") ?? "system" }
    static var english:Bool {
        preference=="system" ? !(Locale.preferredLanguages.first ?? "en").hasPrefix("ru") : preference=="en"
    }
    static let translations = try! JSONDecoder().decode([String:String].self,from:Data(contentsOf:Bundle.main.url(forResource:"en",withExtension:"json")!))
}
func tr(_ text:String)->String { AppLanguage.english ? AppLanguage.translations[text] ?? text : text }
enum PetModel: String, CaseIterable {
    case shino, shinoCherry, shinoCardigan
    var name:String { tr("Сино") }
    var title: String {
        switch self {
        case .shino: return tr("Сино")
        case .shinoCherry: return tr("Сино — Вишнёвая форма")
        case .shinoCardigan: return tr("Сино — Платье с кардиганом")
        }
    }
    var file: String {
        switch self {
        case .shino: return "Shino.vrm"
        case .shinoCherry: return "ShinoCherry.gltf"
        case .shinoCardigan: return "ShinoCardigan.gltf"
        }
    }
}

final class ModelLibrary {
    let resources:URL
    let catalog:[Motion]
    let choices=PetModel.allCases
    init(resources:URL){
        self.resources=resources
        catalog=try! JSONDecoder().decode([Motion].self,from:Data(contentsOf:resources.appendingPathComponent("catalog.json")))
    }
    func configuration(for model:PetModel,preview:[String:Any]?) -> String {
        var data:[String:Any]=["id":model.rawValue,"family":"shino","english":AppLanguage.english,"language":AppLanguage.preference,"translations":AppLanguage.english ? AppLanguage.translations : [:],"name":model.name,"file":model.file,
                               "choices":choices.map{["id":$0.rawValue,"title":$0.title]}]
        if let preview,JSONSerialization.isValidJSONObject(preview){data["preview"]=preview}
        let encoded=try! JSONSerialization.data(withJSONObject:data)
        return "window.petModelConfig="+String(decoding:encoded,as:UTF8.self)+";"
    }
}

// A view always reads the pack it was created with, even while another model is loading.
final class Assets: NSObject, WKURLSchemeHandler {
    let resources:URL
    init(resources:URL){self.resources=resources}
    func webView(_ webView:WKWebView,start task:WKURLSchemeTask){
        guard let url=task.request.url,url.host=="local",url.pathComponents.count==2 else{
            task.didFailWithError(URLError(.badURL));return
        }
        let name=url.lastPathComponent
        do{
            guard name != "..",name != "." else {throw URLError(.badURL)}
            let data=try Data(contentsOf:resources.appendingPathComponent(name),options:.mappedIfSafe)
            let mime=["html":"text/html; charset=utf-8","js":"text/javascript","gltf":"model/gltf+json","png":"image/png"]
            let info=HTTPURLResponse(url:url,statusCode:200,httpVersion:"HTTP/1.1",headerFields:[
                "Content-Type":mime[url.pathExtension] ?? "application/octet-stream","Access-Control-Allow-Origin":"*"])!
            task.didReceive(info);task.didReceive(data);task.didFinish()
        }catch{task.didFailWithError(error)}
    }
    func webView(_ webView:WKWebView,stop task:WKURLSchemeTask){}
}
