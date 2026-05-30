# SparkTerritory AI Basic Build Plan

## Summary

**SparkTerritory AI** is a DGX Spark-powered local market expansion agent that turns Toronto Open Data into ranked, evidence-backed neighbourhood recommendations for small commercial building service companies.

Build the v1 as a web app plus backend pipeline. The product framing is **Commercial Building Services**, with **Exterior + Window Cleaning for a 2-person crew** as the default judged demo preset. The system must ingest Toronto datasets, compute neighbourhood opportunity scores locally on DGX Spark using RAPIDS/cuDF, and use Nemotron via a local NIM endpoint to explain the scored evidence and produce a practical 30-day territory plan.

Primary judging track: **Economic Systems**.

## Key Build Blocks

- Add a `BUILD_PLAN.md` file containing this plan, then implement the prototype around one default demo persona:
  - Product category: commercial building services.
  - Default preset: exterior + window cleaning.
  - Business: 2-person exterior glass / facade cleaning company.
  - Base location: configurable, default `Scarborough`.
  - Max travel: configurable, default `30 minutes`.
  - Target customers: residential and multi-unit buildings.

- Build the data pipeline:
  - Download/cache Toronto Open Data from CKAN for:
    - `building-permits-active-permits`
    - `building-permits-cleared-permits`
    - `development-pipeline`
    - `neighbourhood-profiles`
    - `neighbourhoods`
    - `address-points-municipal-toronto-one-address-repository`
    - `apartment-building-registration`
  - Normalize neighbourhood names and join all scored signals to neighbourhoods.
  - Use Address Points as part of the MVP permit-join path because building permit `GEO_ID` values can map to `ADDRESS_POINT_ID`, enabling defensible point-to-neighbourhood spatial joins instead of postal-code approximations.
  - Use Apartment Building Registration as a direct prospect-density signal for recurring B2B service contracts.
  - Prefer the 2016 140-neighbourhood profile CSV for v1 because it is easier to process reliably in 24 hours; document 2021/158 as a post-MVP upgrade.

- Build the scoring engine:
  - `current_demand_score`: active residential/multi-unit/commercial permits, estimated construction cost, dwelling units created where available.
  - `growth_momentum_score`: cleared permits since 2017 and recent construction activity.
  - `future_growth_score`: proposed residential units and proposed gross floor area from development pipeline.
  - `prospect_density_score`: apartment registrations, multi-unit buildings, and commercial-corridor proxies where available.
  - `customer_fit_score`: neighbourhood profile indicators such as income, households, density proxies, and housing type if available.
  - `overall_opportunity_score`: weighted result:
    - 35% current demand
    - 20% future growth
    - 15% prospect density
    - 15% customer fit
    - 10% growth momentum
    - 5% operational feasibility placeholder based on base-neighbourhood distance/category until routing is added.

- Make NVIDIA integration central:
  - Run the scoring pipeline on DGX Spark with RAPIDS/cuDF as the default dataframe engine.
  - Use pandas/stdlib only as a local development fallback, clearly labeled as non-demo fallback.
  - Run Nemotron through a local NIM endpoint on DGX Spark.
  - Nemotron receives only structured scored evidence and must produce grounded recommendations; it should not invent unsupported neighbourhood claims.
  - No GPT/OpenAI API calls in the judged demo.

- Build the app experience:
  - Web app first screen is the actual tool, not a landing page.
  - Inputs: business preset, crew size, base neighbourhood, max travel minutes, residential/commercial preference, and priority mode such as balanced/growth/low-friction/high-value prospects.
  - Outputs:
    - Top 5 target neighbourhoods now.
    - Top 3 future expansion neighbourhoods.
    - Score breakdown for each area.
    - Confidence level with a plain-English reason.
    - Prospect density and suggested sales targets.
    - Constraints or negative tradeoffs for each recommendation.
    - Evidence bullets from the raw data.
    - Nemotron-generated 30-day action plan.
    - "Why not downtown?" style tradeoff explanation if a dense area is not recommended.
  - UI should use operator language: "Best next zone", "Why this area wins", "Sales targets nearby", and "Crew feasibility".
  - Include a compact NVIDIA Spark evidence strip showing pipeline steps, RAPIDS/cuDF status, local NIM/Nemotron status, and timing/fallback status.

## Interfaces

Backend input shape:

```json
{
  "business_preset": "exterior_window_cleaning",
  "crew_size": 2,
  "base_neighbourhood": "Scarborough Village",
  "max_travel_minutes": 30,
  "customer_focus": "residential",
  "priority_mode": "balanced"
}
```

Backend output shape:

```json
{
  "ranked_neighbourhoods": [
    {
      "name": "Willowdale East",
      "overall_score": 87,
      "current_demand_score": 82,
      "future_growth_score": 91,
      "customer_fit_score": 84,
      "prospect_density_score": 79,
      "growth_momentum_score": 76,
      "operational_feasibility_score": 70,
      "confidence": "High",
      "confidence_reason": "Permit, development, apartment, and neighbourhood-profile signals all point in the same direction.",
      "prospect_count": 42,
      "top_positive_factors": [
        "Strong active permit signal",
        "High apartment/prospect density"
      ],
      "top_negative_factors": [
        "Longer drive from Scarborough base than east-end targets"
      ],
      "evidence": [
        "High active residential/multi-unit permit activity",
        "Strong proposed residential units in development pipeline",
        "Strong customer-fit indicators from neighbourhood profile"
      ],
      "recommended_action": "Target condo boards and property managers with post-construction exterior window cleaning packages."
    }
  ],
  "agent_report": "Nemotron-generated grounded summary here."
}
```

Nemotron prompt contract:

- System role: local market expansion analyst for Toronto service businesses.
- Inputs: business profile, score weights, ranked neighbourhood JSON, and evidence.
- Required output: concise recommendations, action plan, risks, prospecting targets, and expansion timing.
- Constraint: every recommendation must reference provided evidence.

## Judging Optimization

- Technical execution:
  - Demonstrate full workflow: raw Toronto Open Data -> cleaning -> scoring -> ranked output -> agent explanation -> web app.
  - Show custom scoring logic, not a static dashboard.

- NVIDIA ecosystem:
  - Demo runs on DGX Spark.
  - RAPIDS/cuDF powers processing.
  - Nemotron/NIM powers grounded agent reasoning.
  - Pitch Spark utility as local inference, privacy, fast geospatial/data scoring, and repeatable what-if scenario simulation.

- Value and impact:
  - The demo answers a real small-business question: "Where should I sell this month, and where should I expand next?"
  - The output must be specific enough for action: neighbourhoods, reasoning, target customer, suggested offer.

- Innovation:
  - Position the product as civic open data repurposed for small-business market intelligence.
  - Emphasize that ChatGPT can give generic advice, but this system computes evidence-backed territory scores from live city data.

## 24-Hour Build Order

1. Create the plan file and project skeleton.
2. Build dataset download/cache scripts.
3. Load active permits, cleared permits, Address Points, development pipeline, apartment registrations, neighbourhood profiles, and neighbourhood boundaries.
4. Produce first ranked neighbourhood JSON without Nemotron.
5. Add RAPIDS/cuDF execution path on DGX Spark.
6. Add Nemotron/NIM report generation from scored JSON.
7. Build the web app with inputs, ranked table, evidence cards, and report panel.
8. Add a simple map or neighbourhood list visualization if time allows.
9. Prepare demo script, screenshots, and fallback cached data.
10. Final validation on DGX Spark.

## Test Plan

- Data tests:
  - Dataset download succeeds or uses cached files.
  - Required columns are present for each dataset.
  - Permit `GEO_ID` values map to Address Point `ADDRESS_POINT_ID` when available.
  - Address Points spatially join permit records into scored neighbourhoods.
  - Neighbourhood normalization maps remaining records into scored neighbourhoods.
  - Empty or missing numeric fields do not crash scoring.

- Scoring tests:
  - Scores are normalized to 0-100.
  - Weighted `overall_opportunity_score` matches the documented formula.
  - Top ranked areas include evidence bullets from at least two data sources.
  - Confidence level drops when a neighbourhood is missing key data sources.

- Nemotron tests:
  - Local NIM endpoint responds.
  - Agent report references scored evidence.
  - Agent refuses or qualifies claims not present in the input evidence.

- Demo tests:
  - Web app loads on the DGX Spark environment.
  - Default scenario produces top 5 current targets and top 3 future expansion areas.
  - Changing base neighbourhood or travel minutes changes the recommendation output.
  - Cached-data fallback works if Toronto Open Data is temporarily unavailable.

## Assumptions

- V1 product framing is **Commercial Building Services** with **Exterior + Window Cleaning** as the default demo preset because it is the clearest and most judge-friendly use case.
- V1 demo surface is a **web app**.
- The judged run assumes **full local DGX Spark execution** with RAPIDS/cuDF and Nemotron through NIM.
- Route optimization with cuOpt is a stretch goal, not required for the basic build.
- The first version uses neighbourhood-level scoring, not exact parcel-level prospecting.
- Address Points are in-scope for MVP joins; exact parcel-level prospecting remains post-MVP.
- The plan should be saved as `BUILD_PLAN.md` before implementation begins.
