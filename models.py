#!/usr/bin/env python

import os
import re
import logging
from typing import Any

import attrs

from consts import *
import utils

log = logging.getLogger(__name__)


FName = str|bytes|os.PathLike
Ranges = list[list[float]]
APIItem = dict[str,Any]
VariantMatch = tuple[str,int]  #TODO



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
    name: str
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
