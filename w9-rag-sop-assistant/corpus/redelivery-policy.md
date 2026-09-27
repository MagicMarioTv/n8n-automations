# Redelivery Policy

**Doc ID:** SOP-DEL-003 · **Version:** 1.0 · **Effective:** 2026-05-12 · **Owner:** Delivery Lead

Every organisation, title, asset ID and process in this document is invented for a portfolio project.

## 1. What a redelivery is

A redelivery replaces an asset that has already reached status `delivered`, because a defect was found after delivery or the platform asked for a change.

## 2. When a redelivery is required

- A defect reported by a platform partner.
- A caption correction of any size.
- A legal or compliance edit.

Cosmetic metadata changes (a synopsis, a genre tag) are not redeliveries. They go through the metadata update process and do not touch the video.

## 3. Rules

1. The corrected file gets a **higher version number** than the file it replaces (SOP-NAM-001 section 4).
2. The corrected asset goes through **full QC again**. A redelivery that fails QC goes to `qc_hold` like any other asset.
3. A redelivery must reach the platform within **72 hours** of the fix being approved.

## 4. Limit

An asset may be redelivered **at most twice**. A third redelivery needs approval from the Post Production Supervisor, and the asset is flagged in the monthly quality review.

## 5. Status during redelivery

While a redelivery is in progress the asset's status returns to `encoding`, and goes back to `delivered` when the platform confirms receipt.
