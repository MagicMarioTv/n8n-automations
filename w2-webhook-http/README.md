# w2-webhook-http

An n8n workflow that accepts an inbound order over HTTP, validates the payload, hands it to a sub-workflow, and returns a real status code. Week 2 build, from the n8n Academy N8N102 course.

Five nodes. The interesting part isn't the count. It's that this is the first build where something *outside* n8n starts the work, and the first one that has to answer the caller.

---

## Quick start

1. Import `workflow.json` into n8n.
2. Create a **Header Auth** credential and select it on the Webhook node. The workflow ships with `authentication: headerAuth` and no key value, because n8n exports credential references, never secrets.
3. **Import the sub-workflow too.** See *Limitations*: it isn't in this repo, and without it the success path can't run.
4. Activate the workflow, then copy the **Production URL** (not the Test URL; see *Trade-offs*).

```bash
# valid — returns 200
curl -X POST "<production-url>" \
  -H "Content-Type: application/json" \
  -H "<your-auth-header>: <your-key>" \
  -d '{"order_id":"ORD-023","customer_id":"CUST-003","total":"49.99"}'

# missing "total" — returns 400
curl -X POST "<production-url>" \
  -H "Content-Type: application/json" \
  -H "<your-auth-header>: <your-key>" \
  -d '{"order_id":"ORD-023","customer_id":"CUST-003"}'
```

---

## How it works

| Node | What it does | Why |
|---|---|---|
| **WebhookNewOrder** | `POST` on `course/n8n102/new-order`, header auth, response mode set to *Using Respond to Webhook node* | The trigger is external. Response mode is the switch that makes the two branches below possible |
| **ValidateRequireFields** | IF node: `order_id`, `customer_id`, and `total` must all be non-empty (`AND`) | Reject bad input at the edge, before the sub-workflow does any work |
| **ExecuteProcessOrder** | Calls the `Section 2 — Process Order` sub-workflow, passing the three validated fields | Separates transport concerns from processing concerns |
| **RespondSuccess** | `200` with the sub-workflow's result echoed back: order ID, stored flags, processing result | The caller learns what actually happened, not just that something was received |
| **RespondValidationError** | `400` with `"Missing required fields: order_id, customer_id, and total are required"` | A rejection that names the problem is worth ten that say "error" |

The IF node's two outputs are the whole design: true goes to processing then success, false goes straight to the 400. Nothing downstream runs on a bad payload.

---

## Trade-offs

**Test URL vs Production URL.** n8n gives every webhook two. The Test URL only listens while the editor is open with "Listen for test event" armed, and fires once. The Production URL listens whenever the workflow is active. A request to the wrong one fails in a way that looks like a broken workflow rather than a wrong URL.

**Respond to Webhook, not the default acknowledgement.** Without a Respond node, n8n answers immediately with a generic acknowledgement and the caller learns nothing about the outcome. Setting `responseMode: responseNode` buys deliberate status codes, but it also means the caller now waits for the workflow to reach a Respond node, so a slow sub-workflow becomes a slow HTTP request. That's the right trade at this size and the wrong one at scale, where the answer is to accept with `202`, queue, and let the caller poll.

**Validating at the edge, not inside the sub-workflow.** The IF sits before `ExecuteProcessOrder`, so a malformed payload never reaches processing: nothing is written, nothing needs unwinding. The cost is that validation is structural: it checks that fields are present, not that `total` is a sensible number or that `customer_id` refers to anyone real.

**`notEmpty` on `total`, with loose type validation.** `total` is semantically a number but is checked as a non-empty string with `looseTypeValidation` on, so n8n coerces rather than rejecting on type. Fine for a course exercise; in production this is where you'd want a real numeric check, since `"total": "banana"` passes this gate today.

**Splitting processing into a sub-workflow.** More moving parts and an extra hop, in exchange for a transport layer that can be reused by any caller and processing logic testable on its own. It's also why the import instructions above have a step 3.

---

## Idempotency

**What happens if this runs twice?**

Webhooks make the question sharper than a schedule does, because duplicate delivery is normal rather than exceptional. Callers retry on timeout and on non-2xx responses, and a caller that doesn't get an answer fast enough will often send the same payload again.

**This workflow is not idempotent, and that matters more than it looks.** The same `order_id` posted twice runs `ExecuteProcessOrder` twice. Whether that duplicates an order depends entirely on what the sub-workflow does with it, which is exactly the kind of dependency that's invisible until it bites.

The fix is an idempotency key: treat `order_id` as one, record the IDs already processed, and short-circuit a repeat to the original response instead of reprocessing. That check belongs beside the field validation, as a second gate.

Worth contrasting with the Week 3 Gmail build, where labelling is naturally idempotent and needed no key at all. Same question, opposite answer, because the underlying operation differs. It's also the same problem as the bulk-comment automation I maintain at work, where posting twice *does* duplicate and a hash-keyed resume log is what keeps re-runs safe.

---

## Security

The webhook uses **header authentication**, so the endpoint isn't open to anyone who discovers the URL. That's the right default: a production webhook URL without auth is a public endpoint, and this one reaches a workflow that writes.

`workflow.json` carries a credential *reference* only: an ID and a display name, no key material. That's how n8n exports work, and it's what makes committing a workflow safe.

**pinData is the exception, and it caught me.** See *What broke*.

---

## What broke

**I nearly committed a live API key.**

The first export of this workflow included n8n's `pinData` block, the sample data pinned to the Webhook node from a real test call. Pinned webhook data captures the *entire* request, and the headers of a real authenticated call include the header you authenticated with:

```
"x-api-key": "<live key>"
```

Alongside it: the instance hostname, the full production webhook URL, and the originating IP three times over. Key plus URL is a working pair.

Three things worth keeping from this:

1. **`.gitignore` was no help.** It covers `*credentials*.json`, `*token*.json`, `*.pem`, `*.key`, and `workflow.json` matches none of them. Pattern-based secret rules only catch secrets in files you predicted.
2. **The dangerous part was the sample data, not the credential block.** I was watching the node's `credentials` field, which was clean the whole time. The leak was in the debugging convenience I'd forgotten was attached.
3. **The export is not the workflow.** n8n's download includes pinData, `versionId`, and a `meta.instanceId` fingerprint, none of which the workflow needs to run.

Fixed by stripping `pinData`, `versionId`, and `instanceId` before the first commit, and rotating the key. **Check every n8n export for pinData before it goes anywhere public.**

*(Build-time issues from the original N8N102 session aren't recorded here, because this workflow was built during the course in early August and exported on 8/14. Anything that cost real time then is worth adding.)*

---

## Limitations

- **The sub-workflow isn't in this repo.** `ExecuteProcessOrder` references `Section 2 — Process Order` by n8n-internal ID. Importing `workflow.json` alone gives a dangling reference and a success path that can't run. Exporting it as a sibling folder would make this build self-contained.
- **Not idempotent.** No dedup on `order_id`. See above.
- **Structural validation only.** Presence, not plausibility. `"total": "banana"` passes.
- **No error handling past the validation gate.** If the sub-workflow throws, there's no retry, no dead-letter path, and the caller gets no Respond node at all, just a hanging request.
- **No rate limiting.** Nothing stops a caller sending a thousand requests.
- **Ships inactive** (`active: false`). The production URL won't answer until the workflow is activated.

---

## Why this is Week 2 and shipped late

Originally scheduled for Saturday 8/1/2026 and not shipped as a standalone artifact that week. The material was covered inside n8n Academy N8N102 instead, which is where this workflow was actually built, as the course's Section 2 assessment.

Exported and documented on 8/14/2026 so the repo reflects work that genuinely happened. The webhook and validation material here is the direct foundation for Project 1's intake trigger, so it belongs in the build log rather than only in a course completion.

---

## Next

Week 3 moves to Gmail and OAuth: the first build that writes to something real, and the one where the OAuth publishing-status trap costs an evening. Week 4 adds the first AI node.
