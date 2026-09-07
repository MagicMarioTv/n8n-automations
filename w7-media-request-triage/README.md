# w7-media-request-triage

**Project 1, day 1 of 2.** A public intake form for media operations requests, classified by an LLM into a work type and an urgency level, scored against a 15-item test set that a working operator labeled by hand.

Ships complete on 2026-09-12 with a human approval gate and a routed queue. This README covers what exists today and is honest about what doesn't.

The interesting result from day 1 is not the accuracy number. It's that **rewriting the urgency definitions to match the operator's real rubric changed the model's answer on exactly one of fifteen items** — and the model's own reasoning field is the only reason we can see why.

---

## What it does

A requester fills in a form: who they are, the title or asset ID, the platform, whether the title is already live, when they need it, and what's wrong. A single LLM call classifies the request into one of five work types and one of three urgency levels, and returns a one-line summary plus a sentence of reasoning.

The same classifier is wired to a second entry point — a 15-item labeled test set — so the thing being measured is exactly the thing that runs in production. There is one prompt, one schema, one chain.

Day 1 sends nothing, writes nothing, and posts nothing. That's deliberate: the approval gate exists so nothing leaves the system without a human, and building the gate before the sending is the only order that respects it.

---

## Quick start

You need a running n8n instance reachable over HTTPS (this runs on a VPS at `n8n.mariomoreno.dev`, built in [w6-vps-deploy](../w6-vps-deploy)) and an Anthropic API credential.

1. Import `workflow.json` (⋯ → Import from File).
2. Open **Anthropic Chat Model** and select your own Anthropic credential — the credential ID in the export won't resolve on your instance.
3. **Run the eval:** click the **Run Eval** node → Execute step. Fifteen classifications, scored against the labels, in about a minute.
4. **Run the form:** publish the workflow, then open `https://<your-host>/form/media-request`.

`test-set.json` is the same 15 items in plain JSON, derived from the workflow so the two can't drift.

---

## How it works

| Node | What it does | Why |
|---|---|---|
| **Media Request Form** | Form Trigger, path pinned to `media-request`, auth None | Pinning the path keeps the live URL readable. Leave it blank and n8n generates a UUID you wouldn't put on a résumé. |
| **Run Eval** | Manual trigger | Second entry point into the same classifier. One execution fires one trigger, so these two paths never run together. |
| **Test Set** | Code node holding the 15 labeled requests | Makes the test set a permanent, re-runnable artifact rather than fifteen tedious form submissions that leave nothing behind. |
| **Normalize Request** | Set node mapping both inputs onto one shape | The form emits keys named after field *labels* (`Your name`); the test set emits slugs (`name`). `{{ $json['Your name'] \|\| $json.name }}` serves both, so there is exactly one prompt to maintain. Also injects `reference_date`. |
| **Classify Request** | Basic LLM Chain, `claude-haiku-4-5` | Closed-set classification with definitions supplied. At $1/$5 per million tokens it's roughly a fifth the cost of the Opus tier, and the eval exists precisely so upgrading is a one-line change with a number attached. |
| **Anthropic Chat Model** | Model attachment | — |
| **Structured Output Parser** | JSON Schema with `enum` on both classification fields | Enforced as a tool definition, not requested in prose. `request_type` is structurally incapable of returning anything outside the five values. |
| **Score Against Labels** | Code node comparing output to the labels | Reports type accuracy, urgency accuracy, and exact match separately, plus how many items it *couldn't* score. |

### Two design decisions worth naming

**The form collects facts; the model supplies judgment.** Requester, title, platform and live status arrive already structured, so the model never re-extracts them. Asking an LLM to pull a value out of a field you already have as a field is paying money to introduce errors.

**`reference_date` is injected, and pinned per test item.** The urgency rules talk about deadlines "within 24 hours." A language model has no idea what day it is. Without a supplied date the arithmetic is guesswork; with a *pinned* date per test item, the correct label doesn't drift as real time passes. A test set that scores differently on Tuesday than on Saturday is not a test set.

---

## The measurement

Fifteen requests, labeled by hand before the classifier was run, by someone who does this triage as day work. All names, titles, asset IDs and ticket numbers are invented; the vocabulary and the failure modes are not.

Label distribution: `redelivery_fix` 4, `metadata_correction` 4, `caption_subtitle` 3, `new_delivery` 3, `qc_escalation` 1 · urgency `low` 7, `urgent` 6, `standard` 2.

### v1 — the guide's urgency definitions

| Metric | Result |
|---|---|
| Type accuracy | 13/15 (86.7%) |
| Urgency accuracy | 8/13 (61.5%) — two items had no committed label |

**Every single urgency miss was the same disagreement:** the operator said `low`, the model said `standard`. Five for five, no exceptions.

The cause was a definition gap, not a model error. The prompt said `standard` = "a deadline more than 24 hours out," so a 13-day deadline was `standard` by definition. There was no rule in that prompt that could ever produce `low` for a dated request. **The operator's real rubric has a 72-hour boundary the prompt didn't encode.** The model applied the definitions it was given, correctly, five times out of five.

### v2 — definitions rewritten from the operator's rubric

| Metric | Result |
|---|---|
| Type accuracy | 12/15 (80%) |
| Urgency accuracy | 11/15 (73.3%) |
| Exact match | 9/15 (60%) |

**These numbers are measured on the same 15 items that produced the fix.** There is no holdout. They demonstrate that the definitions now match the operator; they do not demonstrate that the classifier generalizes. Reported as such deliberately.

### What actually caused the improvement — and it isn't the prompt

Comparing the two runs item by item:

```
model changed its urgency answer on: [8]   (1 of 15 items)
```

| Item | What happened |
|---|---|
| 4, 13 | "Fixed" because the label moved to `standard`. **The model never changed its answer.** |
| 2, 8 | Not scored in v1 — no committed label |
| 3 | **Regressed.** Label moved to `low`; model still says `standard` |
| 8 | The single genuine prompt-driven fix |

So the headline number rose from 61.5% to 73.3%, and almost none of that is the rewrite working. **The rewritten definitions moved one answer out of fifteen.** Without the item-by-item comparison, this build would have reported a 12-point improvement it did not earn.

### Why the model refuses `low`

Its own reasoning field, verbatim:

> *"…the deadline of 2026-09-22 is 10 days away, falling within 24-72 hours classification for standard urgency."*

Ten days is not within 24–72 hours. It states the rule and violates it in the same sentence. And on item 7:

> *"…13 days away, falling in the standard urgency window (24–72 hours is exceeded, but within reasonable planning horizon for a multi-episode package)."*

It acknowledges the rule is exceeded, then overrides it with a qualifier nobody supplied.

The fault is in the definition:

> `low`: a stated deadline more than 72 hours away, **or** no deadline at all — cleanup, housekeeping, or a cosmetic issue

That is a **mechanical** criterion and a **semantic** one sharing a single enum value. A ten-episode season delivery does not *feel* like housekeeping, so the model declines `low` regardless of the arithmetic. **Given a rule and a vibe for the same label, it follows the vibe.** Splitting the mechanical case from the semantic one is the v3 experiment.

None of this would be visible without the `reasoning` field. It costs about $0.0001 per call.

### Cost

⏳ **Not yet measured.** Token counts come from the `Classify Request` execution data and land here before ship on 9/12, with the arithmetic shown, at $1/M input and $5/M output. Estimating it would defeat the point — see [w4-ai-email-digest](../w4-ai-email-digest), where a plausible estimate was off by 7% against a real measurement.

---

## Trade-offs

**A public form with no authentication.** The definition of done requires a live URL a stranger can use, and auth would defeat that. The cost is that anyone who finds the URL can submit, and every submission costs an API call. Acceptable for a portfolio demo; for production this needs a rate limit and a captcha at minimum. The form carries a visible warning not to enter real or confidential information.

**One enum value per request when reality overlaps.** Item 3 contains both a synopsis error and an audio dropout. The prompt resolves this with *"classify the one that blocks delivery,"* which makes the behaviour specified and defensible rather than arbitrary. It still collapses a two-problem request into one label, and the second problem is silently dropped. A `secondary_type` field is the obvious extension.

**Haiku over a larger model.** Justified by the accuracy number rather than by cost alone, and the eval makes the upgrade a one-line change with a measurement attached. Running the same 15 through a larger model is a genuinely cheap experiment and is listed under Next.

**"Title or asset ID" is not a required field.** The build guide specified it as required. Test item 1 is a panicked requester who doesn't have the ID — which is a real behaviour an intake form should be able to receive, not reject. Requiring it would have made the most realistic item in the set impossible to submit.

**Fifteen items is a small test set.** Large enough to expose a systematic definition gap — which it did, five times over. Too small to trust a single-item difference, and far too small to split into train and holdout. Every number here should be read with that in mind.

---

## Idempotency

**Two identical submissions produce two executions, two classifications, and — from day 2 — two approval prompts and two queue rows.** Nothing deduplicates.

For a request *intake* system that is arguably correct. Two people really can ask for the same thing about the same asset, and those are two real requests that both deserve an answer. The approver is the dedupe step, which is one of the reasons the human gate exists.

If this were production and dedupe were wanted, the mechanism would be a hash of requester + asset ID + a time window, checked before the classifier runs so duplicates cost nothing.

**The eval is fully idempotent in inputs and deliberately not in outputs.** Re-running scores the same 15 items against the same pinned reference dates, so the inputs never drift. The model's answers can still vary between runs — that is a property of the model, not a bug in the harness, and it's a reason not to over-read a one-item difference.

---

## What broke

**The scorer reported every live form submission as a classification miss.** The filter was:

```js
const misses = rows.filter(r => r.verdict && r.verdict.includes('miss'));
```

The verdict string for a form submission is `"live submission"` — and **"sub*miss*ion" contains "miss"**. Substring matching against what is really an enum, which worked fine until the first input that happened to contain the substring. Fixed with an exact-match set.

**The first eval scored 20% and the number was meaningless.** The nine blank label fields were filled with prose — `"Getting the primary audio"`, `"Someone updating the rating"` — while the scorer does exact string equality against the enum. Every one failed automatically regardless of what the model said. The scorer was measuring string equality, not classification. Cause: the blanks were shipped with no format constraint and no filled example to copy. The re-score against the intended values was 86.7% type accuracy, not 20%.

**Two variables were changed in one experiment.** The v2 run altered the urgency definitions *and* shifted item 4's `reference_date`. Item 4's type answer then regressed from `caption_subtitle` to `qc_escalation` — and that regression cannot be attributed to either change. It's the only item in the set whose type flipped, and the run design makes it unreadable.

**A three-value enum was nearly tested on two.** The first complete label pass produced 6 `urgent`, 9 `low`, and **zero** `standard` — the operator's 72-hour rubric is consistent, but no item happened to fall in the 24–72 hour window. A three-way classifier measured against two classes cannot detect over-application of the third. Fixed by shifting two reference dates into the band so the operator's own rule yields `standard`. This is the [w4-ai-email-digest](../w4-ai-email-digest) failure — *"a test set where every example carries the same label proves nothing about the field"* — caught before shipping this time instead of after.

---

## Limitations

- **No holdout.** The v2 definitions were written after seeing the v1 results, on the same 15 items. The v2 score measures fit, not generalization.
- **The model still won't produce `low` for dated requests.** Four of fifteen items remain wrong for this single reason. Unfixed, deliberately — the diagnosis is more useful right now than a patched prompt.
- **`qc_escalation` appears once.** One example is not enough to say anything about that class, and its boundary with `caption_subtitle` and `redelivery_fix` is where both remaining type misses live.
- **Nonsense input is unhandled.** Submit "asdf" and the classifier confidently returns an enum value, because the schema requires one. There is no "cannot classify" escape hatch.
- **Nothing is sent, written, or routed.** No approval gate, no queue. That's day 2.
- **Cost is unmeasured.** See above.
- **Single market, single register.** The vocabulary is drawn from one operational domain. Nothing here says it transfers.

---

## Next

**Day 2 (2026-09-12)** — Slack `Send and Wait for Response` as a human approval gate, then Google Sheets on approve and a Slack note on deny. The approval buttons call back to this n8n instance's own webhook, which only resolves because the VPS has a real domain and real TLS — that step is unbuildable on `localhost`, and it is [w6-vps-deploy](../w6-vps-deploy) paying off. Discord is the pre-agreed fallback if Slack costs more than 30 minutes.

**The v3 experiment** — split the mechanical criterion from the semantic one in the `low` definition and re-run the same 15. Current hypothesis: the model follows the vibe over the rule, so removing the vibe should recover the four remaining urgency misses. Cheap to test, and the eval makes it a single re-run.

**Same 15 through a larger model**, both numbers side by side. About a dollar.

**Beyond this build.** The real trackers this vocabulary came from route by deterministic rule, and the rule engine is *correct* — an LLM asked to reproduce it would be slower, costlier and less reliable. The problem worth solving is the fallback bucket: the rows where the rule engine finds no matching status and hands a human a pile to work through by hand. That's a classification problem with no rule to copy, which is the opposite of this one, and it's the flagship's target.
