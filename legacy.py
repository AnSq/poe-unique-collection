#!/usr/bin/env python

import json
import bisect
import logging

from pob_export import genericize_mod

from pprint import pprint as pp

log = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.DEBUG)

    with open("legacy_test.json") as f:
        test_items = json.load(f)
    
    with open("pob_export.json") as f:
        pob_db = json.load(f)
    
    for test_item in test_items:
        print(get_variant(test_item, pob_db))


def get_variant(api_item, pob_db):
    """return the variant name(s) and number(s) of the given item"""

    fix_timeless_jewel(api_item)

    pob_item = find_pob_unique(pob_db, api_item["name"], api_item["baseType"])
    if not pob_item:
        return None

    variants = make_variants(pob_item)
    
    variant_matches = []
    for variant in variants:
        if variant_match(api_item, variant):
            variant_matches.append((variant["variant_name"], variant["variant_number"]))
    
    return variant_matches


def fix_timeless_jewel(api_item):
    """modifes an item if it is a timeless jewel to split the 'conquered by' line to a separate mod"""
    if "explicitMods" not in api_item:
        return

    for i,mod in enumerate(api_item["explicitMods"]):
        split = mod.split("\n")
        if split[-1].startswith("Passives in radius are Conquered by the "):
            api_item["explicitMods"][i] = split[0]
            api_item["explicitMods"].append(split[-1])
            break



def find_pob_unique(pob_db, name, basetype):
    """return the PoB data of the unique item with the given name and basetype"""

    index = bisect.bisect_left(pob_db, name, key=lambda x:x["name"])
    while pob_db[index]["name"] == name:
        if "basetype" in pob_db[index]:
            if pob_db[index]["basetype"] == basetype:
                return pob_db[index]
        else:
            if basetype in [b["basetype"] for b in pob_db[index]["basetypes"]]:
                return pob_db[index]

        index += 1
    
    return None


def make_variants(pob_item):
    """convert a PoB item into a list of fully-hydrated item variants"""
    result = []

    for v,variant_name in enumerate(pob_item["variants"]):
        basetype = ""
        if "basetype" in pob_item:
            basetype = pob_item["basetype"]
        else:
            for b in pob_item["basetypes"]:
                if v in b["variants"]:
                    basetype = b["basetype"]
                    break
        
        implicits = []
        explicits = []
        for outlist,inlist in ((implicits, pob_item["implicits"]), (explicits, pob_item["explicits"])):
            for mod in inlist:
                if v in mod["variants"]:
                    outlist.append(mod)

        result.append({
            "name"           : pob_item["name"],
            "basetype"       : basetype,
            "variant_name"   : variant_name,
            "variant_number" : v,
            "implicits"      : implicits,
            "explicits"      : explicits
        })
    
    return result


def variant_match(api_item, variant):
    """test if an item matches a variant"""

    log.debug(f'variant testing "{api_item["name"]}" against variant "{variant["variant_name"]}"')

    if "implicitMods" not in api_item:
        api_item["implicitMods"] = []
    if "explicitMods" not in api_item:
        api_item["explicitMods"] = []
    
    if (
        api_item["name"] != variant["name"]
        or api_item["baseType"] != variant["basetype"]
        or len(api_item["implicitMods"]) != len(variant["implicits"])
        or len(api_item["explicitMods"]) != len(variant["explicits"])
    ):
        log.debug("    basic mismatch")
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
    
    log.debug(f"    api impl: {api_implicits_matched}")
    log.debug(f"    var impl: {variant_implicits_matched}")
    log.debug(f"    api expl: {api_explicits_matched}")
    log.debug(f"    var expl: {variant_explicits_matched}")
    
    return all([all(x) for x in (api_implicits_matched, api_explicits_matched, variant_implicits_matched, variant_explicits_matched)])


def mod_match(api_mod:str, variant_mod:dict, item_name=None):  # item_name is a debugging param
    """test if a concrete mod matches a generic mod"""
    
    api_generic = genericize_mod(api_mod)

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

    if normalize_mod_line(api_generic["line"]) != normalize_mod_line(variant_mod["line"]):
        return False  #TODO: increased/reduced/more/less sign swapping

    if "ranges" in api_generic or "ranges" in variant_mod:
        assert len(api_generic["ranges"]) == len(variant_mod["ranges"])

        for api_range, variant_range in zip(api_generic["ranges"], variant_mod["ranges"]):
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
