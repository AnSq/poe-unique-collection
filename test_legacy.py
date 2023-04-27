#!/usr/bin/env python

import pytest
import json
from typing import Any

from legacy import *
import utils


@pytest.fixture
def test_items() -> dict[str,Any]:
    with open("test_data/legacy_test.json") as f:
        test_items_ = json.load(f)
    return test_items_


@pytest.fixture
def pob_db() -> list[PoBItem]:
    pob_db_ = utils.load_pob_db(POB_EXPORT_FNAME)
    return pob_db_


@pytest.mark.parametrize(("test_index", "name", "expected"), (
    (0,  "Marohi Erqi",              [('Pre 2.6.0', 0)]),
    (1,  "Allelopathy",              [('Pre 3.19.0', 0)]),
    (2,  "Ascent From Flesh",        [('Pre 3.16.0', 1)]),
    (3,  "Ashcaller",                [('Pre 3.8.0', 0)]),
    (4,  "Ashrend",                  [('Pre 3.19.0', 1)]),
    (5,  "Slavedriver's Hand",       [('Only', 0)]),
    (6,  "Abhorrent Interrogation",  [('Only', 0)]),
    (7,  "Quickening Covenant",      [('Pre 3.20.0', 0)]),
    (8,  "Tecrod's Gaze",            [('Pre 3.21.0', 0)]),
    (9,  "Asphyxia's Wrath",         [('Pre 3.17.0', 1)]),
    (10, "Astramentis",              [('Pre 0.11.6d', 0), ('Current', 1)]),
    (11, "Atziri's Mirror",          [('Current', 2)]),
    (12, "Atziri's Splendour",       [('Pre 3.14.0 (Evasion/ES + ES)', 13)]),
    (13, "Atziri's Step",            [('Pre 3.16.0', 0), ('Current', 1)]),
    (14, "Badge of the Brotherhood", [('Only', 0)]),
    (15, "Berek's Respite",          [('Current', 1)]),
    (16, "Voidheart",                [('Pre 3.19.0', 1)]),
    (17, "Bloodbond",                [('Pre 3.16.0', 0)]),
    (18, "Bramblejack",              [('Pre 3.19.0', 0)]),
    (19, "Breath of the Council",    [('Current', 1)]),
    (20, "Breathstealer",            [('Only', 0)]),
    (21, "Brutal Restraint",         [('Asenath (Dance with Death)', 0)]),
    (22, "Bubonic Trail",            [('One Abyssal Socket (Pre 3.21.0)', 0)]),
    (23, "Carnage Heart",            [('Current', 2)]),
    (24, "Cinderswallow Urn",        []),  # todo?
    (25, "Clayshaper",               [('Pre 3.19.0', 1)]),
    (26, "Combat Focus",             [('Only', 0)]),
    (27, "Crown of the Pale King",   [('Pre 3.19.0', 1)]),
    (28, "Death Rush",               [('Pre 3.15.0', 1)]),
    (29, "Tremor Rod",               [('Pre 3.8.0', 1)]),
    (30, "Combat Focus",             [('Only', 0)])
))
def test_get_variant(test_items:list[dict[str,Any]], pob_db:list[PoBItem], test_index:int, name:str, expected:list[VariantMatch]) -> None:
    test_item = test_items[test_index]
    variant = get_variant(test_item, pob_db)
    assert test_item["name"] == name
    assert variant == expected
