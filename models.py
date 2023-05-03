#!/usr/bin/env python
from __future__ import annotations

import os
import re
import logging
from typing import Any

import attrs
import numpy as np
import numpy.typing as npt

from consts import *
import utils

log = logging.getLogger(__name__)


FName = str|bytes|os.PathLike
Ranges = list[list[float]]
APIItem = dict[str,Any]



@attrs.define
class BaseTypeVariant:
    """used when an item has multiple basetypes depending on its variant"""
    basetype: str
    variants: list[int]



@attrs.define
class UpgradePath:
    dest: str
    currency: str



@attrs.define
class GenericMod:
    """A genericized form of a mod

    `line` is the text of the mod with the numbers and number ranges replaced by #.
    `ranges` is a list of number ranges (in the form [low, high]) that can be substituted in each #.
        If a # represents single number and not a range, both numbers in the range will be the same.

    For example, the (fictional) mod "(1-2) to (4-6) Added Cold Damage per 10 Dexterity" would be represented by
        line="# to # Added Cold Damage per # Dexterity" and
        ranges=[[1,2], [4,6], [10,10]]
    """
    line: str
    ranges: Ranges = attrs.field(metadata={META_MISSING_VALUE: []})
    variants: list[int] = attrs.field(default=[])
    crafted: bool = attrs.field(default=False)


    @classmethod
    def from_lua_mod(cls, lua_mod, all_variants:list[str], *, item_name=None) -> 'GenericMod':
        """create a GenericMod from a Lua mod (as pulled from PoB)"""
        result = cls.genericize_mod(lua_mod.line, item_name=item_name)

        result.variants = utils.make_variant_list(lua_mod, len(all_variants))

        if lua_mod.crafted:
            assert lua_mod.crafted == r"{crafted}"
            result.crafted = True

        return result


    @classmethod
    def genericize_mod(cls, line:str, *, item_name:str|None=None) -> 'GenericMod':  # item_name is a debgging param
        """create a GenericMod from mod text

        Either general, like "+(20-30) to Strength", or specific, like "+25 to Strength".
        Both of these would result in a `line` of "+# to Strength",
        and a `ranges` of [[20,30]] and [[25,25]] respectively.
        """
        number_pattern = r"-?\d+\.?\d*"
        range_pattern = rf"(?P<sign>-?)\((?P<start>{number_pattern})-(?P<end>{number_pattern})\)|(?P<single>{number_pattern})"

        ranges = []
        for m in re.finditer(range_pattern, line):
            if m["single"]:  # single number
                n = float(m["single"])
                ranges.append([n, n])
            else:  # range
                r = [float(m["start"]), float(m["end"])]
                if m["sign"] == "-":
                    r = [-x for x in r]
                ranges.append(sorted(r))

        line = re.sub(range_pattern, "#", line)

        if "Area of Effect of Area Skills" in line:
            log.info(f'"{item_name}" has "Area of Effect of Area Skills"')
            line = line.replace("Area of Effect of Area Skills", "Area of Effect")  #TODO: fix in PoB

        return cls(line, ranges)


    def is_inside_range(self, other:'GenericMod') -> bool:
        """checks if the ranges of this GenericMod are inside the ranges of another GenericMod"""
        if len(self.ranges) != len(other.ranges):
            return False

        for self_range, other_range in zip(self.ranges, other.ranges):
            if self_range[0] < other_range[0] or self_range[1] > other_range[1]:
                return False

        return True



@attrs.define
class PoBItem:
    name: str
    basetype: str|None = attrs.field(metadata={META_MISSING_VALUE: None})
    basetypes: list[BaseTypeVariant] = attrs.field(metadata={META_MISSING_VALUE: []})
    itemclass: str
    source: str
    league: str
    upgrade: UpgradePath|str|None = attrs.field(metadata={META_MISSING_VALUE: None})
    variants: list[str]
    implicits: list[GenericMod]
    explicits: list[GenericMod]
    variant_slots: int = attrs.field(default=1)


    @classmethod
    def from_lua_item(cls, lua_item:Any) -> 'PoBItem':
        variants = list(lua_item.variantList.values() if lua_item.variantList else ["Only"])

        variant_slots = 1
        if lua_item.variantAlt:
            variant_slots = 2
        if lua_item.variantAlt2:
            variant_slots = 3
        if lua_item.variantAlt3:
            variant_slots = 4
        if lua_item.variantAlt4:
            variant_slots = 5
        if lua_item.variantAlt5:
            variant_slots = 6

        basetypes:list[BaseTypeVariant] = []
        for b in lua_item.baseLines.values():
            basetypes.append(BaseTypeVariant(b["line"], utils.make_variant_list(b, len(variants))))

        implicits:list[GenericMod] = []
        explicits:list[GenericMod] = []
        for outlist, inlist in ((implicits, lua_item.implicitModLines), (explicits, lua_item.explicitModLines)):
            for mod in inlist.values():
                generic = GenericMod.from_lua_mod(mod, variants, item_name=lua_item.title)

                if generic.line.startswith("LevelReq: "):
                    log.info(f'LevelReq: {lua_item.title}')
                    continue

                if generic.line == "This item can be anointed by Cassia":
                    log.info(f'{lua_item.title} can be annointed')
                    continue

                outlist.append(generic)

        basetype:str|None = None
        if len(basetypes) <= 1:
            basetype = lua_item.baseName
            basetypes = []

        upgrade:UpgradePath|str|None = None
        if lua_item.upgradePaths:
            assert len(lua_item.upgradePaths) == 1
            upgrade_pattern = r"Upgrades to unique{(.+?)} (?:using|via) currency{(.+?)}"
            upgrade_match = re.fullmatch(upgrade_pattern, lua_item.upgradePaths[1])
            if upgrade_match:
                upgrade = UpgradePath(upgrade_match[1], upgrade_match[2])
            else:
                upgrade = lua_item.upgradePaths[1]

        return cls(lua_item.title, basetype, basetypes, lua_item.type, lua_item.source, lua_item.league, upgrade, variants, implicits, explicits, variant_slots)



@attrs.define
class ItemVariant:
    item_name: str
    basetype: str
    variant_name: str
    variant_number: int
    implicits: list[GenericMod]
    explicits: list[GenericMod]



@attrs.define
class GGItem:
    index: int
    name: str
    icon: str
    type: str
    hidden_challenge: bool
    hidden_standard: bool
    alt_art: bool
    sort_key: str



@attrs.define
class VariantMatch:
    """describes how well an APIItem matches an ItemVariant"""
    variant_name: str
    variant_number: int
    basic_mismatch: bool = attrs.field(default=False)
    implicit_matrix: npt.NDArray[np.float64] = attrs.field(factory=lambda: np.zeros(0), repr=False)
    explicit_matrix: npt.NDArray[np.float64] = attrs.field(factory=lambda: np.zeros(0), repr=False)
    scores: list[float] = attrs.field(factory=list, repr=False)
    minumim_score: float = attrs.field(init=False, default=-1)
    average_score: float = attrs.field(init=False, default=-1)
    aggregate_score: float = attrs.field(init=False, default=-1)


    def __str__(self) -> str:
        score = "basic mismatch" if self.basic_mismatch else f'{self.minumim_score:.0f} / {self.average_score:.0f} / {self.aggregate_score:.0f}\n{self.scores}\n{self.implicit_matrix.round(0)}\n{self.explicit_matrix.round(0)}'
        return f'{{{self.variant_name} ({self.variant_number}) {score}}}'



@attrs.define
class VariantMatchList:
    match_list: list[VariantMatch] = attrs.field(factory=list)
    """match_list must remain sorted by minimum_score. This is done automatically by __init__. Don't mess it up"""


    def __attrs_post_init__(self) -> None:
        self.match_list.sort(key=lambda x: x.minumim_score, reverse=True)  # enforces sorted match_list at instantiation


    def __str__(self) -> str:
        return "\n\n".join(str(x) for x in self.match_list)


    def __len__(self) -> int:
        return len(self.match_list)


    def backwards_compatible(self, threshold=100) -> list[tuple[str,int]]:
        """return a tuple that's compatible with the old way of dealing with matches, before they were classes. TODO: fix consumers and delete this."""
        return [(x.variant_name, x.variant_number) for x in self.match_list if x.minumim_score >= threshold]


    def best_score(self) -> float:
        if not self.match_list:
            return -1
        return self.match_list[0].minumim_score  # assumes sorted match_list


    def top(self, threshold=100) -> 'VariantMatchList':
        """return a new VariantMatchList with only the matches that are tied for the highest minimum score.
        If there are no matches with a score >= threshold, return an empty VariantMatchList"""

        if not self.match_list or self.best_score() < threshold:
            return VariantMatchList()

        result_list = []
        for match in self.match_list:
            assert match.minumim_score <= self.best_score()
            if match.minumim_score == self.best_score():
                result_list.append(match)
            else:
                break
        return VariantMatchList(result_list)
