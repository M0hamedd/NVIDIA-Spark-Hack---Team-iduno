# Live Contract Radar

## One-Line Pitch

A live/daily Toronto Open Data procurement agent that helps small businesses find realistic City contract opportunities, filters out poor fits, alerts the owner, and prepares an approval-gated bid packet.

## Judging Strategy

- **Insight:** Small businesses miss public revenue because of discovery, procurement language, deadlines, and capacity mismatch.
- **Usability:** The owner gets clear decisions: `Bid This`, `Urgent`, `Get Partner`, `Watchlist`, or `Skip`.
- **Creativity:** The system combines live solicitations, historical awards, business capacity, local AI extraction, and an approval workflow.
- **Performance:** The pipeline performs a fast local scan of procurement records, then runs Nemotron only on viable candidates.

## Core Datasets

- `Toronto Bids Solicitations`
- `Toronto Bids Awarded Contracts`
- `Toronto Bids Non-Competitive Contracts`
- `Procurement Pipeline`
- `Business Licences and Permits`
- `Business Improvement Areas`
- `Business Incubation`

## V1 Scope

- Use `Toronto Bids Solicitations` and `Toronto Bids Awarded Contracts`.
- Simulate one month of monitoring for one strong demo business.
- Show an owner view and a judge evidence view.
- Simulate submission only after approval; do not actually submit to SAP Ariba.

## Demo Business

`Leslieville KitchenCare` is a 3-person commercial kitchen equipment service company based in east Toronto.

- **Services:** Preventative maintenance, emergency repair, small appliance replacement, blade sharpening, dishwasher/oven/fridge servicing.
- **Capacity:** Up to 2 city sites per day and contracts up to `$120k`.
- **Ready:** Insurance, WSIB, HST, references.
- **Not ready:** Major construction bonding or large design/build work.

## Milestones

- **M0: Repo reset.** Remove the previous SparkTerritory/window-washing implementation and keep only reference material.
- **M1: Procurement data ingestion.** Load and cache Toronto Bids Solicitations and Toronto Bids Awarded Contracts.
- **M2: Business profile and fit labels.** Convert the owner profile into clear decision labels: `Bid This`, `Urgent`, `Get Partner`, `Watchlist`, or `Skip`.
- **M3: Historical award comparison.** Compare live opportunities to similar past awards to estimate whether each opportunity is realistic for the business.
- **M4: Owner view and judge evidence view.** Show simple owner-facing alerts plus a technical evidence panel for judges.
- **M5: 30-day simulation.** Simulate a month of monitoring, notifications, approvals, and packet generation.
- **M6: Nemotron extraction and packet generation.** Use local Nemotron/NIM to extract requirements and draft approval-gated bid materials.
- **M7: Demo polish.** Tighten the 3-5 minute story, runtime metrics, fallback data, and final presentation flow.

## DGX Spark Role

- Local data processing and fast filtering over live/daily procurement records.
- Local Nemotron/NIM for requirement extraction and bid packet drafting.
- Business profile, strategy, and bid-readiness information stay local.

## Verification

After reset, `git status --short` should show removed old files and new `PLAN.md`.

The workspace root should contain only:

- `.git/`
- `.gitignore`
- `Resources.md`
- `Getting Started.txt`
- `PLAN.md`
