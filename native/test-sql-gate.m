#define main ThingsReadHelperMain
#include "ThingsReadHelper.m"
#undef main

int main(void) {
    @autoreleasepool {
        sqlite3 *database = NULL;
        if (sqlite3_open(":memory:", &database) != SQLITE_OK) return 1;
        const char *setup = "CREATE TABLE TMTask(uuid TEXT, title TEXT, payload BLOB);"
                            "CREATE TABLE TMSettings(secret TEXT);"
                            "INSERT INTO TMTask VALUES('test-1', 'Synthetic task', x'0102');";
        if (sqlite3_exec(database, setup, NULL, NULL, NULL) != SQLITE_OK) return 1;
        if (sqlite3_set_authorizer(database, authorizeRead, NULL) != SQLITE_OK) return 1;
        executeQuery(database, @{@"sql": @"SELECT title, payload FROM TMTask WHERE uuid = ?",
                                 @"parameters": @[@"test-1"]});
        executeQuery(database, @{@"sql": @"SELECT COUNT(*) FROM TMTask"});
        executeQuery(database, @{@"sql": @"SELECT secret FROM TMSettings"});
        executeQuery(database, @{@"sql": @"SELECT name FROM sqlite_master"});
        executeQuery(database, @{@"sql": @"SELECT name FROM pragma_table_info('TMSettings')"});
        executeQuery(database, @{@"sql": @"PRAGMA database_list"});
        executeQuery(database, @{@"sql": @"UPDATE TMTask SET title='changed'"});
        executeQuery(database, @{@"sql": @"SELECT title FROM TMTask; SELECT title FROM TMTask"});
        sqlite3_close(database);
        return 0;
    }
}
