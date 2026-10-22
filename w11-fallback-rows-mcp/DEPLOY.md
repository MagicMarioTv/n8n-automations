# Deploying w11 to the VPS

**Not planned (10/21/2026).** This build is a pattern study and is not going on the VPS; see the [README](README.md). The checklist is kept as written, because it is the deploy pattern the flagship's MCP tools follow.

The checklist for putting the three tools on `n8n.mariomoreno.dev` and running the ship checks from a machine off the box. About 15 minutes. Every step either changes one thing or checks one thing, and it says which.

This adds two workflows and one credential. It doesn't upgrade n8n, change w9 or w10, or touch Qdrant, so there's no droplet snapshot step. Rollback is at the bottom.

---

## 1. Get the files

On the home computer, in the repo:

```bash
git checkout main && git pull
cd w11-fallback-rows-mcp
```

## 2. The token, as a file

```bash
openssl rand -hex 32 > ~/.w11-mcp-token && chmod 600 ~/.w11-mcp-token
cat ~/.w11-mcp-token
```

The file lives in your home directory, not in the repo. The probe and the client both read it from there.

## 3. In n8n: import and publish

1. **Import** `tracker-workflow.json`, then **publish** it.
2. **Create the credential:** Credentials, then **Bearer Auth**, named `W11 MCP token`. Paste the value printed in step 2.
3. **Import** `workflow.json`, then:
   - **MCP Server Trigger:** select `W11 MCP token`.
   - **`list_fallback_rows`, `get_fallback_row` and `get_status_vocabulary`:** on each one, open **Workflow** and select `W11 - Mock tracker (fallback bucket)` from the list. Do all three. The committed ID is from the local test instance and won't resolve, so a tool you skip will fail when it's called.
   - **Publish.**
4. **Check:** both workflows show as published. Remember that the canvas can show a draft that isn't serving yet ([w7](../w7-media-request-triage#quick-start)).

## 4. The probe, through Caddy

From the home computer, in `w11-fallback-rows-mcp/`:

```bash
python3 -I scripts/probe.py https://n8n.mariomoreno.dev ~/.w11-mcp-token \
  mcp-checks/vps-checks-$(date +%F).json \
  --compare mcp-checks/local-checks-2026-10-21.json
```

**Expected:** `18 of 18 checks match.` and exit code 0. Nothing in a response names the host, so the VPS should answer exactly like the local instance did. Only timings differ, and they aren't compared.

If something doesn't match, the DIFF lines show the response that came back. The first three rows were reproduced on the local instance on 10/21 and the text is quoted exactly; the others are the likely causes, not yet seen.

| What the probe shows | Cause |
|---|---|
| All 18 checks get **404**, `The requested webhook "POST fallback-rows" is not registered.` | The MCP workflow isn't published (reproduced) |
| All of one tool's calls DIFF, each `There was an error: "Workflow does not exist."` with `isError: true` | That tool's **Workflow** wasn't re-selected in step 3, so it still holds the local instance's ID (reproduced with that exact ID) |
| Every tool call DIFFs, each `There was an error: "Workflow is not active and cannot be executed."`; 5 of 18 still match | The tracker isn't published (reproduced). The 5 are the checks that never reach a tool |
| `no token` and `wrong token` match, but every other check gets 403 | The credential's value doesn't match `~/.w11-mcp-token` |
| `tools/list` DIFF, a tool missing or described differently | A change was saved but not published, or the import isn't the committed file |
| `initialize` DIFF, a different `protocolVersion` | The VPS isn't on 2.35.7. Note it and stop; the numbers are only comparable on one version |

## 5. The client checks

Register the server with Claude Code:

```bash
claude mcp add --transport http fallback-n8n https://n8n.mariomoreno.dev/mcp/fallback-rows --header "Authorization: Bearer $(cat ~/.w11-mcp-token)"
```

Then send these two prompts, **each in a fresh session**, word for word:

> Using the fallback-n8n server's tools, list the fallback bucket for Discovery+, then open each row and tell me in one line per row what you think it needs. Do not do anything else.

> Using the fallback-n8n server's tools, list the fallback bucket for Discovery+, then open each row and tell me which status each row should be routed to, one line per row. Do not do anything else.

Then open **Executions** for `W11 - Fallback rows over MCP` and note the execution IDs each session produced, and which tool each one called.

## 6. Send back

- The probe's output from `Compared with ...` down to the last line.
- `mcp-checks/vps-checks-<date>.json`. It holds no token, but check that before committing it.
- Both client replies, as returned, and the execution IDs from step 5.

With those, the README's status line, latency and Verification sections get updated to the VPS run, and this piece ships.

---

## Rollback

Unpublish `W11 - Fallback rows over MCP`. The endpoint stops answering at once. Nothing else depends on it: no other workflow calls the tracker, the credential is used only by this trigger, and none of the tools has ever written anything. To remove the build completely, delete both workflows and the credential, and run `claude mcp remove fallback-n8n` on the client.
