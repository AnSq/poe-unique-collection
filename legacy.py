#!/usr/bin/env python

import json
import bisect
import logging
import io

import cattrs
import rapidfuzz
import numpy as np
import numpy.typing as npt

from consts import POB_EXPORT_FNAME
from models import UpgradePath, APIItem, PoBItem, ItemVariant, GenericMod, VariantMatch, VariantMatchList
import utils

from pprint import pprint as pp

log = logging.getLogger(__name__)
vm_log = logging.getLogger(__name__ + ".variant_match")
vm_log.propagate = False

cattrs.register_structure_hook(UpgradePath|str|None, lambda o,t: cattrs.structure(o, UpgradePath) if isinstance(o, dict) else o)  # not sure why it can't figure that out itself

FUZZ_FUNCTION = rapidfuzz.fuzz.ratio


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

        variant_matches = get_variant(test_item, pob_db).backwards_compatible()
        print(f'({i}, "{test_item["name"]}", {variant_matches})')
        if not variant_matches:
            failures.append(test_item["name"])
            print(stream.getvalue())

        vm_log.removeHandler(handler)

    print("\nFailures:")
    pp(failures)


def get_variant(api_item:APIItem, pob_db:list[PoBItem]) -> VariantMatchList:
    """return the variant(s) of the given item"""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    vm_log.addHandler(handler)

    fix_timeless_jewel(api_item)

    pob_item = find_pob_unique(pob_db, api_item["name"], api_item["baseType"])
    if not pob_item:
        return VariantMatchList()

    variants = make_variants(pob_item)

    variant_matches:list[VariantMatch] = []
    for variant in variants:
        variant_matches.append(variant_match_fuzzy(api_item, variant))

    if not variant_matches and "corrupted" not in api_item and pob_item.variant_slots == 1 and "synthesised" not in api_item:
        print(stream.getvalue())
        print("=======================================================")
    vm_log.removeHandler(handler)

    return VariantMatchList(variant_matches)


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

        result.append(ItemVariant(pob_item.name, basetype, variant_name, variant_num, implicits, explicits))

    return result


def variant_match(api_item:APIItem, variant:ItemVariant) -> bool:
    """test if an item matches a variant"""

    vm_log.debug(f'variant testing "{api_item["name"]}, {api_item["baseType"]}" ({api_item["ilvl"]}) against variant "{variant.variant_name}"')

    ensure_modlists(api_item)

    if check_basic_mismatch(api_item, variant):
        return False

    api_implicits_matched = [False] * len(api_item["implicitMods"])
    api_explicits_matched = [False] * len(api_item["explicitMods"])
    variant_implicits_matched = [False] * len(variant.implicits)
    variant_explicits_matched = [False] * len(variant.explicits)

    implicit_lists = (api_item["implicitMods"], variant.implicits, api_implicits_matched, variant_implicits_matched)
    explicit_lists = (api_item["explicitMods"], variant.explicits, api_explicits_matched, variant_explicits_matched)

    for api_modlist, variant_modlist, api_matched, variant_matched in (implicit_lists, explicit_lists):
        for i,api_mod in enumerate(api_modlist):
            for j,variant_mod in enumerate(variant_modlist):
                if mod_match(api_mod, variant_mod, api_item["name"]):
                    api_matched[i] = True
                    variant_matched[j] = True

    bad_api_impl = GenericMod.genericize_mod(api_item['implicitMods'][api_implicits_matched.index(False)]) if api_implicits_matched.count(False) == 1     else ''
    bad_var_impl =                           variant.implicits[variant_implicits_matched.index(False)]     if variant_implicits_matched.count(False) == 1 else ''
    bad_api_expl = GenericMod.genericize_mod(api_item['explicitMods'][api_explicits_matched.index(False)]) if api_explicits_matched.count(False) == 1     else ''
    bad_var_expl =                           variant.explicits[variant_explicits_matched.index(False)]     if variant_explicits_matched.count(False) == 1 else ''

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

    return api_generic.is_inside_range(variant_mod)


def variant_match_fuzzy(api_item:APIItem, variant:ItemVariant, *, fuzz_function=FUZZ_FUNCTION) -> VariantMatch:
    """test if an item fuzzy matches a variant"""

    vm_log.debug(f'fuzzy variant testing "{api_item["name"]}, {api_item["baseType"]}" ({api_item["ilvl"]}) against variant "{variant.variant_name}"')

    ensure_modlists(api_item)

    if check_basic_mismatch(api_item, variant):
        return VariantMatch(variant.variant_name, variant.variant_number, True)

    api_implicit_generics = [GenericMod.genericize_mod(m) for m in api_item["implicitMods"]]
    api_explicit_generics = [GenericMod.genericize_mod(m) for m in api_item["explicitMods"]]

    implicit_matrix = np.zeros((len(api_implicit_generics), len(variant.implicits)))
    explicit_matrix = np.zeros((len(api_explicit_generics), len(variant.explicits)))

    implicit_data = ("implicit", api_implicit_generics, variant.implicits, implicit_matrix)
    explicit_data = ("explicit", api_explicit_generics, variant.explicits, explicit_matrix)

    for which, api_generic_modlist, variant_modlist, matrix in (implicit_data, explicit_data):
        for r,api_generic in enumerate(api_generic_modlist):
            for c,variant_mod in enumerate(variant_modlist):
                matrix[r,c] = mod_match_fuzzy(api_generic, variant_mod, fuzz_function=fuzz_function)

    result = VariantMatch(variant.variant_name, variant.variant_number, False, implicit_matrix.copy(), explicit_matrix.copy())

    scores = []
    api_mod_order = []
    variant_mod_order = []

    for which, api_generic_modlist, variant_modlist, matrix in (implicit_data, explicit_data):
        if (mmc := matrix_max_count(matrix)) > 1:
            log.warning(f'"{api_item["name"]}, {api_item["baseType"]}" {which} matrix max count = {mmc} (>1). This probably indicates an improperly-worded mod in PoB')

        assert len(matrix.shape) == 2 and matrix.shape[0] == matrix.shape[1]

        # find the closest matching api/variant pairs of mods
        for _ in range(matrix.shape[0]):
            # find the largest score in the matrix and store it and the corresponding mods
            r, c = np.unravel_index(np.argmax(matrix), matrix.shape)
            scores.append(matrix[r,c])
            api_mod_order.append(api_generic_modlist[r].line)
            variant_mod_order.append(variant_modlist[c].line)

            # block those mods from being matched again
            matrix[r,:] = -1
            matrix[:,c] = -1

    result.scores = scores
    result.minumim_score = min(scores) if scores else 100
    result.average_score = sum(scores) / len(scores) if scores else 100
    result.aggregate_score = fuzz_function(" ".join(api_mod_order), " ".join(variant_mod_order), processor=normalize_mod_line)

    return result


def mod_match_fuzzy(api_generic:GenericMod, variant_mod:GenericMod, *, fuzz_function=FUZZ_FUNCTION) -> float:
    """find the similarity (from 0 to 100) between two mods using fuzzy matching.
    If the ranges of the API mod don't match the variant mod, the similarity is 0"""

    if not api_generic.is_inside_range(variant_mod):
        return 0
    #TODO: increased/reduced/more/less sign swapping
    return fuzz_function(api_generic.line, variant_mod.line, processor=normalize_mod_line)


def matrix_max_count(matrix:npt.NDArray, threshold:float=100) -> int:
    """count the number of times the threshold is exceeded in each row and column of a matrix and return the maximum"""
    rows, columns = matrix.shape
    row_counts = [0] * rows
    col_counts = [0] * columns
    for r in range(rows):
        for c in range(columns):
            if matrix[r,c] >= threshold:
                row_counts[r] += 1
                col_counts[c] += 1
    counts = row_counts + col_counts
    return max(counts) if counts else 0


def ensure_modlists(api_item:APIItem) -> None:
    """make sure an API item has implicit and explicit members, creating empty lists for them if not"""
    if "implicitMods" not in api_item:
        api_item["implicitMods"] = []
    if "explicitMods" not in api_item:
        api_item["explicitMods"] = []


def check_basic_mismatch(api_item:APIItem, variant:ItemVariant) -> bool:
    """check if an API item has a basic mismatch with a variant (ie, it's name, basetype, or number of mods are unequal)"""
    basic_mismatch = False
    if api_item["name"] != variant.item_name:
        vm_log.debug(f'    name: "{api_item["name"]}"/"{variant.item_name}" (a/v)')
        basic_mismatch = True
    if api_item["baseType"] != variant.basetype:
        vm_log.debug(f'    basetype: "{api_item["baseType"]}"/"{variant.basetype}" (a/v)')
        basic_mismatch = True
    if len(api_item["implicitMods"]) != len(variant.implicits):
        vm_log.debug(f'    implicits: {len(api_item["implicitMods"])}/{len(variant.implicits)} (a/v)')
        basic_mismatch = True
    if len(api_item["explicitMods"]) != len(variant.explicits):
        vm_log.debug(f'    explicits: {len(api_item["explicitMods"])}/{len(variant.explicits)} (a/v)')
        basic_mismatch = True
    return basic_mismatch


def normalize_mod_line(line:str) -> str:
    return (
        line.lower()
        .replace("\n", " ")
        .replace(" additional attack physical damage", " added attack physical damage")  # hack for Clayshaper
    )


if __name__ == "__main__":
    main()
