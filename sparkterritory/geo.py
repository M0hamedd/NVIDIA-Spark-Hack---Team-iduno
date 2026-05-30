from __future__ import annotations

from sparkterritory.utils import normalize_name


FSA_TO_DISTRICT = {
    "M1": "Scarborough",
    "M2": "North York",
    "M3": "North York",
    "M4": "East York",
    "M5": "Downtown",
    "M6": "West Toronto",
    "M7": "Mississauga",
    "M8": "Etobicoke",
    "M9": "Etobicoke",
}

WARD_TO_DISTRICT = {
    1: "Etobicoke",
    2: "Etobicoke",
    3: "Etobicoke",
    4: "West Toronto",
    5: "West Toronto",
    6: "North York",
    7: "North York",
    8: "Central Toronto",
    9: "West Toronto",
    10: "Downtown",
    11: "Downtown",
    12: "Central Toronto",
    13: "Downtown",
    14: "East York",
    15: "Central Toronto",
    16: "North York",
    17: "North York",
    18: "North York",
    19: "East York",
    20: "Scarborough",
    21: "Scarborough",
    22: "Scarborough",
    23: "Scarborough",
    24: "Scarborough",
    25: "Scarborough",
}

DISTRICT_DISTANCE = {
    "Scarborough": {
        "Scarborough": 0,
        "East York": 1,
        "North York": 1,
        "Central Toronto": 2,
        "Downtown": 2,
        "West Toronto": 3,
        "Etobicoke": 4,
    },
    "East York": {
        "East York": 0,
        "Scarborough": 1,
        "Downtown": 1,
        "Central Toronto": 1,
        "North York": 1,
        "West Toronto": 2,
        "Etobicoke": 3,
    },
    "North York": {
        "North York": 0,
        "Scarborough": 1,
        "Central Toronto": 1,
        "East York": 1,
        "Downtown": 2,
        "West Toronto": 2,
        "Etobicoke": 2,
    },
    "Central Toronto": {
        "Central Toronto": 0,
        "Downtown": 1,
        "North York": 1,
        "East York": 1,
        "West Toronto": 2,
        "Scarborough": 2,
        "Etobicoke": 3,
    },
    "Downtown": {
        "Downtown": 0,
        "Central Toronto": 1,
        "East York": 1,
        "West Toronto": 1,
        "North York": 2,
        "Scarborough": 2,
        "Etobicoke": 3,
    },
    "West Toronto": {
        "West Toronto": 0,
        "Downtown": 1,
        "Etobicoke": 1,
        "Central Toronto": 2,
        "North York": 2,
        "East York": 2,
        "Scarborough": 3,
    },
    "Etobicoke": {
        "Etobicoke": 0,
        "West Toronto": 1,
        "North York": 2,
        "Downtown": 3,
        "Central Toronto": 3,
        "East York": 3,
        "Scarborough": 4,
    },
}

SCARBOROUGH_NAMES = {
    "agincourt north",
    "agincourt south-malvern west",
    "bendale",
    "birchcliffe-cliffside",
    "centennial scarborough",
    "clairlea-birchmount",
    "cliffcrest",
    "dorset park",
    "eglinton east",
    "guildwood",
    "highland creek",
    "ionview",
    "kennedy park",
    "lamoreaux",
    "malvern",
    "milliken",
    "morningside",
    "oakridge",
    "rouge",
    "scarborough village",
    "tam oshanter-sullivan",
    "west hill",
    "wexford/maryvale",
    "woburn",
}

NORTH_YORK_NAMES = {
    "banbury-don mills",
    "bathurst manor",
    "bayview village",
    "bayview woods-steeles",
    "black creek",
    "clanton park",
    "don valley village",
    "downsview-roding-cfb",
    "flemingdon park",
    "glenfield-jane heights",
    "henry farm",
    "hillcrest village",
    "humber summit",
    "humbermede",
    "lansing-westgate",
    "maple leaf",
    "newtonbrook east",
    "newtonbrook west",
    "parkwoods-donalda",
    "pleasant view",
    "steeles",
    "thorncliffe park",
    "westminster-branson",
    "willowdale east",
    "willowdale west",
    "york university heights",
    "yorkdale-glen park",
}

ETOBICOKE_NAMES = {
    "alderwood",
    "edenbridge-humber valley",
    "elms-old rexdale",
    "eringate-centennial-west deane",
    "etobicoke west mall",
    "humber heights-westmount",
    "islington-city centre west",
    "kingsview village-the westway",
    "kingsway south",
    "long branch",
    "markland wood",
    "mimico includes humber bay shores",
    "new toronto",
    "princess-rosethorn",
    "rexdale-kipling",
    "stonegate-queensway",
    "thistletown-beaumond heights",
    "west humber-clairville",
    "willowridge-martingrove-richview",
}

DOWNTOWN_NAMES = {
    "annex",
    "bay street corridor",
    "cabbagetown-south st. james town",
    "church-yonge corridor",
    "kensington-chinatown",
    "moss park",
    "niagara",
    "north st. james town",
    "palmerston-little italy",
    "regent park",
    "south riverdale",
    "trinity-bellwoods",
    "university",
    "waterfront communities-the island",
}

EAST_YORK_NAMES = {
    "blake-jones",
    "broadview north",
    "danforth",
    "danforth east york",
    "east end-danforth",
    "greenwood-coxwell",
    "north riverdale",
    "oconnor-parkview",
    "old east york",
    "playter estates-danforth",
    "the beaches",
    "taylor-massey",
    "victoria village",
    "woodbine corridor",
    "woodbine-lumsden",
}

WEST_TORONTO_NAMES = {
    "beechborough-greenbrook",
    "briar hill-belgravia",
    "brookhaven-amesbury",
    "caledonia-fairbank",
    "corso italia-davenport",
    "dovercourt-wallace emerson-junction",
    "dufferin grove",
    "high park north",
    "high park-swansea",
    "humewood-cedarvale",
    "junction area",
    "keelesdale-eglinton west",
    "lambton baby point",
    "little portugal",
    "mount dennis",
    "oakwood village",
    "pelmo park-humberlea",
    "rockcliffe-smythe",
    "roncesvalles",
    "runnymede-bloor west village",
    "rustic",
    "south parkdale",
    "weston",
    "weston-pelham park",
    "wychwood",
}


def district_from_fsa(postal: object) -> str:
    text = str(postal or "").strip().upper()
    if len(text) >= 2:
        return FSA_TO_DISTRICT.get(text[:2], "Unknown")
    return "Unknown"


def district_from_ward(ward: object) -> str:
    try:
        return WARD_TO_DISTRICT.get(int(float(str(ward).strip())), "Unknown")
    except (TypeError, ValueError):
        return "Unknown"


def district_from_neighbourhood(name: str, number: float | int | None = None) -> str:
    normalized = normalize_name(name)
    normalized = normalized.replace("'", "")
    normalized = normalized.replace(".", "")
    if normalized in SCARBOROUGH_NAMES:
        return "Scarborough"
    if normalized in NORTH_YORK_NAMES:
        return "North York"
    if normalized in ETOBICOKE_NAMES:
        return "Etobicoke"
    if normalized in DOWNTOWN_NAMES:
        return "Downtown"
    if normalized in EAST_YORK_NAMES:
        return "East York"
    if normalized in WEST_TORONTO_NAMES:
        return "West Toronto"
    if number is not None:
        try:
            n = int(float(number))
            if 1 <= n <= 23:
                return "Etobicoke"
            if 24 <= n <= 56:
                return "North York"
            if 57 <= n <= 72:
                return "East York"
            if 73 <= n <= 100:
                return "Downtown"
            if 101 <= n <= 115:
                return "West Toronto"
            if 116 <= n <= 140:
                return "Scarborough"
        except (TypeError, ValueError):
            pass
    return "Central Toronto"


def operational_score(base_district: str, target_district: str, max_travel_minutes: int) -> float:
    distance = DISTRICT_DISTANCE.get(base_district, {}).get(target_district, 3)
    base_scores = {0: 100.0, 1: 82.0, 2: 65.0, 3: 45.0, 4: 28.0}
    score = base_scores.get(distance, 35.0)
    if max_travel_minutes >= 45:
        score += 12.0
    elif max_travel_minutes <= 20:
        score -= 18.0
    elif max_travel_minutes <= 25:
        score -= 8.0
    return max(0.0, min(100.0, score))
