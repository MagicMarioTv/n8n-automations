# Naming Conventions

**Doc ID:** SOP-NAM-001 · **Version:** 1.1 · **Effective:** 2025-11-01 · **Owner:** Media Operations

Every organisation, title, asset ID and process in this document is invented for a portfolio project.

## 1. Asset IDs

Every asset gets an ID in the form `TT-NNNN`: the letters `TT`, a hyphen, and exactly four digits, for example `TT-0142`. IDs are assigned by the catalog at ingest and are never reused, even if an asset is deleted.

## 2. Filename pattern

```
<AssetID>_<TitleNoSpaces>_<Episode>_<Type>_v<NN>.<ext>
```

Example: `TT-0142_HarborLights_S02E07_MEZZ_v01.mov`

- `TitleNoSpaces`: the title in PascalCase, with spaces and punctuation removed.
- `Episode`: `SxxEyy` for episodes. Features, trailers and promos use `FEAT`, `TRLR` or `PROMO` instead.
- `Type`: `MEZZ` for the mezzanine, `CAP` for a caption file, `ART` for artwork.
- `vNN`: a two digit version, starting at `v01`.

## 3. Allowed characters

Letters, digits, underscore and the single hyphen inside the asset ID. No spaces, no other hyphens, no accented letters. Extensions are lower case.

## 4. Versions

The version increases by one every time a changed file is delivered. A redelivery (see SOP-DEL-003) always carries a higher version than the file it replaces. Two files with the same asset ID, type and version must be identical.

## 5. What fails QC

A filename that does not match the pattern sends the asset to `qc_hold`. Renaming the file and resubmitting is the fix; the version number does not change for a rename only.
