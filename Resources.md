# Toronto Open Data Resources

Live Contract Radar uses Toronto Open Data to turn public procurement records into small-business opportunity decisions.

V1 uses public Toronto Open Data procurement feeds. These feeds are the proof source for the MVP, not a claim that the app covers every possible live City bid source. The product story is a local bid intelligence engine that can later ingest more sources through the same filtering, award-comparison, and evidence pipeline.

## Core V1 Datasets

| Dataset | Link | Why it matters |
| --- | --- | --- |
| Toronto Bids Solicitations | [Open Data](https://open.toronto.ca/dataset/tobids-all-open-solicitations/) | Main current open-data opportunity feed. The system scans this for active City solicitations and classifies them as `Pursue`, `Review`, `Monitor`, or `Skip`. |
| Toronto Bids Awarded Contracts | [Open Data](https://open.toronto.ca/dataset/tobids-awarded-contracts/) | Historical award evidence. The system compares active opportunities to similar past awards to estimate whether a contract looks realistic for a small business. |

## Strong Stretch Datasets

| Dataset | Link | Why it matters |
| --- | --- | --- |
| Toronto Bids Non-Competitive Contracts | [Open Data](https://open.toronto.ca/dataset/tobids-non-competitive-contracts/) | Adds purchasing pattern evidence, especially for smaller or specialized work that may not look like a large competitive RFP. |
| Procurement Pipeline | [Open Data](https://open.toronto.ca/dataset/procurement-pipeline/) | Lets the app create early monitor alerts before opportunities become active solicitations. Useful for "prepare now" recommendations. |

## Supporting Economic Datasets

| Dataset | Link | Why it matters |
| --- | --- | --- |
| Municipal Licensing and Standards - Business Licences and Permits | [Open Data](https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/) | Helps map Toronto business categories, possible local vendor types, and future matching between opportunities and nearby businesses. |
| Business Improvement Areas | [Open Data](https://open.toronto.ca/dataset/business-improvement-areas/) | Supports future BIA/corridor alerting so groups of small businesses can receive relevant opportunity notifications. |
| Business Incubation | [Open Data](https://open.toronto.ca/dataset/business-incubation/) | Helps recommend support programs when a business is close to bid-ready but needs help with procurement, operations, or growth readiness. |

## Stretch Opportunity Datasets

| Dataset | Link | Why it matters |
| --- | --- | --- |
| Festivals & Events | [Open Data](https://open.toronto.ca/dataset/festivals-events/) | Future expansion for event vendors, caterers, rentals, cleaning, security, and pop-up businesses. |
| Library Branch Programs and Events Feed | [Open Data](https://open.toronto.ca/dataset/library-branch-programs-and-events-feed/) | Future expansion for educators, workshop providers, artists, tutors, and community service providers. |
| Library Branch Space Rentals | [Open Data](https://open.toronto.ca/dataset/library-branch-space-rentals/) | Future expansion for small businesses testing services before leasing storefront or studio space. |
| CafeTO Locations | [Open Data](https://open.toronto.ca/dataset/cafeto-curb-lane-parklet-cafe-locations/) | Future expansion for restaurant, patio, streetscape, maintenance, and hospitality-related businesses. |
| DineSafe | [Open Data](https://open.toronto.ca/dataset/dinesafe/) | Future expansion for restaurant compliance readiness and bid-readiness checks for food-service vendors. |
| BodySafe | [Open Data](https://open.toronto.ca/dataset/bodysafe/) | Future expansion for salons, spas, tattoo shops, and other personal-service compliance readiness. |

## Later Procurement Source Expansion

Keep these as future work until the Toronto Open Data demo is excellent:

- **Toronto Bids Portal / SAP Ariba:** Source-of-truth path for City opportunities beyond the open-data export.
- **CanadaBuys:** Federal tender opportunities and federal award history.
- **Ontario Tenders:** Ontario government and broader public-sector opportunities.
- **TTC / MERX:** Toronto transit solicitations, results, and awarded solicitations posted through MERX.
- **Nearby municipalities:** Mississauga, Brampton, Vaughan, Markham, Richmond Hill, Peel, York, Durham, Halton, Hamilton, and other GTA buyers.
- **bids&tenders / Link2Build:** Construction-heavy and municipal Ontario opportunities.

## Official Nemotron/NIM Resources

These are the official NVIDIA references for the optional local structured extraction layer. They support the implementation story without changing the product boundary: Nemotron/NIM extracts requirements and evidence fields from shortlisted contracts; the deterministic bid engine owns the final `Pursue`, `Review`, `Monitor`, or `Skip` labels.

| Resource | Link | Why it matters |
| --- | --- | --- |
| NVIDIA-NeMo/Nemotron GitHub | [GitHub](https://github.com/NVIDIA-NeMo/Nemotron) | Official Nemotron repository and model family reference. |
| Nemotron Usage Cookbook | [Docs](https://docs.nvidia.com/nemotron/latest/usage-cookbook/README.html) | Practical guidance for using Nemotron models in local and hosted workflows. |
| NVIDIA NIM for LLM API Reference | [Docs](https://docs.nvidia.com/nim/large-language-models/latest/api-reference.html) | API reference for calling NIM-hosted large language models through an OpenAI-compatible interface. |
| NVIDIA NIM Structured Generation Reference | [Docs](https://docs.nvidia.com/nim/vision-language-models/1.1.0/structured-generation.html) | Reference for schema-constrained outputs, which matches the requirement-extraction pattern used by the demo. |

## Dataset Tiers For V1 Planning

- **Must build:** Toronto Bids Solicitations, Toronto Bids Awarded Contracts.
- **Strong stretch:** Toronto Bids Non-Competitive Contracts, Procurement Pipeline.
- **Later expansion:** Business Licences, BIAs, Business Incubation, events, libraries, CafeTO, DineSafe, BodySafe, plus additional procurement feeds listed above.

The V1 demo should stay focused on procurement. Extra datasets should support the story only if they make the owner decision clearer.
