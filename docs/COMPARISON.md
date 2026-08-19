# Comparison: mcp-server-things vs hald/things-mcp

Comparison as of 2026-08-19 — versions: this server v1.6.2, [hald/things-mcp](https://github.com/hald/things-mcp) v0.8.1; details go stale, check both changelogs.

| Dimension | mcp-server-things (this repo) | hald/things-mcp |
|---|---|---|
| Write mechanism | AppleScript | Things URL scheme + `THINGS_AUTH_TOKEN` (required for bulk-update via JSON endpoint) |
| Delete / move / remove-tags | `delete_todo`, `move_record`, `bulk_move_records`, `remove_tags` all supported | No delete tool; no dedicated move/remove-tags tools (bulk-update can move/re-tag via the URL scheme's update command) |
| Checklist support | Yes | Yes |
| Structured output | Yes (FastMCP 3) | Yes (FastMCP 3) |
| Someday-project filtering | Yes — opt-in inheritance via `include_project_tasks` on `get_someday` | Yes (shipped first, in their v0.7.3/v0.8 line) |
| Large-result handling | Response modes (`summary`/`minimal`/`standard`/`detailed`) for context optimization | `limit`/`offset` pagination |
| Diagnostics | `mcp-server-things doctor` (Automation/TCC, DB access, `uv` on PATH, versions) | No equivalent |
| Client config generator | `mcp-server-things config --client ... --write` | No equivalent |
| Install | `uvx` + one-click `.mcpb` | `uvx` + one-click `.mcpb` |
| HTTP transport | Yes (`THINGS_MCP_TRANSPORT=http`) | Yes |
| Automation (TCC) permission | Required for writes (one-time prompt) | Not required (URL scheme) |
| Codebase / test size | Larger, heavily tested (~16.8k LOC, ~800 unit tests) | Smaller & easy to audit (~1.5k LOC, ~174 tests) |

## Which should you pick?

Pick **hald/things-mcp** if you want the smallest possible footprint, no Automation permission prompt, and don't need delete/move operations. Pick **this server** if you want full CRUD (including delete and move), work with large Things databases and want context-optimized responses, or want built-in diagnostics (`doctor`) and config tooling for setup and troubleshooting.

Credit where due: hald/things-mcp shipped Someday-project filtering, tag usage reporting, and `.mcpb` packaging first (their v0.7.3/v0.8 releases) — this server adopted the same ideas. Their [issue #62](https://github.com/hald/things-mcp/issues/62) has a good writeup of the TCC/Automation-permission trade-off that AppleScript-based servers like this one accept.
