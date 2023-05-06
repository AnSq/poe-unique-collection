#!/usr/bin/env python

import requests
import urllib.parse
import json

from consts import CORRUPTED_EXPORT_FNAME


def main(fname:str=CORRUPTED_EXPORT_FNAME) -> None:
    query = {
        "tables": "mods, mod_spawn_weights",
        "join on": "mods._pageID=mod_spawn_weights._pageID",
        "fields": 'mods.domain, mods.id, mods.stat_text_raw=text, mods.required_level, GROUP_CONCAT(CONCAT(mod_spawn_weights.tag, ":", mod_spawn_weights.value))=weights, GROUP_CONCAT(mod_spawn_weights.ordinal)=ord,',
        "where": "(mods.domain=1 OR mods.domain=10) AND mods.generation_type=5",
        "group by": "mods.id, mods.domain",
        "order by": '`cargo__mods`.`id`',
        "limit": "5000",
        "format": "json",
    }
    url = f"https://www.poewiki.net/index.php?title=Special:CargoExport&{urllib.parse.urlencode(query)}"

    data = requests.get(url).json()

    for mod in data:
        if mod["id"] == "V2ChillEffectOnYouJewelCorrupted" and "weights" not in mod:  # this mod is broken in the database
            mod["weights"] = {"jewel" : 1000}
            continue

        weights = {}
        for w in mod["weights"].split(","):
            s = w.split(":")
            weights[s[0]] = int(s[1])
        mod["weights"] = weights

    with open(fname, "w") as f:
        json.dump(data, f, indent="\t")



if __name__ == "__main__":
    main()
