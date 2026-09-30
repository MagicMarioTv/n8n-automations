# Delivery Deadlines

**Doc ID:** SOP-DEL-001 · **Version:** 2.0 · **Effective:** 2026-03-01 · **Owner:** Delivery Lead · **Status:** Current

Every organisation, title, asset ID and process in this document is invented for a portfolio project.

## 1. What the deadline means

The `deadline` field in the catalog is the date the finished asset must be delivered to the platform. It is not the go live date. Go live is later, by the lead time below.

## 2. Lead times by asset type

| Asset type | Delivered before go live |
|---|---|
| Feature | 10 business days |
| Episode | 5 business days |
| Trailer | 3 business days |
| Promo | 2 business days |

## 3. At risk

An asset is **at risk** when its deadline is less than 48 hours away and its status is anything other than `delivered`. At risk assets are listed in the morning ops report.

An asset in `qc_hold` that becomes at risk is escalated immediately under SOP-QC-003 section 3, without waiting for the hold's own 24 hour window.

## 4. Missed deadlines

If a deadline is missed:

1. The Delivery Lead informs the platform partner the same business day.
2. A new deadline is agreed and written into the catalog. The original deadline is kept in the asset's history.
3. A missed feature deadline also goes to Tier 2 under SOP-OPS-004, because features have fixed marketing dates.

## 5. Weekends

Deadlines never fall on a weekend. A deadline calculated to land on a Saturday or Sunday moves back to the previous Friday.
