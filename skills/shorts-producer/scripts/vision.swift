// Apple Vision requests for the shorts producer. macOS only.
//
// Usage:
// vision.swift.txt is its byte-identical install mirror (tessl install drops
// .swift files); shorts_plan.vision_script runs whichever is present.
//
//   swift vision.swift faces <frames-dir>   every *.jpg in name order
//   swift vision.swift qr <image>...        QR payloads per image
//
// Stdout: one JSON array. `faces` rows are {file, faces: [{x, y, w, h,
// confidence}]} with normalized top-left coordinates. `qr` rows are
// {file, payloads: [string]}. A frame Vision cannot read is a row with
// `error`; a bad mode or unreadable directory exits 2 with a message on stderr.
import Foundation
import Vision

func fail(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(2)
}

func box(_ b: CGRect, _ confidence: Float) -> [String: Double] {
    ["x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height, "confidence": Double(confidence)]
}

let args = Array(CommandLine.arguments.dropFirst())
guard let mode = args.first else { fail("usage: vision.swift faces <dir> | qr <image>...") }
var rows: [[String: Any]] = []

switch mode {
case "faces":
    guard args.count == 2 else { fail("usage: vision.swift faces <frames-dir>") }
    let folder = URL(fileURLWithPath: args[1])
    let listing: [URL]
    do {
        listing = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
    } catch {
        fail("cannot list \(folder.path): \(error) — run prepare-clip.py first")
    }
    for path in listing.filter({ $0.pathExtension == "jpg" }).sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
        let request = VNDetectFaceRectanglesRequest()
        do {
            try VNImageRequestHandler(url: path, options: [:]).perform([request])
            let faces = (request.results ?? []).map { box($0.boundingBox, $0.confidence) }
            rows.append(["file": path.lastPathComponent, "faces": faces])
        } catch {
            rows.append(["file": path.lastPathComponent, "error": String(describing: error)])
        }
    }
case "qr":
    guard args.count >= 2 else { fail("usage: vision.swift qr <image>...") }
    for path in args.dropFirst() {
        let request = VNDetectBarcodesRequest()
        request.symbologies = [.qr]
        do {
            try VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:]).perform([request])
            rows.append(["file": path, "payloads": (request.results ?? []).compactMap { $0.payloadStringValue }])
        } catch {
            rows.append(["file": path, "error": String(describing: error)])
        }
    }
default:
    fail("unknown mode \(mode) — use faces or qr")
}

do {
    FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: rows, options: [.sortedKeys]))
} catch {
    fail("cannot encode the result: \(error)")
}
