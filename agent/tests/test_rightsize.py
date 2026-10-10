from healer.rightsize import recommend, should_propose, to_millicores


def test_never_below_floor():
    assert recommend(0.5) == 10


def test_safety_margin():
    assert recommend(30) == 60


def test_units():
    assert to_millicores("250m") == 250 and to_millicores("0.5") == 500


def test_only_big_savings_are_proposed():
    assert should_propose(250, 10)
    assert not should_propose(25, 10)
