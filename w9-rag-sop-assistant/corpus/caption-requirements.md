# Caption Requirements

**Doc ID:** SOP-CAP-001 · **Version:** 1.2 · **Effective:** 2026-02-20 · **Owner:** Accessibility and QC · **Status:** Current

Every organisation, title, asset ID and process in this document is invented for a portfolio project.

## 1. Which assets need captions

- Episodes and features: always. No exceptions and no waivers.
- Trailers: always.
- Promos: required only when the promo is **longer than 15 seconds**. A 15 second or shorter promo may be delivered without captions.

## 2. Accepted formats

- WebVTT (`.vtt`) is the preferred format.
- SCC (`.scc`) is accepted from suppliers and converted to WebVTT during ingest.
- Burned in (open) captions are never accepted as the only caption track.

## 3. Timing

- Each caption must appear within **100 milliseconds** of the start of the speech it represents.
- A caption stays on screen for at least 1 second and no more than 7 seconds.
- Captions must not overlap each other in time.

## 4. Layout

- At most **2 lines** per caption.
- At most **32 characters** per line.
- Speaker changes are marked with a leading hyphen on the new speaker's line.

## 5. What fails QC

Any of the following sends the asset to `qc_hold` under SOP-QC-003:

- No caption file for an asset that requires one.
- A caption file that does not cover the full runtime (last caption ends more than 60 seconds before the programme ends, not counting end credits).
- More than 10 captions outside the timing rules in section 3.
- Any caption over 2 lines or 32 characters per line.

Caption failures cannot be waived.
