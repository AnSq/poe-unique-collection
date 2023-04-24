#!/usr/bin/env python

import re
import logging
from typing import Any
import attrs


Ranges = list[list[float]]

log = logging.getLogger(__name__)


@attrs.define
class GenericMod:
    line: str
    ranges: Ranges
    variants: list[int] = attrs.field(default=[])
    crafted: bool = attrs.field(default=False)
    

    @classmethod
    def from_lua_mod(cls, lua_mod, all_variants:list[str], *, item_name=None):
        result = cls.genericize_mod(lua_mod.line, item_name=item_name)

        result.variants = make_variant_list(lua_mod, len(all_variants))

        if lua_mod.crafted:
            assert lua_mod.crafted == r"{crafted}"
            result.crafted = True
        
        return result

    
    @classmethod
    def genericize_mod(cls, line:str, *, item_name:str=None) -> 'GenericMod':  # item_name is a debgging param
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
    

    @staticmethod
    def asdict_filter(at:attrs.Attribute, value:Any) -> bool:
        if at.name in ("ranges", "variants", "crafted") and not value:
            return False
        return True
    

def make_variant_list(mod, num_variants:int) -> list[int]:
    if mod.variantList:
        mod_variants = list(x-1 for x in mod.variantList.keys())
    else:
        mod_variants = list(range(num_variants))
    return mod_variants
