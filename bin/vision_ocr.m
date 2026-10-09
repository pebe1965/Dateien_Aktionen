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

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            printf("Usage: vision_ocr <file_path> [max_pages]\n");
            return 1;
        }
        
        NSString *filePath = [NSString stringWithUTF8String:argv[1]];
        int maxPages = 5;
        if (argc > 2) {
            maxPages = atoi(argv[2]);
            if (maxPages <= 0) maxPages = 5;
        }
        
        NSURL *url = [NSURL fileURLWithPath:filePath];
        NSMutableArray *collectedText = [NSMutableArray array];
        
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
        
        if ([collectedText count] == 0) {
            // Try standard image
            CGImageSourceRef source = CGImageSourceCreateWithURL((__bridge CFURLRef)url, NULL);
            if (source) {
                CGImageRef image = CGImageSourceCreateImageAtIndex(source, 0, NULL);
                if (image) {
                    performOCR(image, collectedText);
                    CGImageRelease(image);
                }
                CFRelease(source);
            }
        }
        
        NSString *fullOutput = [collectedText componentsJoinedByString:@"\n"];
        printf("%s\n", [fullOutput UTF8String]);
    }
    return 0;
}
