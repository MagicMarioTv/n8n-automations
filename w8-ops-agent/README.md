# w8-ops-agent: a content ops agent with tools, and what it costs

An n8n **AI Agent** behind a chat trigger, with three tools it can call on its own: a calculator for encoding math, an asset catalog API for status lookups, and a Wikipedia summary fetch for format questions. It is the first build in this repo that uses the AI Agent node rather than a chain, and the point of the build is the number that difference produces: **the same three questions cost 816 tokens through a chain and 12,011 through the agent, a 14.7x multiplier**, measured on the live instance rather than quoted from a blog post.

The catalog the agent calls is a second workflow on the same instance, a mock API with ten invented assets, real HTTP status codes, one ID that always fails and one that fails two calls out of three. That is deliberate. An agent's tools will fail in production, and this build measures what the agent does about it under three different configurations, one of which reported a server timeout to the user as a missing record.

Built and measured 2026-09-20, a day after the Saturday slot. Both workflows are live on the VPS from [w6-vps-deploy](../w6-vps-deploy).

---

## What it does

You ask a question in a chat window. The agent decides, per question, which of its tools to call, calls them, reads the results, and answers. A plain LLM chain answers from whatever is in its weights; this one can look things up and do arithmetic it would otherwise get wrong, at a cost that is measured below.

The three tools:

| Tool | What it is | Why it earns its place |
|---|---|---|
| `calculator` | n8n's built-in Calculator tool | Arithmetic is exactly what a language model gets wrong without help. A 112 minute feature at 22.7 Mbps is 152,544 megabits, and a model will confidently tell you a nearby number. |
| `asset_catalog` | HTTP Request Tool against a mock catalog API on the same instance | The "API call" from the week's brief. It returns title, duration, bitrate, platform, status and deadline for an invented asset ID, and it returns **real HTTP errors** when asked to. |
| `wiki_summary` | HTTP Request Tool against the Wikipedia REST API | The "web search" stand-in, with no API key. Started life as n8n's built-in Wikipedia tool, which failed on every call from the VPS; see What broke. |

Plus **Simple Memory** with a five message window, so "and how long does that take at 100 Mbps?" works as a follow-up. Plus a second branch, `Run Baseline`, which sends the same three questions through a Basic LLM Chain with no tools at all. That branch is the control group.

Every tool is read-only. Nothing in this build sends, writes or spends, so there is no approval gate, and the idempotency answer is short.

---

## Quick start

Two workflows. Import the catalog first, because the agent calls it.

**1. `catalog-api.json`**, the mock API.

- Import from file (not from URL; that import path is going away in n8n 3.0).
- **Publish it.** The production URL only serves once a version is published, and the agent calls the production URL. A draft serves nothing; that is the same mechanism that made w7's form return 404 for eight days.
- Check: `https://<your-instance>/webhook/asset-catalog?id=TT-0142` returns JSON with `Harbor Lights S02E07`. `?id=TT-9999` returns `{"error":"asset not found"}` with HTTP 404.

**2. `workflow.json`**, the agent.

- Import from file. Select your Anthropic credential on both `Anthropic Chat Model` nodes.
- On `asset_catalog`, change the URL's hostname to your instance if it is not `n8n.mariomoreno.dev`.
- `When chat message received` is committed with **Make Chat Publicly Available off** and **Authentication** `none`. That is deliberate: the build was measured by posting to the public endpoint from a script, and the endpoint was closed again afterwards. To use the hosted chat page, set Authentication to **Basic Auth** with a credential first, then turn public on. A public form costs nothing when strangers find it; a public agent costs tokens per message.
- Publish. Open the chat from the editor (or the public URL once gated). Ask: `What is the status and deadline of TT-0142?`

**3. The baseline**, optional: `GET https://<your-instance>/webhook/ops-agent-baseline` runs the three questions through the no-tools chain. The response carries the first answer; all three are in the execution record.

The ten asset IDs in the catalog: `TT-0142`, `TT-0217`, `TT-0288`, `TT-0301`, `TT-0356`, `TT-0410`, `TT-0477`, `TT-0503`, `TT-0619`, `TT-0731`. Two special ones: `TT-0500` always returns HTTP 500, and `TT-0503` returns HTTP 503 on two calls out of every three, then succeeds on the third.

The whole build was driven through the n8n public API rather than the canvas: both workflows created with `POST /api/v1/workflows`, activated with `POST /workflows/{id}/activate`, updated in place with `PUT` between experiments. Nine versions of the agent were published that way in one evening, and the export confirms `versionId` equals `activeVersionId`, so what is committed is what is serving.

---

## How it works

### The catalog API (`catalog-api.json`)

```
Catalog Request (Webhook, GET /asset-catalog)
   -> Look Up Asset (Code)
   -> Send Response (Respond to Webhook, status code from the data)
```

| Node | What it does | Why |
|---|---|---|
| **Catalog Request** | Webhook, GET, respond via a Respond node | The agent's HTTP tool needs a real URL that returns real status codes, and n8n can be that URL. Same pattern as [w2-webhook-http](../w2-webhook-http). |
| **Look Up Asset** | Code node holding a ten row catalog, returns `{ status, body }` | The catalog lives in code rather than a Sheet so the repo is self-contained and nothing real is ever in it. The node decides the status code: 400 with no `id`, 404 when the ID is not in the catalog, 500 for `TT-0500`, 503 two calls out of three for `TT-0503`, 200 otherwise. |
| **Send Response** | Respond to Webhook, `responseCode: {{ $json.status }}` | The status code is an expression on the data, so one Respond node covers every branch. An HTTP tool that only ever saw 200s would teach nothing about error handling. |

The 503 counter uses `$getWorkflowStaticData('global')`, which persists only across **production** executions of an active workflow. Calling the test URL from the editor would never advance it. That was verified from outside: four calls to the production URL returned 503, 503, 200, 503, with `attempt` counting 1 through 4.

### The agent (`workflow.json`)

```
When chat message received (Chat Trigger)
   -> Ops Agent (AI Agent)
         |-- Anthropic Chat Model (Haiku 4.5)     ai_languageModel
         |-- Simple Memory (window 5)             ai_memory
         |-- calculator                           ai_tool
         |-- asset_catalog (HTTP Request Tool)    ai_tool
         |-- wiki_summary  (HTTP Request Tool)    ai_tool

Run Baseline (Webhook) -> Baseline Questions (Code) -> Answer Without Tools (Basic LLM Chain)
                                                             |-- Anthropic Chat Model (baseline)
```

The connections under the agent are not `main`. They are `ai_languageModel`, `ai_memory` and `ai_tool`, and that is the whole difference between this build and the six before it: data does not flow *through* the model and the tools, the agent *reaches for* them, as many times as it decides to, until it has an answer or hits the iteration cap.

| Node | What it does | Why |
|---|---|---|
| **When chat message received** | Chat Trigger, public, hosted chat | The production chat endpoint is a webhook like any other: `POST /webhook/<id>/chat` with `{ action, chatInput, sessionId }`. That is how every run in this README was made, from a script on a different network from the VPS. |
| **Ops Agent** | AI Agent v2, `maxIterations: 6`, `returnIntermediateSteps: true` | Six iterations because the hardest reasonable question here is one lookup plus three calculations plus an answer, and six leaves room for one retry. `returnIntermediateSteps` puts every tool call and its result into the output. It costs no tokens and it is how every finding below was found. |
| **Anthropic Chat Model** | `claude-haiku-4-5`, default options | Same model and credential as w7. Haiku supports tool use, and at $1/$5 per million tokens the agent's multiplier stays under a cent per question. |
| **Simple Memory** | Buffer window, 5 messages, keyed on `sessionId` | Without it, "and how long does that take?" has no antecedent. With it, the last five turns are re-sent on every LLM call, which is part of why prompts grow. |
| **calculator** | Built-in tool | The system prompt tells the model to use it for every arithmetic step. It mostly does. The exception is the most interesting failure in this build. |
| **asset_catalog** | HTTP Request Tool, `GET .../webhook/asset-catalog?id={{ $fromAI('asset_id') }}`, retry 3x, On Error: continue | `$fromAI()` is the mechanism worth understanding: the model fills that parameter in, guided by the description string, and n8n makes the call. The retry and On Error settings are the subject of the Trade-offs section. |
| **wiki_summary** | HTTP Request Tool, `GET en.wikipedia.org/api/rest_v1/page/summary/{{ $fromAI('title') }}`, sends a `User-Agent` header, On Error: continue | Replaced the built-in Wikipedia tool after it failed silently on every call. Being an HTTP Request Tool means its errors reach the model; the built-in tool's did not. |
| **Run Baseline** → **Answer Without Tools** | Webhook → Code with three questions → Basic LLM Chain, same model, same conventions, no tools | The control. Without it the multiplier is a number from a blog post. With it, the multiplier is a measurement on this workflow, this model, these questions. |

The system prompt is in the `Ops Agent` node. The load-bearing lines: use the calculator for every arithmetic step; use the catalog for any `TT-NNNN`; on a 503 from the catalog, call it again up to two more times; on any other error, quote the exact error text and stop; never suggest a similar ID.

---

## The number: agent versus chain

Three questions, each sent once through the chain and once through the agent in a fresh session. Tokens are read from `tokenUsage` on each LLM call in the execution record and summed. Haiku 4.5 at $1 per million input and $5 per million output.

| Question | Chain tokens | Chain $ | Agent LLM calls | Tool calls | Agent tokens (in + out) | Agent $ | Multiplier |
|---|---|---|---|---|---|---|---|
| Q1: 1h52m feature at 22.7 Mbps, size in GB and transfer at 185 Mbps | 319 | $0.00088 | 2 | 7 | 2,927 + 454 = 3,381 | $0.00520 | **10.6x** |
| Q2: status, deadline and platform of TT-0142 | 247 | $0.00062 | 2 | 1 | 2,517 + 112 = 2,629 | $0.00308 | **10.6x** |
| Q3: transfer time for TT-0142's mezzanine at 150 Mbps | 250 | $0.00062 | 4 | 4 | 5,652 + 349 = 6,001 | $0.00740 | **24.0x** |
| **Total** | **816** | **$0.00212** | | | **12,011** | **$0.01567** | **14.7x** |

Arithmetic for Q3, the expensive one: 5,652 / 1,000,000 x $1 = $0.005652, plus 349 / 1,000,000 x $5 = $0.001745, which is $0.0074 for one question.

**What the multiplier bought.** On Q1 the chain got the right answer without any tool (19.0 GB, 13.7 minutes; the agent said 19.1 GB, which is the correctly rounded value of 19.068). On Q2 and Q3 the chain said, honestly, that it had no access to asset data and could not answer. It did not invent an asset, which is to Haiku 4.5's credit and is not something to rely on. So on these three questions the agent's 14.7x bought **capability** (two questions the chain could not answer at all) rather than accuracy. The calculator's value shows up in What broke, not in this table.

**Where the tokens go.** Q3's four LLM calls had prompt sizes of 1,194, 1,344, 1,517 and 1,597. Every call re-sends the system prompt, the tool definitions, the memory window and every tool result so far. Of Q3's 6,001 tokens, 5,652 were input. The agent's cost is dominated by re-reading its own context, and it grows with every tool call. That is the mechanism behind the "5 to 30x" figure, and it is why an agent is the wrong shape for anything a chain can do in one pass.

**Why the same question twice varies.** Q1 made seven calculator calls in **two** LLM calls: the model emitted all seven in one turn. Q3 made four tool calls in **four** LLM calls: one per turn. The difference is where the numbers came from. In Q1 they were in the question, so the model could write all seven inputs up front. In Q3 the duration and bitrate had to come back from the catalog first. Same agent, same prompt, twice the calls, and the cost follows.

---

## Trade-offs

**Agent or chain.** The measured answer is above: 10.6x to 24x per question here. w4 and w7 used chains because one prompt in, one structured answer out, is all they needed, and that decision was right. This build uses an agent because the question decides which tool to call, and no chain can do that. The rule that falls out: reach for an agent when the *routing* is the problem, and pay for it knowingly.

**Tool errors: three configurations, all measured.** This is the most useful table in the README.

| Config | `asset_catalog` settings | TT-0503 (503, flaky) | TT-0500 (500, permanent) | Cost of the 503 case |
|---|---|---|---|---|
| **A** | Retry 3x, On Error: stop | Node retried, second try succeeded, correct answer | **Wrong answer:** "This asset ID does not exist in the catalog" | 2,595 tokens |
| **B** | Retry 3x, On Error: continue | No retry fired; user told `503 - MAM busy, retry later` | Correct: quotes `500 - upstream MAM timeout`, tells the user to retry | 3,691 tokens |
| **C** (shipped) | B, plus the system prompt says retry a 503 up to two more times | Model called the tool again, second call succeeded, correct answer | Correct, as B | 6,363 tokens |

Config A is the one you get by ticking "Retry On Fail" and stopping there. The retries work (the 503 recovered on the node's second try, and the user never knew), but when retries are exhausted the tool fails, the agent gets an **empty observation**, and the model guesses. For the 500 it guessed "does not exist", which is a wrong answer delivered confidently, and the real error text (`upstream MAM timeout`) was sitting in the execution log the whole time where the model could not see it.

Config B fixes the blindness: with On Error set to continue, the tool hands the error back as data and the model quotes it. But **On Error: continue switches the retries off**. One run, 320 ms, against three runs 1.2 seconds apart in config A. Node settings alone give you either retries or the error text, not both.

Config C gets both by moving the retry into the prompt, and the price is exactly what the reliability track predicts: a retry is plumbing, and asking the model to do plumbing cost 6,363 tokens where the node did the same retry for 2,595. Each model-driven attempt is a full LLM call with the previous error object in context. It ships because it is the only one of the three that is honest and self-healing with no new nodes, and because the number that justifies replacing it is now in this table. The replacement is in Next.

**Retries on a 404.** In config A the node retried the 404 three times too. A not-found does not become found on the third try, and every retry is a call against the upstream API. Node-level retry has no idea which errors are transient. A real integration classifies before retrying: 5xx and timeouts yes, 4xx no. That classification belongs in a sub-workflow wrapper, not in the model.

**The chat gate.** w7's form is public with no auth because strangers submitting requests is what an intake form is for. This agent is different: every message costs money and any tool it has can be driven by whoever types. The committed trigger has `authentication: none` because the build was tested by script; Basic Auth is one dropdown away and is the minimum before leaving it up. The general rule: a public surface that spends per request needs a gate, and the cheapest gate is the right one until it isn't.

**`maxIterations: 6`.** The cap is a cost ceiling, not a feature. Each iteration here is roughly 1,300 to 2,500 prompt tokens, so the worst case per message is about 15,000 tokens, or two cents. Without a cap, a model that keeps calling a failing tool is an open loop on your API bill. What happens at the cap was tested, not assumed, by setting it to 1 and asking the four-turn question: the agent answered with the literal string `Agent stopped due to max iterations.`, HTTP 200, execution status **success**. It did not return what it had (the catalog result was already in hand). So the cap protects the bill and nothing else: the user gets a non-answer, and monitoring sees a green run. Anything downstream of this agent has to check the output text for that sentence, because nothing else flags it.

**Memory window of 5.** Follow-ups work. The cost is that the whole window is re-sent on every LLM call in every subsequent message, so a long session gets more expensive per message, not less. Five is enough for "and at 100 Mbps?" and not enough to make the tenth message cost triple.

**A mock catalog, on the same instance.** The alternative was a real public API, and every one of those either needs a key, returns only 200s, or both. The mock returns whatever status the build needs, lives in the repo, holds nothing real, and can be broken on purpose. The static data counter is the only state in the build, and it is the mock's.

**`returnIntermediateSteps: true`.** On by default here and it should be on everywhere. It puts every tool call, its input and its observation into the agent's output. It costs zero tokens (it is n8n recording what already happened) and it is the reason the empty observation in config A was visible at all.

---

## Idempotency

**Ask the same question twice: nothing bad, same cost twice.** All three tools are read-only. There is no row to duplicate, no message to double-send, no charge to repeat. A replayed question spends tokens again and changes nothing.

**Same `sessionId` twice is not the same as a fresh session.** Memory appends. The second time a message arrives with a session ID the model already has history for, it answers with the previous exchange in context. That is the feature, and it means a chat session is stateful even though the tools are not. The measured runs above used a fresh session per question for that reason.

**The catalog's 503 counter is the one piece of state, and it is deliberately not idempotent.** Same ID, different answer, by design, because the whole point is a failure that clears on retry. It lives in workflow static data and is the mock's problem, not the agent's.

**The baseline webhook** runs three LLM calls per hit and writes nothing. Hitting it twice costs $0.004.

---

## What broke

Real failures, real error text, in the order they happened.

**1. The agent reported a 500 as a missing record.** With Retry On Fail and the default On Error, asking about `TT-0500` produced this in the execution log:

```
NodeOperationError: The service was not able to process your request
Details: upstream MAM timeout
```

three times, 1.2 seconds apart. And this in the chat:

> The asset catalog returned no results for TT-0500. This asset ID does not exist in the catalog. Please verify the asset ID (format TT-NNNN) and try again.

The trace shows why: `observation: ""`. The tool's error never reached the model, so it invented the most plausible reason for an empty result. The system prompt said "quote the exact error text and stop", and the model could not comply with an instruction about text it never saw. Fix: On Error set to continue (regular output). After that: *"The asset catalog returned an error: `500 - upstream MAM timeout` for asset TT-0500."* Correct, and a different answer from the 404 case, which now reads *"The system returned: "asset not found"."*

**2. Retries stopped when the error became visible.** The fix for (1) turned off the retries, measured as one run of 320 ms against three runs before. `TT-0503` went from "recovered silently on the second try" to `503 - MAM busy, retry later` delivered to the user. Documented in Trade-offs, worked around in the prompt, properly fixed in Next.

**3. `134.4 seconds = 13.4 minutes`, three times out of three.** A two-message session: first "What is the duration and mezzanine bitrate of TT-0731?" (28 minutes, 8 Mbps, correct, memory then holds them), then "And how many minutes does that take to transfer at 100 Mbps?" The model called the calculator with `28 * 60 * 8 / 100`, got `134.4`, and answered:

> **13.4 minutes** (or 804 seconds)

134.4 seconds is 2.2 minutes. The model did the last step in its head, dropped a digit, and then fabricated "804 seconds" to match its wrong minutes figure. Reproduced in a second fresh session, identically. Then the system prompt got an explicit rule: *"Every unit conversion is its own calculator call, including seconds to minutes. Never convert units in your head."* Third run, rule in context, same wrong answer, and this time the model's own formula line said "then divide by 60 for minutes" and it still did not. The rule was reverted because it changed nothing but the token count.

What makes it worth a paragraph: Q3 in the main table asked "how long" and got `150.4 seconds (2.5 minutes)`, which is right. The difference is that Q3 reported the tool's unit first and converted as an aside; the follow-up demanded minutes, the tool returned seconds, and the conversion between the two is where it broke. A prompt rule did not fix a mechanical error, which is the same finding as w7's `low` urgency definition: the model follows the semantics of the question over the mechanics of the rule. The structural fix is a tool that returns the answer in the unit asked for, so there is nothing left to convert.

**4. The batch that pre-computed its own inputs.** Q1's seven calculator calls arrived in a single LLM turn. Look at the inputs: `1*60 + 52`, then `112 * 60`, then `6720 * 22.7`, then `152544 / 8`. The model could only write `112 * 60` before seeing the result of `1*60 + 52` if it had already done that sum itself. The calculator confirmed the model's arithmetic; it did not perform it. The tell is the last call: `824.3 / 60`, where the previous observation was `824.5621`. A transcription drift that did not change the rounded answer this time. The same behaviour with worse luck is finding 3.

**5. The built-in Wikipedia tool failed on every call and the model answered anyway.**

```
NodeOperationError: Network response was not ok
```

on both lookups (`HEVC codec`, `AV1 codec`), `observation: ""`, and then a fluent, roughly accurate, completely unsourced answer with no indication that the source was never consulted. Setting On Error to continue on that node did **nothing**: the LangChain-native tool nodes (`toolWikipedia`, and presumably its siblings) do not honour the setting that the HTTP Request Tool does. Replaced with an HTTP Request Tool against `en.wikipedia.org/api/rest_v1/page/summary/{title}` sending a `User-Agent` header. Both lookups then returned real article summaries from the VPS. Working hypothesis, not verified: Wikimedia refuses anonymous requests from cloud IP ranges, and the built-in tool sends none. The lesson that is verified: a tool whose failures are invisible to the model is worse than no tool, because the model fills the gap and the user cannot tell.

**6. The baseline webhook returned one answer, not three.** `Respond: last node` returns the first item by default. All three answers were in the execution record, which is where the numbers in this README came from anyway. Not fixed, because the execution record is the right source.

**7. Hitting the iteration cap is a success.** With `maxIterations` set to 1 for the test, the lookup-plus-math question produced one LLM call, one catalog call, and this as the agent's entire output:

```
Agent stopped due to max iterations.
```

Execution status `success`, HTTP 200 to the caller. The first draft of this README said the agent "returns what it has" at the cap. It does not, and that sentence was written before the cap had ever been hit, which is exactly the kind of claim the Verification section below exists to prevent. Cap restored to 6 afterwards.

---

## Limitations

- **Three questions is a smoke test, not a golden set.** w7 had fifteen hand-labeled items and a scorer. This build has three questions and the answers were checked by hand. The 14.7x figure is real for these three; it is not a property of the agent in general.
- **The unit conversion bug is unpatched.** Any question that demands minutes when the natural computation is in seconds is at risk. Three of three failed. The fix is a tool, not a prompt, and it is not built yet.
- **Retry lives in the prompt**, which is the wrong layer and costs 2.5x. Documented, measured, not yet moved.
- **Default temperature.** The Anthropic node runs at its default rather than 0. Fine for a chat; wrong for an eval, and it is one reason three runs of the same question can differ.
- **Wikipedia summaries are verbose.** Each one arrives as a full JSON object with HTML in it, about a thousand tokens. The HTTP Request Tool has an Optimize Response option that would cut that to the `extract` field.
- **No tracing.** Token counts were read out of execution records by a script. Langfuse is the reliability track's answer and it is scheduled for Project 2, not retrofitted here.
- **The catalog has ten rows and lives in a Code node.** It is a fixture, not a system. That is the right size for the build and would be the wrong size for anything else.
- **Single instance, single user.** Memory is keyed on the session ID the chat widget generates. Two people in one session would share a history.

---

## Next

Week 10 (9/26) is RAG: documents into a vector store, questions answered with citations. That is the other half of what Project 2 needs. Carried from this build:

1. **A sub-workflow tool for the catalog.** An Execute Workflow trigger, an HTTP Request node with Retry On Fail and On Error: continue, and a Code node that returns `{ ok, status, error }` compact. Node-level retries and a visible, short error, in one tool, and it retires the prompt-driven retry with its 2.5x cost. It also gets to classify: retry 5xx, do not retry 4xx.
2. **A `transfer_time` tool** that takes duration, bitrate and link speed and returns seconds *and* minutes. Removes the conversion step the model gets wrong.
3. **Optimize Response on `wiki_summary`**, extract only.
4. **A twenty question golden set** for the agent, scored the way w7's fifteen were, at temperature 0.
5. Langfuse, in Project 2, and left in.

---

## Verification, by named check

Following the rule this repo adopted on 9/14: a README may claim something works only if it names the check that was run.

- **Catalog production URL:** `curl` from a network other than the VPS's, `?id=TT-0142` 200, `?id=tt-0217` 200 (case insensitive), `?id=TT-9999` 404, no `id` 400, `?id=TT-0500` 500, `?id=TT-0503` four times: 503, 503, 200, 503.
- **Agent production endpoint:** `POST /webhook/<id>/chat` from a script on a different network, executions 37 through 73 in `webhook` (production) mode, all `success`, outputs as quoted above.
- **Published version:** export shows `versionId` equal to `activeVersionId` on both workflows, agent version counter 7.
- **Committed files:** exported from the instance after the last change, `pinData`, `versionId`, `meta.instanceId` and `staticData` stripped, checked by script before writing.
- **Iteration cap:** `maxIterations` set to 1 through the API, the four-turn question asked, output `Agent stopped due to max iterations.` with execution status success, cap set back to 6, export confirms 6.
- **End state of the instance, 2026-09-20:** the chat trigger is **not public** (a POST to the production chat endpoint returns 404, checked), the catalog is still live (200, checked), `versionId` equals `activeVersionId`, version counter 9. The committed `workflow.json` is that export.
- **Not yet verified:** the hosted chat page opened from a phone with Basic Auth on. That is the remaining manual step and it is not claimed here.
