#!/usr/bin/env python

import os
import json
import logging
import re
import urllib.parse

import pathofexile

from pprint import pprint as pp

logging.basicConfig(level=logging.INFO)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


def main():
    poe = pathofexile.PoEClient("oauth.json", "secrets.json", "token.json")
    compare_unique_tabs(poe)


def compare_unique_tabs(poe:pathofexile.PoEClient):
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
    
    with open("gg_export.json") as f:
        uniques = json.load(f)
    
    items_dict = []
    for j, item_list in enumerate(items):
        items_dict.append({})
        for item in item_list:
            name = item["name"]
            icon = item["icon"].split("/")[-1].split(".")[0]
            items_dict[j][(name, icon)] = item

    with open("tab_compare.csv", "w") as f:
        tab0_name = f'{league[0]} {tab[0]["name"]}'
        tab1_name = f'{league[1]} {tab[1]["name"]}'
        f.write(f'#,Name,Icon,Type,Hidden (Challenge),Hidden (Standard),Alt Art,"{tab0_name}","{tab1_name}",Either Tab\n')
        for j,u in enumerate(sorted(uniques, key=lambda x:x["sort_key"])):
            name = u["name"]
            icon = u["icon"]
            tab0 = (name, icon) in items_dict[0]
            tab1 = (name, icon) in items_dict[1]
            f.write(f'{j},"{name}","{icon}",{u["type"]},{u["hidden_challenge"]},{u["hidden_standard"]},{u["alt_art"]},{tab0},{tab1},{tab0 or tab1}\n')


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
