import AppKit

let app = URL(fileURLWithPath: CommandLine.arguments[1])
let icon = app.appendingPathComponent("Contents/Resources/Shino.icns")
guard let portrait = NSImage(contentsOf: icon),
      NSWorkspace.shared.setIcon(portrait, forFile: app.path, options: []) else {
    exit(1)
}
NSWorkspace.shared.noteFileSystemChanged(app.path)
