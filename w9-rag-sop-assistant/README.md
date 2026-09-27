# w9-rag-sop-assistant: questions answered from SOPs, with citations, and a golden set that scores them

A chat assistant that answers questions about a media operations team's standard operating procedures by searching them first, and cites the file every fact came from. Ten SOPs are split into chunks, embedded, and stored in a **Qdrant** vector store running beside n8n on the VPS. An n8n **AI Agent** gets one tool, a search over that store, and a system prompt that says: search before every answer, cite every fact, and say so when the SOPs don't cover something.

The point of the build is two numbers and one failure. The failure first: asked the SLA for clearing a QC hold, the first version **answered with a superseded procedure and called the current one "the previous version"**, with citations on both. The fix was one ingest change, and it was measured. Then a twenty question golden set, reviewed by hand against the SOPs before anything was scored: **18 of 20 correct on both answer and citation**, at **$0.0042 a question** on Haiku 4.5.

Built and measured 2026-09-26, on the instance from [w6-vps-deploy](../w6-vps-deploy). It is the first half of Project 2, which exposes the same search over MCP.

The [LinkedIn post](https://lnkd.in/p/e2BTy83B) is the short version: the superseded answer and its fix.

---

## What it does

You ask a question in a chat window. The agent turns it into a search query, gets back the four chunks of SOP text that best match, and answers from those alone, with each fact followed by its source file in square brackets:

> The SLA for clearing a QC hold is **24 hours** (calendar hours, including weekends) [qc-hold-procedure.md].
> Note: An older version of the SOP specified 48 hours on business hours only [qc-hold-procedure-2025.md], but this has been superseded by the current version.

The corpus is in [`corpus/`](corpus): ten short SOPs covering QC holds, the mezzanine spec, the encoding ladder, captions, naming, delivery deadlines, redelivery, promos and trailers, and on call escalation. **Every organisation, title, asset ID and procedure in them is invented.** The platforms are "Platform A" and "Platform B" on purpose: a procedure document naming a real streaming service reads as a leaked one. Three things were built into the corpus deliberately, because a corpus with no traps tests nothing:

- **A superseded edition.** `qc-hold-procedure-2025.md` contradicts the current `qc-hold-procedure.md` on the SLA (48 hours against 24), on who can clear a hold, and on whether a caption failure can be waived. Its header says it is superseded. Nothing else in it does.
- **Answers that need two documents.** A promo's QC hold escalates after 4 hours, not 24, and that exception lives in the promo SOP, not the QC hold SOP.
- **A gap.** Nothing covers audio loudness. The right answer to a loudness question is "the SOPs don't cover it."

A second branch of the same workflow is the ingest: a gated webhook that takes the SOPs as JSON, wipes the collection, and stores them again.

---

## Quick start

Four pieces: a box with room for Qdrant, credentials, the workflow, and the corpus.

**1. The box.** This builds on the w6 deploy, which is a 1GB droplet. On 9/26 that box had 210MB available and **no swap**, with n8n alone using 375MB. Add swap before adding a second service, or the kernel's out of memory killer will pick a process for you, and n8n is the biggest one:

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo "/swapfile none swap sw 0 0" >> /etc/fstab
echo "vm.swappiness=10" > /etc/sysctl.d/99-swap.conf && sysctl -p /etc/sysctl.d/99-swap.conf
```

Then add a key to the compose directory's `.env` and use [`docker-compose.yml`](docker-compose.yml) from this folder, which is w6's file plus a `qdrant` service:

```bash
echo "QDRANT_API_KEY=$(openssl rand -hex 32)" >> .env
docker compose up -d qdrant
```

That starts Qdrant only. n8n's config didn't change, so its container keeps running. **The `qdrant` service has no `ports:` line**, so nothing outside the compose network can reach it; n8n reaches it at `http://qdrant:6333` through Compose's internal DNS.

**2. Credentials in n8n**, five of them. The workflow references them by these names:

| Credential | Type | What goes in it |
|---|---|---|
| `W9 Qdrant (internal)` | Qdrant API | URL `http://qdrant:6333`, API key from the `.env` above |
| `OpenAI account` | OpenAI | An OpenAI API key. Used for embeddings only (see Trade-offs) |
| `Anthropic account` | Anthropic | For the chat model |
| `W9 ingest token` | Header Auth | Name `X-Ingest-Token`, value any long random string |
| `W9 chat gate` | Basic Auth | Any username and password |

**3. The workflow.** Import [`workflow.json`](workflow.json) from file, select your credential on each node that shows a warning, and **publish**. This n8n serves a published version, not the canvas; a draft serves nothing.

**4. The corpus**, then a question:

```bash
SOP_INGEST_URL=https://<your-instance>/webhook/sop-ingest SOP_INGEST_TOKEN=<token> python scripts/ingest.py
```

Expect `"chunks": 21, "files": 10`. Then open the chat trigger's URL, log in, and ask `What's the SLA for clearing a QC hold?`

To score the golden set yourself, `scripts/score.py` (its docstring lists the environment variables; token counts are optional and need an n8n API key).

---

## How it works

```
INGEST
Ingest Request (Webhook, POST /sop-ingest, header auth)
   -> Reset Collection (HTTP DELETE /collections/sop_corpus, errors continue)
   -> Split Docs (Code: one item per SOP, header fields parsed out)
   -> Store Chunks (Qdrant Vector Store, insert)
         |-- Embeddings (ingest)   OpenAI text-embedding-3-small   ai_embedding
         |-- Load Doc              Default Data Loader              ai_document
               |-- Split Text      Recursive splitter, 1000 / 100   ai_textSplitter
   -> Summarize Ingest (Code: chunks per file) -> Send Ingest Result

CHAT
When chat message received (Chat Trigger, Basic Auth)
   -> SOP Assistant (AI Agent)
         |-- Anthropic Chat Model (Haiku 4.5, temperature 0)   ai_languageModel
         |-- Simple Memory (window 5)                          ai_memory
         |-- sop_search (Qdrant Vector Store, retrieve as tool, top 4)   ai_tool
               |-- Embeddings (query)  OpenAI text-embedding-3-small      ai_embedding
```

| Node | What it does | Why |
|---|---|---|
| **Ingest Request** | Webhook, POST, Header Auth | Ingest deletes the collection and spends OpenAI tokens. Neither should be something a stranger can trigger by finding a URL. |
| **Reset Collection** | `DELETE http://qdrant:6333/collections/sop_corpus` using the Qdrant credential, On Error: continue | The Qdrant node in this n8n version (2.35.7) has **no option to clear the collection before inserting**, checked in the node's source. Without this step every ingest adds another copy of every chunk. On Error: continue so the very first run, when there is no collection to delete, carries on. |
| **Split Docs** | Code: one item per SOP, plus `doc_id`, `version`, `effective` and `status` parsed from the header line | The fix for the headline failure, below. It reads the docs from `$('Ingest Request')` by name, because the node before it replaced the item with Qdrant's reply to the DELETE. |
| **Load Doc** | Default Data Loader, JSON mode, text from `$json.text`, five metadata fields | Metadata set here is copied onto **every chunk** the splitter makes from that document. That is the mechanism the fix depends on. |
| **Split Text** | Recursive character splitter, 1,000 characters, 100 overlap | It splits at paragraph breaks first and packs whole paragraphs until the next would pass 1,000. The SOPs run 1,250 to 2,265 characters, so every doc becomes 2 or 3 chunks and a short section stays whole. |
| **Embeddings** (both) | OpenAI `text-embedding-3-small`, 1,536 dimensions | Anthropic has no embeddings endpoint. Ingest and query **must** use the same model: vectors from two different models are not comparable, and nothing warns you if they don't match. |
| **Store Chunks** / **sop_search** | Qdrant Vector Store, collection `sop_corpus`, insert mode and retrieve as tool mode | Retrieve as tool hands the agent a search tool. With Include Metadata on (the default), each result reaches the model as JSON: the chunk's text plus its metadata, including `source`, which is where the citation comes from. Checked in the node source and in the execution traces. |
| **SOP Assistant** | AI Agent, `maxIterations: 4`, `returnIntermediateSteps: true` | Four iterations: every answer here took two LLM calls (search, then answer) except one that took three. The intermediate steps are how every finding below was found. |
| **Anthropic Chat Model** | Haiku 4.5, **temperature 0** | Zero because the golden set needs repeatable answers. It still isn't fully repeatable; see Trade-offs. |

The system prompt's five rules: search before every answer and never answer from general knowledge; cite every fact as `[filename.md]`, which is in each result's metadata under `source`; if the results don't answer the question, say the SOPs don't cover it; if two sources disagree, say so and cite both; answer first, citations after.

---

## The finding: a superseded document, answered as current

**Before.** First ingest, only `source` stamped on each chunk. Asked *"What's the SLA for clearing a QC hold?"* (execution 81):

> **Current version (2025):** A QC hold must be cleared or escalated within **48 hours** [...] [qc-hold-procedure-2025.md]
> **Previous version:** A QC hold must be cleared or escalated within **24 hours** [...] [qc-hold-procedure.md]
> Note: The 2025 version superseded the earlier version on 2026-06-01, so the 48-hour business-hours SLA is the current standard.

Exactly backwards, and cited. The trace shows the four chunks the search returned:

| Chunk | Says 24h | Says 48h | Says SUPERSEDED |
|---|---|---|---|
| `qc-hold-procedure.md`, lines 28 to 40 | yes | | |
| `qc-hold-procedure-2025.md`, lines 25 to 33 | | yes | |
| `qc-hold-procedure-2025.md`, lines 1 to 25 | | yes | **yes** |
| `qc-hold-procedure.md`, lines 14 to 28 | yes | yes | |

The 2025 header, with "SUPERSEDED by SOP-QC-003", *was* retrieved. What was not retrieved was the current document's header, lines 1 to 13, the only place that says `qc-hold-procedure.md` **is** SOP-QC-003. So the model had a claim that SOP-QC-003 replaced something, no way to connect SOP-QC-003 to either file, and a file with "2025 edition" in its title. It built the most plausible story from that and got it wrong. This isn't lying: a fact that exists only in a document's header is lost to every chunk that doesn't contain the header.

**The fix.** Parse the header at ingest and stamp `doc_id`, `version`, `effective` and `status` onto every chunk as metadata. Verified by scrolling Qdrant afterwards: all 21 chunks carry them, and both 2025 chunks read `superseded: by SOP-QC-003 on 2026-06-01`.

**After.** Same question, three fresh sessions (executions 83 to 85): **24 hours from `qc-hold-procedure.md`, 3 of 3.** Two of the three also said the 48 hour version is superseded; the third didn't mention it.

| | Before | After |
|---|---|---|
| Answer | 48h, stale doc presented as current | 24h, 3 of 3 |
| Prompt tokens | 2,999 | 3,200 |

The metadata costs about 7% more prompt tokens per question, because every retrieved chunk now carries four more fields.

---

## The golden set: 18 of 20

[`golden-set.json`](golden-set.json) holds twenty questions, each with an expected answer, the file or files it should cite, and strings the answer must contain. It was **reviewed by hand against the SOPs before scoring**, the same role the hand labels played in [w7](../w7-media-request-triage). Scored on two axes: is the answer right, and are the right files cited, with the superseded file never presented as current. Each question runs in a fresh session. Full replies, execution IDs and tokens are in [`golden-results.json`](golden-results.json).

| Category | Items | Both correct |
|---|---|---|
| Single fact | 11 | 11 |
| Conditional ("does a 10 second promo need captions?") | 2 | 2 |
| Contradiction (current against superseded) | 2 | 2 |
| Not covered (loudness, cloud provider) | 2 | 2 |
| Cross document | 3 | **1** |
| **Total** | **20** | **18** (answer alone: 19) |

**Every automatic miss was read by hand** before it counted:

- **Q17, the real miss.** *"A promo has been sitting in qc_hold for 5 hours. What should have happened by now?"* Right answer: it should already have been escalated, because promo holds escalate after 4 hours. The assistant said it was "still within the service level window" of 24 hours. The trace: all four retrieval slots went to QC hold chunks, **two of them to the correctly labelled superseded edition**, and the promo SOP's 4 hour rule never reached the model. So the metadata fix stops the stale doc from being *believed*, but not from taking up retrieval slots. That needs a filter at retrieval time, which is Next.

  The phone check (below) asked nearly the same thing as a follow-up, *"And for a promo?"* after the SLA question, and got it right: 4 hours, citing the promo SOP and the escalation SOP. The difference was the search query the agent wrote. For Q17 it wrote `qc_hold promo time limit deadline`, and the `qc_hold` term alone pulled four QC hold chunks. For the follow-up it wrote `promo SLA deadline turnaround time`, which retrieved the promo SOP. **Retrieval depends on how the agent phrases its search, not only on what is in the store**, so a fix that only works for one phrasing isn't a fix.
- **Q18, correct but incomplete.** Asked what happens to a 6 Mbps episode mezzanine, it said the file goes to `qc_hold` because the minimum is 8 Mbps, which is right, and cited the mezzanine spec. The key also expected the QC hold SOP (the 24 hour window, and that a spec failure can't be waived). It was left as a miss rather than loosening the key after seeing the result.
- **Q06, a scorer bug, not an answer bug.** The reply cited `[caption-requirements.md, promo-and-trailer-handling.md]`, two files in one bracket, and the first version of the scorer only read one file per bracket. Fixed, and the saved replies were re-scored without asking again.

**Cost, measured.** Tokens were read from `tokenUsage` on every LLM call in every execution and summed: 69,615 prompt and 2,770 completion across the twenty. At Haiku 4.5's $1 and $5 per million: 69,615 / 1,000,000 x $1 = $0.0696, plus 2,770 / 1,000,000 x $5 = $0.0139, **$0.083 for the set, $0.0042 a question.** Median prompt was 3,192 tokens.

**Declining was the most expensive answer.** Q19 (loudness) took 3 LLM calls and 7,722 prompt tokens, 2.4 times the median: finding nothing, the agent searched again with a different query before saying the SOPs don't cover it. It declined correctly, and its reply named what the SOPs *do* say about audio (track layout, rendition bitrates), which is a good answer. It's also the pattern to watch: a question with no answer costs the most.

**Embeddings, measured and reconciled.** OpenAI's usage page shows **12,644 input tokens** on `text-embedding-3-small` for the build: 8,360 on 9/26 UTC and 4,284 on 9/27 UTC. Every one of them is accounted for:

| UTC day | Billed | Full ingests | Left for searches | Searches that day |
|---|---|---|---|---|
| 9/26 | 8,360 | 2 x 4,167 = 8,334 | 26 | 4 (executions 81, 83 to 85) |
| 9/27 | 4,284 | 1 x 4,167 | 117 | about 24 (the golden set, one script test, the phone check) |

A full ingest is **4,167 tokens**: the text of the 21 stored chunks, counted with `tiktoken`'s `cl100k_base`, *after replacing newlines with spaces*. That last part matters. The raw chunks count 4,093, and the first reconciliation came out 174 tokens heavy on a day with only four searches. The cause is in LangChain's OpenAI embeddings class, which n8n's node uses: `stripNewLines` defaults to true, and every text is sent with `\n` replaced by a space, which tokenizes differently. The corpus files themselves are 3,997 tokens; the chunk overlap and the newline rewrite account for the rest.

At OpenAI's listed $0.02 per million tokens: 12,644 / 1,000,000 x $0.02 = **$0.00025 for everything**, $0.000083 per ingest, and about $0.0000001 per search. Every embedding in the build cost **0.3% of what the golden set alone cost in chat model calls** ($0.083); the chat model is where the money goes.

---

## Trade-offs

**Qdrant, not the in-memory store.** n8n's Simple Vector Store needs no setup and is **wiped on every container restart**. That's fine for a demo and wrong for something Project 2 builds on. Qdrant costs a second service, swap on a 1GB box, and a key. It runs idle at 46MB inside its 384MB cap. PGVector was the other option, and it was out because this instance runs on SQLite, so it would mean standing up Postgres first.

**Two model vendors.** Anthropic for answers, OpenAI for embeddings, because Anthropic has no embeddings endpoint. That's another bill and another key, and it **couples the index to one embedding model**: switching models means re-embedding everything, because vectors from two models can't be compared. OpenAI was chosen over the Gemini, Cohere and Hugging Face nodes (all available on 2.35.7) because it was the account that could be opened and billed that afternoon.

**Reset, then insert.** It makes ingest idempotent, proven: three ingests, 21 chunks each time. The cost is a window, for the length of an ingest, where the collection is empty or partial, and a question asked then gets nothing. If ingest fails halfway, it **stays** partial until the next successful run. For ten documents that window is a few seconds. For a real library, the fix is to build a new collection and switch an alias to it, which Qdrant supports; it's in Next.

**Keeping the superseded document in the index.** It would be simpler to delete it. It stays because real SOP libraries are full of old editions nobody removed, and a system that only works when the library is clean doesn't work. The metadata fix is one layer of defence. Q17 shows it isn't enough on its own.

**An agent with a search tool, not a fixed retrieve-then-answer chain.** A chain would do exactly one search per question and cost one LLM call. The agent writes its own search query, and it can search again: on Q19 it did, which is why that answer cost 2.4x. Every answer costs at least two LLM calls. It's worth it here because the agent rewords the question into a search query (*"qc_hold promo time limit deadline"*), and it's the shape Project 2 needs, where other agents call this same search over MCP.

**Top 4.** Four chunks of about 1,000 characters is enough context for any one SOP question and cheap. Q17 shows its limit: a document with two editions can fill all four slots by itself. Raising it to 6 or 8 would likely have caught the promo rule, and would make every question cost more. A reranker, or a `status` filter, fixes the cause instead.

**Temperature 0 is not determinism.** Three identical questions at temperature 0 gave two answers that mentioned the superseded version and one that didn't. The facts were identical all three times and the wording was not. A golden set run once is one sample.

**Gates on both endpoints.** Ingest is gated with a header token because it is destructive and it spends money. The chat has Basic Auth because every message spends money. Same reasoning as the [w8](../w8-ops-agent) gate.

---

## Idempotency

**Ingest twice: same collection.** Proven, not claimed: the collection holds 21 chunks after the first ingest, 21 after the second (with changed metadata) and 21 after the third (from `scripts/ingest.py`). The price is the window described in Trade-offs.

**Chat twice: same answer, same cost twice.** The chat only reads. Nothing is written, sent or charged apart from the tokens. At temperature 0 the facts repeat and the wording may not.

**Same session twice is not a fresh session.** Simple Memory keeps the last five messages per session ID and re-sends them on every call. The golden set runs each question in a new session so no answer leans on a previous one.

---

## What broke

Real failures, real error text, in the order they happened.

**1. The superseded answer.** Above, in full. It's the one that matters.

**2. SSH by hostname.** The first connection to the droplet failed:

```
Host key verification failed.
```

The droplet's host key was in `known_hosts` under its IP, not under `n8n.mariomoreno.dev`, and the non-interactive session couldn't accept a new entry. Connecting by IP worked. Leaving `BatchMode` on was the right call: a script that silently accepts a changed host key has stopped checking anything.

**3. The golden set stopped parsing after review.** Marking items reviewed by hand produced:

```
json.decoder.JSONDecodeError: Expecting value: line 10 column 44 (char 750)
```

Column 44 was the `T` in `"reviewed": True`. JSON's only literals are lowercase `true`, `false` and `null`; `True` is Python. Fixed, the next run failed further down:

```
json.decoder.JSONDecodeError: Expecting ',' delimiter: line 114 column 49 (char 5640)
```

A review note written after the value, `true (No SLA rules)`. JSON has no comments, so the notes moved into a `review_note` field rather than being deleted.

**4. The reviewer fell into the same trap as the model.** Reviewing the golden set, three items were first marked wrong: Q14, Q15 and Q16, the three whose answers depend on which QC hold edition is current. The expected answers were checked line by line against both editions and stood. The same question wording that misled the model misled the person checking it, which is the best evidence in this build that the trap is realistic rather than contrived.

**5. The scorer misread two citations as none.** Q06, above. The regex `\[([\w.-]+\.md)\]` requires the bracket to contain exactly one filename. The reply's `[caption-requirements.md, promo-and-trailer-handling.md]` matched nothing, so a correct answer scored as citing nothing. The scorer now reads every `.md` name inside any bracket.

**6. A false positive while inspecting a miss.** Checking Q17's retrieved chunks for the promo rule with `'4 hours' in chunk` flagged the current QC hold chunk. It matched the tail of **2**`4 hours`. The promo rule never arrived; a substring check on a number is not a check.

---

## Limitations

- **Twenty questions, run once.** 18 of 20 describes this set on this day. Temperature 0 did not make runs identical (Trade-offs), so a second run could move a borderline item.
- **The automatic checks are string matches.** They are a first pass. Every miss was read by hand; a pass was not, and a reply can contain the right string for the wrong reason.
- **Retrieval fails on stale editions (Q17).** The fix is known and not built.
- **The header parser defaults to `current`.** A document with no Status line, or a typo in it, is stamped current. That fails in the dangerous direction; it should be `unknown`.
- **Ten small documents is easy mode.** 15,539 characters in 21 chunks. Retrieval gets harder with every document added, and nothing here measures how.
- **Ingest is not atomic.** Reset then insert leaves an empty or partial collection during an ingest, and after a failed one.
- **Documents arrive as JSON only.** No PDF, no Drive folder, no watch for changes. Someone runs the ingest.
- **No tracing.** Tokens were read from execution records by a script. Langfuse is scheduled for Project 2.
- **The chat greets users as "Nathan".** That is n8n's default initial message on the hosted chat, never changed. Harmless, and wrong for an SOP assistant.

---

## Next

Project 2 (ships 10/10) builds on this directly:

1. **Filter out superseded chunks at retrieval** (a metadata filter on `status`), or add the Cohere reranker node that is already on this instance. Then re-run the same twenty and compare Q17.
2. **Expose `sop_search` over MCP** with the MCP Server Trigger, so Claude or any MCP client can query the SOPs as a tool. The README for that cites the NSA/CISA MCP security guidance and OWASP ASI04.
3. **Ingest by alias swap:** build `sop_corpus_<timestamp>`, then move an alias, so a question never lands on an empty collection.
4. **The parser defaults to `unknown`**, and a document with no Doc ID is refused rather than stored.
5. **The golden set grows**: a follow-up question that depends on memory ("and for a trailer?"), more cross document items since that category scored 1 of 3, and each run done three times.
6. Langfuse, wired in and left in.

---

## Verification, by named check

Following the repo's rule since 9/14: a README may claim something works only if it names the check that was run.

- **Qdrant is private:** `curl http://198.211.112.8:6333/collections` from a machine off the VPS timed out (curl exit 28).
- **Qdrant needs its key:** from inside the n8n container, `GET http://qdrant:6333/collections` returned `401 Must provide an API key or an Authorization bearer token` without the key and `200` with it.
- **n8n was not restarted** by adding Qdrant: `docker ps` still showed n8n "Up 5 days" after `docker compose up -d qdrant`.
- **Swap:** `swapon --show` lists `/swapfile`, 2G; `/etc/fstab` carries the line; `vm.swappiness` reads 10.
- **Ingest and idempotency:** three ingests through the production webhook each returned `"chunks": 21, "files": 10`.
- **Metadata on every chunk:** a Qdrant scroll of `sop_corpus` listed all 21 chunks with `doc_id`, `version`, `effective` and `status`, and both 2025 chunks as superseded.
- **Before and after:** executions 81 (wrong) and 83 to 85 (right), production mode, read back through the n8n API.
- **Golden set:** executions 86 to 105, production mode, via the Basic Auth gated chat endpoint from a machine off the VPS. Replies and token counts in `golden-results.json`.
- **Portable scripts:** `scripts/ingest.py` ran a third ingest (21 chunks) and `scripts/score.py Q03` scored one question with token counts matching the full run, both against the live instance.
- **Published version:** the export shows `versionId` equal to `activeVersionId`. The committed `workflow.json` is that export with `pinData`, `versionId`, `meta` and `staticData` removed, and it was checked by script for the ingest token and chat password before writing.
- **The phone check:** the hosted chat opened on a phone on cellular (Wi-Fi off), logged in through Basic Auth, asked `What's the SLA for clearing a QC hold?` and got 24 hours from `qc-hold-procedure.md`, with the 48 hour edition named as superseded. Follow-up in the same session, `And for a promo?`, got 4 hours from `promo-and-trailer-handling.md` and `on-call-escalation.md`. **Executions 108 and 109**, `mode: webhook`, status success, one session ID, 3,209 and 3,428 prompt tokens, read back through the n8n API.
- **Embedding tokens:** OpenAI's usage page (Usage, Embeddings, last 7 days) shows 12,644 input tokens on `text-embedding-3-small`, 8,360 on 9/26 UTC and 4,284 on 9/27 UTC. Reconciled to three ingests of 4,167 tokens plus 143 tokens of search queries, with execution timestamps placing each ingest and search on its UTC day. Price read from OpenAI's pricing page, not assumed.
