#!/usr/bin/env python

import os
import json
import logging
import attrs

import lupa.lua51 as lupa  #type: ignore

from typing import Any, Sequence
from pprint import pprint as pp

from consts import POB_DIR
from models import PoBItem
import utils

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
                return self._encode_object(attrs.asdict(o, filter=utils.asdict_filter, recurse=False))
            return super().encode(o)
except ImportError:
    class JE (json.JSONEncoder):  #type: ignore
        def default(self, o:Any) -> Any:
            if attrs.has(o):
                # recursion in attrs means that the filter is only applied to the top-level attrs object.
                # recurse=False lets json handle the recursion, which allows the filter to apply to member objects
                return attrs.asdict(o, filter=utils.asdict_filter, recurse=False)
            return super().default(o)


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


def pob_export(uniqueDB:Any, generated_names:Sequence[str]) -> list[PoBItem]:
    uniques:list[PoBItem] = []
    for i in uniqueDB:
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
