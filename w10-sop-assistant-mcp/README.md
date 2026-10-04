# w10: SOP assistant, exposed over MCP (Project 2)

**Work in progress. Ships Sat 10/10/2026**, when this page becomes the full write-up: quick start, node table, trade-offs, idempotency, what broke, limitations, security, and a walkthrough video.

Project 2 takes the [w9 RAG assistant](../w9-rag-sop-assistant) (ten invented media operations SOPs in Qdrant, cited answers) and exposes its search as an MCP tool, so any MCP client can use the knowledge base with its own model. Every SOP, title and process in the corpus is invented for this portfolio.

## Measured so far

Each number links to the record it came from.

- **Golden set, 20 hand reviewed questions:** 18 of 20 answers on 9/29, **19 of 20** after filtering superseded editions out at retrieval ([before](golden-results-before.json), [after](golden-results-after.json)). Compared item by item, only Q17 changed. Its citation still misses under strict scoring; the answer is correct and supported by what it cites. Cost unchanged at $0.0044 a question.
- **Top 6 instead of top 4:** tried and rejected. 19 to 26% more prompt tokens, and Q17's citations got worse ([runs](topk6)).
- **The MCP endpoint:** n8n's MCP Server Trigger with Bearer auth, one read only tool, `search_sops`. A missing or wrong token gets 403. Proposed protocol `2026-07-28`, and the server answered `2025-11-25` with a session ID ([checks](mcp-checks)).
- **A real client:** Claude Code answered the Q17 question through the endpoint by searching three times with its own queries; the chat agent searches once ([record](mcp-checks/claude-code-client-q17-execs-189-191.txt)).
- **Latency:** median 801ms over ten calls. About half is the OpenAI query embedding, Qdrant is 34ms.
- **No match:** a question the SOPs do not cover still returns four passages, and the similarity score never reaches the client.
- **Ingest without a gap:** the old ingest deleted and rebuilt the collection, and queries during it came back empty or failed (6 full of 10). Ingest now replaces in place, and 9 of 9 overlapping queries came back full ([race records](ingest-race)). A Qdrant alias swap was the first plan; [it does not work with this n8n version](ingest-race/alias-check-2026-10-03.md).

## What is in this folder

| Path | What it is |
|---|---|
| `workflow.json` | The MCP server workflow, exported clean |
| `chat-workflow.json` | The w9 chat and ingest workflow as it now runs: the status filter and the in place ingest |
| `golden-results-*.json` | The golden set before and after the filter |
| `topk6/` | The top 6 experiment |
| `mcp-checks/` | Auth, handshake, tool call, latency and no match records |
| `ingest-race/` | Queries fired during an ingest, before and after the fix, and the alias check |
