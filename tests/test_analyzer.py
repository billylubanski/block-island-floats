from analyzer import normalize_location, split_extreme_float_numbers


def test_greenway_reports_use_specific_named_anchors():
    cases = {
        "Greenway off Cooneymus Road": "Cooneymus Road/Beach",
        "Old Mill Greenway steps": "Old Mill Road",
        "Greenway trail off of Lakeshore Drive": "Lakeshore Drive",
        "Beacon Hill Greenway under a log": "Beacon Hill Road",
        "Nathan Mott Park - B.I. Greenway": "Nathan Mott Park",
        "Greenway Trail, Fresh Swamp Preserve": "Fresh Swamp Preserve",
        "Greenway Trail": "Greenway Trail",
    }

    for raw_location, expected in cases.items():
        assert normalize_location(raw_location) == expected


def test_greenway_trail_numbers_use_official_guide_order():
    cases = {
        "Greenway Trail #1": "Hodge Family Wildlife Preserve",
        "Greenway Trail #2": "Long Lot Trail",
        "Jett - Greenway Trail #3 in a stump": "Clay Head Trail",
        "Greenway Trail #4": "Harrison Trail",
        "Greenway Trail #5": "Turnip Farm",
        "Greenway Trail #6": "Nathan Mott Park",
        "Greenway Trail #7": "Lewis-Dickens Farm",
        "Greenway Trail #8": "Win Dodge Preserve",
        "Greenway Trail #9": "Rodman's Hollow",
        "Greenway Trail #10": "Fresh Pond",
        "Greenway Trail #11": "Fresh Swamp Preserve",
    }

    for raw_location, expected in cases.items():
        assert normalize_location(raw_location) == expected


def test_greenway_out_of_range_numbers_stay_generic_without_named_anchor():
    assert normalize_location("Greenway Trail #13") == "Greenway Trail"
    assert normalize_location("Greenway #13 - Fresh swamp preserve") == "Fresh Swamp Preserve"
    assert normalize_location("Greenway Trail. Will rehide #95") == "Greenway Trail"


def test_known_source_typos_normalize_to_canonical_locations():
    cases = {
        "Labrinyth": "The Labyrinth",
        "Win - Dodge Presrve": "Win Dodge Preserve",
        "Bench at the Tranfer Station": "Transfer Station",
        "oceanview pavillion": "Ocean View Pavilion",
        "Oceanview Hotel foundation area": "Ocean View Hotel",
        "Dorrey's Cove": "Dorry's Cove",
        "Slovekian Property by Monument Stone": "Solviken Preserve",
        "Loefflers loop": "Loffredo Loop",
    }

    for raw_location, expected in cases.items():
        assert normalize_location(raw_location) == expected


def test_split_extreme_float_numbers_ignores_isolated_outlier():
    clean_numbers, outlier_numbers = split_extreme_float_numbers(
        [546, 550, 551, 552, 553, 558, 2044]
    )

    assert clean_numbers == [546, 550, 551, 552, 553, 558]
    assert outlier_numbers == [2044]


def test_split_extreme_float_numbers_keeps_normal_year_distribution():
    clean_numbers, outlier_numbers = split_extreme_float_numbers(
        [508, 517, 543, 550, 551, 552, 553, 558]
    )

    assert clean_numbers == [508, 517, 543, 550, 551, 552, 553, 558]
    assert outlier_numbers == []
