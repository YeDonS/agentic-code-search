from checkout import calculate_total


def test_default_discount():
    assert calculate_total(100) == 90


def test_explicit_zero_discount():
    assert calculate_total(100, discount=0) == 100


def test_positive_discount():
    assert calculate_total(100, discount=20) == 80
