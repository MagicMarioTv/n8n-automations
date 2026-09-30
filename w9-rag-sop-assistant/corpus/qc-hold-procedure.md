# QC Hold Procedure

**Doc ID:** SOP-QC-003 · **Version:** 3.0 · **Effective:** 2026-06-01 · **Owner:** QC Lead, Media Operations · **Status:** Current
**Replaces:** SOP-QC-002 (2025 edition)

Every organisation, title, asset ID and process in this document is invented for a portfolio project.

## 1. Purpose

A QC hold stops an asset from moving to delivery until a named person has looked at a problem and decided what happens next. The hold exists so that a known defect never reaches a platform by default.

## 2. What triggers a hold

An asset moves to status `qc_hold` when any of the following is found during automated or manual QC:

- Captions are missing, or fail the checks in the Caption Requirements SOP (SOP-CAP-001).
- The mezzanine file does not meet the Mezzanine Specification (SOP-MEZ-002): wrong codec, frame rate, resolution, or a bitrate below the minimum for its asset type.
- The filename does not match the Naming Conventions SOP (SOP-NAM-001).
- Video dropouts, black frames longer than 2 seconds outside of programme breaks, or frozen frames longer than 1 second.
- Runtime differs from the catalog duration by more than 30 seconds.

## 3. Service level

**A QC hold must be cleared or escalated within 24 hours of being raised.** The clock runs on calendar hours, including weekends.

If the asset's delivery deadline is less than 48 hours away when the hold is raised, the QC Lead is notified immediately rather than at the end of the 24 hour window.

## 4. Who clears a hold

Only the **QC Lead on shift** can clear a hold. The operator who raised it cannot clear their own hold. This separation was introduced in version 3.0.

To clear a hold the QC Lead records one of three outcomes:

1. **Fixed:** the defect was corrected and the asset passed a second QC pass. Status returns to `encoding` or `ingested`, whichever it came from.
2. **Waived:** the defect is accepted for this delivery. A waiver needs a written reason and is only allowed for the black frame and runtime triggers. Caption and spec failures cannot be waived.
3. **Rejected:** the source is unusable and a new mezzanine is requested from the supplier.

## 5. Escalation

If a hold is not cleared within 24 hours, it is escalated to Tier 2 under the On Call Escalation SOP (SOP-OPS-004).
