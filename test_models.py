#!/usr/bin/env python

import pytest

from models import *


@pytest.mark.parametrize("line, generic_line, ranges", (
    ("(1-2) to (4-6) Added Cold Damage per 10 Dexterity",               "# to # Added Cold Damage per # Dexterity",               [[1,2], [4,6], [10,10]]),  # fake mod from documentation example
    ("+(20-30) to Strength",                                            "+# to Strength",                                         [[20,30]]),
    ("+25 to Strength",                                                 "+# to Strength",                                         [[25,25]]),
    ("(7-12)% increased maximum Life",                                  "#% increased maximum Life",                              [[7,12]]),
    ("+(30-40)% to Fire Resistance",                                    "+#% to Fire Resistance",                                 [[30,40]]),
    ("Adds (30-36) to (44-50) Cold Damage to Attacks",                  "Adds # to # Cold Damage to Attacks",                     [[30,36], [44,50]]),
    ("(10--10)% increased Charges per use",                             "#% increased Charges per use",                           [[-10,10]]),
    ("2% increased Attack Speed per Frenzy Charge",                     "#% increased Attack Speed per Frenzy Charge",            [[2,2]]),
    ("+1 to Level of Socketed Aura Gems",                               "+# to Level of Socketed Aura Gems",                      [[1,1]]),
    ("Bow Attacks fire 2 additional Arrows",                            "Bow Attacks fire # additional Arrows",                   [[2,2]]),
    ("Hits can't be Evaded",                                            "Hits can't be Evaded",                                   []),
    ("Far Shot",                                                        "Far Shot",                                               []),
    ("(-40-40)% increased Rarity of Items found",                       "#% increased Rarity of Items found",                     [[-40,40]]),
    ("+(-25-50)% to Cold Resistance",                                   "+#% to Cold Resistance",                                 [[-25,50]]),
    ("(-10--20)% increased Charges per use",                            "#% increased Charges per use",                           [[-20,-10]]),
    ("-(20-10)% to Chaos Resistance",                                   "#% to Chaos Resistance",                                 [[-20,-10]]),
    ("(0.4-0.6)% of Physical Attack Damage Leeched as Life",            "#% of Physical Attack Damage Leeched as Life",           [[0.4,0.6]]),
    ("(1.2-2)% of Physical Attack Damage Leeched as Life",              "#% of Physical Attack Damage Leeched as Life",           [[1.2,2]]),
    ("-30% to Fire Resistance",                                         "#% to Fire Resistance",                                  [[-30,-30]]),
    ("-(-10--30)% increased Dexterity",                                 "#% increased Dexterity",                                 [[10,30]]),     # fake mod
    ("-(5--6)% Chance to Block Spell Damage",                           "#% Chance to Block Spell Damage",                        [[-5,6]]),      # fake mod
    ("Minions Leech -(0.2-0.3)% of Lightning Damage to you as Life",    "Minions Leech #% of Lightning Damage to you as Life",    [[-.3,-.2]]),   # fake mod
    ("Mines have +(-10.5-20)% Cold Resistance",                         "Mines have +#% Cold Resistance",                         [[-10.5,20]]),  # fake mod
    ("Nearby Allies have (2.5--5.5)% increased Critical Strike Chance", "Nearby Allies have #% increased Critical Strike Chance", [[-5.5,2.5]]),  # fake mod
    (
        "1 (2-3)4-5%-6 -7 (8--9) (-10-11) (-12--13) -(14-15) -(-16-17) -(18--19) -(-20--21)(22)(-23) -(24) (25-)(-26-)",
        "# ###%# # # # # # # # #(#)(#) -(#) (#-)(#-)",
        [[1,1], [2,3], [4,4], [-5,-5], [-6,-6], [-7,-7], [-9,8], [-10,11], [-13,-12], [-15,-14], [-17,16], [-18,19], [20,21], [22,22], [-23,-23], [24,24], [25,25], [-26,-26]]
    )
))
def test_GenericMod_genericize_mod(line, generic_line, ranges):
    generic = GenericMod.genericize_mod(line)
    assert generic.line == generic_line
    assert generic.ranges == ranges
