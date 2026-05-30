# Toronto Open Data Datasets To Obtain

This project should use Toronto open data to score service-area opportunity for small service businesses such as window washing, HVAC, cleaning, landscaping, pest control, and maintenance crews.

## Core datasets

| Priority | Dataset | Package name | Why it matters |
| --- | --- | --- | --- |
| Must have | [Building Permits - Active Permits](https://open.toronto.ca/dataset/building-permits-active-permits/) | `building-permits-active-permits` | Best signal for current construction, renovation, new building work, and near-term service demand. |
| Must have | [Building Permits - Cleared Permits](https://open.toronto.ca/dataset/building-permits-cleared-permits/) | `building-permits-cleared-permits` | Historical construction trend signal. Use it to learn which neighbourhoods are growing or renovating over time. |
| Must have | [Development Pipeline](https://open.toronto.ca/dataset/development-pipeline/) | `development-pipeline` | Future growth signal: where residential, mixed-use, and commercial capacity is expected to appear. |
| Must have | [Development Applications](https://open.toronto.ca/dataset/development-applications/) | `development-applications` | Earlier-stage future demand signal before construction permits appear. |
| Must have | [Neighbourhood Profiles](https://open.toronto.ca/dataset/neighbourhood-profiles/) | `neighbourhood-profiles` | Income, housing, household, population, and demographic context for estimating demand and ability to pay. |
| Must have | [Neighbourhoods](https://open.toronto.ca/dataset/neighbourhoods/) | `neighbourhoods` | Boundary layer for aggregating permit, income, route, and demand scores into explainable service zones. |
| Must have | [Toronto Centreline (TCL)](https://open.toronto.ca/dataset/toronto-centreline-tcl/) | `toronto-centreline-tcl` | Road network base for routing, drive-time estimates, and crew coverage analysis. |
| Must have | [Address Points (Municipal) - Toronto One Address Repository](https://open.toronto.ca/dataset/address-points-municipal-toronto-one-address-repository/) | `address-points-municipal-toronto-one-address-repository` | Helps geocode and spatially join permit records, properties, and service locations. |

## Strong additions

| Priority | Dataset | Package name | Why it matters |
| --- | --- | --- | --- |
| Should have | [Municipal Licensing and Standards - Business Licences and Permits](https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/) | `municipal-licensing-and-standards-business-licences-and-permits` | Useful for estimating business density, possible customers, and competitor/prospect locations. |
| Should have | [Property Boundaries](https://open.toronto.ca/dataset/property-boundaries/) | `property-boundaries` | Parcel-level geometry for spatial joins, density, and property-level opportunity analysis. |
| Should have | [Zoning By-law](https://open.toronto.ca/dataset/zoning-by-law/) | `zoning-by-law` | Helps distinguish residential, commercial, mixed-use, industrial, height, and density potential. |
| Should have | [Committee of Adjustment Applications](https://open.toronto.ca/dataset/committee-of-adjustment-applications/) | `committee-of-adjustment-applications` | Good signal for small-scale infill, additions, and renovations that may create local service demand. |
| Should have | [Business Improvement Areas](https://open.toronto.ca/dataset/business-improvement-areas/) | `business-improvement-areas` | Useful for identifying dense commercial corridors and local business clusters. |
| Should have | [Parking Lot Facilities](https://open.toronto.ca/dataset/parking-lot-facilities/) | `parking-lot-facilities` | Useful for operational feasibility: where crews can park near target service zones. |
| Should have | [Green P Parking](https://open.toronto.ca/dataset/green-p-parking/) | `green-p-parking` | Another parking/crew logistics layer for route planning and service-zone practicality. |

## Optional datasets for richer scoring

| Priority | Dataset | Package name | Why it matters |
| --- | --- | --- | --- |
| Optional | [311 Service Requests - Customer Initiated](https://open.toronto.ca/dataset/311-service-requests-customer-initiated/) | `311-service-requests-customer-initiated` | Proxy for civic maintenance issues and neighbourhood service intensity. |
| Optional | [Traffic Signal Vehicle and Pedestrian Volumes](https://open.toronto.ca/dataset/traffic-signal-vehicle-and-pedestrian-volumes/) | `traffic-signal-vehicle-and-pedestrian-volumes` | Helps estimate congestion and operational friction for service crews. |
| Optional | [Traffic Volumes - Multimodal Intersection Turning Movement Counts](https://open.toronto.ca/dataset/traffic-volumes-at-intersections-for-all-modes/) | `traffic-volumes-at-intersections-for-all-modes` | More detailed movement data for route difficulty and travel-time penalties. |
| Optional | [Current Value Assessment (CVA) Tax Impact Residential Properties](https://open.toronto.ca/dataset/current-value-assessment-cva-tax-impact-residential-properties/) | `current-value-assessment-cva-tax-impact-residential-properties` | Possible proxy for property value and willingness to pay, if the granularity is useful. |
| Optional | [Street Tree Data](https://open.toronto.ca/dataset/street-tree-data/) | `street-tree-data` | Useful for vertical-specific opportunities like gutter cleaning, landscaping, window obstruction, and property maintenance. |
| Optional | [Heritage Register](https://open.toronto.ca/dataset/heritage-register/) | `heritage-register` | Useful for specialized service constraints and premium maintenance opportunities around older buildings. |
| Optional | [School Locations - All Types](https://open.toronto.ca/dataset/school-locations-all-types/) | `school-locations-all-types` | Useful for B2B service prospects and neighbourhood anchors. |
| Optional | [Apartment Building Registration](https://open.toronto.ca/dataset/apartment-building-registration/) | `apartment-building-registration` | Strong prospect list for window washing, HVAC, pest control, cleaning, and property maintenance if available and current. |

## Recommended first prototype bundle

Start with these 8 datasets:

1. `building-permits-active-permits`
2. `building-permits-cleared-permits`
3. `development-pipeline`
4. `development-applications`
5. `neighbourhood-profiles`
6. `neighbourhoods`
7. `toronto-centreline-tcl`
8. `municipal-licensing-and-standards-business-licences-and-permits`

This is enough to build a strong hackathon demo:

- Score current demand from active permits.
- Score growth momentum from cleared permits.
- Score future expansion from development applications and pipeline data.
- Score customer quality from neighbourhood profiles.
- Score operational feasibility from road geography.
- Generate an agentic recommendation report for a specific small business profile.
