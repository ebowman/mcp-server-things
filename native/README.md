# Scoped Things reader

Run `sh native/build.sh` on macOS. The signed app is written to
`build/ThingsReadHelper.app` by default. Set `THINGS_MCP_SCOPED_BUILD_DIR` to
another directory when the checkout is on a File Provider volume that adds
Finder metadata to app bundles (for example,
`THINGS_MCP_SCOPED_BUILD_DIR=/private/tmp sh native/build.sh`). Set
`THINGS_MCP_SCOPED_HELPER_APP` to the printed absolute app path in the
connector's environment.

The app has three actions: `select` shows a picker for the exact
`Things Database.thingsdatabase` bundle under a `ThingsData-*` folder; `serve`
resolves the saved read-only bookmark and uses stdin/stdout JSON lines; `clear`
removes the bookmark. A `serve` process first emits
`{"ready":true,"readonly":true}`. Send
`{"sql":"SELECT ... WHERE uuid = ?","parameters":["..."]}` and read one
`{"ok":true,"columns":[...],"rows":[...]}` response. SQLite blobs appear as
`{"$blob":"base64..."}`. Send `{"action":"quit"}` to close it. Errors have
`{"ok":false,"error":"...","code":1}`; startup errors use `ready:false`.

The helper opens only `main.sqlite` in read-only mode. SQLite's authorizer
permits reads from the Things task, area, tag, checklist, and `Meta` tables.
`TMSettings`, schema tables, attached databases, pragmas, and writes are denied.
Run `sh native/test-sql-gate.sh` for the synthetic SQL check.
