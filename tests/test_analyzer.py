from analyzer import split_extreme_float_numbers


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
