//
//  mktext.swift — 生成带文字的 PNG 测试图（mac-photos 技能 doctor 自检用）
//
//  用法:
//    mktext OUTPUT.png "要渲染的文字"
//
//  白底黑字、PingFang 系统字体 48pt；用于验证 ocr-vision 识别链路是否正常。
//

import AppKit

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write(Data("usage: mktext OUTPUT.png TEXT\n".utf8))
    exit(2)
}
let outPath = args[1]
let text = args[2]

let size = NSSize(width: 1200, height: 220)
let image = NSImage(size: size)
image.lockFocus()
NSColor.white.setFill()
NSRect(origin: .zero, size: size).fill()
(text as NSString).draw(
    at: NSPoint(x: 30, y: 90),
    withAttributes: [
        .font: NSFont.systemFont(ofSize: 48),
        .foregroundColor: NSColor.black,
    ])
image.unlockFocus()

guard
    let tiff = image.tiffRepresentation,
    let rep = NSBitmapImageRep(data: tiff),
    let png = rep.representation(using: .png, properties: [:])
else {
    FileHandle.standardError.write(Data("mktext: render failed\n".utf8))
    exit(1)
}

do {
    try png.write(to: URL(fileURLWithPath: outPath))
    print(outPath)
} catch {
    FileHandle.standardError.write(Data("mktext: write failed \(error)\n".utf8))
    exit(1)
}
