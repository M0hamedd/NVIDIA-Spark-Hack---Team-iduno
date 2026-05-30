from __future__ import annotations

from contract_radar.models import AwardRecord, Solicitation


SAMPLE_SOLICITATION_RECORDS = [
    {
        "Document Number": "RFQ-2026-1001",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Solicitation Document Description": (
            "Preventative maintenance, emergency repairs, boiler service, chiller service, "
            "and building automation systems (BAS) controls support for HVAC equipment at "
            "City-operated libraries, recreation centres, and municipal facilities."
        ),
        "Division": "Corporate Real Estate Management",
        "Issue Date": "2026-05-29",
        "Submission Deadline": "2026-06-18",
        "Buyer Name": "Maya Patel",
        "Buyer Email": "maya.patel@toronto.ca",
        "Buyer Phone Number": "416-555-0142",
        "Wards": "Toronto and East York",
    },
    {
        "Document Number": "RFP-2026-2210",
        "RFx (Solicitation) Type": "Request for Proposal",
        "High Level Category": "Professional Services",
        "Solicitation Document Description": (
            "Pure software implementation for an enterprise facilities analytics platform, "
            "including data migration, licensing, training, and multi-year managed services."
        ),
        "Division": "Technology Services",
        "Issue Date": "2026-05-20",
        "Submission Deadline": "2026-06-28",
        "Buyer Name": "Daniel Chen",
        "Buyer Email": "daniel.chen@toronto.ca",
        "Buyer Phone Number": "416-555-0188",
        "Wards": "All",
    },
    {
        "Document Number": "RFSQ-2026-3304",
        "RFx (Solicitation) Type": "Request for Supplier Qualification",
        "High Level Category": "Construction Services",
        "Solicitation Document Description": (
            "Major design-build construction for a new public works facility including "
            "structural work, electrical upgrades, full mechanical systems, and "
            "bonding-required general contractor delivery."
        ),
        "Division": "Corporate Real Estate Management",
        "Issue Date": "2026-05-16",
        "Submission Deadline": "2026-06-25",
        "Buyer Name": "Avery Morgan",
        "Buyer Email": "avery.morgan@toronto.ca",
        "Buyer Phone Number": "416-555-0199",
        "Wards": "Scarborough",
    },
    {
        "Document Number": "RFQ-2026-0415",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Solicitation Document Description": (
            "Road paving, curb repair, line painting, and streetscape landscaping services "
            "for multiple municipal road corridors."
        ),
        "Division": "Transportation Services",
        "Issue Date": "2026-04-01",
        "Submission Deadline": "2026-04-15",
        "Buyer Name": "Samira Ali",
        "Buyer Email": "samira.ali@toronto.ca",
        "Buyer Phone Number": "416-555-0120",
        "Wards": "All",
    },
    {
        "Document Number": "RFQ-2026-1442",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Solicitation Document Description": (
            "Emergency mechanical repairs and seasonal HVAC maintenance for arenas, "
            "community centres, and public facility service locations, including rooftop "
            "units and BAS controls troubleshooting."
        ),
        "Division": "Parks, Forestry and Recreation",
        "Issue Date": "2026-05-27",
        "Submission Deadline": "2026-06-14",
        "Buyer Name": "Renee Wallace",
        "Buyer Email": "renee.wallace@toronto.ca",
        "Buyer Phone Number": "416-555-0164",
        "Wards": "Etobicoke York",
    },
    {
        "Document Number": "RFQ-2026-1775",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Solicitation Document Description": (
            "Supply and delivery of packaged food, beverages, and disposable serving "
            "materials for summer recreation programs."
        ),
        "Division": "Parks, Forestry and Recreation",
        "Issue Date": "2026-05-22",
        "Submission Deadline": "2026-06-12",
        "Buyer Name": "Noah Singh",
        "Buyer Email": "noah.singh@toronto.ca",
        "Buyer Phone Number": "416-555-0177",
        "Wards": "All",
    },
]


SAMPLE_AWARD_RECORDS = [
    {
        "Document Number": "RFQ-2025-9088",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Successful Supplier": "Metro Mechanical Service Inc.",
        "Award": "$126,450.00",
        "Award Authority Obtained Date": "2025-09-15",
        "Division": "Corporate Real Estate Management",
        "Solicitation Document Description": (
            "Preventative maintenance, emergency repairs, and BAS controls troubleshooting "
            "for HVAC equipment at libraries and municipal office facilities."
        ),
    },
    {
        "Document Number": "RFQ-2024-7711",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Successful Supplier": "East End HVAC Maintenance",
        "Award": "$84,900.00",
        "Award Authority Obtained Date": "2024-11-04",
        "Division": "Parks, Forestry and Recreation",
        "Solicitation Document Description": (
            "Inspection, repair, and seasonal HVAC maintenance for arenas, recreation "
            "centres, rooftop units, boilers, and chillers."
        ),
    },
    {
        "Document Number": "RFSQ-2025-3350",
        "RFx (Solicitation) Type": "Request for Supplier Qualification",
        "High Level Category": "Construction Services",
        "Successful Supplier": "Ontario Institutional Builders Ltd.",
        "Award": "$2,850,000.00",
        "Award Authority Obtained Date": "2025-08-19",
        "Division": "Corporate Real Estate Management",
        "Solicitation Document Description": (
            "Design-build construction of a municipal facility with full mechanical, "
            "electrical, structural, and general contractor scope."
        ),
    },
    {
        "Document Number": "RFQ-2025-6120",
        "RFx (Solicitation) Type": "Request for Quotation",
        "High Level Category": "Goods and Services",
        "Successful Supplier": "Controls North Ltd.",
        "Award": "$142,300.00",
        "Award Authority Obtained Date": "2025-05-21",
        "Division": "Toronto Public Library",
        "Solicitation Document Description": (
            "Building automation systems support, BAS controls calibration, energy retrofit "
            "support, and preventative maintenance for public library branches."
        ),
    },
]


def sample_solicitations() -> list[Solicitation]:
    return [Solicitation.from_record(record) for record in SAMPLE_SOLICITATION_RECORDS]


def sample_awards() -> list[AwardRecord]:
    return [AwardRecord.from_record(record) for record in SAMPLE_AWARD_RECORDS]
