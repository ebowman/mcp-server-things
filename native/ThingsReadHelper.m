#import <AppKit/AppKit.h>
#import <pwd.h>
#import <sqlite3.h>
#import <stdio.h>
#import <stdlib.h>
#import <string.h>
#import <unistd.h>

static NSString *const BookmarkKey = @"thingsDatabaseBundleBookmark";

static NSString *thingsRoot(void) {
    struct passwd *account = getpwuid(getuid());
    if (account == NULL) return nil;
    return [[NSString stringWithUTF8String:account->pw_dir]
        stringByAppendingPathComponent:@"Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac"];
}

static BOOL isThingsBundle(NSURL *url) {
    NSString *path = url.URLByResolvingSymlinksInPath.path.stringByStandardizingPath;
    NSString *parent = path.stringByDeletingLastPathComponent;
    return [path.lastPathComponent isEqualToString:@"Things Database.thingsdatabase"]
        && [parent.lastPathComponent hasPrefix:@"ThingsData-"]
        && [parent.stringByDeletingLastPathComponent isEqualToString:thingsRoot()];
}

static void sendJSON(NSDictionary *value) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:value options:0 error:nil];
    if (data == nil) data = [@"{\"ok\":false,\"error\":\"serialization_failed\"}" dataUsingEncoding:NSUTF8StringEncoding];
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
    fflush(stdout);
}

static void sendError(NSString *code) {
    sendJSON(@{@"ok": @NO, @"error": code, @"code": @1});
}

static int authorizeRead(void *context, int action, const char *first, const char *second,
                         const char *database, const char *trigger) {
    (void)context;
    (void)trigger;
    if (action == SQLITE_SELECT) return SQLITE_OK;
    if (action == SQLITE_FUNCTION) {
        static const char *const functions[] = {
            "abs", "avg", "coalesce", "count", "date", "datetime", "group_concat",
            "ifnull", "instr", "length", "like", "lower", "max", "min", "nullif",
            "printf", "replace", "round", "strftime", "substr", "sum", "time", "trim", "upper"
        };
        if (second == NULL) return SQLITE_DENY;
        for (size_t i = 0; i < sizeof(functions) / sizeof(functions[0]); i++) {
            if (strcasecmp(second, functions[i]) == 0) return SQLITE_OK;
        }
        return SQLITE_DENY;
    }
    if (action != SQLITE_READ || first == NULL ||
        (database != NULL && strcmp(database, "main") != 0) ||
        (database == NULL && (second == NULL || second[0] != '\0'))) {
        return SQLITE_DENY;
    }
    static const char *const tables[] = {
        "TMArea", "TMAreaTag", "TMChecklistItem", "TMTag", "TMTask", "TMTaskTag", "Meta"
    };
    for (size_t i = 0; i < sizeof(tables) / sizeof(tables[0]); i++) {
        if (strcmp(first, tables[i]) == 0) return SQLITE_OK;
    }
    return SQLITE_DENY;
}

static id columnValue(sqlite3_stmt *statement, int index) {
    switch (sqlite3_column_type(statement, index)) {
        case SQLITE_INTEGER: return @(sqlite3_column_int64(statement, index));
        case SQLITE_FLOAT: return @(sqlite3_column_double(statement, index));
        case SQLITE_TEXT: {
            const void *bytes = sqlite3_column_text(statement, index);
            NSUInteger length = (NSUInteger)sqlite3_column_bytes(statement, index);
            NSString *text = [[NSString alloc] initWithBytes:bytes length:length encoding:NSUTF8StringEncoding];
            return text ?: [NSNull null];
        }
        case SQLITE_BLOB: {
            const void *bytes = sqlite3_column_blob(statement, index);
            NSUInteger length = (NSUInteger)sqlite3_column_bytes(statement, index);
            NSData *data = [NSData dataWithBytes:bytes length:length];
            return @{@"$blob": [data base64EncodedStringWithOptions:0]};
        }
        default: return [NSNull null];
    }
}

static BOOL bindParameter(sqlite3_stmt *statement, int index, id value) {
    if (value == [NSNull null]) return sqlite3_bind_null(statement, index) == SQLITE_OK;
    if ([value isKindOfClass:[NSString class]]) {
        NSData *utf8 = [value dataUsingEncoding:NSUTF8StringEncoding];
        return sqlite3_bind_text(statement, index, utf8.bytes, (int)utf8.length, SQLITE_TRANSIENT) == SQLITE_OK;
    }
    if ([value isKindOfClass:[NSNumber class]]) {
        if (strcmp([value objCType], @encode(double)) == 0 || strcmp([value objCType], @encode(float)) == 0) {
            return sqlite3_bind_double(statement, index, [value doubleValue]) == SQLITE_OK;
        }
        return sqlite3_bind_int64(statement, index, [value longLongValue]) == SQLITE_OK;
    }
    return NO;
}

static void executeQuery(sqlite3 *database, NSDictionary *request) {
    id sql = request[@"sql"];
    id parameters = request[@"parameters"] ?: @[];
    if (![sql isKindOfClass:[NSString class]] || ![parameters isKindOfClass:[NSArray class]]) {
        sendError(@"invalid_request");
        return;
    }
    const char *tail = NULL;
    sqlite3_stmt *statement = NULL;
    int status = sqlite3_prepare_v2(database, [sql UTF8String], -1, &statement, &tail);
    if (status != SQLITE_OK || statement == NULL) {
        if (statement != NULL) sqlite3_finalize(statement);
        sendError(@"query_denied_or_invalid");
        return;
    }
    while (tail != NULL && (*tail == ' ' || *tail == '\t' || *tail == '\r' || *tail == '\n')) tail++;
    if (tail == NULL || *tail != '\0' || sqlite3_stmt_readonly(statement) != 1 ||
        (NSUInteger)sqlite3_bind_parameter_count(statement) != [parameters count]) {
        sqlite3_finalize(statement);
        sendError(@"query_denied_or_invalid");
        return;
    }
    for (NSUInteger i = 0; i < [parameters count]; i++) {
        if (!bindParameter(statement, (int)i + 1, parameters[i])) {
            sqlite3_finalize(statement);
            sendError(@"invalid_parameter");
            return;
        }
    }
    NSMutableArray *columns = [NSMutableArray array];
    int count = sqlite3_column_count(statement);
    for (int i = 0; i < count; i++) {
        [columns addObject:[NSString stringWithUTF8String:sqlite3_column_name(statement, i)] ?: @""];
    }
    NSMutableArray *rows = [NSMutableArray array];
    while ((status = sqlite3_step(statement)) == SQLITE_ROW) {
        NSMutableArray *row = [NSMutableArray arrayWithCapacity:(NSUInteger)count];
        for (int i = 0; i < count; i++) [row addObject:columnValue(statement, i)];
        [rows addObject:row];
    }
    sqlite3_finalize(statement);
    if (status != SQLITE_DONE) {
        sendError(@"query_failed");
        return;
    }
    sendJSON(@{@"ok": @YES, @"columns": columns, @"rows": rows});
}

static int serve(void) {
    NSData *bookmark = [[NSUserDefaults standardUserDefaults] dataForKey:BookmarkKey];
    if (bookmark == nil) {
        sendJSON(@{@"ready": @NO, @"error": @"no_saved_bookmark"});
        return 1;
    }
    BOOL stale = NO;
    NSURL *bundle = [NSURL URLByResolvingBookmarkData:bookmark
                                              options:NSURLBookmarkResolutionWithSecurityScope
                                        relativeToURL:nil bookmarkDataIsStale:&stale error:nil];
    if (bundle == nil || stale || !isThingsBundle(bundle) || ![bundle startAccessingSecurityScopedResource]) {
        sendJSON(@{@"ready": @NO, @"error": @"bookmark_access_denied"});
        return 1;
    }
    NSURL *file = [bundle URLByAppendingPathComponent:@"main.sqlite"];
    sqlite3 *database = NULL;
    int status = sqlite3_open_v2(file.path.fileSystemRepresentation, &database, SQLITE_OPEN_READONLY, NULL);
    if (status != SQLITE_OK || sqlite3_db_readonly(database, "main") != 1 ||
        sqlite3_set_authorizer(database, authorizeRead, NULL) != SQLITE_OK) {
        if (database != NULL) sqlite3_close(database);
        [bundle stopAccessingSecurityScopedResource];
        sendJSON(@{@"ready": @NO, @"error": @"database_open_failed"});
        return 1;
    }
    sendJSON(@{@"ready": @YES, @"readonly": @YES});
    char *line = NULL;
    size_t capacity = 0;
    ssize_t length;
    while ((length = getline(&line, &capacity, stdin)) != -1) {
        @autoreleasepool {
            NSData *data = [NSData dataWithBytes:line length:(NSUInteger)length];
            id request = data == nil ? nil : [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            if (![request isKindOfClass:[NSDictionary class]]) {
                sendError(@"invalid_request");
            } else if ([request[@"action"] isEqual:@"quit"]) {
                sendJSON(@{@"ok": @YES});
                break;
            } else {
                executeQuery(database, request);
            }
        }
    }
    free(line);
    sqlite3_close(database);
    [bundle stopAccessingSecurityScopedResource];
    return 0;
}

static int selectBundle(void) {
    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    [NSApp activateIgnoringOtherApps:YES];
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.message = @"Choose Things Database.thingsdatabase to allow read-only task access.";
    panel.prompt = @"Grant Database";
    panel.treatsFilePackagesAsDirectories = NO;
    panel.canChooseFiles = YES;
    panel.canChooseDirectories = NO;
    panel.allowsMultipleSelection = NO;
    panel.directoryURL = [NSURL fileURLWithPath:thingsRoot() isDirectory:YES];
    if ([panel runModal] != NSModalResponseOK) {
        sendError(@"selection_canceled");
        return 1;
    }
    NSURL *bundle = panel.URL;
    if (!isThingsBundle(bundle)) {
        sendError(@"wrong_bundle_selected");
        return 1;
    }
    NSData *bookmark = [bundle bookmarkDataWithOptions:NSURLBookmarkCreationWithSecurityScope |
                                                        NSURLBookmarkCreationSecurityScopeAllowOnlyReadAccess
                           includingResourceValuesForKeys:nil relativeToURL:nil error:nil];
    if (bookmark == nil) {
        sendError(@"bookmark_creation_failed");
        return 1;
    }
    [[NSUserDefaults standardUserDefaults] setObject:bookmark forKey:BookmarkKey];
    sendJSON(@{@"ok": @YES});
    return 0;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2) { sendError(@"usage"); return 1; }
        NSString *action = [NSString stringWithUTF8String:argv[1]];
        if ([action isEqual:@"select"]) return selectBundle();
        if ([action isEqual:@"serve"]) return serve();
        if ([action isEqual:@"clear"]) {
            [[NSUserDefaults standardUserDefaults] removeObjectForKey:BookmarkKey];
            sendJSON(@{@"ok": @YES});
            return 0;
        }
        sendError(@"unknown_action");
        return 1;
    }
}
