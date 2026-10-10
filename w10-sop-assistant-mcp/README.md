# w10-sop-assistant-mcp: the SOP search, exposed over MCP (Project 2)

The [w9 RAG assistant](../w9-rag-sop-assistant) answers questions about a media operations team's SOPs from a Qdrant vector store. Project 2 puts that same search behind an **MCP endpoint**, so any MCP client (Claude Code here) can search the SOPs as a tool and answer with its own model. It also fixes the miss w9 left open, stops ingest from emptying the store while people are searching it, and adds tracing.

The headline numbers. The golden set's one real miss, Q17, is fixed in its answer by **one retrieval filter**, and **18 of 20 questions are right on both answer and citation in all four runs from 9/29 to 10/10**, with answer alone moving from 18 to 20. Cost stayed at **$0.0044 a question**. The endpoint has **one read only tool and Bearer auth**, and a missing or wrong token gets 403. An ingest used to leave **4 of 10** overlapping searches empty or failed; it now leaves **0 of 9**.

Built 10/3 to 10/10/2026 on the instance from [w6-vps-deploy](../w6-vps-deploy). Every SOP, title and process in the corpus is invented.

The walkthrough video and the post are still to come and will be linked here.

---

## What it does

An MCP client connects to `https://n8n.mariomoreno.dev/mcp/sop-search` with a Bearer token and finds one tool:

| Tool | Input | Returns |
|---|---|---|
| `search_sops` | `input`: a search query in plain English | Up to 4 passages, each with its text and metadata: `source` (the file to cite), `doc_id`, `version`, `effective`, `status` |

Superseded editions never come back. The client's model writes the answer, so the tool's description carries the rules w9's system prompt gave its own agent: cite the source file for every fact, say so when a passage's status is `unknown`, and say the SOPs don't cover something rather than guess.

On ship day, Claude Code sent golden set Q17 through the endpoint word for word (execution 291):

> *"A promo has been sitting in qc_hold for 5 hours. What should have happened by now?"*

Four passages came back, all `current`: three from `qc-hold-procedure.md` and the promo rule from `promo-and-trailer-handling.md`, *"A promo in `qc_hold` is escalated after **4 hours** rather than 24"*. Before the filter, the chat's search for the same question gave two of its four slots to the superseded edition, and the promo rule never arrived.

Beside the endpoint, three things changed in the w9 workflow, which now lives in this folder as [`chat-workflow.json`](chat-workflow.json):

- **The status filter.** The chat's `sop_search` and the MCP tool both search with a Qdrant filter that keeps `current` and `unknown` passages and drops superseded ones.
- **Ingest replaces in place.** No more deleting the collection first, so a search during an ingest always finds a full set.
- **Tracing.** The golden set scorer sends one Langfuse trace per question, with tokens, cost, latency and both scores.

---

## Quick start

This builds on w9: Qdrant beside n8n, the credentials, and the corpus ingested. Follow [w9's quick start](../w9-rag-sop-assistant#quick-start) first.

**1. Update the w9 workflow.** Import [`chat-workflow.json`](chat-workflow.json) in place of w9's `workflow.json` and publish. It carries the status filter and the in place ingest. Re-ingest with w9's `scripts/ingest.py`. The response now ends with:

```json
"old_chunks_deleted": true,
"points_in_collection": 21,
"only_this_run": true
```

**2. A token for the endpoint.** In n8n, create a **Bearer Auth** credential named `W10 MCP token` with a long random value (`openssl rand -hex 32`). Keep the value somewhere that isn't a repo.

**3. The MCP workflow.** Import [`workflow.json`](workflow.json), select the token, the Qdrant and the OpenAI credentials on the nodes that show a warning, and **publish**. This n8n serves a published version, not the canvas. The endpoint is `https://<your-instance>/mcp/sop-search`.

**4. A client.** For Claude Code, with the token in an environment variable rather than typed into your shell history:

```bash
claude mcp add --transport http sop-n8n https://<your-instance>/mcp/sop-search --header "Authorization: Bearer $SOP_MCP_TOKEN"
```

Then ask it something the SOPs answer, for example the Q17 question above. If another connected server also has a tool called `search_sops`, name this server in the prompt (see Security).

---

## How it works

```
MCP (new workflow: W10 - SOP search over MCP)
MCP Server Trigger (path /mcp/sop-search, Bearer auth)
   <- search_sops (Qdrant Vector Store, retrieve as tool, top 4, status filter)
         <- Embeddings (query)  OpenAI text-embedding-3-small

CHAT (w9's workflow, changed)
When chat message received (Basic Auth) -> SOP Assistant (AI Agent, Haiku 4.5)
   <- sop_search (same store, same filter, top 4)

INGEST (w9's workflow, changed)
Ingest Request (header auth) -> Split Docs (stamps ingest_id) -> Store Chunks
   -> Summarize Ingest (guard) -> Delete Old Chunks -> Count Points -> Ingest Report -> Send Ingest Result
```

| Node | What it does | Why |
|---|---|---|
| **MCP Server Trigger** | n8n's MCP server node, v2, path `sop-search`, Bearer auth | It turns any tool node connected to it into an MCP tool. Choosing it over running the [9/29 Python learning server](#trade-offs) on the VPS meant no new container, no new port, and Caddy already terminating TLS. |
| **search_sops** | Qdrant Vector Store in retrieve as tool mode, collection `sop_corpus`, top 4, metadata included, the status filter below | The same store and settings as the chat's `sop_search`, so the MCP path and the chat path retrieve identically. The tool description is written for a model that has never seen w9's system prompt. |
| **Embeddings (query)** | OpenAI `text-embedding-3-small` | Has to match the model the chunks were embedded with, as in w9. |
| **Split Docs** (changed) | Stamps every SOP with `ingest_id`, `ingest-` plus the execution ID | Lets the delete step tell this run's chunks from the last run's. The prefix keeps it a string, so Qdrant's exact match works. |
| **Summarize Ingest** (changed) | Counts chunks per file, and **throws** if any stored chunk lacks this run's `ingest_id` | The next node deletes everything *without* this run's ID. A run that stored chunks without the ID would delete its own chunks too, so it stops first. |
| **Delete Old Chunks** (new) | `POST /collections/sop_corpus/points/delete`, filter `must_not` this run's `ingest_id` | Removes the previous edition only after the new one is fully stored. |
| **Count Points** (new) and **Ingest Report** (new) | An exact count of the collection, then `only_this_run: points_in_collection == chunks` | The ingest proves its own result instead of claiming it. |

w9's `Reset Collection`, which deleted the collection before every ingest, is gone (What broke, 2).

**The filter**, on both `search_sops` and the chat's `sop_search`:

```json
{ "should": [
    { "key": "metadata.status", "match": { "value": "current" } },
    { "key": "metadata.status", "match": { "value": "unknown" } } ] }
```

Qdrant's `should` keeps a point that matches at least one condition. Two simpler filters fail. Excluding the value `superseded` matches nothing, because the stored status is the whole sentence `superseded: by SOP-QC-003 on 2026-06-01` and `match` is exact. Keeping only `current` would also hide every `unknown` document, and then the w9 rule that tells users a document is unverified could never fire. The node passes this JSON to Qdrant in retrieve as tool mode; that was checked in n8n 2.35.7's source before relying on it, then in execution 157.

**What a client actually receives.** JSON inside JSON inside JSON. The MCP result is one text block. Its text is a JSON array of four items, and each item's text is a JSON string holding `pageContent`, `metadata` and the point `id`. A client parses three times to reach `metadata.source`. The similarity score is not anywhere in it (Trade-offs).

**Protocol.** The probe proposed MCP revision `2026-07-28`, the stateless one, and the server answered **`2025-11-25`** with a session ID header. So this endpoint runs the session based Streamable HTTP revision, and a client has to keep the session ID between calls. Claude Code negotiated that without being told.

**Tracing.** The scorer (`--trace`) sends each golden question to Langfuse Cloud's free tier as a trace holding one generation (model, prompt and completion tokens, cost, latency) and two boolean scores, `answer_ok` and `citation_ok`. It uses the Langfuse Python SDK 4.17.0, which speaks OpenTelemetry, rather than plain HTTP calls, because Langfuse's docs say the legacy REST ingestion API is sunset on Langfuse Cloud on 11/16/2026, and this account, created after 9/16/2026, already gets 410 from the legacy read endpoint (What broke, 5). Screenshots: [the Q17 trace](langfuse/langfuse-trace-q17.png), [latency and cost per question](langfuse/langfuse-latency-cost.png).

---

## The golden set, before and after

The same twenty hand reviewed questions as [w9](../w9-rag-sop-assistant#the-golden-set-18-of-20), scored on answer and citation, each in a fresh chat session. **The golden set measures the chat agent.** The MCP path is checked separately below, because over MCP the answer depends on whichever client model is calling.

| | 9/29, before the filter | 10/3, after the filter | 10/9, traced | 10/10, final |
|---|---|---|---|---|
| Executions | 137 to 156 | 158 to 177 | 271 to 290 | 292 to 311 |
| Answer correct | 18 | 19 | 20 | 20 |
| Citation correct | 18 | 18 | 18 | 18 |
| **Both correct** | **18** | **18** | **18** | **18** |
| Q17 answer, citation | miss, miss | pass, miss | pass, miss | pass, miss |
| Q18 answer, citation | miss, miss | miss, miss | pass, miss | pass, miss |
| Prompt tokens | 74,234 | 74,440 | 75,544 | 75,544 |
| Completion tokens | 2,679 | 2,721 | 2,643 | 2,605 |
| Cost for the set | $0.08763 | $0.08805 | $0.08876 | $0.08857 |
| Median latency per answer | not measured | not measured | 2,791ms | 2,914ms |

Records: [before](golden-results-before.json), [after](golden-results-after.json), [traced](langfuse/golden-results-traced.json), [final](golden-results-final.json). Compared item by item, **only Q17 and Q18 ever change**, and no workflow changed between 10/3 and today (checked against the live instance on 10/10). So the honest reading is a range, not a best run.

- **Q17 is fixed in its answer by the filter.** Before: all four slots went to QC hold chunks, two of them the superseded edition, and the assistant said a 5 hour old promo hold was "still within the service level window". After: the freed slots let the promo SOP in, and every run since says it should already have been escalated after 4 hours. **Its citation still misses under strict scoring**: the key expects `on-call-escalation.md` for what escalation means (Tier 2), and that file never reaches the chat's top four. The reply's Tier 2 claim is supported by section 5 of `qc-hold-procedure.md`, which it does cite, so the label was left as written rather than loosened after the fact.
- **Q18 flickers.** Every reply gets the core fact (a 6 Mbps episode mezzanine is below the 8 Mbps minimum, so it goes to QC hold). It passes the answer check only when the reply contains the literal string `qc_hold`, and the 10/3 reply also said the file "is rejected", which a hold is not. Its citation always omits the QC hold SOP. Nothing about it changed with the filter.

**Cost, measured, for the final run.** Tokens were read from `tokenUsage` on every LLM call in every execution: 75,544 prompt and 2,605 completion across the twenty. At Haiku 4.5's $1 and $5 per million: 75,544 / 1,000,000 x $1 = $0.0755, plus 2,605 / 1,000,000 x $5 = $0.0130, **$0.0886 for the set, $0.0044 a question**, the same as on 9/29. Langfuse's own cost total for the run is also $0.08857.

**10/9 and 10/10 match more closely than expected.** Every verdict is the same, item by item, and the prompt tokens are identical on all twenty questions. That is what the same searches returning the same passages would produce; only the wording of the replies changed (2,643 completion tokens, then 2,605).

Prompt tokens rose 1,104 from 10/3 to 10/9, about 55 a question. The `ingest_id` field arrived in between and now rides on every passage the agent reads. That is the likely cause; it was not isolated.

**Top 6 instead of top 4: tried and rejected** ([runs](topk6)). Q14 and Q17, three runs each: prompt tokens up 19% and 26%, and Q17's citation got *worse*, citing only the promo SOP and leaving the Tier 2 claim unsupported. `on-call-escalation.md` wasn't in the top six either.

---

## The endpoint, checked

A probe script (kept outside the repo, because it reads the token from a local file) runs named checks against the live endpoint through Caddy. Its records are in [`mcp-checks/`](mcp-checks).

| Check | Result |
|---|---|
| No token | **403** `Authorization data is wrong!` |
| Wrong token | **403**, same text. w8's Basic Auth gave 401 for none and 403 for wrong; this trigger gives 403 for both |
| `initialize`, proposing `2026-07-28` | 200, `protocolVersion: 2025-11-25`, a session ID header |
| `tools/list` | One tool, `search_sops`, with the description from `workflow.json` |
| `tools/call` with Q14 | 200 in 674ms, four passages, each with `source` and `status` |

**Latency**, ten calls on 10/3: **median 801ms**, slowest 2,516ms. From n8n's per node times, the OpenAI query embedding is about half (median 407ms), Qdrant is **34ms**, and about 300ms is outside the tool (network, Caddy, the MCP layer). The two slow calls were one slow embedding (1,475ms) and the first call of a session.

**A question the SOPs don't cover** (*"How do I make pizza dough?"*) returns four unrelated passages and no error. n8n's search computes a similarity score and sends only the passage, so nothing in the result says "weak match" (Trade-offs).

**A real client, two ways.** On 10/3 Claude Code answered the Q17 question correctly through the endpoint, citing all three SOPs, but it took **three searches with its own rewordings**; only the third (*"on call escalation Tier 2 what happens when a QC hold is escalated"*) brought back `on-call-escalation.md` ([executions 189 to 191](mcp-checks/claude-code-client-q17-execs-189-191.txt)). The chat agent searches once. On 10/10 the question went in word for word and came back with the promo rule in slot four and no escalation SOP ([execution 291](mcp-checks/claude-code-q17-2026-10-10-exec-291.txt)). **Over MCP, answer quality depends partly on how the client searches**, which no server side setting controls.

---

## Ingest without a gap

w9's ingest deleted the collection and rebuilt it. Four workers sent the same query while an ingest ran ([records](ingest-race)):

| | Queries during ingest | Full (4 passages) | Empty | Error |
|---|---|---|---|---|
| Before, delete then insert | 10 | 6 | 2 (`[]`) | 2 (`NodeOperationError: Conflict`) |
| After, replace in place (ingest-234) | 9 | 9 | 0 | 0 |
| After, again (ingest-252) | 9 | 9 | 0 | 0 |

**Why the empties and the conflicts.** The cause is in the library n8n's Qdrant node uses, `@langchain/qdrant` 1.0.1: every search first runs `ensureCollection()`, which lists the real collections and **creates the collection if it's missing**. A search that lands after the delete builds a brand new empty collection and searches it, which is the `[]`. Two searches doing that at once race to create the same name, which is the `Conflict`.

w9's plan was to build a new collection and swap an alias to it. **That can't work with this node** ([check](ingest-race/alias-check-2026-10-03.md)): `ensureCollection()` lists collections, not aliases, so a search through an alias tries to create the alias's name and Qdrant refuses with `Bad request - please check your parameters` (execution 228, a throwaway workflow deleted afterwards). Replacing in place needs no alias.

---

## Trade-offs

**n8n's MCP Server Trigger, not the Python server.** A hand built Python MCP server already existed from 9/29 (local only, never published). Putting it on the VPS meant a new container, a port, its own TLS route and its own auth. The trigger needed none of that and reuses the exact search node the chat uses. The cost: the protocol revision, the auth options and the response shape are whatever n8n 2.35.7 ships, which is why this endpoint speaks `2025-11-25` and drops the similarity score.

**One shared Bearer token.** Simple, and enough to keep strangers out. It gives no per client identity (the logs can say "the token holder", never who), no way to revoke one client without rotating it for every client, and no rate limit. Each call spends an OpenAI embedding and an n8n execution. Cheap (a search's embedding costs about $0.0000001), but unbounded.

**Filter at retrieval, keep the superseded edition stored.** The superseded 2025 edition stays in the collection, so a question can still be asked about it by going to the file, and the store looks like a real SOP library full of old editions. The filter keeps it out of every answer. A filter is cheaper than the reranker (an extra model call per search) and fixed the cause, so the reranker, third in the plan, was never tried.

**Top 4 kept.** Measured against top 6 above: more tokens, no better citations.

**Replace in place, not swap.** No empty window, no alias, no second collection. The cost: for the few seconds between storing the new chunks and deleting the old, both editions are in the collection, so a search *could* get the same passage twice. None of the 9 overlapping queries whose passages were recorded got one, which shows it's rare, not that it can't happen. A failed ingest leaves both editions until the next good one (Idempotency).

**No score in the result.** The node sends `document[0]` from each `[document, score]` pair, so a client can't tell a strong match from a weak one. Returning the score means replacing the vector store node with a custom search, which loses the shared configuration with the chat. Left as is, and stated.

**Shipping on n8n 2.35.7.** Every number in this folder was measured on one version, so the before and after comparison means something. The cost is in Security, item 8.

**Langfuse Cloud, not self hosted.** The box is a 1GB droplet already carrying n8n and Qdrant; Langfuse's self hosted stack needs several more services. The cost is that golden set questions, replies and token counts go to a third party. The corpus is invented, so nothing sensitive goes.

---

## Idempotency

**Search twice: same passages, two executions.** The tool only reads. Each call is an n8n execution and one embedding call, and nothing is written.

**Ingest twice: one copy, proven.** Each ingest stores its chunks under a new `ingest_id`, then deletes every point without that ID, then counts. Last check, ingest-252: 21 chunks stored, `points_in_collection: 21`, `only_this_run: true`.

**An ingest that fails halfway** leaves the old edition in place, plus whatever part of the new one was stored, because the delete only runs after the guard passes. Searches keep working, possibly with duplicates, until the next successful ingest deletes everything that isn't its own.

**Score twice: a new trace set each time.** Each traced run gets its own Langfuse session name (`golden-YYYYMMDD-HHMM`), so runs never overwrite each other there. Locally, `--out` writes each run to its own file (What broke, 1).

---

## What broke

Real failures, real error text, in the order they happened.

**1. A partial run overwrote the baseline.** A run of a few questions wrote its results over w9's `golden-results.json`, the 9/29 file this whole comparison depends on. The committed copy was untouched in git (its last commit is still 9/29), so nothing was lost. The scorer gained `--out <file>`, and every run in this folder uses it.

**2. Ingest emptied the store under live searches.** Above, in full: `[]` and `NodeOperationError: Conflict`.

**3. The alias swap.** `ERROR: Bad request - please check your parameters`. Above.

**4. The first traced run asked nothing.** It finished cleanly with zero questions. The golden IDs are zero padded, `Q01`, and the run was started with `Q1`, which matched nothing and raised no error. A filter that silently matches nothing looks exactly like success.

**5. Langfuse's legacy API refused this account.** Reading a trace back by ID:

```
410 LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION
```

Langfuse organizations created on or after 9/16/2026 must use the v2 observations API. The traces were read back through `/api/public/v2/observations` and `/api/public/v3/scores` instead. Reads on the free tier also return `429` quickly, so the check is two windowed queries, not one call per trace.

**6. The trace counted time that wasn't the answer.** The first traced latency included an n8n API lookup the scorer makes before asking: 7.18 seconds traced against 6.54 for the answer itself. After moving the timer: 3.033 seconds traced against 3,032ms in n8n.

**7. The median was wrong for even counts.** It took the upper middle value instead of averaging the two. Twenty questions is an even count.

---

## Security

**The guidance this section follows** is NSA's *Model Context Protocol (MCP): Security Design Considerations for AI-Driven Automation*, May 2026 Ver. 1.0 (U/OO/6030316-26). Its eight recommendations, and what this build does about each:

| NSA recommendation | What this build does | What it doesn't |
|---|---|---|
| **Choose supported MCP projects** | The server is n8n's own MCP Server Trigger node and the client is Claude Code. No third party MCP server runs on the VPS. | The n8n version is behind; see item 8. |
| **Design for boundaries** | Qdrant has no published port and needs a key. The endpoint can only search: ingest and chat sit behind their own separate credentials. The corpus is invented, so the data is public grade. | No outgoing proxy: n8n calls OpenAI directly. |
| **Validate parameters** | One tool, one string input, required by the schema n8n publishes. | No length limit of its own, and the published schema allows extra properties. |
| **Constrain and sandbox tool execution** | The tool is a read only search. No shell, no file access, no writes. The workflow holds three credentials: its token, Qdrant and OpenAI. | The Qdrant key it uses is the full access key. Qdrant supports a separate read only key (`QDRANT__SERVICE__READ_ONLY_API_KEY`, since v1.7.0; this box runs 1.19.1), and this tool should use one. |
| **Sign and verify MCP messages** | TLS from Caddy, a Bearer token on every request. | No message signing, no expiry, no replay protection. The token is static and shared. |
| **Filter and monitor output pipelines** | Passages come only from a corpus behind a gated ingest, so anything in them came through the ingest token. | Passages go out verbatim with no output filtering. A poisoned SOP would reach the client model as written; the client is the last line. |
| **Instrument for logging and detection** | Every call is an n8n execution with the query and the passages returned, readable through the API (execution 291 was checked that way). Scored runs are traced in Langfuse. | No caller identity beyond the shared token, and nothing feeds an alerting system. |
| **Track and patch MCP related vulnerabilities** | The version is pinned and recorded, and the advisories were counted (below). | **This is the one the build currently misses.** |

**The version, plainly.** The VPS runs n8n **2.35.7**. Between 8/29 and 10/1/2026 n8n published 49 security advisories, and the stated version ranges of 46 of them include 2.35.7: 24 rated high, none critical. "In range" is not the same as "affected"; each one depends on whether the vulnerable feature is in use. It shipped on 2.35.7 on purpose, so every before and after number here was measured on one version. The patch is planned for after ship day: snapshot the droplet first (minor upgrades run database migrations, so changing the tag back is not a safe rollback), pin **2.41.5** exactly, then rerun the golden set, these MCP checks and the phone checks as the regression gate.

**OWASP ASI04, Agentic Supply Chain Vulnerabilities**, from the OWASP Top 10 for Agentic Applications (2026), is the risk an agent takes on from components it loads and trusts at runtime. To a client, this server *is* one of those components: its tool description becomes instructions in the client model's context, and its passages become context too. What it does to be a safe one: one tool with a fixed description you can read in [`workflow.json`](workflow.json), a tool list that doesn't change between calls, read only, Bearer auth, a fixed path. One real hazard turned up in testing. **Two servers connected to the same Claude Code session both expose a tool named `search_sops`**: this one and the local learning server. Claude Code keeps them apart by server name, but a prompt that says "search the SOPs" doesn't say which. Name the server, and confirm a call by its n8n execution, which is what every check here did.

**What leaves the box:**

| Data | Goes to |
|---|---|
| Every search query | OpenAI, for the embedding |
| The passages a search returns | The calling client, and that client's own model provider |
| Chat questions and replies | Anthropic (Haiku 4.5) and OpenAI (the embedding) |
| Golden set questions, replies, tokens and scores | Langfuse Cloud, US region, on traced runs only |

---

## Why MCP, in this industry

At IBC 2026 in September, media vendors announced this shape. Tedial announced MCP for its media supply chain platform ([TV Technology, 8/26](https://www.tvtechnology.com/infrastructure/tedial-to-demo-ai-driven-media-supply-chain-solutions-at-ibc-2026)), and a [Key Code Media roundup](https://www.keycodemedia.com/ibc-2026-the-biggest-broadcast-production-and-av-technology-announcements/) reports Telestream adopting MCP, Imagine Communications adding MCP connectivity, and Backlight introducing an Iconik MCP server. They point approved AI assistants at the systems that run content operations. This build is the same idea at portfolio scale: an assistant of your choosing, searching operating procedures it was never trained on, through a gate.

---

## Limitations

- **Twenty questions.** Four runs now, and two items move between runs with no change to the workflow. The golden set is a range, not a score.
- **The golden set doesn't run over MCP.** It measures the chat agent. The MCP path is checked by named calls, and two Claude Code sessions searched it differently.
- **Q17's citation and Q18's both still miss**, under a strict key that wasn't loosened.
- **No score, no "nothing found".** Every search returns four passages, relevant or not.
- **One shared token, no rate limit, a full access Qdrant key.** Security has the details.
- **Session based protocol.** `2025-11-25`, not the stateless `2026-07-28`.
- **n8n 2.35.7**, inside the stated ranges of 46 advisories.
- **Tracing covers scored runs only.** Live chat and MCP traffic isn't traced. The `--trace` option lives in the scorer I run locally; w9's portable `scripts/score.py` doesn't have it yet.
- **A stale comment.** `Split Docs` still says the node before it replaced the item with Qdrant's reply. That was `Reset Collection`, which no longer exists. The code is right and the comment isn't.
- **Ten small documents**, as in w9.

---

## Next

1. **Patch n8n to 2.41.5** after ship day, on the plan in Security, with this folder's numbers as the regression gate.
2. **A read only Qdrant key for the search tools**, and a token per client.
3. **Return the score**, or a threshold, so a client can tell "nothing relevant" from four passages.
4. **The golden set over MCP**, with one fixed client model, run three times.
5. **Q17's citation:** the reranker, the one option of the three not tried.
6. **`--trace` in the portable scorer**, and the stale comment fixed.
7. The flagship (Project 3) reuses this pattern: its tools go over MCP too.

---

## Verification, by named check

Following the repo's rule since 9/14: a README may claim something works only if it names the check that was run.

- **Live workflows match this folder:** on 10/10 both workflows were fetched through the n8n API and compared node by node with `workflow.json` and `chat-workflow.json` (positions ignored): identical. Both active, `versionId` equal to `activeVersionId`. Last changed 10/3.
- **Auth:** no token and a wrong token both returned 403 through Caddy from a machine off the VPS ([record](mcp-checks/checks-2026-10-03_1957-propose-2026-07-28.json)).
- **Protocol and tools:** `initialize` answered `2025-11-25` with a session ID; `tools/list` returned `search_sops` alone; `tools/call` returned four passages with `source` and `status` (same record).
- **The filter:** execution 157 smoke test, four `current` passages; then every passage in executions 189 to 191 and 291 reads `current`.
- **Claude Code as a client:** executions 189 to 191 (10/3) and 291 (10/10), `mode: webhook`, read back through the n8n API, queries and sources in the [records](mcp-checks).
- **Golden set runs:** executions 158 to 177, 271 to 290 and 292 to 311, production mode, through the Basic Auth gated chat from a machine off the VPS. Replies, execution IDs and tokens in the results files.
- **Langfuse:** the 10/9 run read back from Langfuse, not taken from the SDK's "sent": 20 generations, tokens equal to n8n's on all 20, total cost equal to the scorer's, 40 scores. The 10/10 final run the same way (session `golden-20261010-1206`): 20 generations, tokens equal on all 20, cost $0.08857 on both sides, and 40 scores, `answer_ok` 20 true and `citation_ok` 18 true and 2 false, matching the results file.
- **Ingest in place:** ingest-234 and ingest-252 each returned `only_this_run: true` with 21 points; the race records show 9 of 9 overlapping queries full both times.
- **The alias failure:** execution 228, a throwaway workflow, deleted afterwards; the alias was removed and `Aliases After` returned an empty list.
- **Latency:** ten timed `tools/call` requests ([record](mcp-checks/latency-2026-10-03_2010.json)), with per node times read from each execution.
- **Phone check:** not yet run for this ship day. The last one is w9's on 9/26 (executions 108 and 109); this line gets the new execution numbers when it's done.
- **Exports:** `workflow.json` and `chat-workflow.json` are instance exports with `pinData`, `versionId`, `meta` and `staticData` removed, checked by script for every token and key by value before each commit.
