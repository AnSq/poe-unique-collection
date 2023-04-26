#!/usr/bin/env python

import json
import bisect
import logging
import io
from typing import Any, cast

import attrs
import cattrs
import rapidfuzz

from consts import POB_EXPORT_FNAME
from models import UpgradePath, APIItem, PoBItem, VariantMatch, ItemVariant, GenericMod
import utils

from pprint import pprint as pp

log = logging.getLogger(__name__)
vm_log = logging.getLogger(__name__ + ".variant_match")
vm_log.propagate = False

cattrs.register_structure_hook(UpgradePath|str|None, lambda o,t: cattrs.structure(o, UpgradePath) if isinstance(o, dict) else o)  # not sure why it can't figure that out itself


def main() -> None:
    logging.basicConfig(level=logging.DEBUG)

    with open("test_data/legacy_test.json") as f:
        test_items:list[APIItem] = json.load(f)

    pob_db = utils.load_pob_db(POB_EXPORT_FNAME)

    failures = []
    for i,test_item in enumerate(test_items):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        vm_log.addHandler(handler)

        variant = get_variant(test_item, pob_db)
        print(f'({i}, "{test_item["name"]}", {variant})')
        if not variant:
            failures.append(test_item["name"])
            print(stream.getvalue())

        vm_log.removeHandler(handler)

    print("\nFailures:")
    pp(failures)


def get_variant(api_item:APIItem, pob_db:list[PoBItem]) -> list[VariantMatch]|None:
    """return the variant name(s) and number(s) of the given item"""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    vm_log.addHandler(handler)

    fix_timeless_jewel(api_item)

    pob_item = find_pob_unique(pob_db, api_item["name"], api_item["baseType"])
    if not pob_item:
        return None

    variants = make_variants(pob_item)

    variant_matches:list[VariantMatch] = []
    for variant in variants:
        if variant_match(api_item, variant):
            variant_matches.append((variant["variant_name"], variant["variant_number"]))

    if not variant_matches and "corrupted" not in api_item and pob_item.variant_slots == 1 and "synthesised" not in api_item:
        print(stream.getvalue())
        print("=======================================================")
    vm_log.removeHandler(handler)

    return variant_matches


def fix_timeless_jewel(api_item:APIItem) -> None:
    """modifes an item if it is a timeless jewel to split the 'conquered by' line to a separate mod"""
    if "explicitMods" not in api_item:
        return

    for i,mod in enumerate(api_item["explicitMods"]):
        split = mod.split("\n")
        if split[-1].startswith("Passives in radius are Conquered by the "):
            api_item["explicitMods"][i] = split[0]
            api_item["explicitMods"].append(split[-1])
            break



def find_pob_unique(pob_db:list[PoBItem], name:str, basetype:str) -> PoBItem|None:
    """return the PoB data of the unique item with the given name and basetype"""

    index = bisect.bisect_left(pob_db, name, key=lambda x:x.name)
    while pob_db[index].name == name:
        if pob_db[index].basetype is not None:
            if pob_db[index].basetype == basetype:
                return pob_db[index]
        else:
            if basetype in [b.basetype for b in pob_db[index].basetypes]:
                return pob_db[index]

        index += 1

    return None


def make_variants(pob_item:PoBItem) -> list[ItemVariant]:
    """convert a PoB item into a list of fully-hydrated item variants"""
    result = []

    for variant_num, variant_name in enumerate(pob_item.variants):
        basetype = ""
        if pob_item.basetype is not None:
            basetype = pob_item.basetype
        else:
            for b in pob_item.basetypes:
                if variant_num in b.variants:
                    basetype = b.basetype
                    break

        implicits:list[GenericMod] = []
        explicits:list[GenericMod] = []
        for outlist,inlist in ((implicits, pob_item.implicits), (explicits, pob_item.explicits)):
            for mod in inlist:
                if variant_num in mod.variants:
                    outlist.append(mod)

        result.append({
            "name"           : pob_item.name,
            "basetype"       : basetype,
            "variant_name"   : variant_name,
            "variant_number" : variant_num,
            "implicits"      : implicits,
            "explicits"      : explicits
        })

    return result


def variant_match(api_item:APIItem, variant:ItemVariant) -> bool:
    """test if an item matches a variant"""

    vm_log.debug(f'variant testing "{api_item["name"]}, {api_item["baseType"]}" ({api_item["ilvl"]}) against variant "{variant["variant_name"]}"')

    if "implicitMods" not in api_item:
        api_item["implicitMods"] = []
    if "explicitMods" not in api_item:
        api_item["explicitMods"] = []

    basic_mismatch = False
    if api_item["name"] != variant["name"]:
        vm_log.debug(f'    name: "{api_item["name"]}"/"{variant["name"]}" (a/v)')
        basic_mismatch = True
    if api_item["baseType"] != variant["basetype"]:
        vm_log.debug(f'    basetype: "{api_item["baseType"]}"/"{variant["basetype"]}" (a/v)')
        basic_mismatch = True
    if len(api_item["implicitMods"]) != len(variant["implicits"]):
        vm_log.debug(f'    implicits: {len(api_item["implicitMods"])}/{len(variant["implicits"])} (a/v)')
        basic_mismatch = True
    if len(api_item["explicitMods"]) != len(variant["explicits"]):
        vm_log.debug(f'    explicits: {len(api_item["explicitMods"])}/{len(variant["explicits"])} (a/v)')
        basic_mismatch = True
    if basic_mismatch:
        return False

    api_implicits_matched = [False] * len(api_item["implicitMods"])
    api_explicits_matched = [False] * len(api_item["explicitMods"])
    variant_implicits_matched = [False] * len(variant["implicits"])
    variant_explicits_matched = [False] * len(variant["explicits"])

    implicit_lists = (api_item["implicitMods"], variant["implicits"], api_implicits_matched, variant_implicits_matched)
    explicit_lists = (api_item["explicitMods"], variant["explicits"], api_explicits_matched, variant_explicits_matched)

    for api_modlist, variant_modlist, api_matched, variant_matched in (implicit_lists, explicit_lists):
        for i,api_mod in enumerate(api_modlist):
            for j,variant_mod in enumerate(variant_modlist):
                if mod_match(api_mod, variant_mod, api_item["name"]):
                    api_matched[i] = True
                    variant_matched[j] = True

    # fuzzy = rapidfuzz.process.cdist([genericize_mod(x)["line"] for x in api_item["explicitMods"]], [x["line"] for x in variant["explicits"]], processor=normalize_mod_line)
    # vm_log.debug(fuzzy.round(0))

    bad_api_impl = GenericMod.genericize_mod(api_item['implicitMods'][api_implicits_matched.index(False)]) if api_implicits_matched.count(False) == 1     else ''
    bad_var_impl =                           variant['implicits'][variant_implicits_matched.index(False)]  if variant_implicits_matched.count(False) == 1 else ''
    bad_api_expl = GenericMod.genericize_mod(api_item['explicitMods'][api_explicits_matched.index(False)]) if api_explicits_matched.count(False) == 1     else ''
    bad_var_expl =                           variant['explicits'][variant_explicits_matched.index(False)]  if variant_explicits_matched.count(False) == 1 else ''

    vm_log.debug(f"    api impl: {api_implicits_matched} {bad_api_impl}")
    vm_log.debug(f"    var impl: {variant_implicits_matched} {bad_var_impl}")
    vm_log.debug(f"    api expl: {api_explicits_matched} {bad_api_expl}")
    vm_log.debug(f"    var expl: {variant_explicits_matched} {bad_var_expl}")

    return all([all(x) for x in (api_implicits_matched, api_explicits_matched, variant_implicits_matched, variant_explicits_matched)])


def mod_match(api_mod:str, variant_mod:GenericMod, item_name:str|None=None) -> bool:  # item_name is a debugging param
    """test if a concrete mod matches a generic mod"""

    api_generic = GenericMod.genericize_mod(api_mod)

    # if api_generic["line"] != variant_mod["line"] and api_generic["line"].lower() == variant_mod["line"].lower():
    #     print(item_name)
    #     print(api_generic["line"])
    #     print(variant_mod["line"])
    #     print()

    # if api_generic["line"].lower() != variant_mod["line"].lower() and api_generic["line"].lower().replace("\n"," ") == variant_mod["line"].lower():
    #     print(item_name)
    #     print(api_generic["line"])
    #     print(variant_mod["line"])
    #     print()

    if normalize_mod_line(api_generic.line) != normalize_mod_line(variant_mod.line):
        return False  #TODO: increased/reduced/more/less sign swapping

    if api_generic.ranges or variant_mod.ranges:
        assert len(api_generic.ranges) == len(variant_mod.ranges)

        for api_range, variant_range in zip(api_generic.ranges, variant_mod.ranges):
            if api_range[0] < variant_range[0] or api_range[1] > variant_range[1]:
                return False

    return True


def normalize_mod_line(line:str) -> str:
    return (
        line.lower()
        .replace("\n", " ")
        .replace(" additional attack physical damage", " added attack physical damage")  # hack for Clayshaper
    )


if __name__ == "__main__":
    main()
