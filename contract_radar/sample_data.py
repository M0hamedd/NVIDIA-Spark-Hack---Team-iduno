from __future__ import annotations

from contract_radar.models import AwardRecord, Solicitation


SAMPLE_SOLICITATION_RECORDS = [
    {
        "Document Number": "RFQ-2026-RC-101",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Construction Services",
        "Solicitation Document Description": (
            "Road resurfacing, asphalt paving, curb repair, concrete sidewalk replacement, "
            "minor drainage restoration, traffic control, and pavement markings for local "
            "municipal road corridors."
        ),
        "Division": "Transportation Services",
        "Issue Date": "2026-05-29",
        "Submission Deadline": "2026-06-22",
        "Buyer Name": "Maya Patel",
        "Buyer Email": "maya.patel@toronto.ca",
        "Buyer Phone Number": "416-555-0142",
        "Wards": "North York",
        "Demo Profile": "road_civil_infrastructure",
        "Demo Role": "strong_fit",
    },
    {
        "Document Number": "RFP-2026-RC-202",
        "RFx (Solicitation) Type": "Request for Proposal",
        "High Level Category": "Professional Services",
        "Solicitation Document Description": (
            "Transportation asset management software implementation for road condition "
            "analytics, data migration, SaaS licensing, dashboards, training, and multi-year "
            "managed services for pavement planning."
        ),
        "Division": "Technology Services",
        "Issue Date": "2026-05-20",
        "Submission Deadline": "2026-06-28",
        "Buyer Name": "Daniel Chen",
        "Buyer Email": "daniel.chen@toronto.ca",
        "Buyer Phone Number": "416-555-0188",
        "Wards": "All",
        "Demo Profile": "road_civil_infrastructure",
        "Demo Role": "false_positive",
    },
    {
        "Document Number": "RFQ-2026-RC-303",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Construction Services",
        "Solicitation Document Description": (
            "Urgent pothole repair, asphalt patching, curb reinstatement, catch basin frame "
            "adjustments, sidewalk trip hazard repair, and traffic control at multiple road "
            "and laneway locations."
        ),
        "Division": "Transportation Services",
        "Issue Date": "2026-05-28",
        "Submission Deadline": "2026-06-03",
        "Buyer Name": "Avery Morgan",
        "Buyer Email": "avery.morgan@toronto.ca",
        "Buyer Phone Number": "416-555-0199",
        "Wards": "Scarborough",
        "Demo Profile": "road_civil_infrastructure",
        "Demo Role": "capacity_deadline_warning",
    },
    {
        "Document Number": "RFQ-2026-PL-111",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Construction Services",
        "Solicitation Document Description": (
            "Park improvements including playground surfacing repairs, trail resurfacing, "
            "planting beds, topsoil supply, sod restoration, site furnishings, and fencing "
            "at neighbourhood parks."
        ),
        "Division": "Parks, Forestry and Recreation",
        "Issue Date": "2026-05-26",
        "Submission Deadline": "2026-06-21",
        "Buyer Name": "Samira Ali",
        "Buyer Email": "samira.ali@toronto.ca",
        "Buyer Phone Number": "416-555-0120",
        "Wards": "Toronto and East York",
        "Demo Profile": "parks_landscape",
        "Demo Role": "strong_fit",
    },
    {
        "Document Number": "RFQ-2026-PL-222",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Solicitation Document Description": (
            "Supply and delivery of packaged food, beverages, compostable plates, and "
            "disposable serving materials for summer recreation programs in parks."
        ),
        "Division": "Parks, Forestry and Recreation",
        "Issue Date": "2026-05-22",
        "Submission Deadline": "2026-06-12",
        "Buyer Name": "Renee Wallace",
        "Buyer Email": "renee.wallace@toronto.ca",
        "Buyer Phone Number": "416-555-0164",
        "Wards": "All",
        "Demo Profile": "parks_landscape",
        "Demo Role": "false_positive",
    },
    {
        "Document Number": "RFQ-2026-PL-333",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Solicitation Document Description": (
            "Urgent arborist services, tree pruning, stump grinding, storm-damaged limb "
            "removal, trail clearing, planting restoration, and sports field turf repairs "
            "across city parks."
        ),
        "Division": "Parks, Forestry and Recreation",
        "Issue Date": "2026-05-28",
        "Submission Deadline": "2026-06-03",
        "Buyer Name": "Noah Singh",
        "Buyer Email": "noah.singh@toronto.ca",
        "Buyer Phone Number": "416-555-0177",
        "Wards": "Etobicoke York",
        "Demo Profile": "parks_landscape",
        "Demo Role": "capacity_deadline_warning",
    },
    {
        "Document Number": "RFP-2026-ED-121",
        "RFx (Solicitation) Type": "Request for Proposal",
        "High Level Category": "Professional Services",
        "Solicitation Document Description": (
            "Professional engineering services for preliminary design, detailed design, "
            "traffic safety review, public realm accessibility upgrades, tender support, "
            "construction inspection, and contract administration for complete street work."
        ),
        "Division": "Transportation Services",
        "Issue Date": "2026-05-24",
        "Submission Deadline": "2026-06-26",
        "Buyer Name": "Priya Desai",
        "Buyer Email": "priya.desai@toronto.ca",
        "Buyer Phone Number": "416-555-0135",
        "Wards": "All",
        "Demo Profile": "professional_engineering_design",
        "Demo Role": "strong_fit",
    },
    {
        "Document Number": "RFQ-2026-ED-242",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Construction Services",
        "Solicitation Document Description": (
            "Construction services for asphalt road paving, curb replacement, pavement "
            "markings, traffic control, equipment, labour, materials, and general contractor "
            "site delivery. No design or contract administration scope is included."
        ),
        "Division": "Transportation Services",
        "Issue Date": "2026-05-27",
        "Submission Deadline": "2026-06-19",
        "Buyer Name": "Liam Roberts",
        "Buyer Email": "liam.roberts@toronto.ca",
        "Buyer Phone Number": "416-555-0151",
        "Wards": "Scarborough",
        "Demo Profile": "professional_engineering_design",
        "Demo Role": "false_positive",
    },
    {
        "Document Number": "RFP-2026-ED-363",
        "RFx (Solicitation) Type": "Request for Proposal",
        "High Level Category": "Professional Services",
        "Solicitation Document Description": (
            "Urgent bridge condition assessment, structural engineering review, preliminary "
            "design, detailed design drawings, environmental assessment support, construction "
            "inspection, and contract administration for state-of-good-repair work."
        ),
        "Division": "Transportation Services",
        "Issue Date": "2026-05-29",
        "Submission Deadline": "2026-06-04",
        "Buyer Name": "Olivia Brooks",
        "Buyer Email": "olivia.brooks@toronto.ca",
        "Buyer Phone Number": "416-555-0194",
        "Wards": "All",
        "Demo Profile": "professional_engineering_design",
        "Demo Role": "capacity_deadline_warning",
    },
]


SAMPLE_AWARD_RECORDS = [
    {
        "Document Number": "RFQ-2025-RC-718",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Construction Services",
        "Successful Supplier": "GTA Roadworks Ltd.",
        "Award": "$418,600.00",
        "Award Authority Obtained Date": "2025-09-15",
        "Division": "Transportation Services",
        "Solicitation Document Description": (
            "Road resurfacing, asphalt paving, curb repair, concrete sidewalk replacement, "
            "traffic control, and pavement markings for local municipal road corridors."
        ),
    },
    {
        "Document Number": "RFQ-2025-RC-443",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Construction Services",
        "Successful Supplier": "Urban Asphalt Repair Corp.",
        "Award": "$186,250.00",
        "Award Authority Obtained Date": "2025-04-28",
        "Division": "Transportation Services",
        "Solicitation Document Description": (
            "Urgent pothole repair, asphalt patching, curb reinstatement, catch basin frame "
            "adjustments, sidewalk trip hazard repair, and traffic control."
        ),
    },
    {
        "Document Number": "RFQ-2025-PL-612",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Construction Services",
        "Successful Supplier": "Green Acre Parkworks Inc.",
        "Award": "$264,900.00",
        "Award Authority Obtained Date": "2025-08-19",
        "Division": "Parks, Forestry and Recreation",
        "Solicitation Document Description": (
            "Park improvements with playground surfacing repairs, trail resurfacing, "
            "planting beds, topsoil, sod restoration, site furnishings, and fencing."
        ),
    },
    {
        "Document Number": "RFQ-2025-PL-884",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Successful Supplier": "Canopy Arbor Services Ltd.",
        "Award": "$98,750.00",
        "Award Authority Obtained Date": "2025-05-21",
        "Division": "Parks, Forestry and Recreation",
        "Solicitation Document Description": (
            "Arborist services, tree pruning, stump grinding, storm-damaged limb removal, "
            "trail clearing, planting restoration, and sports field turf repairs."
        ),
    },
    {
        "Document Number": "RFP-2025-ED-531",
        "RFx (Solicitation) Type": "Request for Proposal",
        "High Level Category": "Professional Services",
        "Successful Supplier": "Civic Design Partners",
        "Award": "$642,000.00",
        "Award Authority Obtained Date": "2025-10-02",
        "Division": "Transportation Services",
        "Solicitation Document Description": (
            "Professional engineering services for preliminary design, detailed design, "
            "traffic safety review, accessibility upgrades, tender support, construction "
            "inspection, and contract administration for complete street work."
        ),
    },
    {
        "Document Number": "RFP-2025-ED-774",
        "RFx (Solicitation) Type": "Request for Proposal",
        "High Level Category": "Professional Services",
        "Successful Supplier": "Harbour Structural Engineering",
        "Award": "$528,400.00",
        "Award Authority Obtained Date": "2025-06-17",
        "Division": "Transportation Services",
        "Solicitation Document Description": (
            "Bridge condition assessment, structural engineering review, preliminary design, "
            "detailed design drawings, environmental assessment support, construction "
            "inspection, and contract administration."
        ),
    },
]


def sample_solicitations() -> list[Solicitation]:
    return [Solicitation.from_record(record) for record in SAMPLE_SOLICITATION_RECORDS]


def sample_awards() -> list[AwardRecord]:
    return [AwardRecord.from_record(record) for record in SAMPLE_AWARD_RECORDS]
