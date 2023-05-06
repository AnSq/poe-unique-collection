#!/usr/bin/env python

import requests
import urllib.parse
import json

from consts import CORRUPTED_EXPORT_FNAME


def main(fname:str=CORRUPTED_EXPORT_FNAME) -> None:
    query = {
        "tables": "mods, mod_spawn_weights",
        "join on": "mods._pageID=mod_spawn_weights._pageID",
        "fields": 'mods.stat_text_raw=text, GROUP_CONCAT(CONCAT(mod_spawn_weights.tag, ":", mod_spawn_weights.value))=weights',
        "where": "(mods.domain=1 OR mods.domain=10) AND mods.generation_type=5",
        "group by": "text",
        "limit": "5000",
        "format": "json",
    }
    url = f"https://www.poewiki.net/index.php?title=Special:CargoExport&{urllib.parse.urlencode(query)}"

    data = requests.get(url).json()

    for mod in data:
        if mod["text"] == "(25-20)% reduced Effect of Chill on you" and "weights" not in mod:  # this mod is broken in the database
            mod["weights"] = {"jewel" : 1000}
            continue

        weights:dict[str,int] = {}
        for weight_spec in mod["weights"].split(","):
            type_name, value = weight_spec.split(":")
            value = int(value)
            if type_name not in weights or value > weights[type_name]:
                weights[type_name] = value
        mod["weights"] = weights

    with open(fname, "w") as f:
        json.dump(data, f, indent="\t")



if __name__ == "__main__":
    main()
