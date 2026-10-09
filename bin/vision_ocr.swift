import Foundation
import Vision
import CoreGraphics
import ImageIO

guard CommandLine.arguments.count > 1 else {
    print("Usage: vision_ocr <image_or_pdf_path>")
    exit(1)
}

let filePath = CommandLine.arguments[1]
let url = URL(fileURLWithPath: filePath)

guard let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil),
      let cgImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else {
    fputs("Error: Could not load image from \(filePath)\n", stderr)
    exit(2)
}

let request = VNRecognizeTextRequest { request, error in
    guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
    var recognizedStrings = [String]()
    for observation in observations {
        if let topCandidate = observation.topCandidates(1).first {
            recognizedStrings.append(topCandidate.string)
        }
    }
    print(recognizedStrings.joined(separator: "\n"))
}

request.recognitionLevel = .accurate
request.recognitionLanguages = ["de-DE", "en-US"]
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("Error performing OCR: \(error)\n", stderr)
    exit(3)
}
