//
//  ocr_vision.swift — mac-photos 技能的 OCR 工具（Apple Vision 框架，本地识别，支持中文）
//
//  用法:
//    ocr-vision [--lang zh-Hans,en-US] [--level fast|accurate] IMAGE [IMAGE ...]
//
//  输出: 每张图一行 JSON（UTF-8），可被 photos_read.py 逐行解析:
//    {"error":"","lines":["第一行","第二行"],"path":"/abs/path.png","text":"第一行\n第二行"}
//
//  说明:
//    - 识别语言默认 简体中文+英文；--level fast 用于大批量粗扫
//    - HEIC/JPEG/PNG 均可直接读（走系统图像解码，无需转换）
//

import Foundation
import Vision

struct Options {
    var langs: [String] = ["zh-Hans", "en-US"]
    var level: VNRequestTextRecognitionLevel = .accurate
}

func parseArgs() -> (Options, [String]) {
    var opts = Options()
    var paths: [String] = []
    let args = CommandLine.arguments
    var i = 1
    while i < args.count {
        switch args[i] {
        case "--lang":
            i += 1
            if i < args.count {
                opts.langs = args[i].split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }
            }
        case "--level":
            i += 1
            if i < args.count {
                opts.level = args[i] == "fast" ? .fast : .accurate
            }
        default:
            paths.append(args[i])
        }
        i += 1
    }
    return (opts, paths)
}

func ocr(path: String, opts: Options) -> [String: Any] {
    var result: [String: Any] = [
        "path": path,
        "text": "",
        "lines": [String](),
        "error": "",
    ]
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = opts.level
    request.recognitionLanguages = opts.langs
    request.usesLanguageCorrection = true
    do {
        let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
        try handler.perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        result["lines"] = lines
        result["text"] = lines.joined(separator: "\n")
    } catch {
        result["error"] = "\(error)"
    }
    return result
}

let (opts, paths) = parseArgs()
if paths.isEmpty {
    FileHandle.standardError.write(
        Data("usage: ocr-vision [--lang zh-Hans,en-US] [--level fast|accurate] IMAGE...\n".utf8))
    exit(2)
}

let stdout = FileHandle.standardOutput
for path in paths {
    guard let data = try? JSONSerialization.data(withJSONObject: ocr(path: path, opts: opts)) else { continue }
    stdout.write(data)
    stdout.write(Data("\n".utf8))
}
