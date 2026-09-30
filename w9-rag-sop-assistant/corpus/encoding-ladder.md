# Encoding Ladder

**Doc ID:** SOP-ENC-001 · **Version:** 1.4 · **Effective:** 2026-04-02 · **Owner:** Encoding Engineering · **Status:** Current

Every organisation, title, asset ID and process in this document is invented for a portfolio project.

## 1. What the ladder is

Streaming players switch between several versions of the same video depending on the viewer's connection. Each version is a rung. The ladder is the list of rungs we encode from every mezzanine.

## 2. Standard ladder (all asset types)

| Rung | Resolution | Video bitrate |
|---|---|---|
| 1080p | 1920x1080 | 6.0 Mbps |
| 720p | 1280x720 | 3.5 Mbps |
| 540p | 960x540 | 2.0 Mbps |
| 432p | 768x432 | 1.2 Mbps |
| 360p | 640x360 | 0.8 Mbps |

All rungs use H.264 High Profile with a 2 second keyframe interval.

## 3. The 2160p rung

Features supplied with a 3840x2160 mezzanine also get a **2160p rung at 16 Mbps**, encoded in HEVC Main 10. Episodes, trailers and promos never get a 2160p rung, even if the source is UHD.

## 4. Audio renditions

Every asset gets an AAC stereo rendition at 128 kbps. Assets with a 5.1 mix also get an E-AC-3 5.1 rendition at 384 kbps.

## 5. Platform differences

Platform A takes the full ladder. Platform B does not take the 360p rung, and takes the 2160p rung only for features marked as UHD titles in the catalog.

## 6. Encode time

Plan on encode time of roughly 1.5 times the asset's runtime for the standard ladder, and 3 times runtime when a 2160p rung is included. An asset stays in status `encoding` for that whole period.
