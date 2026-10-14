// Local Apple Vision adapter. Bounding boxes: normalized, top-left origin.
// Build explicitly: swiftc scroll_vision.swift -o /outside/repo/video-screenshot-vision
import Foundation
import Vision
import ImageIO
let paths = Array(CommandLine.arguments.dropFirst())
if paths.isEmpty { fputs("usage: video-screenshot-vision IMAGE...\n", stderr); exit(2) }
for path in paths {
    var result: [String: Any] = ["path": path, "lines": [[String: Any]](), "error": ""]
    do {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hans", "en-US"]
        // Preserve the screen's wording; do not apply language correction.
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:]).perform([request])
        let lines: [[String: Any]] = (request.results ?? []).compactMap { observation in
            guard let candidate = observation.topCandidates(1).first else { return nil }
            let box = observation.boundingBox
            return ["text": candidate.string, "confidence": candidate.confidence,
                    "bbox": [box.minX, 1 - box.maxY, box.maxX, 1 - box.minY]]
        }
        result["lines"] = lines
    } catch { result["error"] = String(describing: error) }
    do {
        let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
        FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data("\n".utf8))
    } catch { fputs("JSON serialization failed\n", stderr); exit(3) }
}
