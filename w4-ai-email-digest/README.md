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
| **Gmail: Get Many Messages** | Fetches messages matching a query, capped at 5 | The cap is a cost control, not a convenience |
| **Basic LLM Chain** | One prompt per message, `claude-haiku-4-5` | A chain, deliberately, not an agent; see Trade-offs |
| **Structured Output Parser** | Forces the response into `{sender, summary, category, needs_reply}` | Never let free text reach a downstream node |
| **Code** | Flattens five structured items into one digest string | Discord gets one message, not five |
| **Discord** | Posts the digest | Write-only, to a throwaway channel |

Sample run: **5 messages in, 5 summaries out, 1 Discord message.**

---

## Cost per run

**Measured exactly, from the execution log.** Re-run 8/30/2026 against live Gmail/Anthropic/Discord credentials on the VPS instance, after the enum fix below. Real numbers, not an average:

| Message | Category | Input tokens | Output tokens | Total |
|---|---|---:|---:|---:|
| Google security alert | automated | 516 | 69 | 585 |
| LinkedIn Job Alerts | automated | 720 | 67 | 787 |
| Aéropostale (back-to-school) | promotional | 821 | 73 | 894 |
| LensCrafters | promotional | 535 | 66 | 601 |
| Aéropostale (accessories) | promotional | 840 | 67 | 907 |
| **Total, 5 messages** | | **3,432** | **342** | **3,774** |

```
3,432 input  ÷ 1,000,000 × $1 = $0.003432
  342 output ÷ 1,000,000 × $5 = $0.001710
                                ≈ $0.00514 per run of 5
                                ≈ $0.00103 per email
```

At 50 emails a day, every day: roughly **$1.55/month.**

### Where the tokens actually go

Input tokens ranged from 516 (the shortest email, a one-line Google security alert) to 840 (the longest promotional email), a 324-token spread driven entirely by email content length. The floor of that range is the useful number: even the shortest possible email still costs ~516 input tokens, and the actual prompt plus that email's content is well under 100 tokens of it. **The remaining ~400+ tokens on every single call are the JSON Schema formatting instructions** n8n sends to enforce the output shape (a full explanation of JSON Schema, a worked example, a warning about trailing commas), independent of what the email says.

That is not an argument against structured output. It is an argument for knowing what it costs, because the number is invisible until you look, and it scales with item count rather than with content size.

---

## Trade-offs

**A chain, not an agent.** A Basic LLM Chain sends one prompt and returns one response. An AI Agent reasons in a loop and calls tools, at five to thirty times the tokens. Summarizing an email needs no tools and no reasoning loop. Using an agent here would have been a way to spend real money on a solved problem.

**The snippet, not the body.** Gmail returns `snippet` (about 100 characters) alongside a full payload. One message in the test set had a `sizeEstimate` of 86KB. Summarizing full bodies would push input to roughly 21,000 tokens per email, about **$32/month at the same volume, versus $1.65.** Same workflow, twenty times the cost, one field different. For a digest, the snippet is enough.

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

**Fixed 8/30/2026.** The Structured Output Parser's Schema Type was switched from "Generate From JSON Example" (which only infers a loose type per field, `category: string`) to "Define using JSON Schema," with:

```json
"category": {"type": "string", "enum": ["promotional", "automated", "personal", "work", "other"]}
```

Re-ran against five fresh emails from the same inbox. Every one came back clean: `automated` × 2 (Google, LinkedIn), `promotional` × 3 (two Aéropostale, LensCrafters), with no casing drift and no invented compound categories. This isn't the model being better-behaved this time; it's structural. Anthropic's structured output runs the schema as a tool definition, so the model is constrained to pick one of five literal strings; it cannot emit `Automated/Promotional` even if it wanted to. The "before" failure mode (three casings and one invented value, [above](#3-validation-that-validated-nothing)) is no longer reachable by construction, not just discouraged by a stricter prompt.

The five categories (`promotional`, `automated`, `personal`, `work`, `other`) are a judgment call, not something the test data forced. The five real emails only ever produced `promotional`/`automated`. `personal`, `work`, and `other` exist because the [Limitations](#limitations) section below already flags that an all-promotional test set proves nothing about the field; a real digest needs headroom for the categories this particular inbox pull didn't happen to contain.

---

## Limitations

- ~~`category` is unconstrained.~~ **Fixed 8/30/2026.** Enum constraint added to the Structured Output Parser's schema. See [What broke #3](#3-validation-that-validated-nothing).
- **The test set has no positive cases.** All five messages are promotional or automated, so `needs_reply` is `false` on every item. A test set where every example carries the same label proves nothing about the field. Needs at least one message from a human before it means anything.
- **No error handling.** If the parser rejects a response or the Anthropic call fails, the run dies with no retry and no dead-letter path.
- **No dedup.** Re-running re-summarizes the same messages and pays for them again. Harmless today because nothing is written, and not harmless the moment this posts somewhere that matters.
- **No empty-input case.** Unclear what this posts when zero messages match.
- **Fixed cap of five.** Deliberate. Raising it needs the error handling above first.

---

## Notes

`pinData` was stripped from the export before committing. Pinning the Gmail output made prompt iteration free, and it also meant the raw export carried real email content. This is the second consecutive build where the export contained something that should not be public. The first was a live API key in the Week 2 workflow.

**Standing rule: check every n8n export for `pinData` before it goes anywhere.**

---

## Next

Week 5 self-hosts n8n with Docker. The reliability track formally starts in Week 9, though three of its items (structured output, cost per run, and secrets discipline) have now shown up on their own by Week 4.
