#!/usr/bin/env python

import os
import json
import logging
import re
import sys

import pathofexile
import legacy

from pprint import pprint as pp

logging.basicConfig(level=logging.INFO)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


def main():
    poe = pathofexile.PoEClient("oauth.json", "secrets.json", "token.json")
    compare_unique_tabs(poe)


def compare_unique_tabs(poe:pathofexile.PoEClient):
    league, tab, api_items = load_unique_tabs(poe, "-c" in sys.argv)
    
    with open("gg_export.json") as f:
        gg_export = json.load(f)

    with open("pob_export.json") as f:
        pob_db = json.load(f)
    
    api_items_dict = []
    for j, api_item_list in enumerate(api_items):
        api_items_dict.append({})
        for api_item in api_item_list:
            name = api_item["name"]
            icon = api_item["icon"].split("/")[-1].split(".")[0]
            api_items_dict[j][(name, icon)] = api_item

    num_broken = 0
    with open("tab_compare.csv", "w") as f:
        tab0_name = f'{league[0]} {tab[0]["name"]}'
        tab1_name = f'{league[1]} {tab[1]["name"]}'
        f.write(f'#,Name,Icon,Type,Hidden (Challenge),Hidden (Standard),Alt Art,"{tab0_name}","{tab1_name}",Either Tab,Left Variant,Right Variant,L Corrupted,R Corrupted,L Slots,R Slots\n')
        for j,gg_item in enumerate(sorted(gg_export, key=lambda x:x["sort_key"])):
            name = gg_item["name"]
            icon = gg_item["icon"]

            tab = []
            tab.append((name, icon) in api_items_dict[0])
            tab.append((name, icon) in api_items_dict[1])

            variant = [None, None]
            corrupt = [None, None]
            slots = [None, None]
            for i in range(2):
                if tab[i]:
                    it = api_items_dict[i][(name, icon)]
                    variant[i] = legacy.get_variant(it, pob_db)
                    corrupt[i] = "corrupted" in it and it["corrupted"]
                    pob_item = legacy.find_pob_unique(pob_db, name, it["baseType"])
                    slots[i] = pob_item.get("variant_slots", 1) if pob_item else None

            f.write(f'{j},"{name}","{icon}",{gg_item["type"]},{gg_item["hidden_challenge"]},{gg_item["hidden_standard"]},{gg_item["alt_art"]},{tab[0]},{tab[1]},{tab[0] or tab[1]},"{variant[0]}","{variant[1]}",{corrupt[0]},{corrupt[1]},{slots[0]},{slots[1]}\n')
            if tab[0] and not corrupt[0] and variant[0] == [] and slots[0] == 1:
                num_broken += 1
    
    print(num_broken)


def load_unique_tabs(poe:pathofexile.PoEClient, cached=False):
    CACHE_FNAME = "unique_tabs_cache.json"
    
    if cached:
        with open(CACHE_FNAME) as f:
            data = json.load(f)
        
        league = data["league"]
        tab    = data["tab"]
        items  = data["items"]

    else:
        characters = poe.list_characters()
        leagues = []
        for c in characters:
            if c["league"] not in leagues:
                leagues.append(c["league"])
        
        league = []
        tab = []
        stash_tabs = {}
        for j in range(2):
            for i,l in enumerate(leagues):
                print(f"{i}: {l}")
            
            league.append(leagues[prompt_number("Enter a leauge number: ", range(len(leagues)))])
            print()

            if league[j] not in stash_tabs:
                stash_tabs[league[j]] = poe.list_stashes(league[j])
            valids = set()
            for i,t in enumerate(stash_tabs[league[j]]):
                if t["type"] == "UniqueStash":
                    print(f'{i}: {t["name"]}\t{pathofexile.STASH_TAB_COLOUR_NAMES[t["metadata"]["colour"]]}')
                    valids.add(i)
            tab.append(stash_tabs[league[j]][prompt_number("Enter a tab number: ", valids)])
            print()

        utab = []
        items = []
        for i in range(2):
            u = poe.get_stash(league[i], tab[i]["id"], get_children=True)
            utab.append(u)
            it = []
            for s in u["children"]:
                it += s["items"]
            items.append(it)
            print(f'{league[i]} {tab[i]["name"]} {sum(map(lambda x:x["metadata"]["items"], utab[i]["children"]))} {len(it)}')
        
        with open(CACHE_FNAME, "w") as f:
            json.dump({
                "league" : league,
                "tab"    : tab,
                "items"  : items
            }, f, indent='\t')
    
    return (league, tab, items)


def prompt_number(prompt, valids):
    while True:
        try:
            result = int(input(prompt))
            if result in valids:
                return result
        except ValueError as e:
            pass
        
        print("Invalid entry")


def save(data, fname):
    with open(fname, "w") as f:
        json.dump(data, f)


def fix_name(x):
    return re.sub(r'[<>:"/\\|?*]', "~", x)


def download_all(poe:pathofexile.PoEClient, league:str, output_folder:str, start_index=0):
    folder = f"{output_folder}/{league}"
    os.makedirs(folder, exist_ok=True)
    
    stash_list = poe.list_stashes(league)
    save(stash_list, f"{folder}/stash_list.json")
    print(f"Found {len(stash_list)} tabs in {league}")
    
    all_tabs = []
    for i, s in enumerate(stash_list):
        if s["index"] < start_index:
            continue

        print(f'Downloading tab {i+1}/{len(stash_list)} "{s["name"]}" ({s["type"]}) [{s["index"]}]')
        stash_data = poe.get_stash(league, s["id"])
        
        if "children" in stash_data:
            save(stash_data, f'{folder}/{stash_data["index"]}_{fix_name(stash_data["name"])}_{stash_data["type"]}_list.json')

            if stash_data["type"] == "MapStash":
                print("\tSkipping MapStash subtabs")
            else:
                num_subtabs = len(stash_data["children"])
                print(f'\tFound {num_subtabs} subtabs')

                for j, sub in enumerate(stash_data["children"]):
                    print(f"\tDownloading subtab {j+1}/{num_subtabs}")
                    subtab_data = poe.get_stash(league, stash_data["id"], sub["id"])
                    all_tabs.append(subtab_data)
                    save(subtab_data, f'{folder}/{stash_data["index"]}_{j}_{fix_name(subtab_data["name"])}_{subtab_data["type"]}.json')
        else:
            all_tabs.append(stash_data)
            save(stash_data, f'{folder}/{stash_data["index"]}_{fix_name(stash_data["name"])}_{stash_data["type"]}.json')
    
    save(all_tabs, f'{output_folder}/{league}_all.json')


def load_cache(folder:str, league:str):
    parent_names = {}
    all_uniques = []

    with os.scandir(f"{folder}/{league}") as scan:
        for entry in scan:
            # print(entry.path)
            if not entry.is_file():
                continue
            
            with open(entry.path) as f:
                data = json.load(f)
            
            if entry.name.endswith("_list.json"):
                if type(data) == list:
                    continue
                parent_names[data["id"]] = data["name"]
                continue
            
            if "items" not in data:
                # print("\tno items")
                continue

            for item in data["items"]:
                if item["frameType"] not in (3, 9, 10) or item["name"] == "":
                    continue
                
                item["tab_id"] = data["id"]
                if "parent" in data:
                    item["parent_tab_id"] = data["parent"]
                item["tab_name"] = data["name"]

                all_uniques.append(item)
    
    for item in all_uniques:
        if "parent_tab_id" in item:
            item["tab_name"] = parent_names[item["parent_tab_id"]]
        
        if "properties" in item:
            del item["properties"]
        if "flavourText" in item:
            del item["flavourText"]
        if "requirements" in item:
            del item["requirements"]
    
    return all_uniques


if __name__ == "__main__":
    main()
