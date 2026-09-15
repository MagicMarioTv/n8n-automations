# w7-media-request-triage

**Project 1.** A public intake form for media operations requests, classified by an LLM into a work type and an urgency level, held at a human approval gate in Slack, and written to a queue only once a person has said yes.

The build shipped **2026-09-14**, two days after the 2026-09-12 target, and the slip is recorded rather than smoothed over: the Saturday build block did not run, and the week that contained it produced no commits at all. Two of the project's five definition-of-done items, a walkthrough video and a written post, are still outstanding and are listed under Next. The code is finished; the project is not closed by its own definition.

Two findings carry this build, and neither is the accuracy number.

**The classifier states a rule and violates it in the same sentence, and it does so on live traffic.** The eval surfaced it first. Then three real form submissions, written by nobody with a test set in mind, produced the identical false statement. That moves the finding from "a property of my fifteen items" to "a property of this classifier."

**Four bugs in one session were all the same habit.** A name written down in one place and retyped somewhere else. Every one of them failed silently or near-silently, including a public form URL that had been recorded as working for eight days and had never once served a page.

---

## What it does

A requester fills in a form: who they are, the title or asset ID, the platform, whether the title is already live, when they need it, and what is wrong. A single LLM call classifies the request into one of five work types and one of three urgency levels, and returns a one-line summary plus a sentence of reasoning.

That classification is posted to Slack with approve and decline buttons, and **the workflow stops there**. On approve, a row lands in a Google Sheets queue. On decline, a note posts back to Slack and nothing is written anywhere.

The same classifier is wired to a second entry point, a 15-item labeled test set, so the thing being measured is exactly the thing that runs in production. One prompt, one schema, one chain, two ways in.

---

## Quick start

You need a running n8n instance reachable over HTTPS (this runs on a VPS at `n8n.mariomoreno.dev`, built in [w6-vps-deploy](../w6-vps-deploy)), plus three credentials.

1. Import `workflow.json` (⋯ → Import from File).
2. **Anthropic:** open **Anthropic Chat Model** and select your own credential. The credential ID in the export will not resolve on your instance.
3. **Slack:** an app in a workspace you own. This is the fiddliest step and every part of it fails silently, so all five:
   - Bot scopes `chat:write`, `chat:write.public`, `users:read`, `users:read.email`. The second lets the bot post to a channel it was never invited to, without which you get `not_in_channel`. The last two resolve who approved.
   - **Reinstall to Workspace** after adding scopes. Scopes added post-install do nothing until you reinstall, and the symptom is missing output fields rather than an error.
   - **Socket Mode off.** If it is on, Slack hides the Request URL field entirely and tells you that you do not need one. You do: Socket Mode is the workaround for apps that cannot receive inbound traffic, and this one can.
   - **Interactivity & Shortcuts** on, Request URL `https://<your-host>/webhook-waiting-slack`. One fixed endpoint per instance, not per node. Slack permits one Request URL per app.
   - The app's **Signing Secret** (Basic Information) pasted into the **Signature Secret** field of the n8n Slack credential. Without it n8n rejects Slack's callback as unverified and the workflow waits forever with nothing logged.
4. **Google Sheets:** enable **both** the Google Sheets API *and* the Google Drive API in your Cloud project. Sheets is for reading and writing cells; Drive is what populates the document picker. Enabling only Sheets gives you a `403 Forbidden` on a dropdown that has not touched your data yet. If you would rather not grant Drive at all, switch the Document field to **By URL** and paste the spreadsheet link.
5. Create the destination sheet with this header row: `timestamp`, `requester`, `asset_id`, `platform`, `request_type`, `urgency`, `summary`, `approved_by`, `approved_at`. Then open **Append to Queue** and pick your own document from the dropdown: the committed `documentId` is the literal string `REPLACE_WITH_YOUR_SPREADSHEET_ID`, scrubbed deliberately because the real one points at a private file in a private Drive. The generator fails the build if it ever reappears.
6. **Run the eval:** click **Run Eval** → Execute step. Fifteen classifications, scored against the labels, in about a minute. Touches no credential but Anthropic.
7. **Run the form:** publish the workflow, then open `https://<your-host>/form/media-request`.

Step 7 says **publish**, not save. This n8n publishes a *version*: edits to the canvas change a draft, and a draft serves no traffic. A workflow can read "Published" in green while serving a version that predates the node you just added. That distinction cost this build eight days of a dead form URL.

`test-set.json` is the same 15 items in plain JSON, derived from the workflow so the two cannot drift.

---

## How it works

```
 PATH A                                  PATH B
 Media Request Form                      Run Eval
 public form, no auth                        |
        |                                Test Set        15 hand-labeled items
        |                                    |
        +-----------------+------------------+
                          |
                 Normalize Request           one shape for two very different inputs
                          |
                 Classify Request            Haiku 4.5, JSON Schema with enums
                          |
                 Route By Source             $('Media Request Form').isExecuted
                          |
             +-- true ----+---- false --+
             |                          |
    Flatten For Approval        Score Against Labels
             |
     Request Approval                   Slack, send and wait, execution parks here
             |
         Approved?                      $json.data.approved
             |
      +- true +- false -+
      |                 |
 Append to Queue   Post Denial Note
 Google Sheets        Slack
```

| Node | What it does | Why |
|---|---|---|
| **Media Request Form** | Form Trigger, path `media-request`, auth None, responds on submit | The path is set under the node's **Options → Form Path**, not in the main parameters. Left unset, n8n serves the form at its webhook UUID instead, which is a URL you would not put on a résumé. |
| **Run Eval** | Manual trigger | Second entry point into the same classifier. One execution fires one trigger, so the two paths never run together. |
| **Test Set** | Code node holding the 15 labeled requests | Makes the test set a permanent, re-runnable artifact rather than fifteen tedious form submissions that leave nothing behind. |
| **Normalize Request** | Set node mapping both inputs onto one shape | The form emits keys named after field *labels* (`Your name`); the test set emits slugs (`name`). `{{ $json['Your name'] \|\| $json.name }}` serves both, so there is exactly one prompt to maintain. Also injects `reference_date`. |
| **Classify Request** | Basic LLM Chain, `claude-haiku-4-5` | Closed-set classification with definitions supplied. At $1/$5 per million tokens it is roughly a fifth the cost of the Opus tier, and the eval exists precisely so upgrading is a one-line change with a number attached. |
| **Structured Output Parser** | JSON Schema with `enum` on both classification fields | Enforced as a tool definition, not requested in prose. `request_type` is structurally incapable of returning anything outside the five values. |
| **Route By Source** | IF node on `{{ $('Media Request Form').isExecuted }}` | Splits the paths back apart so only real submissions reach Slack. This asks a question about the *run*, not about the item, so it never touches paired-item tracking. The obvious alternative, testing a field on the item, has to trace each item back through the AI chain, and `Score Against Labels` already carries a fallback for that going wrong. |
| **Flatten For Approval** | Set node, twelve fields, one item | The LLM chain emits `{output: {...}}` and **discards its input**. After classification the requester's name no longer exists on the item. This node reaches back to `Normalize Request` once and produces a flat item, so nothing downstream has to reach through the chain twice. |
| **Request Approval** | Slack, Send and Wait for Response, approve and decline, `captureResponder` on | The execution parks here indefinitely. Slack posts the decision back to `/webhook-waiting-slack` on this instance and signs it, so the approval carries a verified identity. Both directions of that need a real domain, real TLS and `N8N_WEBHOOK_URL`, which makes this [w6-vps-deploy](../w6-vps-deploy) paying off twice: the gate is unbuildable on localhost, and so is the thing that authenticates it. |
| **Approved?** | IF node on `{{ $json.data.approved }}`, Boolean is true | A real boolean, not the string `"true"`. Verified by reading the node's output rather than trusting the docs. |
| **Append to Queue** | Google Sheets, Append Row | Eight of its nine values reach back to `Flatten For Approval`; only `approved_at` reads `$json`, because the Slack node emits the decision and nothing else. |
| **Post Denial Note** | Slack, Send a message | Same split for the same reason. A denial writes nothing and says so out loud, which is the point of having a gate. |
| **Score Against Labels** | Code node comparing output to the labels | Reports type accuracy, urgency accuracy, and exact match separately, plus how many items it could not score. |

### Three design decisions worth naming

**The form collects facts; the model supplies judgment.** Requester, title, platform and live status arrive already structured, so the model never re-extracts them. Asking an LLM to pull a value out of a field you already have as a field is paying money to introduce errors.

**`reference_date` is injected, and pinned per test item.** The urgency rules talk about deadlines "within 24 hours." A language model has no idea what day it is. Without a supplied date the arithmetic is guesswork; with a *pinned* date per test item, the correct label does not drift as real time passes. A test set that scores differently on Tuesday than on Saturday is not a test set.

**One node holds the whole request.** `Flatten For Approval` exists because two separate nodes in this workflow throw their input away: the LLM chain, and the Slack approval node. Without it, the Sheets row and the denial note would each have to reach backwards independently, and every one of those reaches is a node name typed by hand. Given what went wrong in this build, reducing the number of hand-typed node references from about twenty to about ten was worth a node.

---

## The measurement

Fifteen requests, labeled by hand before the classifier was run, by someone who does this triage as day work. All names, titles, asset IDs and ticket numbers are invented; the vocabulary and the failure modes are not.

Label distribution: `redelivery_fix` 4, `metadata_correction` 4, `caption_subtitle` 3, `new_delivery` 3, `qc_escalation` 1. Urgency: `low` 7, `urgent` 6, `standard` 2.

### v1: the guide's urgency definitions

| Metric | Result |
|---|---|
| Type accuracy | 13/15 (86.7%) |
| Urgency accuracy | 8/13 (61.5%), two items had no committed label |

**Every single urgency miss was the same disagreement:** the operator said `low`, the model said `standard`. Five for five, no exceptions.

The cause was a definition gap, not a model error. The prompt said `standard` meant "a deadline more than 24 hours out," so a 13-day deadline was `standard` by definition. There was no rule in that prompt that could ever produce `low` for a dated request. **The operator's real rubric has a 72-hour boundary the prompt did not encode.** The model applied the definitions it was given, correctly, five times out of five.

### v2: definitions rewritten from the operator's rubric

| Metric | Result |
|---|---|
| Type accuracy | 12/15 (80%) |
| Urgency accuracy | 11/15 (73.3%) |
| Exact match | 9/15 (60%) |

**These numbers are measured on the same 15 items that produced the fix.** There is no holdout. They demonstrate that the definitions now match the operator; they do not demonstrate that the classifier generalizes. Reported as such deliberately.

### What actually caused the improvement, and it is not the prompt

Comparing the two runs item by item:

```
model changed its urgency answer on: [8]   (1 of 15 items)
```

| Item | What happened |
|---|---|
| 4, 13 | "Fixed" because the label moved to `standard`. **The model never changed its answer.** |
| 2, 8 | Not scored in v1, no committed label |
| 3 | **Regressed.** Label moved to `low`; model still says `standard` |
| 8 | The single genuine prompt-driven fix |

So the headline number rose from 61.5% to 73.3%, and almost none of that is the rewrite working. **The rewritten definitions moved one answer out of fifteen.** Without the item-by-item comparison, this build would have reported a 12-point improvement it did not earn.

**Two caveats that keep this comparison honest.**

Items 4 and 13 had their `reference_date` changed between runs, so their inputs are not the same question. The only clean comparison is the **13 items whose input was identical**, and on those, type accuracy is **11/13 in both runs, unchanged**. Item 4's type flip (`caption_subtitle` to `qc_escalation`) is the reason the v2 headline reads 12/15 rather than 13/15, and it cannot be attributed to the prompt, because its input moved at the same time. That is a flaw in the run design, not a finding.

And `standard` was never actually *tested* by the rewrite. The two items now labeled `standard` were answered `standard` by the model in v1 as well. The middle tier is not something the new definitions produced, it is the value the model already over-applies.

### The `low` refusal, and why it is now a stronger claim

Its own reasoning field, from the eval, verbatim:

```
...the deadline of 2026-09-22 is 10 days away, falling within 24-72 hours
classification for standard urgency.
```

Ten days is not within 24 to 72 hours. It states the rule and violates it in the same sentence.

Until 2026-09-14 that finding rested entirely on fifteen items written by the person who then went looking for the failure, which is always open to the objection that the test set caused it. Then the day 2 build put real submissions through the same classifier:

```
Title not yet live requiring complete encode and delivery of source video with
audio and captions; deadline 2026-09-18 is 4 days away, falling within 24-72
hour standard window.
```

Ninety-six hours, described as inside a seventy-two hour window. **Three times, on three separate live submissions, none written as a test case.** Same shape as the eval: the arithmetic is stated correctly and the conclusion contradicts it.

The fault is in the definition:

```
low: a stated deadline more than 72 hours away, or no deadline at all -- cleanup,
housekeeping, or a cosmetic issue on a title that is otherwise playing correctly
```

That is a **mechanical** criterion and a **semantic** one sharing a single enum value. A ten-episode season delivery does not *feel* like housekeeping, so the model declines `low` regardless of the arithmetic. **Given a rule and a vibe for the same label, it follows the vibe.** Splitting the mechanical case from the semantic one is the v3 experiment, and it is now testable against live traffic as well as the eval.

None of this would be visible without the `reasoning` field. It costs about $0.0001 per call.

### Cost

**Measured:** one clean eval execution, 15 classifications, **13,933 total tokens**. n8n's Logs panel totals the AI call tree at its root, which is the fast way to read it.

Three single-classification executions from the day 2 build read **905**, **908** and **910** tokens. The eval average is 13,933 / 15 = **929**. Those corroborate the total from a completely separate code path, which is worth more than a third decimal place would be.

**Measured exemplar** (item 1, from `tokenUsage` on its `Anthropic Chat Model` call):

| | Tokens |
|---|---:|
| `promptTokens` | 798 |
| `completionTokens` | 93 |
| **Total** | **891** |

Input is **89.6%** of that call. Applying the same ratio to the run:

```
~12,479 input  / 1,000,000 x $1 = $0.012479
~1,454  output / 1,000,000 x $5 = $0.007271
                                  = $0.01975 per run of 15
                                  = $0.00132 per classification
```

⏳ **The input/output split is still measured on 1 call of 15 and extrapolated.** The grand total is exact and now corroborated by three independent single-call totals, so the extrapolation only affects how that total divides between input and output, not its size. The exact figure lands by reading `tokenUsage` on all fifteen. Flagged rather than presented as a full measurement.

**Roughly 28% more expensive per item than [w4-ai-email-digest](../w4-ai-email-digest)** at $0.00103/email, and the reason is worth stating, because it is the same lesson escalating.

Item 1's variable content (requester, platform, live flag, and a 30-word request) is about 60 tokens. **The other ~738 input tokens are the prompt and schema**, which means roughly **92% of the input cost is fixed overhead paid identically on every call**, before a single word of the actual request. Week 4 measured about 58% on the same axis. The taxonomy bought that increase: five work types with written definitions, three urgency tiers, a tiebreaker rule, and a four-field JSON Schema all ride along on every call.

**The operational consequence:** cost scales with *item count*, not with request length. A verbose request costs barely more than a terse one. That makes batching the obvious lever at volume, and it means the honest way to cut cost is to shorten the prompt, not to ask requesters to write less.

The approval gate and the queue add **zero** model cost. Slack and Sheets calls are free at this volume, and the human is the expensive part.

---

## Trade-offs

**A public form with no authentication.** The definition of done requires a live URL a stranger can use, and auth would defeat that. The cost is that anyone who finds the URL can submit, and every submission costs an API call and a Slack message. Acceptable for a portfolio demo; production needs a rate limit and a captcha at minimum. The form carries a visible warning not to enter real or confidential information.

**The approval used to be a capability URL. It is not any more, and the difference is worth reading.** The first version of this gate sent buttons that were ordinary links:

```
/webhook-waiting/8/b3d66c7e-...?approved=true&signature=1886696948d8b2bc...
```

n8n generated that URL, signed it, and verified its own signature when the browser came back. The signature stops someone editing `approved=true` by hand. It does **not** authenticate who is clicking, so anyone holding the link could approve, and the link sat in a Slack channel.

Turning on `captureResponder` reverses the direction of trust. Slack now makes the call, to a fixed endpoint on this instance, and signs the request with the app's signing secret; n8n verifies it and rejects anything that fails. The identity of the clicker comes from Slack's own interaction payload rather than from possession of a URL.

So the control moved from "who has the link" to "who is in the workspace", which is a real improvement and not a cosmetic one. The residual exposure is the endpoint itself: `/webhook-waiting-slack` is public, and the signing secret is the only thing standing in front of it. That is the right shape, and it is worth naming rather than assuming.

**The queue records a handle, not an email.** The responder payload carries `id`, `name`, `username` and `email`. `approved_by` stores `name`. The email is the better identifier for a real ops queue, since a handle can change and an address usually cannot, but it is a personal address and this sheet is a portfolio artifact. The handle goes in the queue; the email stays in the execution data where it is available if it were ever genuinely needed.

**The execution waits indefinitely, by choice.** Limit Wait Time is off. A media request nobody has looked at has not stopped being a real request, and auto-declining after an hour would discard work silently, which is worse than a queue that grows. The cost is that a stalled request **fails silently**: no error, no alert, nothing in a log, indistinguishable from one still under consideration. The missing piece is not a timeout, it is a reminder, and that is named under Next rather than pretended away. Also worth knowing: "indefinitely" is bounded by n8n's execution pruning, so a waiting execution is not immortal.

**The gate was built in two passes, on purpose.** Pass one shipped with `captureResponder` off, because capture needs four other things configured and every one of them fails silently. Getting the round trip working with the fewest moving parts, then adding identity as a separate change, is the same one-variable-at-a-time discipline that the v1 to v2 eval run failed to follow and got punished for. The intermediate state was honest about itself: `approved_by` held the literal string `not captured` rather than a blank cell that would have read as a bug.

**One enum value per request when reality overlaps.** Item 3 contains both a synopsis error and an audio dropout. The prompt resolves this with *"classify the one that blocks delivery,"* which makes the behaviour specified and defensible rather than arbitrary. It still collapses a two-problem request into one label, and the second problem is silently dropped. A `secondary_type` field is the obvious extension.

**Haiku over a larger model.** Justified by the accuracy number rather than by cost alone, and the eval makes the upgrade a one-line change with a measurement attached.

**"Title or asset ID" is not a required field.** The build guide specified it as required. Test item 1 is a panicked requester who does not have the ID, which is a real behaviour an intake form should receive rather than reject. Requiring it would have made the most realistic item in the set impossible to submit.

**Fifteen items is a small test set.** Large enough to expose a systematic definition gap, which it did, five times over. Too small to trust a single-item difference, and far too small to split into train and holdout.

---

## Idempotency

**Two identical submissions produce two executions, two classifications, two approval prompts, and two rows.** Nothing deduplicates. This is no longer a prediction; it is what the built system does.

The mechanism is worth stating precisely, because it is also what makes both `.first()` and `.item` safe downstream. A Form Trigger fires **once per submission and emits exactly one item**. Two people submitting at the same moment do not produce one execution with two items, they produce two separate executions, each carrying one. So there is never a second item for `.first()` to pick wrongly from, and there is never a point at which two requests could be collapsed into one.

For a request *intake* system that is arguably correct. Two people really can ask for the same thing about the same asset, and those are two real requests that both deserve an answer. The approver is the dedupe step, which is one of the reasons the human gate exists.

If dedupe were wanted, the mechanism would be a hash of requester plus asset ID plus a time window, checked **before** the classifier runs so duplicates cost nothing.

**The eval is idempotent in inputs and deliberately not in outputs.** Re-running scores the same 15 items against the same pinned reference dates, so the inputs never drift. The model's answers can still vary between runs. That is a property of the model, not a bug in the harness, and it is a reason not to over-read a one-item difference.

---

## What broke

### Four bugs, one habit

Every one of these is a name that existed in one place and was retyped in another. They are listed together because they are not four lessons.

**The public form URL had never worked, and had been recorded as working for eight days.** Tested from a phone on cellular for the first time on 2026-09-14, it returned n8n's *"Problem loading form"* page, and a direct request returned a bare **HTTP 404**. The workflow was published, all nodes were present, and the Week 6 infrastructure was fine: DNS resolved, TLS handed over a valid cert, Caddy proxied, and n8n itself generated that error page. The cause was that **Form Path was never set on the instance**. It lives under the node's Options via *Add Option*, not in the main parameters, so it is invisible unless you go looking. n8n had been serving the form at its webhook UUID the whole time. A note in the project handoff said the form URL existed. Nobody had opened it.

**The committed `workflow.json` describes a workflow that does not exist.** It carries `"path": "media-request"` and a `webhookId` of `3c2b7a10-...`. The live instance had no path at all and a webhook ID of `c07303b2-...`. Neither string matched. The file is *generated* by a script rather than exported from the instance, which is what keeps `pinData` out of every commit, and it is also what let the two drift the moment one of them was hand-authored. The README's Quick start tells a stranger to import that file, and nobody had ever run that instruction.

**`Referenced node doesn't exist`.** A node named `Flatten For Approval` on the canvas, referenced as `$('Flatten for Approval')` in an expression. One capital letter. The deny branch routed correctly, the IF node evaluated correctly, and the Slack message was the only thing that failed. Renaming the node would not have fixed it either: n8n rewrites the references it is tracking, and a hand-typed name pointing at a node that does not exist is just a string.

**`invalid syntax`.** Fixing the capital letter by editing in place left the tail of the old string behind:

```
$('Flatten For Approval')or Approval').first().json.name
```

The expression editor's Result pane had been showing `[invalid syntax]` in red, live, against real data, before the workflow was ever run. That pane evaluates as you type. It was not being read.

The fix for all four is the same and it is not "be more careful": **drag node references from the expression editor's left panel instead of typing them.** n8n writes the real name. `Flatten For Approval` exists partly to reduce the number of such references from roughly twenty to roughly ten.

### That fix introduced a different dependency

Dragging does not write what typing writes. Side by side, from the same node:

```
"requester": "={{ $('Flatten For Approval').first().json.name }}"      typed
"asset_id":  "={{ $('Flatten For Approval').item.json.asset_id }}"     dragged
```

`.first()` takes item one of that node's output, unconditionally. `.item` asks which item over there is *paired* with the item being held now, and that is **paired-item tracking**, the exact mechanism `Route By Source` was deliberately built to avoid. Six expressions in the shipped workflow use it because they were dragged rather than typed.

They are all correct, for the same reason `.first()` is correct: the form branch carries exactly one item, so there is only one thing either form could resolve to. But the fix for a name-typo problem quietly introduced a dependency on the mechanism that had just been routed around, and that is worth writing down rather than tidying into consistency after the fact. Both forms are left in place.

### Two columns, two different ways to be silently wrong

A denial writing nothing was verified against a spreadsheet holding exactly one row. That same screenshot showed `approved_by` empty, and the reason was not a failure. **The column was never mapped.** n8n's `schema` block listed it, because n8n reads the header row and learns which columns exist, but no value was ever assigned to it. Nine columns specified, eight filled, and the node reported success both times.

The fix exposed a second one. The mapping key was `"summary "`, with a trailing space, because cell G1 of the spreadsheet contained a trailing space and n8n mapped faithfully to the column name it actually found. It worked. It would also have quietly defeated every formula, filter or script that looked for `summary`.

Neither raised an error. A Google Sheets append succeeds whether or not you gave it everything you meant to.

### Slack said the Request URL was not needed, and it was wrong for this use

Turning on `captureResponder` requires an Interactivity Request URL in the Slack app. The field was not there. In its place:

> Socket Mode is enabled. You won't need to specify a Request URL.

Socket Mode and Request URL are two mutually exclusive delivery mechanisms. Socket Mode has the app dial **out** and hold a WebSocket that Slack pushes events down. A Request URL has Slack POST **in** to a public HTTPS endpoint. Socket Mode exists for apps that cannot receive inbound traffic: running on a laptop, behind NAT, no domain, no TLS.

n8n does not hold a Slack WebSocket. It sits at `/webhook-waiting-slack` waiting to be called, so it needs the inbound path, and Slack hides that field whenever Socket Mode is on. Turning Socket Mode off is not a downgrade here; it is the whole reason [w6-vps-deploy](../w6-vps-deploy) exists. The message was accurate about Slack and wrong about this workflow.

### `403 Forbidden` from a dropdown that had not touched any data

The Google Sheets document picker failed with:

```
Could not load list
403 - Forbidden

Google Drive API has not been used in project ... before or it is disabled.
```

The **Google Sheets API** was enabled. The **Google Drive API** was not. Listing the spreadsheets in a Drive is a Drive operation; the Sheets API only works inside a spreadsheet you can already name. n8n's UI suggested *"Check your credential"*, and the credential was fine. The error text named a different API and supplied the URL to fix it. **The tool's proposed fix and the error's own content disagreed, and the error was right.**

### From day 1

**The scorer reported every live form submission as a classification miss.** The filter was:

```js
const misses = rows.filter(r => r.verdict && r.verdict.includes('miss'));
```

The verdict string for a form submission is `"live submission"`, and **"sub*miss*ion" contains "miss"**. Substring matching against what is really an enum, which worked fine until the first input that happened to contain the substring. Fixed with an exact-match set.

**The first eval scored 20% and the number was meaningless.** Nine blank label fields were filled with prose such as `"Getting the primary audio"`, while the scorer does exact string equality against the enum. Every one failed automatically regardless of what the model said. The scorer was measuring string equality, not classification. The re-score against the intended values was 86.7% type accuracy, not 20%.

**Two variables were changed in one experiment.** The v2 run altered the urgency definitions *and* shifted item 4's `reference_date`. Item 4's type answer then regressed, and that regression cannot be attributed to either change.

**A three-value enum was nearly tested on two.** The first complete label pass produced 6 `urgent`, 9 `low`, and **zero** `standard`. A three-way classifier measured against two classes cannot detect over-application of the third. Fixed by shifting two reference dates into the band so the operator's own rule yields `standard`. This is the [w4-ai-email-digest](../w4-ai-email-digest) failure, *"a test set where every example carries the same label proves nothing about the field"*, caught before shipping this time instead of after.

---

## Limitations

- **The model still will not produce `low` for dated requests**, and now demonstrably not on live traffic either. Unfixed, deliberately: the diagnosis is more useful right now than a patched prompt.
- **No holdout.** The v2 definitions were written after seeing the v1 results, on the same 15 items. The v2 score measures fit, not generalization.
- **Live submissions are never scored.** The eval path is measured; the production path is not. Nothing checks whether the classifier is right about a real request, and nothing ever tells it when it was wrong.
- **A stalled request is invisible.** No timeout, no reminder, no alert. It waits, and it looks exactly like a request still being considered.
- **`qc_escalation` appears once** in the test set. One example says nothing about that class, and its boundary with `caption_subtitle` and `redelivery_fix` is where both remaining type misses live.
- **Nonsense input is unhandled.** Submit "asdf" and the classifier confidently returns an enum value, because the schema requires one. There is no "cannot classify" escape hatch.
- **No dedupe, no rate limit, no captcha** on a public endpoint that costs money per submission.
- **Single market, single register.** The vocabulary is drawn from one operational domain. Nothing here says it transfers.

---

## Next

**The two open definition-of-done items.** A three to five minute walkthrough video, submission through to the row landing, and one written post. Neither is code, both are the project's own criteria, and it is not closed until they exist.

**The v3 experiment.** Split the mechanical criterion from the semantic one in the `low` definition and re-run the same 15. Current hypothesis: the model follows the vibe over the rule, so removing the vibe should recover the remaining urgency misses. Cheap to test, the eval makes it a single re-run, and there are now live submissions to check it against as well.

**A reminder for stalled approvals.** The honest answer to indefinite waiting. Something that notices a request has been pending for three days and says so.

**Same 15 through a larger model**, both numbers side by side. About a dollar.

**A note for whoever edits this next, including me:** `workflow.json` and `test-set.json` are **generated**, not hand-written. The source is `tools/build_w7_workflow.py` outside this repo. Edit the generator and re-run it; a hand-edit to the JSON will be silently overwritten, and generating is also why no commit here has ever needed `pinData` stripped. As of 2026-09-14 the generator is reconciled against the live instance, including the real node names and the form path. It had drifted once, and that is documented above rather than quietly corrected.

**Beyond this build.** The real trackers this vocabulary came from route by deterministic rule, and the rule engine is *correct*: an LLM asked to reproduce it would be slower, costlier and less reliable. The problem worth solving is the fallback bucket, the rows where the rule engine finds no matching status and hands a human a pile to work through by hand. That is a classification problem with no rule to copy, which is the opposite of this one, and it is the flagship's target.
