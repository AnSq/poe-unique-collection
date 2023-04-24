#!/usr/bin/env python

import os
import json
import re
import logging
import attrs

import lupa.lua51 as lupa  #type: ignore

from typing import Any
from pprint import pprint as pp

from utils import GenericMod, make_variant_list


POB_DIR = r"./PathOfBuilding/src"

log = logging.getLogger(__name__)

try:
    from CompactJSONEncoder import CompactJSONEncoder
    class JE (CompactJSONEncoder):
        MAX_WIDTH = 240
        MAX_ITEMS = 50

        def _primitives_only(self, o:list|tuple|dict):
            if isinstance(o, (list, tuple)) and all(super(JE, self)._primitives_only(x) for x in o):
                return True
            return super()._primitives_only(o)
        
        def encode(self, o):
            if attrs.has(o):
                if hasattr(o, "asdict_filter"):
                    return self._encode_object(attrs.asdict(o, filter=o.asdict_filter, recurse=False))
                return self._encode_object(attrs.asdict(o, recurse=False))
            return super().encode(o)
except ImportError:
    class JE (json.JSONEncoder):
        def default(self, o:Any) -> Any:
            if attrs.has(o):
                if hasattr(o, "asdict_filter"):
                    # recursion in attrs means that filter is only applied to the top-level attrs object.
                    # recurse=False lets json handle the recursion, which allows the filter to apply to member objects
                    return attrs.asdict(o, filter=o.asdict_filter, recurse=False)
                return attrs.asdict(o, recurse=False)
            return super().default(o)



@attrs.define
class BaseTypeVariant:
    basetype: str
    variants: list[int]



@attrs.define
class UpgradePath:
    dest: str
    currency: str



@attrs.define
class PoBItem:
    name: str
    basetype: str|None
    basetypes: list[BaseTypeVariant]|None
    itemclass: str
    source: str
    league: str
    upgrade: UpgradePath|str|None
    variants: list[str]
    implicits: list[GenericMod]
    explicits: list[GenericMod]
    variant_slots: int = attrs.field(default=1)


    @classmethod
    def from_lua_item(cls, lua_item):
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

        basetypes:list[BaseTypeVariant]|None = []
        for b in lua_item.baseLines.values():
            basetypes.append(BaseTypeVariant(b["line"], make_variant_list(b, len(variants))))

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
        if len(basetypes) == 1:
            basetype = lua_item.baseName
            basetypes = None
        
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
    

    @staticmethod
    def asdict_filter(at:attrs.Attribute, value:Any) -> bool:
        # print("PoBItem.asdict_filter")
        if at.name in ("basetype", "basetypes", "upgrade") and value is None:
            return False
        if at.name == "variant_slots" and value == 1:
            return False
        return True



def main():
    logging.basicConfig(level=logging.DEBUG)

    lua = lupa.LuaRuntime()
    os.chdir(POB_DIR)
    
    lua_paths = [
        "./?.lua",
        "../runtime/lua/?.lua",
        "../runtime/lua/?/init.lua",
        "../../bitop-lua/src/?.lua",
        "../../?.lua"
    ]
    lua.execute(f'package.path = "{";".join(lua_paths)}"')
    
    lua.execute('arg = {}')
    lua.execute(f'bit = require("bitop.funcs")')

    lua.execute(f'inspect = require("inspect")')
    inspect = inspect_func(lua.eval('inspect'))

    def process(item, path):
        last = path[len(path)]
        if lupa.lua_type(last) == "table" and str(last) == "inspect.METATABLE":
            return None
        if path[1] == "affixes":
            return None
        return item

    lua.execute(f'pob = dofile("HeadlessWrapper.lua")')
    print("===== PoB Loaded ==================================\n")

    
    uniqueDB = lua.globals().launch.main.uniqueDB.list
    
    generated_names = set()
    for item_text in lua.globals().data.uniques.generated.values():
        lines = item_text.split("\n")
        generated_names.add(lines[0])
    
    uniques = pob_export(uniqueDB, generated_names)

    with open("../../pob_export.json", "w") as f:
        json.dump(uniques, f, cls=JE, indent=4)


def pob_export(uniqueDB, generated_names):
    uniques:list[PoBItem] = []
    for i in uniqueDB:
        # print(i)
        item = uniqueDB[i]

        if item.title in generated_names:
            log.info(f"generated skipped: {item.title}, {item.baseName}")
            continue  # todo?
        
        uniques.append(PoBItem.from_lua_item(item))
    
    uniques.sort(key=lambda x:x.name)
    
    return uniques


def l(x) -> int|None:
    try:
        return len(x)
    except TypeError as e:
        return None


def inspect_func(lua_inspect):
    def inspect(table, depth=None, newline="\n", indent="    ", process=lambda i,p:i):
        return lua_inspect(table, {"depth":depth, "newline":newline, "indent":indent, "process":process})
    return inspect


if __name__ == "__main__":
    main()
