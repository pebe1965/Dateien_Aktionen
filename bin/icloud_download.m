#import <Foundation/Foundation.h>
#import <sys/stat.h>
#import <fcntl.h>
#import <unistd.h>

BOOL isFileDataless(const char *path) {
    struct stat st;
    if (stat(path, &st) == 0) {
        if (st.st_flags & 0x40000000) {
            return YES;
        }
    }
    return NO;
}

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            printf("Usage: icloud_download <file_path> [timeout_seconds]\n");
            return 1;
        }
        
        NSString *filePath = [NSString stringWithUTF8String:argv[1]];
        int timeout = 20;
        if (argc > 2) {
            timeout = atoi(argv[2]);
            if (timeout <= 0) timeout = 20;
        }
        
        const char *cpath = [filePath UTF8String];
        
        // 1. Check if already local
        if (!isFileDataless(cpath) && ![filePath hasSuffix:@".icloud"]) {
            printf("ALREADY_LOCAL\n");
            return 0;
        }
        
        NSURL *url = [NSURL fileURLWithPath:filePath];
        NSFileManager *fm = [NSFileManager defaultManager];
        NSError *error = nil;
        
        // 2. Request iCloud download via Foundation
        BOOL started = [fm startDownloadingUbiquitousItemAtURL:url error:&error];
        if (!started && error) {
            fprintf(stderr, "Notice: startDownloadingUbiquitousItem returned: %s\n", [[error localizedDescription] UTF8String]);
        }
        
        // 3. Also trigger APFS fault read asynchronously or via non-blocking open
        // In background thread, attempting a read will cause the kernel to fault the data in
        dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
            int fd = open(cpath, O_RDONLY);
            if (fd >= 0) {
                char buf[1024];
                read(fd, buf, sizeof(buf));
                close(fd);
            }
        });
        
        // 4. Poll until dataless flag is cleared
        NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:timeout];
        while ([[NSDate date] compare:deadline] == NSOrderedAscending) {
            [NSThread sleepForTimeInterval:0.3];
            
            // If file was .icloud, check if the un-prefixed file now exists
            if (!isFileDataless(cpath)) {
                printf("DOWNLOADED\n");
                return 0;
            }
            
            // Check ubiquitous downloading status
            NSString *status = nil;
            [url getResourceValue:&status forKey:NSURLUbiquitousItemDownloadingStatusKey error:nil];
            if ([status isEqualToString:NSURLUbiquitousItemDownloadingStatusCurrent]) {
                printf("DOWNLOADED\n");
                return 0;
            }
        }
        
        // Still dataless after timeout
        if (isFileDataless(cpath)) {
            fprintf(stderr, "Timeout waiting for iCloud download: %s\n", cpath);
            return 2;
        }
        
        printf("DOWNLOADED\n");
        return 0;
    }
}
