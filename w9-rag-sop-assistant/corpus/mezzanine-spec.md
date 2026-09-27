# Mezzanine Specification

**Doc ID:** SOP-MEZ-002 · **Version:** 2.0 · **Effective:** 2026-01-10 · **Owner:** Encoding Engineering

Every organisation, title, asset ID and process in this document is invented for a portfolio project.

## 1. What a mezzanine is

The mezzanine is the high quality master file a supplier delivers to us. Every platform version is encoded from it, so a defect in the mezzanine is a defect in every output.

## 2. Container and codec

- Container: QuickTime (`.mov`).
- Video codec: H.264 High Profile, or Apple ProRes 422 HQ. No other codec is accepted.
- Scan: progressive only. Interlaced sources are rejected, not deinterlaced.

## 3. Minimum video bitrate by asset type

| Asset type | Minimum bitrate |
|---|---|
| Episode | 8 Mbps |
| Feature | 20 Mbps |
| Trailer | 15 Mbps |
| Promo | 15 Mbps |

A file below its minimum goes to `qc_hold` (see SOP-QC-003). A file above the minimum is always accepted; there is no maximum.

## 4. Resolution and frame rate

- Resolution: 1920x1080, or 3840x2160 for features supplied with a UHD master.
- Frame rates accepted: 23.976, 25 and 29.97 fps. The frame rate must be constant.
- A feature supplied at 3840x2160 is also the only asset type that gets the 2160p rung in the Encoding Ladder (SOP-ENC-001).

## 5. Audio tracks

- Track 1 and 2: stereo programme mix, 48 kHz, 24 bit PCM.
- Tracks 3 to 8: 5.1 mix, when supplied. A 5.1 mix is optional for episodes and required for features.
