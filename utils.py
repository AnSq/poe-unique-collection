#!/usr/bin/env python
from __future__ import annotations

import logging
import json
from typing import Any, cast

import attrs
import cattrs

from consts import META_MISSING_VALUE, POB_EXPORT_FNAME
import models as m

log = logging.getLogger(__name__)


def make_variant_list(lua_mod, num_variants:int) -> list[int]:
    """make a list of (zero-indexed) variant numbers that a Lua mod applies to"""
    if lua_mod.variantList:
        mod_variants = list(x-1 for x in lua_mod.variantList.keys())
    else:
        mod_variants = list(range(num_variants))
    return mod_variants


def asdict_filter(at:attrs.Attribute, value:Any) -> bool:
    """A filter function for attrs.asdict that removes superfluous attributes that don't need to be exported.

    Superfluous attributes are ones that either have thier default value,
    or (for attributes that are not at the end of the attribute list and therefore cannot have a default)
    have a metadata[META_MISSING_VALUE] value and are equal to it.
    Use attrs.field(metadata={META_MISSING_VALUE: ...}) to set it.
    """
    if at.default != attrs.NOTHING and value == at.default:
        return False
    if META_MISSING_VALUE in at.metadata and at.metadata[META_MISSING_VALUE] == value:
        return False
    return True


def load_pob_db(fname:m.FName=POB_EXPORT_FNAME) -> list[m.PoBItem]:
    """load list of PoBItem from json"""
    with open(fname) as f:
        data:list[dict[str,Any]] = json.load(f)
    for item in data:
        _fix_loaded_data(item, m.PoBItem)
        for modlist in (item["implicits"], item["explicits"]):
            for mod in modlist:
                _fix_loaded_data(mod, m.GenericMod)
    return cattrs.structure(data, list[m.PoBItem])


def _fix_loaded_data(o:dict[str,Any], type_:type) -> None:
    """hack to add missing attributes to loaded json. Basically the oposite of utils.asdict_filter"""
    for at in attrs.fields(type_):
        at = (cast)((attrs.Attribute), at)  #noop
        if at.name not in o:
            if at.default != attrs.NOTHING:
                o[at.name] = at.default
            elif META_MISSING_VALUE in at.metadata:
                o[at.name] = at.metadata[META_MISSING_VALUE]
