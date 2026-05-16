from rkn_tui.presets import ALL, DEFAULT, QUICK, THOROUGH, by_name


def test_all_presets_have_distinct_names():
    names = {p.name for p in ALL}
    assert len(names) == len(ALL)


def test_by_name_returns_singleton():
    assert by_name("quick") is QUICK
    assert by_name("default") is DEFAULT
    assert by_name("thorough") is THOROUGH


def test_unknown_preset_raises():
    import pytest

    with pytest.raises(KeyError):
        by_name("nope")


def test_quick_is_faster_than_default():
    assert QUICK.workers > DEFAULT.workers
    assert QUICK.timeout < DEFAULT.timeout


def test_thorough_is_slower_than_default():
    assert THOROUGH.workers < DEFAULT.workers
    assert THOROUGH.timeout > DEFAULT.timeout
    assert THOROUGH.identify is True


def test_quick_skips_self_info_by_default():
    assert QUICK.no_self_info is True


def test_all_presets_are_immutable():
    import dataclasses

    for p in ALL:
        assert dataclasses.is_dataclass(p)
        import pytest

        with pytest.raises(dataclasses.FrozenInstanceError):
            p.workers = 999  # type: ignore[misc]
