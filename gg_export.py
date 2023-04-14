#!/usr/bin/env python

import json
import requests
import subprocess
import shutil
import urllib.parse


EXPORT_DIR = "export"

config = {
    "translations": ["English"],
    "tables": [
        {
            "name": "UniqueStashLayout",
            "columns": [
                "WordsKey",
                "ItemVisualIdentityKey",
                "UniqueStashTypesKey",
                "ShowIfEmptyChallengeLeague",
                "ShowIfEmptyStandard",
                "RenamedVersion",
                "BaseVersion",
                "IsAlternateArt"
            ]
        },
        {
            "name": "Words",
            "columns": [
                "Wordlist",
                "Text",
                "Text2"
            ]
        },
        {
            "name": "ItemVisualIdentity",
            "columns": [
                "Id",
                "DDSFile",
                "IsAlternateArt"
            ]
        },
        {
            "name": "UniqueStashTypes",
            "columns": [
                "Id",
                "Order",
                "Name",
                "IsDisabled"
            ]
        }
    ]
}


def main():
    latest_version = requests.get("https://raw.githubusercontent.com/poe-tool-dev/latest-patch-version/main/latest.txt").text
    config["patch"] = latest_version
    
    with open(f"{EXPORT_DIR}/config.json", "w") as f:
        json.dump(config, f, indent="\t")
    
    subprocess.run(shutil.which("pathofexile-dat"), cwd=EXPORT_DIR)

    tables_folder = f"{EXPORT_DIR}/tables/English/"
    with open(tables_folder + "UniqueStashLayout.json") as f:
        unique_stash_layout = json.load(f)
    with open(tables_folder + "UniqueStashTypes.json") as f:
        unique_stash_types = json.load(f)
    with open(tables_folder + "ItemVisualIdentity.json") as f:
        item_visual_identity = json.load(f)
    with open(tables_folder + "Words.json") as f:
        words = json.load(f)
    
    data = []
    for u in unique_stash_layout:
        if u["RenamedVersion"] is None:
            name = words[u["WordsKey"]]["Text2"]
            icon = urllib.parse.quote(item_visual_identity[u["ItemVisualIdentityKey"]]["DDSFile"].split("/")[-1].split(".")[0])
            alt_art = u["IsAlternateArt"]
            
            sort_key = name if u["BaseVersion"] is None else f'{words[unique_stash_layout[u["BaseVersion"]]["WordsKey"]]["Text2"]}/{name}'
            if alt_art:
                sort_key += f"?{icon}"

            data.append({
                "_index"   : u["_index"],
                "name"     : name,
                "icon"     : icon,
                "type"     : unique_stash_types[u["UniqueStashTypesKey"]]["Name"],
                "hidden_challenge" : not u["ShowIfEmptyChallengeLeague"],
                "hidden_standard"  : not u["ShowIfEmptyStandard"],
                "alt_art"  : alt_art,
                "sort_key" : sort_key
            })
    
    with open("gg_export.json", "w") as f:
        json.dump(data, f, indent="\t")


if __name__ == "__main__":
    main()
