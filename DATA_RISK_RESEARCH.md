# Data Risk Research

Checked: 2026-05-30

This note ranks the Toronto Open Data datasets for the SparkTerritory AI MVP. The goal is not to use the most datasets. The goal is to use the fewest datasets that produce defensible, judge-friendly neighbourhood recommendations for a 2-person window washing business.

## Executive recommendation

Use this as the MVP data spine:

1. `neighbourhoods`
2. `neighbourhood-profiles`
3. `building-permits-active-permits`
4. `building-permits-cleared-permits`
5. `address-points-municipal-toronto-one-address-repository`
6. `development-pipeline`
7. `apartment-building-registration`

Use these only after the spine works:

1. `development-applications`
2. `business-improvement-areas`
3. `municipal-licensing-and-standards-business-licences-and-permits`

Skip or stretch-goal these for v1:

1. `toronto-centreline-tcl`
2. `green-p-parking`
3. `parking-lot-facilities`
4. `311-service-requests-customer-initiated`
5. `zoning-by-law`
6. `property-boundaries`
7. `street-tree-data`

The biggest risk is not downloading data. The biggest risk is correctly joining records to neighbourhoods. Permit records do not include a neighbourhood name, but they do include `GEO_ID`, which can join to Address Points as `ADDRESS_POINT_ID`. That makes Address Points important, even though it is large.

## Most important datasets

| Rank | Dataset | Use in product | Integration risk | Recommendation |
| --- | --- | --- | --- | --- |
| 1 | `neighbourhoods` | Map polygons and final scoring geography | Low | Must use. Use historical 140 if using 2016 profiles, or current 158 if using 2021 profiles. Do not mix them casually. |
| 2 | `neighbourhood-profiles` | Customer fit: income, households, density, housing mix | Medium | Must use. 2016 140 CSV is easiest. 2021 158 XLSX is more current but needs Excel parsing. |
| 3 | `building-permits-active-permits` | Current window-washing demand from active construction, renovations, apartments, residential work | Medium | Must use. Join `GEO_ID` to Address Points, then spatial join to neighbourhoods. Postal FSA is fallback only. |
| 4 | `building-permits-cleared-permits` | Momentum and backtesting from completed construction | Medium | Must use if time allows. Same schema and same `GEO_ID` strategy as active permits. |
| 5 | `address-points-municipal-toronto-one-address-repository` | Converts permit `GEO_ID` into point geometry | Medium-high | Use for a defensible permit-to-neighbourhood join. Large but worth it on DGX Spark. |
| 6 | `development-pipeline` | Future growth: proposed residential units and GFA | Medium | Use. Small and high value, but only has address and ward, not direct neighbourhood. |
| 7 | `apartment-building-registration` | Direct prospect signal for window washing: units, storeys, property manager, address | Medium | Strong addition. Small, directly relevant, and judge-friendly. |

## Dataset details and risks

### `neighbourhoods`

Source: https://open.toronto.ca/dataset/neighbourhoods/

Observed resources:

- Current neighbourhoods: 158 records, GeoJSON datastore active.
- Historical neighbourhoods: 140 records, GeoJSON datastore active.
- Available as CSV, GeoJSON, GPKG, and SHP.

Useful fields:

- `AREA_NAME`
- `AREA_SHORT_CODE`
- `AREA_DESC`
- `geometry`

Risk:

- The main trap is mixing current 158-neighbourhood geometry with 2016 140-neighbourhood profile columns.

Recommendation:

- For speed: use `neighbourhood-profiles-2016-140-model` plus `Neighbourhoods - historical 140`.
- For a more current demo: parse `neighbourhood-profiles-2021-158-model` XLSX plus current `Neighbourhoods`.

### `neighbourhood-profiles`

Source: https://open.toronto.ca/dataset/neighbourhood-profiles/

Observed resources:

- 2021 158-neighbourhood model: XLSX, small, not datastore active in the checked metadata.
- 2016 140-neighbourhood model: CSV, datastore active, about 2,383 rows.
- Older 140-neighbourhood models for 2011, 2006, and 2001.

Useful fields:

- Rows are characteristics, columns are neighbourhoods.
- Need to extract only a small set of characteristics, then transpose to one row per neighbourhood.

Suggested v1 features:

- Population
- Private households
- Average or median household income
- Apartment or multi-unit housing indicators if easy to identify
- Housing density proxies

Risk:

- The file is wide and awkward. Trying to use every row will waste time.

Recommendation:

- Extract 5 to 10 known characteristics and ignore the rest.
- Prefer 2016 CSV if the implementation agent is moving fast.

### `building-permits-active-permits`

Source: https://open.toronto.ca/dataset/building-permits-active-permits/

Observed resources:

- Datastore active CSV resource.
- About 228,691 records at time checked.
- Download CSV about 72 MB.

Useful fields:

- `GEO_ID`
- `POSTAL`
- `APPLICATION_DATE`
- `ISSUED_DATE`
- `STATUS`
- `PERMIT_TYPE`
- `STRUCTURE_TYPE`
- `WORK`
- `DESCRIPTION`
- `CURRENT_USE`
- `PROPOSED_USE`
- `DWELLING_UNITS_CREATED`
- `EST_CONST_COST`
- `RESIDENTIAL`
- `BUSINESS_AND_PERSONAL_SERVICES`
- `MERCANTILE`

Join strategy:

- Best: `GEO_ID` to Address Points `ADDRESS_POINT_ID`, then point-in-polygon join to neighbourhoods.
- Fallback: use `POSTAL` first three characters as FSA and map rough FSAs to market areas.
- Bad fallback: raw street-name matching. Avoid unless necessary.

Why this matters:

- This is the best current-demand signal. Active apartment, mixed-use, residential, renovation, and new-build permits are highly explainable for window washing.

Risk:

- No direct neighbourhood field.
- Some `GEO_ID` values may not match Address Points.
- Active permits can remain open a long time, so recency weighting matters.

Recommendation:

- Use active permits in MVP.
- Weight recent issued/application dates higher.
- Filter or boost `STRUCTURE_TYPE` and `PROPOSED_USE` values related to apartment, residential, mixed-use, commercial, condo-like, and multi-unit work.

### `building-permits-cleared-permits`

Source: https://open.toronto.ca/dataset/building-permits-cleared-permits/

Related official note: https://open.toronto.ca/exploring-cleared-building-permits/

Observed resources:

- Datastore active resource for cleared permits since 2017.
- About 401,005 records at time checked.
- CSV about 130 MB for since-2017 records.
- Older 2000 to 2016 CSV also exists.

Useful fields:

- Same core schema as active permits.
- `COMPLETED_DATE` is especially useful.

Join strategy:

- Same as active permits: `GEO_ID` to Address Points, then spatial join.

Risk:

- Larger than active permits.
- Cleared permits are useful for momentum, but less urgent than active permits for a basic demo.

Recommendation:

- Use since-2017 only.
- Aggregate by neighbourhood and year.
- Use as growth momentum and validation, not the main current demand signal.

### `address-points-municipal-toronto-one-address-repository`

Source: https://open.toronto.ca/dataset/address-points-municipal-toronto-one-address-repository/

Observed resources:

- Datastore active GeoJSON resource.
- About 525,435 records at time checked.
- CSV about 174 MB.
- GeoJSON about 562 MB.
- GPKG about 199 MB.

Useful fields:

- `ADDRESS_POINT_ID`
- `ADDRESS_FULL`
- `GENERAL_USE`
- `WARD`
- `geometry`

Confirmed sample finding:

- Sample permit `GEO_ID` values matched Address Points `ADDRESS_POINT_ID`.
- This gives permit point geometry without geocoding.

Risk:

- Large dataset.
- Spatial join may be the heaviest data step.

Recommendation:

- Include for the judged build if possible because it makes permit mapping defensible.
- On DGX Spark, this is a good place to show why GPU/geospatial processing matters.
- For local laptop fallback, cache a reduced lookup table with only `ADDRESS_POINT_ID`, `WARD`, and point coordinates.

### `development-pipeline`

Source: https://open.toronto.ca/dataset/development-pipeline/

Observed resources:

- Datastore active CSV resource.
- About 2,411 records at time checked.
- CSV about 1.12 MB.

Useful fields:

- `Pipeline Status`
- `Date Received`
- `Description`
- `Address`
- `Ward`
- `Proposed Residential Gross Floor Area`
- `Proposed Non-Residential Gross Floor Area`
- `Proposed Gross Floor Area`
- `Proposed Residential Units`

Risk:

- No direct neighbourhood field.
- No direct coordinate fields in sampled records.
- Address matching may take time.

Recommendation:

- Use it because it is tiny and future-growth value is high.
- In v1, aggregate by ward or address-match through Address Points when possible.
- Use `Proposed Residential Units` and proposed GFA as the main future-growth features.

### `apartment-building-registration`

Source: https://open.toronto.ca/dataset/apartment-building-registration/

Observed resources:

- Datastore active CSV resource.
- About 3,605 records at time checked.
- CSV about 1.49 MB.

Useful fields:

- `SITE_ADDRESS`
- `WARD`
- `PCODE`
- `CONFIRMED_STOREYS`
- `CONFIRMED_UNITS`
- `NO_OF_STOREYS`
- `NO_OF_UNITS`
- `PROP_MANAGEMENT_COMPANY_NAME`
- `WINDOW_TYPE`
- `YEAR_BUILT`
- `YEAR_OF_REPLACEMENT`
- `VISITOR_PARKING`

Why this matters:

- This is the most obviously window-washing-specific prospect dataset.
- It can support evidence like "many registered apartment buildings with high unit/storey counts."
- It can produce a prospect-list feel without needing every parcel in Toronto.

Risk:

- No geometry in sampled records.
- Some duplicate-style columns exist, such as `CONFIRMED_UNITS` and `NO_OF_UNITS`.
- Needs address or FSA/ward approximation for neighbourhood join.

Recommendation:

- Add immediately after active permits and neighbourhood profiles.
- Use it for prospect density and evidence bullets.
- Even ward-level aggregation is useful for demo storytelling.

## Useful but not first

### `development-applications`

Source: https://open.toronto.ca/dataset/development-applications/

Observed resources:

- Datastore active CSV resource.
- About 26,254 records at time checked.
- CSV about 13.32 MB.

Useful fields:

- `APPLICATION_TYPE`
- `DATE_SUBMITTED`
- `STATUS`
- `X`
- `Y`
- `DESCRIPTION`
- `WARD_NUMBER`
- `WARD_NAME`
- `APPLICATION_URL`

Risk:

- Valuable, but overlaps with development pipeline.
- Has coordinates, but those appear to be projected coordinates, so they need coordinate-system handling before spatial joins.
- Unit counts may only exist inside descriptions for many records.

Recommendation:

- Add after development pipeline.
- Use text keywords and status as early-stage future-demand evidence.

### `business-improvement-areas`

Source: https://open.toronto.ca/dataset/business-improvement-areas/

Observed resources:

- Datastore active GeoJSON resource.
- About 86 records at time checked.

Useful fields:

- `AREA_NAME`
- `AREA_DESC`
- `geometry`

Risk:

- Easy data, but not core for residential window washing.

Recommendation:

- Use as a commercial-corridor boost or explanation layer.
- Stronger if the customer focus includes commercial storefronts.

### `municipal-licensing-and-standards-business-licences-and-permits`

Source: https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/

Observed resources:

- Datastore active CSV resource.
- About 158,776 records at time checked.
- CSV about 33 MB.

Useful fields:

- `Category`
- `Operating Name`
- `Issued`
- `Licence Address Line 1`
- `Licence Address Line 3`
- `Ward`
- `Cancel Date`

Risk:

- No geometry.
- Very noisy for a window-washing MVP.
- Includes many categories that are irrelevant.
- Cancelled and stale licences need filtering.

Recommendation:

- Do not use in the first scoring model.
- Add later for commercial prospect density after filtering to relevant categories.

## Stretch or skip for v1

### `toronto-centreline-tcl`

Source: https://open.toronto.ca/dataset/toronto-centreline-tcl/

Observed resources:

- Datastore active GeoJSON resource.
- About 64,441 records.
- CSV about 35 MB, GeoJSON about 89 to 92 MB, GPKG about 28 MB.

Recommendation:

- Skip for v1 unless implementing route/network analysis.
- For the basic demo, use a simpler operational-feasibility score based on distance from base neighbourhood.

### `green-p-parking`

Source: https://open.toronto.ca/dataset/green-p-parking/

Observed resources:

- JSON resources for 2019 and 2015.
- Not datastore active.

Recommendation:

- Skip for MVP.
- Use only as a light parking evidence layer if parsing is trivial.

### `parking-lot-facilities`

Source: https://open.toronto.ca/dataset/parking-lot-facilities/

Observed resources:

- XLSX only.
- Last modified in checked metadata: 2022.
- Main resource appears to be Q3 2016.

Recommendation:

- Skip. It is stale and not worth v1 integration time.

### `311-service-requests-customer-initiated`

Source: https://open.toronto.ca/dataset/311-service-requests-customer-initiated/

Observed resources:

- Annual ZIP files from 2010 through 2026.
- Not datastore active.

Recommendation:

- Skip for v1.
- Could become a service-intensity signal later, especially for pest control, property maintenance, or waste issues.

### `zoning-by-law`

Source: https://open.toronto.ca/dataset/zoning-by-law

Observed resources:

- Many spatial resources and overlays.
- Official portal notes that mapped zoning data must be read with by-law text.

Recommendation:

- Skip for v1.
- Too easy to misuse, too much explanation overhead for the demo.

### `property-boundaries`

Source: https://open.toronto.ca/dataset/property-boundaries/

Observed resources:

- Datastore active.
- Large spatial dataset.

Recommendation:

- Skip for v1.
- Valuable later for parcel-level targeting, but neighbourhood-level scoring is enough for hackathon demo.

### `street-tree-data`

Source: https://open.toronto.ca/dataset/street-tree-data/

Recommendation:

- Skip for window washing.
- More relevant for landscaping, gutter cleaning, and property maintenance variants.

## MVP implementation path

### Step 1: Choose one geography

Fastest:

- `neighbourhood-profiles-2016-140-model`
- `Neighbourhoods - historical 140`

More current:

- `neighbourhood-profiles-2021-158-model`
- current `Neighbourhoods`

Do not mix 2016 140 profiles with current 158 boundaries unless a crosswalk is added.

### Step 2: Build customer-fit table

From neighbourhood profiles, create one row per neighbourhood:

- `neighbourhood_name`
- `population_score`
- `household_score`
- `income_score`
- `apartment_or_density_score`
- `customer_fit_score`

### Step 3: Build permit demand table

From active permits:

- Filter and boost apartment, mixed-use, residential, renovation, new building, and exterior-relevant work.
- Join `GEO_ID` to Address Points `ADDRESS_POINT_ID`.
- Spatially join points to neighbourhood polygons.
- Aggregate counts, estimated construction cost, residential GFA, and dwelling units.

Output:

- `current_demand_score`
- evidence counts for active permit records

### Step 4: Build growth momentum table

From cleared permits since 2017:

- Same join strategy as active permits.
- Aggregate by neighbourhood and year.
- Weight recent completed permits more highly.

Output:

- `growth_momentum_score`
- optional validation/backtest evidence

### Step 5: Build future-growth table

From development pipeline:

- Use proposed residential units and GFA.
- Join by address if possible, otherwise by ward.

Output:

- `future_growth_score`
- evidence bullets such as proposed units and GFA

### Step 6: Add apartment prospect table

From apartment building registration:

- Normalize `CONFIRMED_UNITS`/`NO_OF_UNITS`.
- Normalize `CONFIRMED_STOREYS`/`NO_OF_STOREYS`.
- Aggregate by ward, FSA, or address-matched neighbourhood.
- Keep top prospect examples with property manager names when available.

Output:

- `apartment_prospect_score`
- prospect evidence for window washing

## Recommended v1 scoring weights

For the 2-person window washing demo:

```text
overall_opportunity_score =
  30% active permit demand
+ 20% apartment prospect density
+ 20% future residential growth
+ 15% neighbourhood customer fit
+ 10% cleared-permit growth momentum
+  5% operational feasibility placeholder
```

Why this differs from the generic plan:

- Apartment prospect density deserves real weight because window washing needs targetable buildings and property managers.
- Business licences are less useful for residential window washing than apartment registrations.
- Operational feasibility should stay light until there is real routing.

## Red flags to avoid

- Do not claim exact neighbourhood precision if using only FSA or ward approximations.
- Do not mix 140-profile data with 158-boundary data without explaining it.
- Do not let Nemotron invent evidence. It should only explain scored facts.
- Do not spend early hours on 311, zoning, property boundaries, or parking.
- Do not make downtown automatically win just because it is dense. Penalize operational friction and boost targetable residential/multi-unit prospects.

## Judge-friendly explanation

The strongest data story is:

> We use neighbourhood profiles for customer fit, active permits for current demand, cleared permits for momentum, development pipeline records for future growth, apartment registration for targetable window-washing prospects, and Address Points to map permit `GEO_ID`s into real neighbourhoods. RAPIDS/cuDF accelerates the messy joins and aggregation locally on DGX Spark, while Nemotron explains only the computed evidence.

That is meaningfully stronger than a generic ChatGPT business advisor.
