#import <Foundation/Foundation.h>
#import <Vision/Vision.h>
#import <CoreGraphics/CoreGraphics.h>
#import <ImageIO/ImageIO.h>
#import <PDFKit/PDFKit.h>

void performOCR(CGImageRef image, NSMutableArray *collectedText) {
    if (!image) return;
    
    VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] initWithCompletionHandler:^(VNRequest * _Nonnull req, NSError * _Nullable error) {
        if (error) return;
        NSArray *results = [req results];
        for (VNRecognizedTextObservation *obs in results) {
            VNRecognizedText *top = [[obs topCandidates:1] firstObject];
            if (top) {
                [collectedText addObject:[top string]];
            }
        }
    }];
    request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
    request.recognitionLanguages = @[@"de-DE", @"en-US"];
    request.usesLanguageCorrection = YES;
    
    VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithCGImage:image options:@{}];
    NSError *err = nil;
    [handler performRequests:@[request] error:&err];
}

void performSceneClassification(CGImageRef image, NSMutableArray *collectedLabels) {
    if (!image) return;
    
    if (@available(macOS 10.15, *)) {
        VNClassifyImageRequest *classifyRequest = [[VNClassifyImageRequest alloc] init];
        VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithCGImage:image options:@{}];
        NSError *err = nil;
        if ([handler performRequests:@[classifyRequest] error:&err]) {
            NSArray<VNClassificationObservation *> *observations = [classifyRequest results];
            int count = 0;
            for (VNClassificationObservation *obs in observations) {
                if (obs.confidence >= 0.35 && count < 8) {
                    NSString *entry = [NSString stringWithFormat:@"%@ (%.0f%%)", obs.identifier, obs.confidence * 100.0];
                    [collectedLabels addObject:entry];
                    count++;
                }
            }
        }
    }
}

uint64_t computeDifferenceHash(CGImageRef image) {
    if (!image) return 0;
    size_t width = 9;
    size_t height = 8;
    uint8_t pixels[9 * 8] = {0};
    CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceGray();
    CGContextRef context = CGBitmapContextCreate(
        pixels, width, height, 8, width, colorSpace, kCGImageAlphaNone
    );
    CGColorSpaceRelease(colorSpace);
    if (!context) return 0;
    CGContextSetInterpolationQuality(context, kCGInterpolationLow);
    CGContextDrawImage(context, CGRectMake(0, 0, width, height), image);
    CGContextRelease(context);

    uint64_t hash = 0;
    int bit = 0;
    for (size_t y = 0; y < height; y++) {
        for (size_t x = 0; x < 8; x++) {
            uint8_t left = pixels[y * width + x];
            uint8_t right = pixels[y * width + x + 1];
            if (left > right) {
                hash |= (1ULL << bit);
            }
            bit++;
        }
    }
    return hash;
}

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            printf("Usage: vision_ocr <file_path> [max_pages] | vision_ocr --dhash <file1> [file2 ...]\n");
            return 1;
        }
        
        NSString *firstArg = [NSString stringWithUTF8String:argv[1]];
        if ([firstArg isEqualToString:@"--dhash"]) {
            for (int i = 2; i < argc; i++) {
                NSString *p = [NSString stringWithUTF8String:argv[i]];
                NSURL *u = [NSURL fileURLWithPath:p];
                CGImageSourceRef src = CGImageSourceCreateWithURL((__bridge CFURLRef)u, NULL);
                if (src) {
                    NSDictionary *thumbOpts = @{
                        (id)kCGImageSourceCreateThumbnailFromImageIfAbsent: @YES,
                        (id)kCGImageSourceThumbnailMaxPixelSize: @64
                    };
                    CGImageRef thumb = CGImageSourceCreateThumbnailAtIndex(src, 0, (__bridge CFDictionaryRef)thumbOpts);
                    if (!thumb) {
                        thumb = CGImageSourceCreateImageAtIndex(src, 0, NULL);
                    }
                    if (thumb) {
                        uint64_t dh = computeDifferenceHash(thumb);
                        printf("%016llx\t%s\n", dh, argv[i]);
                        CGImageRelease(thumb);
                    }
                    CFRelease(src);
                }
            }
            return 0;
        }
        
        NSString *filePath = firstArg;
        int maxPages = 5;
        if (argc > 2) {
            maxPages = atoi(argv[2]);
            if (maxPages <= 0) maxPages = 5;
        }
        
        NSURL *url = [NSURL fileURLWithPath:filePath];
        NSMutableArray *collectedText = [NSMutableArray array];
        NSMutableArray *sceneLabels = [NSMutableArray array];
        
        NSString *ext = [[filePath pathExtension] lowercaseString];
        if ([ext isEqualToString:@"pdf"]) {
            PDFDocument *pdf = [[PDFDocument alloc] initWithURL:url];
            if (pdf) {
                NSUInteger count = [pdf pageCount];
                NSUInteger toScan = MIN(count, (NSUInteger)maxPages);
                for (NSUInteger i = 0; i < toScan; i++) {
                    PDFPage *page = [pdf pageAtIndex:i];
                    if (page) {
                        NSData *data = [page dataRepresentation];
                        if (data) {
                            CGImageSourceRef src = CGImageSourceCreateWithData((__bridge CFDataRef)data, NULL);
                            if (src) {
                                CGImageRef img = CGImageSourceCreateImageAtIndex(src, 0, NULL);
                                if (img) {
                                    performOCR(img, collectedText);
                                    CGImageRelease(img);
                                }
                                CFRelease(src);
                            }
                        }
                    }
                }
            }
        }
        
        if ([collectedText count] == 0 && ![ext isEqualToString:@"pdf"]) {
            // Try standard image (OCR + Scene Classification)
            CGImageSourceRef source = CGImageSourceCreateWithURL((__bridge CFURLRef)url, NULL);
            if (source) {
                CGImageRef image = CGImageSourceCreateImageAtIndex(source, 0, NULL);
                if (image) {
                    performOCR(image, collectedText);
                    performSceneClassification(image, sceneLabels);
                    CGImageRelease(image);
                }
                CFRelease(source);
            }
        }
        
        NSMutableString *finalOutput = [NSMutableString string];
        if ([sceneLabels count] > 0) {
            [finalOutput appendFormat:@"[Apple Vision Bildmotive: %@]\n", [sceneLabels componentsJoinedByString:@", "]];
        }
        if ([collectedText count] > 0) {
            [finalOutput appendString:[collectedText componentsJoinedByString:@"\n"]];
        }
        printf("%s\n", [finalOutput UTF8String]);
    }
    return 0;
}

