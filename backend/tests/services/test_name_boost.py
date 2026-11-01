from rippermod_manager.services.name_boost import boosted_score


def test_boost_applies_from_on_disk_line():
    assert boosted_score(0.80, "endorsed_name") == 0.85
    assert boosted_score(0.75, "requirement") == 0.92
    assert boosted_score(0.90, "collection") == 0.90


def test_no_boost_below_on_disk_line():
    assert boosted_score(0.557, "endorsed_name") == 0.557
    assert boosted_score(0.70, "requirement") == 0.70
