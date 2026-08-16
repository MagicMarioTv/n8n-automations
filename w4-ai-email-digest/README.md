# w4-ai-email-digest

An n8n workflow that reads Gmail, summarizes each message with an LLM, validates the output against a schema, and posts a single digest to Discord. Week 4 build.

Four nodes. The build worked in about 40 minutes. The interesting part is what the token counter said afterwards.

---

## Quick start

1. Import `workflow.json` into n8n.
2. Gmail OAuth2 credential (see the Week 3 build for the setup that actually works).
3. Anthropic credential, model `claude-haiku-4-5`.
4. Discord webhook URL.
5. Set the Gmail query and keep the limit low while testing.

---

## How it works

| Node | What it does | Why |
|---|---|---|
| **Gmail — Get Many Messages** | Fetches messages matching a query, capped at 5 | The cap is a cost control, not a convenience |
| **Basic LLM Chain** | One prompt per message, `claude-haiku-4-5` | A chain, deliberately, not an agent — see Trade-offs |
| **Structured Output Parser** | Forces the response into `{sender, summary, category, needs_reply}` | Never let free text reach a downstream node |
| **Code** | Flattens five structured items into one digest string | Discord gets one message, not five |
| **Discord** | Posts the digest | Write-only, to a throwaway channel |

Sample run: **5 messages in, 5 summaries out, 1 Discord message.**

---

## Cost per run

TODO — fill in the exact input/output split from the execution log.

Measured: **~879 tokens per message**, five messages per run, roughly **4,400 tokens per run.**

```
~820 input  ÷ 1,000,000 × $1 = $0.00082
~60  output ÷ 1,000,000 × $5 = $0.00030
                              ≈ $0.0011 per email
                              ≈ $0.0056 per run of 5
```

At 50 emails a day, every day: roughly **$1.65/month.**

### Where the tokens actually go

The prompt and the email together are about 100 tokens. The other ~780 are the JSON Schema instructions that n8n injects when you enable structured output — a full explanation of what JSON Schema is, a worked `foo`/`bar`/`baz` example, and a warning about trailing commas, sent on every single call.

**Roughly 85% of the input tokens are formatting instructions rather than content.**

That is not an argument against structured output. It is an argument for knowing what it costs, because the number is invisible until you look, and it scales with item count rather than with content size.

---

## Trade-offs

**A chain, not an agent.** A Basic LLM Chain sends one prompt and returns one response. An AI Agent reasons in a loop and calls tools, at five to thirty times the tokens. Summarizing an email needs no tools and no reasoning loop. Using an agent here would have been a way to spend real money on a solved problem.

**The snippet, not the body.** Gmail returns `snippet` (about 100 characters) alongside a full payload. One message in the test set had a `sizeEstimate` of 86KB. Summarizing full bodies would push input to roughly 21,000 tokens per email — about **$32/month at the same volume, versus $1.65.** Same workflow, twenty times the cost, one field different. For a digest, the snippet is enough.

**Structured output despite the token tax.** Free text is fine for a human and useless to a downstream node. Paying the schema overhead buys a shape that a filter, a router, or a Sheets append can rely on.

**A hard item cap.** Five, throughout. Debugging against fifty would have cost ten times as much to learn the same three lessons.

---

## What broke

Three failures, all structural rather than random. None of them were the model behaving badly.

### 1. The prompt had no email in it

The first run returned five variations of *"I don't see any email text in your message. Please paste the email you'd like summarized."*

The prompt described what to do with an email but never referenced the incoming data. Fixed by switching the Prompt field to Expression mode and interpolating `{{ $json.From }}`, `{{ $json.Subject }}`, and `{{ $json.snippet }}`.

Worth noting the model did the right thing. It reported missing input instead of inventing five plausible summaries, which is the failure I would not have caught.

### 2. Four system messages

Adding each schema field as its own entry under Chat Messages produced:

```
System: sender
System: summary
System: category
System: needs_reply
Human: Summarize this email...
```

```
System messages are only permitted as the first passed message.
```

The Anthropic API takes exactly one system message and it must lead. The fix was deleting all of them: the Structured Output Parser already injects its own formatting instructions, so the field names only ever needed to live in the parser's schema.

### 3. Validation that validated nothing

The most interesting one. Five items passed the parser with these `category` values:

```
Promotional
Automated/Promotional
Promotional
promotional
promotional
```

Three casings and one invented compound category, all accepted. The schema types `category` as a string, and every one of those is a valid string.

**Type validation is not value validation.** A downstream filter on `category == "promotional"` would silently drop three of five items, and nothing in the run would have flagged it. The fix is an enum constraint, which also turns this into a proper before-and-after measurement rather than a guess.

TODO — add the enum, re-run, record what changed.

---

## Limitations

- **`category` is unconstrained.** See above. Highest-priority fix.
- **The test set has no positive cases.** All five messages are promotional or automated, so `needs_reply` is `false` on every item. A test set where every example carries the same label proves nothing about the field. Needs at least one message from a human before it means anything.
- **No error handling.** If the parser rejects a response or the Anthropic call fails, the run dies with no retry and no dead-letter path.
- **No dedup.** Re-running re-summarizes the same messages and pays for them again. Harmless today because nothing is written, and not harmless the moment this posts somewhere that matters.
- **No empty-input case.** Unclear what this posts when zero messages match.
- **Fixed cap of five.** Deliberate. Raising it needs the error handling above first.

---

## Notes

`pinData` was stripped from the export before committing. Pinning the Gmail output made prompt iteration free, and it also meant the raw export carried real email content. This is the second consecutive build where the export contained something that should not be public — the first was a live API key in the Week 2 workflow.

**Standing rule: check every n8n export for `pinData` before it goes anywhere.**

---

## Next

Week 5 self-hosts n8n with Docker. The reliability track formally starts in Week 9, though three of its items — structured output, cost per run, and secrets discipline — have now shown up on their own by Week 4.
