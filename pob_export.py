#!/usr/bin/env python

import os
import json
import re

import lupa.lua51 as lupa  #type: ignore



from typing import Any
from pprint import pprint as pp

POB_DIR = r"./PathOfBuilding/src"

try:
    from CompactJSONEncoder import CompactJSONEncoder
    class JE (CompactJSONEncoder):
        MAX_WIDTH = 240
        MAX_ITEMS = 50

        def _primitives_only(self, o: list | tuple | dict):
            if isinstance(o, (list, tuple)) and all(super(JE, self)._primitives_only(x) for x in o):
                return True
            return super()._primitives_only(o)
except ImportError:
    JE = None


def main():
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
        # print(inspect(item, 0), list(path.values()), len(path), last, lupa.lua_type(last)=="table" and str(last)=="inspect.KEY", lupa.lua_type(last)=="table" and str(last)=="inspect.METATABLE")
        if lupa.lua_type(last) == "table" and str(last) == "inspect.METATABLE":
            return None
        if path[1] == "affixes":
            return None
        return item

    lua.execute(f'pob = dofile("HeadlessWrapper.lua")')
    
    uniqueDB = lua.globals().launch.main.uniqueDB.list
    
    generated_names = set()
    for item_text in lua.globals().data.uniques.generated.values():
        lines = item_text.split("\n")
        generated_names.add(lines[0])

    # marohi_erqi = uniqueDB["Marohi Erqi, Karui Maul"]

    # with open("../../Marohi_Erqi.txt", "w") as f:
    #     f.write(inspect(marohi_erqi, process=process))
    # with open("../../Bottled_Faith.txt", "w") as f:
    #     f.write(inspect(uniqueDB["Bottled Faith, Sulphur Flask"], process=process))
    # with open("../../Watcher~s_Eye.txt", "w") as f:
    #     f.write(inspect(uniqueDB["Watcher's Eye, Prismatic Jewel"], process=process))
    # with open("../../Original_Sin.txt", "w") as f:
    #     f.write(inspect(uniqueDB["Original Sin, Amethyst Ring"], process=process))
    # with open("../../Forbidden_Shako.txt", "w") as f:
    #     f.write(inspect(uniqueDB["Forbidden Shako, Great Crown"], process=process))
    # with open("../../Impossible_Escape.txt", "w") as f:
    #     f.write(inspect(uniqueDB["Impossible Escape, Viridian Jewel"], process=process))
    # with open("../../Paradoxica.txt", "w") as f:
    #     f.write(inspect(uniqueDB["Paradoxica, Vaal Rapier"], process=process))
    # with open("../../Replica_Paradoxica.txt", "w") as f:
    #     f.write(inspect(uniqueDB["Replica Paradoxica, Vaal Rapier"], process=process))
    # with open("../../Hyperboreus.txt", "w") as f:
    #     f.write(inspect(uniqueDB["Hyperboreus, Leather Belt"], process=process))
    with open("../../Esh's_Mirror.txt", "w") as f:
        f.write(inspect(uniqueDB["Esh's Mirror, Vaal Spirit Shield"], process=process))
    
    uniques = pob_export(uniqueDB, generated_names)

    with open("../../pob_export.json", "w") as f:
        json.dump(uniques, f, cls=JE, indent=4)
    
    print()

    # counts = {}
    # for u in uniques:
    #     if u["name"] not in counts:
    #         counts[u["name"]] = 0
    #     counts[u["name"]] += 1
    # for c in counts:
    #     if counts[c] > 1:
    #         print(c, counts[c])
    
    # pp(dict(lua.globals().colorCodes))


def pob_export(uniqueDB, generated_names):
    uniques = []
    for i in uniqueDB:
        # print(i)
        item:dict[str,Any] = uniqueDB[i]

        variants = list(item.variantList.values() if item.variantList else ["Only"])

        if item.title in generated_names:
            print(f"{len(variants)} {item.title}, {item.baseName}")
            continue  # todo?
        
        variant_slots = 1
        if item.variantAlt:
            variant_slots = 2
        if item.variantAlt2:
            variant_slots = 3
        if item.variantAlt3:
            variant_slots = 4
        if item.variantAlt4:
            variant_slots = 5
        if item.variantAlt5:
            variant_slots = 6

        basetypes = []
        for b in item.baseLines.values():
            basetypes.append({
                "basetype" : b["line"],
                "variants" : make_variant_list(b, len(variants))
            })

        implicits = []
        explicits = []
        for outlist, inlist in ((implicits, item.implicitModLines), (explicits, item.explicitModLines)):
            for mod in inlist.values():
                mod_data = genericize_mod(mod.line)

                if mod.crafted:
                    assert mod.crafted == r"{crafted}"
                    mod_data["crafted"] = True
                
                mod_data["variants"] = make_variant_list(mod, len(variants))

                outlist.append(mod_data)

        item_data = {"name" : item.title}

        if len(basetypes) > 1:
            item_data["basetypes"] = basetypes
        else:
            item_data["basetype"] = item.baseName

        item_data.update({
            "class"  : item.type,
            "source" : item.source,
            "league" : item.league
        })

        upgrade = {}
        if item.upgradePaths:
            assert len(item.upgradePaths) == 1
            upgrade_pattern = r"Upgrades to unique{(.+?)} (?:using|via) currency{(.+?)}"
            upgrade_match = re.fullmatch(upgrade_pattern, item.upgradePaths[1])
            if upgrade_match:
                upgrade = {
                    "dest"     : upgrade_match[1],
                    "currency" : upgrade_match[2]
                }
            else:
                upgrade = item.upgradePaths[1]
            
            item_data["upgrade"] = upgrade

        
        item_data.update({
            "variants"  : variants,
            "implicits" : implicits,
            "explicits" : explicits
        })

        if variant_slots > 1:
            item_data["variant_slots"] = variant_slots
        
        uniques.append(item_data)
    
    uniques.sort(key=lambda x:x["name"])
    
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


def genericize_mod(line):
    number_pattern = r"-?\d+\.?\d*"
    range_pattern = rf"\(({number_pattern})-({number_pattern})\)|({number_pattern})"
    
    matches = re.findall(range_pattern, line)

    ranges = []
    for m in matches:
        if m[2]:  # single number
            n = float(m[2])
            ranges.append([n, n])
        else:  # range
            ranges.append(sorted([float(m[0]), float(m[1])]))

    line = re.sub(range_pattern, "#", line)

    mod_data = {"line" : line}
    if ranges:
        mod_data["ranges"] = ranges
    
    return mod_data


def make_variant_list(mod, num_variants:int) -> list[int]:
    if mod.variantList:
        mod_variants = list(x-1 for x in mod.variantList.keys())
    else:
        mod_variants = list(range(num_variants))
    return mod_variants


if __name__ == "__main__":
    main()
