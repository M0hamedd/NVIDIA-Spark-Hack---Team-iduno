from __future__ import annotations


SAMPLE_NEIGHBOURHOODS = {
    "Scarborough Village": {
        "number": 139,
        "district": "Scarborough",
        "population": 16724,
        "density": 4100,
        "dwellings": 6400,
        "highrise_apartments": 2400,
        "avg_income": 39500,
    },
    "Woburn": {
        "number": 137,
        "district": "Scarborough",
        "population": 53485,
        "density": 4300,
        "dwellings": 17200,
        "highrise_apartments": 5200,
        "avg_income": 38000,
    },
    "Willowdale East": {
        "number": 51,
        "district": "North York",
        "population": 50434,
        "density": 8800,
        "dwellings": 28800,
        "highrise_apartments": 19500,
        "avg_income": 57000,
    },
    "Mimico (includes Humber Bay Shores)": {
        "number": 17,
        "district": "Etobicoke",
        "population": 33964,
        "density": 6100,
        "dwellings": 18200,
        "highrise_apartments": 10400,
        "avg_income": 62000,
    },
    "Waterfront Communities-The Island": {
        "number": 77,
        "district": "Downtown",
        "population": 65913,
        "density": 14200,
        "dwellings": 44600,
        "highrise_apartments": 36000,
        "avg_income": 61000,
    },
    "The Beaches": {
        "number": 63,
        "district": "East York",
        "population": 21567,
        "density": 5600,
        "dwellings": 9300,
        "highrise_apartments": 1200,
        "avg_income": 73000,
    },
    "High Park-Swansea": {
        "number": 87,
        "district": "West Toronto",
        "population": 23925,
        "density": 5900,
        "dwellings": 11800,
        "highrise_apartments": 4700,
        "avg_income": 67000,
    },
    "Yonge-Eglinton": {
        "number": 100,
        "district": "Central Toronto",
        "population": 11817,
        "density": 11200,
        "dwellings": 7200,
        "highrise_apartments": 4200,
        "avg_income": 88000,
    },
}

SAMPLE_CURRENT_BY_DISTRICT = {
    "Scarborough": {"records": 840, "weighted_value": 1280, "cost": 325000000, "units": 920},
    "North York": {"records": 920, "weighted_value": 1650, "cost": 520000000, "units": 1700},
    "Downtown": {"records": 760, "weighted_value": 1540, "cost": 610000000, "units": 2100},
    "Etobicoke": {"records": 620, "weighted_value": 1180, "cost": 390000000, "units": 1400},
    "East York": {"records": 430, "weighted_value": 820, "cost": 210000000, "units": 720},
    "West Toronto": {"records": 510, "weighted_value": 930, "cost": 275000000, "units": 860},
    "Central Toronto": {"records": 480, "weighted_value": 1010, "cost": 360000000, "units": 900},
}

SAMPLE_GROWTH_BY_DISTRICT = {
    "Scarborough": {"records": 4200, "weighted_value": 7600, "cost": 1400000000, "units": 4200},
    "North York": {"records": 5100, "weighted_value": 9100, "cost": 2200000000, "units": 6100},
    "Downtown": {"records": 4700, "weighted_value": 8800, "cost": 2600000000, "units": 7800},
    "Etobicoke": {"records": 3900, "weighted_value": 6900, "cost": 1700000000, "units": 5000},
    "East York": {"records": 2500, "weighted_value": 4200, "cost": 850000000, "units": 2600},
    "West Toronto": {"records": 3300, "weighted_value": 5700, "cost": 1200000000, "units": 3800},
    "Central Toronto": {"records": 2900, "weighted_value": 5200, "cost": 1100000000, "units": 3200},
}

SAMPLE_FUTURE_BY_DISTRICT = {
    "Scarborough": {"applications": 120, "residential_units": 8700, "gross_floor_area": 1400000},
    "North York": {"applications": 135, "residential_units": 12500, "gross_floor_area": 1900000},
    "Downtown": {"applications": 160, "residential_units": 15000, "gross_floor_area": 2200000},
    "Etobicoke": {"applications": 105, "residential_units": 9500, "gross_floor_area": 1500000},
    "East York": {"applications": 74, "residential_units": 5200, "gross_floor_area": 800000},
    "West Toronto": {"applications": 92, "residential_units": 6800, "gross_floor_area": 1000000},
    "Central Toronto": {"applications": 88, "residential_units": 6200, "gross_floor_area": 900000},
}
