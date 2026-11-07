from gridsense import config


def test_splits_are_ordered_and_disjoint():
    assert config.TRAIN_START < config.TRAIN_END < config.VAL_START
    assert config.VAL_START < config.VAL_END < config.TEST_START
    assert config.TEST_START < config.TEST_END
