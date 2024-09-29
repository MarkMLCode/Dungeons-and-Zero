import typer
import os
import json
import random as rd
import requests
from datetime import datetime, date
import shutil
import threading

import sys
import time
from collections import defaultdict

import string
import traceback

import sys
import copy
import logging
from queue import Queue

from collections import Counter
from typing import Tuple, Dict, Any
from colorama import Fore, Back, Style, just_fix_windows_console

from utils.utils import read_json, write_json, create_convo_obj, is_moderation_flagged, enumerate_folders, send_open_ai_gpt_message, count_tokens, remove_all_asterisks, get_random_choice, remove_username_prefix, segment_text, format_msg_oai, remove_parentheses, extract_json_from_response, process_dice, validate_unspecified, combine_array_as_sentence, write_to_show_text, unlock_next_msg, capitalize_first_letter, get_inventory_text, extract_int, has_talent, get_talent, extract_text_in_parenthesis, singularize_name,join_with_and, validate_bool, add_battle_info_to_convo_obj, get_binomial_dist_result, add_narrator_fields_to_convo, process_user_msg_emotion, process_unrelated, process_refused, convert_text_segments_to_objs, create_expression_obj, remove_system_prefix, create_text_segment_objs, extract_username_from_prefix, remove_username_inside_text, update_print_log_settings, print_log, print_special_text, merge_config, create_folders, get_limited_resources_triples, get_current_quest_text, get_complete_inventory_text, get_available_spell_slots

from utils.alarm import ring_alarm
from utils.print_logger import PrintLogger
from utils.google_drive import update_char_sheet_google_doc, setup_google_drive_credentials
from utils.livestream import get_next_message_stream, del_all_expired_messages
from utils.web import update_char_sheet_html_file

from ai.dnd_server import send_text_command_dnd, get_proficiency_bonus, alignment_to_words, recover_spell_slots_arcane_recovery, get_mc_health_status, get_incapacitated_combatants, update_frenzy_status, get_stat_mod, are_opponents_surprised, get_combatants_cr, get_monsters_attribute_text, get_long_stat_name, get_opponent_max_spell_level, get_monsters_single_value, spells_per_day, use_hit_die, extract_autocast_lvl, get_daily_sorcery_points, get_daily_ki_points, get_monsters_hp, get_char_classes, find_lowest_no_upcast_slot, get_max_spell_level, get_max_cr_additional_opponents, get_bardic_inspiration_dice

from ai.rolls import get_roll_from_action, process_roll_attack, process_roll_skill, process_cast_spell, process_use_item, process_roll_saving_throw, get_clean_item_name, process_combatant_sheets, process_combatant_turn, get_combatant_sheet, Combatant_Action_Object, can_use_spell, get_attack_bonus, get_damage_bonus, get_base_extra_attacks, get_sneak_attack_dice, get_group_from_combatant, get_groups_from_combatants, get_bonus_rage_damage, get_touch_of_magic_bonus, list_class_spells, find_entry_names_in_text, get_remaining_opponents_text, process_are_opponents_defeated, add_explanation_last_opponent_health, get_special_abilities_json_names, get_use_special_ability_stat, create_group, has_matching_token_image, create_section_obj, get_char_obj_healing, get_battle_info_combatants, Cast_Spell_Object

import re
import concurrent.futures

just_fix_windows_console()

#Global
no_gen = 0
previous_user_prompt_web_info = ""
root_path = "../"
ai_path = "ai/"

ai_config_path = f"{ai_path}_config/"
ai_config_file_path = f"{ai_config_path}config.json"

chat_mode_message_history_path = f"{ai_path}chat_mode_message_history/"
chat_history_file = 'messages_history.json'
dnd_history_file = 'messages_history_dnd.json'
dnd_with_chat_history_file = 'messages_history_dnd_chat_mode.json'
archives_dnd_path = f'{ai_path}_archives_dnd/'
stories_history_path = f'{archives_dnd_path}stories_history.json'
root_music_path = f"{root_path}music"
current_story_path = f'{ai_path}current_story/'
current_convo_path = f'{root_path}current_convo/'
current_convo_debug_path = f'{root_path}current_convo_debug/'
blacklist_path = f'{ai_path}blacklist'
character_sheet_html_file = "character_sheet.html"

# if a folder doesn't exist, create it
create_folders([archives_dnd_path, current_story_path, chat_mode_message_history_path, root_music_path, current_convo_path, current_convo_debug_path, blacklist_path])

app = typer.Typer()

# Global vars
auto_mode = False
hardcode_username = None

stream_path = f"{root_path}current_stream_messages"
tts_config_path = "tts/_config/"

is_stream = False
next_msg_direct_mode = None

quests_added_eval = None
main_quests_completed_eval = None
quests_completed_eval = None
important_characters_eval = None
location_eval = None
location_category_eval = None
inventory_eval = None
update_rest_eval = None
battle_end_eval = None

# SETUP LOGGING
# Create folder if it doesn't exist
if not os.path.exists(f"{ai_path}logs"):
    os.makedirs(f"{ai_path}logs")

logname = f"{ai_path}logs/log_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
logging.basicConfig(
    format="%(levelname)s %(asctime)s %(message)s",
    datefmt= '%H:%M:%S', 
    level=logging.INFO,
    handlers=[
        logging.FileHandler(logname, mode='w')#, 
        #logging.StreamHandler() # Report logs to the console
    ])

# Redirect print to logging, while still printing to console
sys.stdout = PrintLogger(logging.getLogger('STDOUT'), sys.stdout)

def get_ai_config():
    config = read_json(ai_config_file_path)

    config_custom_path = f"{ai_config_path}config_custom.json"
    if os.path.exists(config_custom_path):
        config_custom = read_json(f"{ai_config_path}config_custom.json")
        config = merge_config(config, config_custom)

    return config

initial_config = get_ai_config()
update_print_log_settings(initial_config)

if initial_config.get("update_google_doc", False):
    setup_google_drive_credentials() # Setup credentials for google drive

print("\n---DnD server started---")

def get_story_file(filename, create_file_when_missing = True):
    if not os.path.exists(current_story_path + filename):
        #print(f"ERROR: {filename} not found")
        if create_file_when_missing:
            # Create file if it doesn't exist
            with open(current_story_path + filename, 'w+', encoding="utf-8") as f:
                f.write("[]")
            return []
        else:
            return None
    
    return read_json(current_story_path + filename)

# Current story files
def get_current_story():
    return get_story_file('current_story.json', False)

def set_current_story(current_story):
    write_json(f'{current_story_path}current_story.json', current_story)

def get_generated_text_emotions():
    return get_story_file('generated_text_emotions.json')

def set_generated_text_emotions(generated_text_emotions):
    write_json(current_story_path + 'generated_text_emotions.json', generated_text_emotions)

def get_messages_history(filename):
    # Chat history stays in the main folder (for now)
    if filename == chat_history_file:
        return read_json(chat_mode_message_history_path + filename)
    else:
        return get_story_file(filename)
    
def set_messages_history(filename, messages_history):
    if filename == chat_history_file:
        write_json(chat_mode_message_history_path + filename, messages_history)
    else:
        write_json(current_story_path + filename, messages_history)

def get_combatant_sheets():
    return get_story_file("combatant_sheets.json")

def set_combatant_sheets(combatant_sheet):
    write_json(current_story_path + "combatant_sheets.json", combatant_sheet)

def get_previous_battles_history():
    return get_story_file("previous_battles_history.json")

def set_previous_battles_history(previous_battles_history):
    write_json(current_story_path + "previous_battles_history.json", previous_battles_history)

def log_current_story(current_story, location):
    # Add current story to the logs_current_story folder (create if doesn't exist)
    folder_name = f"{ai_path}logs_current_story"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    current_turn = current_story["current_turn"]
    char_name = current_story["char_name"].replace("'", "").replace(" ", "_")

    # Remove anything in parenthesis from the name
    char_name = re.sub(r'\([^)]*\)', '', char_name).strip()

    # Save the current story in the debug folder
    file_name = f'{datetime.now().strftime("%Y%m%d%H%M%S%f")[:-4]}_{current_story["id"]}_{char_name}_{current_turn}_{location}' 

    write_json(f"{folder_name}/{file_name}.json", current_story)

def get_current_event_prompt(user_message, setup, from_dnd=False):
    # Add your Bing Search V7 subscription key and endpoint to your environment variables.
    subscription_key = os.environ['BING_SEARCH_V7_SUBSCRIPTION_KEY']
    endpoint = os.environ['BING_SEARCH_V7_ENDPOINT'] + "/v7.0/search"

    # Query term(s) to search for. 
    query = user_message

    # Construct a request
    mkt = 'en-US' # default market is en-CA if I don't set it, not ideal
    filter = ['Webpages']
    if not from_dnd:
        filter.append('News')

    params = { 'q': query, 'count' : '2', 'responseFilter' : ['News', 'Webpages'], 'mkt': mkt }
    headers = { 'Ocp-Apim-Subscription-Key': subscription_key }

    # Call the API
    try:
        response_http = requests.get(endpoint, headers=headers, params=params)
        response_http.raise_for_status()
        response = response_http.json()
    except Exception as ex:
        print(ex)
        return ""
    
    global previous_user_prompt_web_info
    web_info = []

    if "news" in response:
        news_response = response["news"]
        news_arr = news_response["value"]
        
        for news in news_arr:
            web_info.append(f"Article titled '{news['name']}': {news['description']}")

    if "webPages" in response:
        webpages_response = response["webPages"]
        webpages_arr = webpages_response["value"]
        
        for webpage in webpages_arr:
            web_info.append(f"Webpage titled '{webpage['name']}': {webpage['snippet']}")

    prompt = ""

    if len(web_info) > 0:
        setup = read_json(f'{ai_config_path}setup.json') # Use the default setup file

        prompt = f"{setup['results_from_the_web']}"

        ## Add web info from previous prompt too
        if previous_user_prompt_web_info != "" and not from_dnd:
            prompt = prompt + " " + previous_user_prompt_web_info + "|"

        # Join current web info with '|' and save it for next prompt
        current_web_info = '|'.join(web_info)
        previous_user_prompt_web_info = current_web_info

        prompt =  f"{prompt} {'|'.join(web_info)} | {setup['conclude_current_events']}"

    return prompt

def get_random_choice_text(choices):
    return get_random_choice(choices)["text"]

def archive_current_story():
    current_story = get_current_story()
    char_name = current_story["char_name"] if current_story is not None else "unknown" # Archive all relevant files even if current story is none, in case I did it manually but didn't copy all files.

    new_folder_name = datetime.now().strftime('%Y%m%d%H%M%S') + "_" + char_name

    base_directory = os.getcwd()
    new_folder_path = os.path.join(base_directory, f'{ai_path}_archives_dnd', new_folder_name)

    os.makedirs(new_folder_path, exist_ok=True)

    # Copy the current story folder to the new_folder_path
    for file_name in os.listdir(current_story_path):
        original_file_path = os.path.join(current_story_path, file_name)
        new_file_path = os.path.join(new_folder_path, file_name)
        shutil.copy2(original_file_path, new_file_path)

def get_random_choice_no_weight(choices):
    choices_list = list(choices)
    random_choice = rd.choice(choices_list)  # use rd.choice for single item
    return random_choice

# Get a random choice from the choices that weren't chosen yet
def get_unchosen_choices(choices, chosen_counts):
    min_count = min(chosen_counts.get(choice, 0) for choice in choices)
    unchosen = [choice for choice in choices if chosen_counts.get(choice, 0) == min_count]
    return unchosen

# find character object by name
def get_char_by_name(char_name, characters_arr):
    char_obj = next((char for char in characters_arr if char['name'].lower() == char_name.lower()), None)

    if char_obj is None:
        print(f"ERROR: Character {char_name} not found in characters array")

    return char_obj

# Get a random character and scenarios, but only from the pool that weren't chosen yet. 
    # Once all chosen, loop back and go through all scenarios randomly again, repeat.
def get_char_and_scenario(stories_history, dnd_characters, specific_char_name = None, specific_scenario_id = None, use_generic_scenario = False):
    chosen_characters_counts = defaultdict(int)
    chosen_scenarios_counts = defaultdict(lambda: defaultdict(int))

    # Generic scenarios are always completely random, so don't need to count them
    if not use_generic_scenario:
        for story in stories_history:
            chosen_characters_counts[story['character']] += 1
            chosen_scenarios_counts[story['character']][story['scenario']] += 1

    characters_arr = [char for char in dnd_characters["characters_with_scenarios"] if not char.get('locked', False) and not (char.get("is_non_combatant", False) and use_generic_scenario)] # Ignore locked characters or non-combatants if using generic scenario

    char_name = None
    char_obj = None
    
    # If a specific character is chosen, find it
    if specific_char_name is not None:
        char_name = specific_char_name
        char_obj = get_char_by_name(char_name, characters_arr)

    if char_obj is None:
        # Find unchosen characters
        unchosen_characters = get_unchosen_choices([char_obj['name'] for char_obj in characters_arr], chosen_characters_counts)
        char_name = get_random_choice_no_weight(unchosen_characters)
        char_obj = get_char_by_name(char_name, characters_arr) # find character object by name

    # Find unchosen scenarios for that character
    scenarios_arr = char_obj["scenarios"] if not use_generic_scenario else dnd_characters["generic_scenarios"]
    if specific_scenario_id is None:
        unchosen_scenarios = get_unchosen_choices([scenario_obj['id'] for scenario_obj in scenarios_arr], chosen_scenarios_counts[char_name])

        # Choose a random id
        scenario_id = get_random_choice_no_weight(unchosen_scenarios)
    else:
        scenario_id = specific_scenario_id

    return char_obj, scenario_id

def get_max_hp(level, hit_die, con_mod, char_obj):
    # Tough talent
    has_toughness = has_talent("tough", char_obj)
    toughness_mod = 2 if has_toughness else 0
    toughness_text = " + 2" if has_toughness else ""

    # Aid spell autocast every day
    dnd_text = ""
    dnd_mod = 0
    dnd_talent = get_talent("aid (autocast", char_obj, partial_match=True)

    if dnd_talent is not None:
        dnd_text = extract_text_in_parenthesis(dnd_talent)
        dnd_level = extract_autocast_lvl(dnd_text)
        dnd_mod = max(dnd_level-1, 0) * 5
        dnd_text = f"+ {dnd_mod} (aid autocast)"

    if has_toughness:
        print_log("Character has the toughness feat (+2 hp per level)")

    max_hp = hit_die + con_mod + toughness_mod

    hp_rolls = [f"level_1 : {hit_die} + {con_mod}{toughness_text} = {max_hp}"]

    for i in range(2, level + 1):
        roll = rd.randint(1, hit_die)
        hp_rolls.append(f"level_{i} : {roll} + {con_mod}{toughness_text} = {roll + con_mod}")
        max_hp += roll + con_mod + toughness_mod

    if dnd_text != "":
        hp_rolls.append(dnd_text)
        max_hp += dnd_mod
        
    print_log("; ".join(hp_rolls))
    print_log(f"max hp: {max_hp}")

    return max_hp

def get_starting_money(char_obj):
    starting_gold_dices = char_obj["starting_gold"]
    dice, _ = process_dice(starting_gold_dices)
    if len(dice) == 0:
        print(f"ERROR: Invalid starting gold dice: {starting_gold_dices}")
        return 0, 0

    num_dice, num_faces = dice[0][0], dice[0][1]
    total_gold = sum([rd.randint(1, num_faces) for _ in range(num_dice)])

    if total_gold >= 1000:
        gold = total_gold % 1000
        pp = int((total_gold - gold) / 10) # Convert gold to pp and remaining gold
    else:
        gold = total_gold
        pp = 0

    return pp, gold

def json_obj_to_string(json_obj):
    return ", ".join([f"{key}: {value}" for key, value in json_obj.items()])

def join_with_comma(arr):
    return ", ".join(arr)

def get_quests_text_arr(quests, exlude_extra_info = False):
    quests_str_arr = []

    for quest in quests:
        # If a quest obj or not (main quests have no obj)
        if isinstance(quest, dict):
            extra_info = []
            description = quest.get("description", "")

            # Add quest giver and reward between parenthesis at the end
            if not exlude_extra_info:
                quest_giver = quest.get("quest_giver", "")
                if quest_giver != "":
                    extra_info.append(f"Quest giver: {quest_giver}")

                reward = quest.get("reward", "")
                if reward != "":
                    extra_info.append(f"Reward: {reward}")
                    
                extra_info_str = " (" + ", ".join(extra_info) + ")" if len(extra_info) > 0 else ""

                quest_text = f"{description.strip(' ,.!?')}{extra_info_str}" if extra_info_str != "" else description
            else:
                quest_text = description

        else:
            quest_text = quest

        quest_text.strip(" .,?!") # Will be added later if nec
        quests_str_arr.append(quest_text)

    return quests_str_arr

def join_quests_semicolon(quests, exlude_extra_info = False):
    return "; ".join(get_quests_text_arr(quests, exlude_extra_info))

def format_spells(array):
    if len(array) != 5 and len(array) != 9:
        print("ERROR: Invalid input. The array must contain 5 or 9 numbers.")
        return ""
    
    # Remove spells with 0 slots
    available_spells_arr_text = [f"{array[i]} level {i+1}" for i in range(len(array)) if array[i] > 0]

    return ', '.join(available_spells_arr_text)

# Skip dual wield and frenzy, as they should not be shown in the talent list
def removed_skipped_talents(talents):
    skipped_talents = ["dual wield", "frenzy"]
    return [talent for talent in talents if talent.lower() not in skipped_talents]

def get_all_talent_skills(talent_name_root, talents):
    skills = []

    for talent in talents:
        talent_lower = talent.lower()
        if talent_name_root in talent_lower:
            skills.append(extract_text_in_parenthesis(talent_lower))

    return skills

def get_stat_mod_from_placeholder(talent_name, current_story, is_half = False):
    stat_mod_text = r"#stat_mod_(.*?)#" if not is_half else r"#half_stat_mod_(.*?)#"

    # Get the stat name from the talent name, using regex (ex: #stat_mod_str#)
    match = re.search(stat_mod_text, talent_name)
    stat_name = match.group(1) if match is not None else None

    if stat_name is None:
        print(f"ERROR: No stat name found in talent name {talent_name}")
        return None

    stat_mod = get_stat_mod(current_story, stat_name) if not is_half else int(get_stat_mod(current_story, stat_name) / 2)

    return stat_name, stat_mod

def replace_parenthesis_content(text, parenthesis_content):
    if parenthesis_content is None:
        return text
    
    return text.replace("#parenthesis_content#", parenthesis_content).replace("#domain_name#", parenthesis_content)

def get_talent_obj(target_talent_name, talent_objs):
    target_talent_name_lower = target_talent_name.lower()

    autocast_lvl = extract_autocast_lvl(target_talent_name_lower) if "autocast" in target_talent_name_lower else None
    parenthesis_content = extract_text_in_parenthesis(target_talent_name_lower)

    # Try exact match first
    for talent_obj in talent_objs:
        talent_name = talent_obj["name"]

        # Replace the autocast level in the talent's name with the correct one
        if autocast_lvl is not None:
            talent_name = talent_name.replace("#autocast_level#", f"{autocast_lvl}")

        # Replace the parenthesis content (domain name) in the talent's name with the correct one
        if parenthesis_content is not None:
            talent_name = replace_parenthesis_content(talent_name, parenthesis_content.capitalize())

        alt_talent_names = [replace_parenthesis_content(alt_name, parenthesis_content) for alt_name in talent_obj.get("alt_names", [])]
        all_talent_names = [talent_name] + alt_talent_names

        # Find the next talent that is an exact match, from either the main or alt names
        found_talent_name = next((talent_name_to_match for talent_name_to_match in all_talent_names if target_talent_name_lower == talent_name_to_match.lower()), None)

        # If the talent name is found, return a clone of the talent object
        if found_talent_name is not None:
            cloned_obj = copy.deepcopy(talent_obj)
            cloned_obj["name"] = found_talent_name # update the name
            cloned_obj["parenthesis_content"] = parenthesis_content
            return cloned_obj
        
    # If no exact match found, try partial match (ex: expertise, etc.)
    for talent_obj in talent_objs:
        talent_name = talent_obj["name"]

        alt_talent_names = [alt_name for alt_name in talent_obj.get("alt_names", [])]
        all_talent_names = [talent_name] + alt_talent_names

        # Fine the next talent that partially matches the target talent name, from either the main or alt names
        found_talent_name = next((talent_name_to_match for talent_name_to_match in all_talent_names if target_talent_name_lower in talent_name_to_match.lower() or talent_name_to_match.lower() in target_talent_name_lower), None)

        # If the talent name is found, return a clone of the talent object
        if found_talent_name is not None:
            cloned_obj = copy.deepcopy(talent_obj)
            cloned_obj["name"] = found_talent_name # update the name
            cloned_obj["parenthesis_content"] = parenthesis_content
            return cloned_obj
        
    return None

# Return the list of all talents name + description from dnd_talents.json file that matches the current character's talents
def get_talent_explanations_lists(current_story):
    talent_objs = read_json(f"{ai_config_path}dnd_talents.json")

    char_talents = current_story.get("talents", [])
    char_talents = removed_skipped_talents(char_talents)
    found_autocast_talent = False

    matched_talent_objs = []

    for talent in char_talents:

        if "autocast" in talent.lower() and not found_autocast_talent:
            matched_talent_objs.append(get_talent_obj("autocast", talent_objs))
            found_autocast_talent = True

        talent_obj = get_talent_obj(talent, talent_objs) #, partial_match)
        if talent_obj is not None:
            matched_talent_objs.append(talent_obj)
        else:
            print(f"ERROR: Talent {talent} not found in talent_objs.")

    # Replace the placeholders
    for talent_obj in matched_talent_objs:
        talent_name = talent_obj["name"]
        talent_name_lower = talent_obj["name"].lower()

        talent_name_root = remove_parentheses(talent_name).lower()
        parenthesis_content = talent_obj["parenthesis_content"]

        talent_description = talent_obj["description"]

        if "#sneak_damage_dice#" in talent_description:
            talent_description = talent_description.replace("#sneak_damage_dice#", get_sneak_attack_dice(current_story))
        if "#skills#" in talent_description:
            # Get the text in parenthesis for every talent in char_talents that partially matches the talent_name_root and add it to the skills list
            skills = get_all_talent_skills(talent_name_root, char_talents)
            talent_description = talent_description.replace("#skills#", combine_array_as_sentence(skills))
        if "#class_level#" in talent_description:
            talent_description = talent_description.replace("#class_level#", f"{current_story['level']}")
        if "#half_class_level#" in talent_description:
            talent_description = talent_description.replace("#half_class_level#", f"{int(current_story['level']) // 2}")
        if "#parenthesis_content#" in talent_description or "#domain_name#" in talent_description:
            talent_description = replace_parenthesis_content(talent_description, parenthesis_content)
        if "#parenthesis_content_stat#" in talent_description:
            talent_description = talent_description.replace("#parenthesis_content_stat#", f"{get_long_stat_name(parenthesis_content).capitalize()}")
        if "#max_sorcery_points#" in talent_description:
            talent_description = talent_description.replace("#max_sorcery_points#", f"{current_story.get('max_sorcery_points', 0)}")
        if "#unarmed_damage_dice#" in talent_description:
            talent_description = talent_description.replace("#unarmed_damage_dice#", f"{current_story.get('base_weapon_damage', '1d4')}")
        if "#max_ki_points#" in talent_description:
            talent_description = talent_description.replace("#max_ki_points#", f"{current_story.get('max_ki_points', 0)}")
        if "#rage_bonus#" in talent_description:
            talent_description = talent_description.replace("#rage_bonus#", f"{get_bonus_rage_damage(current_story)}")
        if "#daily_max_rage_amount#" in talent_description:
            talent_description = talent_description.replace("#daily_max_rage_amount#", f"{current_story.get('daily_max_rage_amount', 0)}")
        if "#touch_of_magic_bonus#" in talent_description:
            talent_description = talent_description.replace("#touch_of_magic_bonus#", f"{get_touch_of_magic_bonus(current_story)}")
        if "#stat_mod_" in talent_description:
            stat_name, stat_mod = get_stat_mod_from_placeholder(talent_description, current_story)
            talent_description = talent_description.replace(f"#stat_mod_{stat_name}#", f"{stat_mod}")
        if "#half_stat_mod_" in talent_description:
            stat_name, stat_mod = get_stat_mod_from_placeholder(talent_description, current_story, True)
            talent_description = talent_description.replace(f"#half_stat_mod_{stat_name}#", f"{stat_mod}")
        if "#bardic_inspiration_dice#" in talent_description:
            talent_description = talent_description.replace("#bardic_inspiration_dice#", f"{get_bardic_inspiration_dice(current_story)}")
        if "#max_arcane_ward_hp#" in talent_description:
            talent_description = talent_description.replace("#max_arcane_ward_hp#", f"{current_story.get('max_arcane_ward_hp', 0)}")
        if "#dnd_hp#" in talent_description:
            autocast_lvl = extract_autocast_lvl(talent_name_lower)
            dnd_hp = max(5 * (autocast_lvl - 1), 0)
            talent_description = talent_description.replace("#dnd_hp#", f"{dnd_hp}")

        talent_obj["description"] = talent_description

    active_talents_list = [talent_obj for talent_obj in matched_talent_objs if talent_obj.get("is_active", False)]
    passive_talents_list = [talent_obj for talent_obj in matched_talent_objs if not talent_obj.get("is_active", False)]

    return active_talents_list, passive_talents_list

def get_talent_title(talent_obj):
    return f"{talent_obj['name']}{' (' + talent_obj['type'] + ')' if talent_obj['type'] != 'original' else ''}"

# Could use roll20, but formatting a bit better there
def get_spell_link(spell_name):
    is_non_phb = spell_name.startswith("#NON_PHB#")
    spell_name = spell_name.replace("#NON_PHB#", "")

    base_url = "http://dnd5e.wikidot.com/spell:" if is_non_phb else "https://www.dndbeyond.com/spells/"
    url = base_url + spell_name.replace("'", "").replace(" ", "-").replace("/", "-")

    return f"#LINK#[{spell_name}]({url})"

def spell_level_text(spell_level):
    return f"Level {spell_level}" if int(spell_level) > 0 else "Cantrip"

def update_char_sheet_doc(current_story):
    char_sheet = {
        f"{current_story['char_summary']}": "#title#",
        "Class": f'Level {current_story["level"]} ' + current_story["class"] + (f" ({current_story['specialization']})" if current_story.get("specialization") is not None else ""),
        "Race": capitalize_first_letter(current_story["race"]),
        "Alignment": f'{alignment_to_words(current_story["alignment"])}',
        "HP": f'{current_story["hp"]} / {current_story["max_hp"]}',
        "AC": current_story["AC"],
        "Proficiency Bonus": get_proficiency_bonus(current_story["level"]),
        "Stats": json_obj_to_string(current_story["stats"]),
        "Saving Throws": join_with_comma(current_story.get("saving_throws")),
        "Skills": capitalize_first_letter(join_with_comma(current_story["skills"])),
        "Inventory": get_inventory_text(current_story, True),
        "Currency": json_obj_to_string(current_story["currency"]),
        "Current Turn": current_story["current_turn"],
        "Remaining_hit_die": current_story["remaining_hit_die"],
        "Attack": "",
        "Attacks": "",
        "Damage": "",
        "Ranged Attack": "",
        "Ranged Damage": "",
        "Sneak Attack Dice": get_sneak_attack_dice(current_story) if has_talent("sneak attack", current_story) else "",
        "Main Quests": get_main_quests_sentence(current_story, include_main_quests_condition=True),
        "Side Quests": join_quests_semicolon(current_story["quests"]), # Remove empty fields later
        "Completed Quests": join_quests_semicolon(current_story["completed_quests"]), # Remove empty fields later
        "Main Location": current_story.get("main_location", ""),
        "Sub Location": current_story.get("sub_location", ""),
        "Description": current_story["char_description"],
        "Scenario": f'{current_story["title"]} - {current_story["scenario"]}',
        # "Physical Description": current_story["char_physical_description"], # Not really relevant
        "Other proficiencies": current_story["proficiencies"] if current_story["proficiencies"] != "" else "None"   
    }

    if not has_talent("sneak attack", current_story):
        del char_sheet["Sneak Attack Dice"]

    if not current_story.get("sub_location", ""):
        del char_sheet["Sub Location"]

    # Attack
    nb_of_attacks, _, _, has_crossbow_expert_bonus_attack = get_base_extra_attacks(current_story, 1, False)

    weapon_name = current_story.get("weapon_name", "Fists")
    ranged_weapon_name = current_story.get("ranged_weapon_name")
    has_no_extra_ranged_weapon = ranged_weapon_name is None

    attack_ability_override = current_story.get("attack_ability")
    roll_stat_name = None
    if attack_ability_override is not None:
        roll_stat_name = attack_ability_override
    else:
        roll_stat_name = "str" 

    attack_bonus, attack_text = get_attack_bonus(current_story, has_no_extra_ranged_weapon, roll_stat_name) # Set is ranged = true, unless there's a second ranged wep (often the ranged wep is the base wep, so want to apply the ranged wep bonus)
    damage_dice, damage_mod, damage_mod_text = get_damage_bonus(current_story, has_no_extra_ranged_weapon, roll_stat_name)

    base_extra_attacks_text = f"x{nb_of_attacks}" if not has_crossbow_expert_bonus_attack else "x1 + x1 Hand Crossbow Offhand"
    attack_label = "Attacks" if nb_of_attacks > 1 else "Attack"

    char_sheet[attack_label] = f"{weapon_name} ({base_extra_attacks_text}): {attack_bonus} => [{attack_text}]"
    char_sheet["Damage"] = f"{damage_dice} + {damage_mod} => [{damage_mod_text}]"

    # Remove extra attack field
    if nb_of_attacks > 1:
        del char_sheet["Attack"]
    else:
        del char_sheet["Attacks"]

    if ranged_weapon_name is not None:
        roll_stat_name_ranged = "dex" # Ranged attacks are always based on dexterity
        ranged_attack_bonus, ranged_attack_text = get_attack_bonus(current_story, True, roll_stat_name_ranged)
        ranged_damage_dice, ranged_damage_mod, ranged_damage_mod_text = get_damage_bonus(current_story, True, roll_stat_name_ranged)

        char_sheet["Ranged Attack"] = f"{ranged_weapon_name} (x{nb_of_attacks}): {ranged_attack_bonus} => [{ranged_attack_text}]"
        char_sheet["Ranged Damage"] = f"{ranged_damage_dice} + {ranged_damage_mod} => [{ranged_damage_mod_text}]"
    else:
        del char_sheet["Ranged Attack"]
        del char_sheet["Ranged Damage"]

    # Remove empty fields (still include them in obj so they are next to main quests)
    if len(current_story["quests"]) == 0:
        del char_sheet["Side Quests"]

    if len(current_story["completed_quests"]) == 0:
        del char_sheet["Completed Quests"]

    if current_story.get("spellcasting_ability"):
        char_sheet["Spellcasting Ability"] = current_story["spellcasting_ability"]
        
        spell_slots, spells_per_day = get_available_spell_slots(current_story)
        char_sheet["Spells per Day"] = get_formatted_spell_slots(spells_per_day) #+ " (" + format_spells(spells_per_day) + ")"
        char_sheet["Spell Slots"] = get_formatted_spell_slots(spell_slots)

    if current_story.get("special_abilities"):
        char_sheet["Special Abilities"] = join_with_comma(current_story["special_abilities"])

    # Rage info
    if current_story.get("daily_max_rage_amount"):
        char_sheet["Rage Amount"] = current_story["daily_max_rage_amount"]
    if current_story.get("rage_remaining"):
        char_sheet["Rage Remaining"] = current_story["rage_remaining"]
    if current_story.get("is_raging"):
        char_sheet["Is Raging"] = current_story["is_raging"]

    # Lay on hands
    if current_story.get("lay_on_hands_hp") is not None and current_story.get("max_lay_on_hands_hp") is not None:
        char_sheet["Lay on Hands Available HP"] = f"{current_story['lay_on_hands_hp']}/{current_story['max_lay_on_hands_hp']}"

    # Ki points
    if current_story.get("ki_points") is not None and current_story.get("max_ki_points") is not None:
        # Don't call 'Ki Points', will clash with the talent of the same name
        char_sheet["Current Ki Points"] = f"{current_story['ki_points']}/{current_story['max_ki_points']}"

    # sorcerer points
    if current_story.get("sorcery_points") is not None and current_story.get("max_sorcery_points") is not None:
        # Don't call 'Sorcery Points', will clash with the talent of the same name
        char_sheet["Current Sorcery Points"] = f"{current_story['sorcery_points']}/{current_story['max_sorcery_points']}"

    # bardic inspiration
    if current_story.get("bardic_inspiration") is not None and current_story.get("max_bardic_inspiration") is not None:
        # Don't call 'Bardic Inspiration', will clash with the talent of the same name
        char_sheet["Current Bardic Inspiration"] = f"{current_story['bardic_inspiration']}/{current_story['max_bardic_inspiration']}"

    # arcane ward
    if current_story.get("arcane_ward_hp") is not None and current_story.get("max_arcane_ward_hp") is not None:
        char_sheet["Arcane Ward HP"] = f"{current_story['arcane_ward_hp']}/{current_story['max_arcane_ward_hp']}"

    if current_story.get("available_misc_objects"):
        char_sheet["Available Objects"] = current_story["available_misc_objects"]
     
    if current_story.get("side_characters") is not None and len(current_story["side_characters"]) > 0:
        char_sheet["Side Characters"] = join_with_comma(current_story["side_characters"])

    if current_story.get("talents"):
        char_sheet["All Talents"] = ", ".join(removed_skipped_talents(current_story["talents"]))

    # Include all spell lists with their titles
    if current_story.get("spellcasting_ability"):
        class_spells_dict, domains_spells_dict, default_spells = list_class_spells(current_story)

        # Add default spells list
        if len(default_spells) > 0:
            char_sheet["Default Spells"] = "#title#"

            formatted_default_spells = [f"{spell_level_text(x).lower()}: {get_spell_link(spell)}" for x, spell in enumerate(default_spells)]
            char_sheet["Spells#"] = join_with_comma(formatted_default_spells)

        # Add domain spells list
        if len(domains_spells_dict) > 0:
            char_sheet["Domain Spells"] = "#title#"
            x = 0

            for spell_level, spell_list in domains_spells_dict.items():
                formatted_spell_list = [get_spell_link(spell) for spell in spell_list] # call get_spell_link for each spell
                char_sheet[f"{spell_level_text(spell_level)}#"] = join_with_comma(formatted_spell_list) # Add '#' to avoid clash with the 'Level x' fields, will be removed in the google drive script
                
                # Add space between all spell levels except the last one
                if x < len(domains_spells_dict) - 1:
                    char_sheet[f"#empty#domain_{spell_level}"] = ""
                x += 1

        char_sheet["Spells List"] = "#title#"
        x = 0

        # Add class spells list
        for spell_level, spell_list in class_spells_dict.items():
            formatted_spell_list = [get_spell_link(spell) for spell in spell_list] # call get_spell_link for each spell
            char_sheet[f"{spell_level_text(spell_level)}"] = join_with_comma(formatted_spell_list)

            # Add space between all spell levels except the last one
            if x < len(class_spells_dict) - 1:
                char_sheet[f"#empty#{spell_level}"] = "" # Add spell level at the end to keep each field unique
            x += 1

    if current_story.get("talents"):
        active_talents_list, passive_talents_list = get_talent_explanations_lists(current_story)

        # Add active and passive talents lists + descriptions
        if len(active_talents_list) > 0 or current_story.get("special_abilities") is not None:
            char_sheet["Active Talents"] = "#title#"

            for talent_obj in active_talents_list:
                talent_title = get_talent_title(talent_obj)
                char_sheet[talent_title] = talent_obj["description"]

            # Add special ability explanation if the char has any
            if current_story.get("special_abilities") is not None:
                joined_special_abilities = join_with_comma(current_story["special_abilities"])
                special_ability_title = "Special Abilities" if len(current_story["special_abilities"]) > 1 else "Special Ability"
                special_ability_title += f" ({joined_special_abilities})"
                special_ability_skill_name = current_story.get("special_ability_skill", "")

                special_ability_text = f"A special ability allows you to use an existing skill ({special_ability_skill_name}) in a unique way (see \"Other Proficiencies\" section)."
                special_ability_text += " This ability can't be used in battle." if current_story.get("special_ability_oob_only", False) else ""
                char_sheet[special_ability_title] = special_ability_text


        if len(passive_talents_list) > 0:
            char_sheet["Passive Talents (Always on)"] = "#title#"

            for talent_obj in passive_talents_list:
                talent_title = get_talent_title(talent_obj)
                char_sheet[talent_title] = talent_obj["description"]

        # Add legend at the end of the sheet
        char_sheet["Legend"] = "#title#"
        char_sheet["Talent"] = "A talent can be a race ability, class ability, feat, or any other unique ability that the character has."
        char_sheet["Modified Talent"] = "Has been modified compared to the original D&D 5e version."
        char_sheet["Homebrew Talent"] = "Is completely new and has no matching talent with the same name in D&D 5e."
        char_sheet["Advantage / Disadvantage"] = "When you have advantage / disadvantage on a d20 roll, you roll a second d20. You use the higher of the two rolls if you have advantage, and the lower roll if you have disadvantage. If circumstances cause a roll to have both advantage and disadvantage, you are considered to have neither of them, and you roll only one d20."

    config = get_ai_config()
    update_char_sheet_html_file(character_sheet_html_file, char_sheet)
    update_char_sheet_google_doc(config.get("char_sheet_doc_id", ""), char_sheet) # Update the shared google doc

def update_character_sheet_worker(queue):
    while True:
        current_story = queue.get()
        update_char_sheet_doc(current_story)
        queue.task_done()

# Initialize the queue and start the worker thread
game_log_queue = Queue()
threading.Thread(target=update_character_sheet_worker, args=(game_log_queue,), daemon=True).start()

def start_update_char_sheet_doc_thread(current_story):
    game_log_queue.put((current_story))

def get_inventory_objs(inventory):
    inventory_objs = []

    for item_text in inventory:
        text_in_parenthesis = extract_text_in_parenthesis(item_text)

        is_equipped = False
        magic_weapon_bonus = magic_focus_bonus = magic_armor_bonus = None

        if text_in_parenthesis:
            text_in_parenthesis = text_in_parenthesis.strip().lower()
            is_equipped = "equipped" in text_in_parenthesis

            match = re.search(rf'focus\+(\d+)', text_in_parenthesis)
            magic_focus_bonus = match.group(1) if match else None

            match = re.search(rf'weapon\+(\d+)', text_in_parenthesis)
            magic_weapon_bonus = match.group(1) if match else None

            match = re.search(rf'armor\+(\d+)', text_in_parenthesis)
            magic_armor_bonus = match.group(1) if match else None

        cleaned_name = item_text.split('(')[0] if '(' in item_text else item_text # Remove the '(Equipped)' part if present
        cleaned_name = cleaned_name.strip()

        item_obj = {
            "name": cleaned_name,
            "is_equipped": is_equipped,
            "quantity": 1
        }

        if magic_weapon_bonus is not None:
            item_obj["magic_weapon_bonus"] = int(magic_weapon_bonus)

        if magic_focus_bonus is not None:
            item_obj["magic_focus_bonus"] = int(magic_focus_bonus)

        if magic_armor_bonus is not None:
            item_obj["magic_armor_bonus"] = int(magic_armor_bonus)

        inventory_objs.append(item_obj)

    return inventory_objs

def create_story(char_name = None, scenario_id = None, use_generic_scenario = None):
    dnd_config = read_json(f'{ai_config_path}dnd_config.json')

    if dnd_config.get("character_name") is not None:
        char_name = dnd_config["character_name"]
    
    if dnd_config.get("scenario_id") is not None:
        scenario_id = dnd_config["scenario_id"]
    
    if dnd_config.get("use_generic_scenario") is not None:
        use_generic_scenario = dnd_config["use_generic_scenario"]

    dnd_characters = read_json(f'{ai_config_path}dnd_characters.json')

    dnd_characters_extra_path = f'{ai_config_path}dnd_characters_extra.json'
    if os.path.exists(dnd_characters_extra_path):
        dnd_characters_extra = read_json(dnd_characters_extra_path)
        dnd_characters["characters_with_scenarios"] += dnd_characters_extra["characters_with_scenarios"]

    if not os.path.exists(stories_history_path):
        write_json(stories_history_path, [])
        stories_history = []
    else:
        stories_history = read_json(stories_history_path)

    # 25% chance to use a generic scenario
    if use_generic_scenario is None:
        use_generic_scenario = rd.randint(1, 4) == 1

    char_obj, scenario_id = get_char_and_scenario(stories_history, dnd_characters, char_name, scenario_id, use_generic_scenario)

    char_name = char_obj["name"]
    char_summary = char_obj["summary"]
    char_description = char_obj["description"]

    scenarios = char_obj["scenarios"] if not use_generic_scenario else dnd_characters["generic_scenarios"]
    scenario = [s for s in scenarios if s["id"] == scenario_id][0]

    location = scenario.get("location")
    if location is None:
        location = char_obj.get("location")
    if location is None:
        location = dnd_characters["location"]

    location_category = scenario.get("location_category")
    if location_category is None:
        location_category = char_obj.get("location_category")
    if location_category is None:
        location_category = "default"

    location_category_is_interior = scenario.get("location_category_is_interior")
    if location_category_is_interior is None:
        location_category_is_interior = char_obj.get("location_category_is_interior")
    if location_category_is_interior is None:
        location_category_is_interior = False

    side_characters = scenario.get("side_characters")
    if side_characters is None:
        side_characters = char_obj.get("side_characters")

    proficiencies = scenario.get("proficiencies")
    if proficiencies is None:
        proficiencies = char_obj.get("proficiencies")

    inventory = scenario.get("inventory")
    if inventory is None:
        inventory = char_obj.get("inventory")

    pp, gp = get_starting_money(char_obj)
    max_hp = get_max_hp(char_obj["level"], char_obj["hit_die"], get_stat_mod(char_obj, "con"), char_obj)

    current_story_obj = {
        "id": stories_history[-1]["id"] + 1 if len(stories_history) > 0 else 1, # last id +1
        "char_name": char_name,
        "alignment" : char_obj["alignment"],
        "level": char_obj["level"],
        "class": char_obj["class"],
        "specialization": char_obj.get("specialization"),
        "race": char_obj["race"],
        "hair_preset": char_obj["hair_preset"],
        "hit_die": char_obj["hit_die"],
        "remaining_hit_die": char_obj["level"],
        "max_hp": max_hp,
        "hp": max_hp,
        "AC": char_obj["AC"],
        "stats": char_obj["stats"],
        "saving_throws": char_obj.get("saving_throws"),
        "skills": char_obj["skills"],
        "weapon_name": char_obj.get("weapon_name"),
        "ranged_weapon_name": char_obj.get("ranged_weapon_name"),
        "difficulty_level": char_obj.get("difficulty_level", "medium"), # Default = medium
        "main_quests": scenario["main_quests"],
        "main_quests_full": scenario.get("main_quests_full"), # Will be removed later if None
        "main_quests_condition": scenario.get("main_quests_condition"),
        "force_quest_order": scenario.get("force_quest_order", False),
        "quests": scenario.get("quests", []),
        "completed_quests": [],
        "main_quests_archive": scenario["main_quests"],
        "main_location": location,
        "sub_location": "",
        "location_category": location_category,
        "location_category_is_interior": location_category_is_interior,
        "side_characters": side_characters if side_characters is not None else "",
        "char_summary": char_summary,
        "char_description": char_description,
        "char_secret_description": char_obj.get("secret_description"),
        "char_physical_description": char_obj["physical_description"],
        "char_personality": char_obj["personality"],
        "rp_tags": char_obj.get("rp_tags"),
        "title": scenario["title"],
        "genre": scenario["genre"],
        "scenario": scenario["scenario"],
        "secret_info": scenario["secret_info"],
        "scenario_id": scenario["id"],
        "original_location": location,
        "proficiencies": proficiencies if proficiencies is not None else "",
        "base_weapon_damage": char_obj.get("base_weapon_damage"),
        "ranged_weapon_damage": char_obj.get("ranged_weapon_damage"),
        "roll_clarifications": char_obj.get("roll_clarifications"),
        "current_turn": 0,
        "is_game_won": False,
        "is_game_lost": False,
        "game_over_quest": "",
        "game_over_time": None,
        "unrelated_or_refused_retries": 0
    }
    
    # Del unused fields (included before to have the right key order)
    if char_obj.get("secret_description") is None:
        del current_story_obj["char_secret_description"]
    if char_obj.get("rp_tags") is None:
        del current_story_obj["rp_tags"]

    if char_obj.get("weapon_name") is None:
        del current_story_obj["weapon_name"]

    if char_obj.get("ranged_weapon_name") is None:
        del current_story_obj["ranged_weapon_name"]

    if char_obj.get("specialization") is None:
        del current_story_obj["specialization"]

    if scenario.get("main_quests_full") is None:
        del current_story_obj["main_quests_full"]

    if scenario.get("main_quests_condition") is None:
        del current_story_obj["main_quests_condition"]

    if current_story_obj.get("roll_clarifications") is None:
        del current_story_obj["roll_clarifications"]

    if char_obj.get("attack_ability"):
        current_story_obj["attack_ability"] = char_obj["attack_ability"]

    if char_obj.get("spellcasting_ability"):
        current_story_obj["spellcasting_ability"] = char_obj["spellcasting_ability"]

        char_classes = [remove_parentheses(class_name) for class_name in char_obj["class"].lower().split("/")]
        
        current_story_obj["spells_per_day"] = spells_per_day(char_classes, char_obj["level"], char_obj.get("talents", []))
        current_story_obj["spell_slots"] = current_story_obj["spells_per_day"][:]

    if char_obj.get("special_abilities"):
        current_story_obj["special_abilities"] = char_obj["special_abilities"]

    if char_obj.get("special_ability_skill"):
        current_story_obj["special_ability_skill"] = char_obj["special_ability_skill"]
    
    if char_obj.get("special_ability_stat"):
        current_story_obj["special_ability_stat"] = char_obj["special_ability_stat"]

    if char_obj.get("special_ability_oob_only"):
        current_story_obj["special_ability_oob_only"] = char_obj["special_ability_oob_only"]

    # Rage info
    if char_obj.get("daily_max_rage_amount"):
        current_story_obj["daily_max_rage_amount"] = char_obj["daily_max_rage_amount"]
        current_story_obj["rage_remaining"] = char_obj["daily_max_rage_amount"]
        current_story_obj["is_raging"] = False
        current_story_obj["started_rage_on_turn"] = None

    if has_talent("ki points", char_obj):
        current_story_obj["max_ki_points"] = get_daily_ki_points(char_obj)
        current_story_obj["ki_points"] = current_story_obj["max_ki_points"]

    if has_talent("lay on hands", char_obj):
        current_story_obj["max_lay_on_hands_hp"] = char_obj["level"] * 5
        current_story_obj["lay_on_hands_hp"] = current_story_obj["max_lay_on_hands_hp"]

    if has_talent("sorcery points", char_obj):
        current_story_obj["max_sorcery_points"] = get_daily_sorcery_points(char_obj)
        current_story_obj["sorcery_points"] = current_story_obj["max_sorcery_points"]

    if has_talent("bardic inspiration", char_obj):
        current_story_obj["max_bardic_inspiration"] = get_stat_mod(char_obj, "cha")
        current_story_obj["bardic_inspiration"] = current_story_obj["max_bardic_inspiration"]

    if has_talent("arcane ward", char_obj):
        current_story_obj["max_arcane_ward_hp"] = char_obj["level"] * 2 + get_stat_mod(char_obj, "int")
        current_story_obj["arcane_ward_hp"] = current_story_obj["max_arcane_ward_hp"]

    # talents
    if char_obj.get("talents"):
        current_story_obj["talents"] = char_obj["talents"]

    # Available misc items to the char
    if char_obj.get("available_misc_objects"):
        current_story_obj["available_misc_objects"] = char_obj["available_misc_objects"]

    if char_obj.get("available_misc_objects_json_name"):
        current_story_obj["available_misc_objects_json_name"] = char_obj["available_misc_objects_json_name"]

    if char_obj.get("available_misc_objects_is_reversed"):
        current_story_obj["available_misc_objects_is_reversed"] = char_obj["available_misc_objects_is_reversed"]
    
    if char_obj.get("base_weapon_damage") is None:
        del current_story_obj["base_weapon_damage"]
    
    if char_obj.get("ranged_weapon_damage") is None:
        del current_story_obj["ranged_weapon_damage"]

    # Inventory
    current_story_obj["currency"] = {"pp": pp, "gp": gp, "sp": 0, "cp": 0}
    current_story_obj["inventory"] = get_inventory_objs(inventory) if inventory is not None else []

    archive_current_story() # Archive the current story before creating a new one, in case we want to go back to it later

    set_current_story(current_story_obj)

    print_log(f"NEW STORY: {char_description} {scenario}")

    current_story_file_names = ["generated_text_emotions.json", "messages_history_dnd.json", 'messages_history_dnd_chat_mode.json', "combatant_sheets.json", "previous_battles_history.json"]

    # init the files
    for file_name in current_story_file_names:
        with open(current_story_path + file_name, 'w+', encoding="utf-8") as f:
            f.write("[]")

    # Don't take note of the story's history if it's a generic scenario
    if not use_generic_scenario:
        # Append the new story to the stories history
        stories_history.append({
            'id': current_story_obj["id"],
            'character': char_name,
            'scenario': scenario_id,
            'date': str(datetime.now())
        })
        write_json(stories_history_path, stories_history)

    config = get_ai_config()
    if config.get("update_google_doc", False):
        start_update_char_sheet_doc_thread(current_story_obj) # Update the shared google doc

def current_date_prefix():
    current_date = date.today()
    current_time = datetime.now().time()
    current_time_hours_minutes = current_time.strftime("%H:%M")
    
    prefix = f"The current date is '{current_date}' and the time is '{current_time_hours_minutes}'."

    return prefix

# Count the number of messaes received by the username
def count_username_instances(json_array, username):
    count = 0
    for json_obj in json_array:
        if 'role' in json_obj and json_obj['role'] == 'user' and 'content' in json_obj and json_obj['content'].startswith(username + ':'):
            count += 1
    return count

# Remove "message history" case insensitive
def remove_message_history_prefix(text):
    pattern = r"\*?(message history:)\*?\s?"

    # Replace the pattern with an empty string using re.IGNORECASE for case insensitivity
    new_text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    return new_text.strip()

# If the phrase is not found as is in the list, check if any word from the phrase is contained in a theme from the list
def find_partial_match(given_phrase, phrase_list, word_partial_match = False):
    # Split the given theme into words
    words = given_phrase.split()

    # First, check if given phrase is contained in any of the themes
    for phrase in phrase_list:
        if given_phrase in phrase or phrase in given_phrase:
            return phrase

    # Then, check for direct word matches
    for word in words:
        for phrase in phrase_list:
            if word == phrase:
                return phrase

    if word_partial_match:
        # If no direct match, check if any word from given_phrase is contained in a phrase from phrase_list
        for word in words:
            for phrase in phrase_list:
                if word in phrase:
                    return phrase
                
        # If still not match, check if any phrase from the phrase list is contained in any of the words
        for word in words:
            for phrase in phrase_list:
                if phrase in word:
                    return phrase

    return None

# Find the last instance of text between double quotes
def find_last_double_quoted_text(text):
    matches = re.findall(r'"(.*?)"', text) 

    if not matches:
        return None

    punctuation_chars = ".,?!;"
    last_match = matches[-1]
    processed_last_match = ''.join(char for char in last_match if char not in punctuation_chars)

    return processed_last_match

# Change the background music
def set_music(response_content, convo_filename, current_game):
    music_obj = extract_json_from_response("GetMusic", response_content)
    if not isinstance(music_obj, dict):
        print_log(f"WARNING: Music not a dict: {response_content}", True)
        return None
    
    new_music_theme = validate_unspecified(music_obj.get("chosen_theme"))
    if new_music_theme is None:
        print_log(f"WARNING: No theme found in prompt: {response_content}", True)
        return

    print_log(f"Music theme found in prompt:{response_content}")

    # Really likes to give this theme, even if not in the list (don't put it in the lsit, otherwise will always chose it)
    if new_music_theme == "epic battle":
        new_music_theme = "battle"

    music_themes = enumerate_folders(root_music_path)

    if new_music_theme not in music_themes:
        print_log(f"WARNING: Music theme {new_music_theme} not found in list of available themes, trying fallback", True)
        
        new_music_theme = find_partial_match(new_music_theme, music_themes, word_partial_match=True)

    if new_music_theme is None:
        print_log(f"WARNING: Music theme {new_music_theme} not found in list of available themes, keeping current theme", True)
        return

    print_log(f"New music theme: {new_music_theme}")

    if os.path.exists(convo_filename):
        # Write the music in the convo file
        convo_obj = read_json(convo_filename)
    else:
        convo_obj = create_convo_obj("", "", "system", current_game, convo_type = "command")
        convo_obj["command"] = "switch_music"

    convo_obj["music_theme"] = new_music_theme
    write_json(convo_filename, convo_obj)

def format_quest(quest, lowercase = True):
    if lowercase:
        quest = quest.lower()

    return quest.strip(" .,!?")

# Determine if 2 given quests are equals, whether in json obj form or not
def quests_are_equal(quest1, quest2):
    quest1_text = quest1.get("description") if isinstance(quest1, dict) else quest1
    quest1_text = format_quest(quest1_text)

    quest2_text = quest2.get("description") if isinstance(quest2, dict) else quest2
    quest2_text = format_quest(quest2_text)

    return quest1_text in quest2_text or quest2_text in quest1_text

# Get the main quests as an array
  # takes into account whether to make it work as a sentence (using pronouns and such, full_only=False) or make each work as standalone (full_only = True)
def get_main_quests_arr(current_story, full_only=True, capitalize=True, include_main_quests_condition=False):
    if current_story.get("main_quests_full") is None:
        quests = current_story["main_quests"][:]

        if include_main_quests_condition and current_story.get("main_quests_condition"):
            quests.append(current_story["main_quests_condition"])

        return [capitalize_first_letter(quest) for quest in quests] if capitalize else quests
    elif full_only:
        quests = current_story["main_quests_full"][:]
        return [capitalize_first_letter(quest) for quest in quests] if capitalize else quests

    fixed_quests = []
    for x in range(len(current_story["main_quests"])):
        quest = current_story["main_quests_full"][x] if x == 0 else current_story["main_quests"][x]
        quest = capitalize_first_letter(quest) if capitalize else quest
        fixed_quests.append(quest)

    return fixed_quests

# Combine the main quests into one sentence
def get_main_quests_sentence(current_story, include_main_quests_condition=False):
    return combine_array_as_sentence(get_main_quests_arr(current_story, full_only = False, capitalize = False, include_main_quests_condition=include_main_quests_condition))

def quest_has_valid_completed_status(quest, is_main_quests):
    label_name = "status" if is_main_quests else "quest_status"
    return quest.get(label_name, "") == "completed"

def complete_main_quest(completed_quest, current_story):
    main_quests_completed = []
    main_quests = get_main_quests_arr(current_story, full_only=True)

    if len(main_quests) == 0:
        print_log("No main quests found in current story")
        return main_quests_completed

    force_quest_order = current_story.get("force_quest_order", False)

    # Can only complete the first main quest when force_quest_order (need to do it in order)
    main_quests = [main_quests[0]] if force_quest_order else main_quests

    for quest in main_quests:
        if completed_quest is not None and quests_are_equal(completed_quest, quest):
            if len(current_story["main_quests"]) == 1:
                print_log(f"Main quest fully Completed: {completed_quest}")
            else:
                print_log(f"Part of main quest Completed: {completed_quest}")

            main_quests_completed.append(quest)

    return main_quests_completed

def complete_quest(completed_quest, current_story):
    quests_completed = []

    # Important : Keep in mind some quests are json obj and others not (main quests)
    for quest in current_story["quests"]:
        quest_has_reward = isinstance(quest, dict) and quest.get("reward")

        if completed_quest is not None and quests_are_equal(completed_quest, quest):
            # Reward not received, don't complete the quest
            reward_received = completed_quest.get("reward_status", "")
            if quest_has_reward and reward_received != "received":
                print_log(f"WARNING: Quest has reward but reward_received is false, skipping. Quest object: {quest}.", True)
                continue

            print_log(f"Quest Completed found: {completed_quest}")
            quests_completed.append(quest)

    return quests_completed

def complete_quests(completed_quests, current_story, is_main_quests):
    all_quests_completed = []

    for quest in completed_quests:
        # If the quest has the wrong status (not completed)
        if not quest_has_valid_completed_status(quest, is_main_quests):
            print_log(f"WARNING: Quest has invalid completion status, skipping. Quest object: {quest}.", True)
            continue

        if is_main_quests:
            quests_completed = complete_main_quest(quest, current_story)
        else:
            quests_completed = complete_quest(quest, current_story)
        
        all_quests_completed.extend(quests_completed)

    return all_quests_completed

def update_story_main_quest_completed(main_quests_completed, current_story):
    # Add completed main quests to the current story
    main_quests = get_main_quests_arr(current_story, full_only=True)

    # inverse range to remove from the end
    for x in range(len(main_quests) - 1, -1, -1):
        quest = main_quests[x]

        # If current main quest is equal to one of the quests in main_quests_completed, complete it
        completed_quest = next((q for q in main_quests_completed if quests_are_equal(q, quest)), None)
        if completed_quest is not None:
            current_story["completed_quests"].append(quest)

            del current_story["main_quests"][x]
            if current_story.get("main_quests_full") is not None:
                del current_story["main_quests_full"][x]

    # Game won when all parts of the main quest are completed
    if main_quests_completed and len(current_story["main_quests"]) == 0:
        current_story["is_game_won"] = True
        current_story["game_over_quest"] = main_quests_completed[-1]

# Set a quest as completed
def validate_is_main_quest_completed(response_content):       
    global main_quests_completed_eval

    quest_completed_obj = extract_json_from_response("GetMainQuestCompleted", response_content)
    if quest_completed_obj is None:
        return None

    completed_quests = quest_completed_obj.get("completed_main_quest_objectives", [])

    if len(completed_quests) <= 0:
        print_log(f"Quest_Status = No changes, found in text: {response_content}")
        main_quests_completed_eval = None # Set to none, in case we are in step 2 and some main quests were added in step 1
        return
    
    print_log(f"Quest completed prompt:{response_content}")
    current_story = get_current_story()

    # Complete or fail, both main quests and side quests
    main_quests_completed_eval = complete_quests(completed_quests, current_story, is_main_quests = True)

# Set a quest as completed
def validate_is_quest_completed(response_content):                 
    quest_completed_obj = extract_json_from_response("GetQuestCompleted", response_content)
    if quest_completed_obj is None:
        return None

    completed_quests = quest_completed_obj.get("completed_quests", [])

    if len(completed_quests) <= 0:
        print_log(f"Quest_Status = No changes, found in text: {response_content}")
        return
    
    print_log(f"Quest completed prompt:{response_content}")
    current_story = get_current_story()

    global quests_completed_eval

    # Complete or fail, both main quests and side quests
    quests_completed_eval = complete_quests(completed_quests, current_story, is_main_quests = False)

def add_dot_if_no_punctuation(text):
    if not text:
        return text
    if text[-1] not in string.punctuation:
        return text + "."
    return text

def remove_quest_prefixed_text(text):
    # Remove the portion in square brackets that contains the word "quest" (case insensitive)
    text = re.sub(r'\[(?i).*?quest.*?\]', '', text)

    # Remove colon and any leading spaces from the start
    text = re.sub(r'^\s*:', '', text).strip()

    # Remove 'quest' (if followed by a number or ':') or just numbers or ':' from the start of the string
    return re.sub(r'^(?i)(quest(?=[0-9:])|[0-9:])*', '', text)

def find_existing_quest(new_quest, current_story):
    # Important : Keep in mind some quests are json obj and others not (main quests)
    all_quests = get_main_quests_arr(current_story, full_only = True) + current_story["quests"] + current_story["completed_quests"]# + current_story["failed_quests"]
    
    # Make sure the new quest is not present in the old quests or vice versa
    for quest in all_quests:
        if quests_are_equal(new_quest, quest):
            return quest
        
    return None

def validate_quest_given(response_content):                 
    quest_given_obj = extract_json_from_response("GetQuestGiven", response_content)
    if quest_given_obj is None:
        return None
    
    print_log(f"Found in prompt:{response_content}")

    new_quests_obj = quest_given_obj.get("new_quests", [])
    if len(new_quests_obj) == 0:
        print_log(f"No new quests found in text.")
        return
    
    global quests_added_eval
    quests_added_eval = []

    current_story = get_current_story()
    new_quests = []
    updated_quest = False

    for quest_obj in new_quests_obj:
        quest_desc = validate_unspecified(quest_obj.get("description"))
        quest_giver = validate_unspecified(quest_obj.get("quest_giver_name"))
        quest_status = validate_unspecified(quest_obj.get("quest_status"))
        reward = validate_unspecified(quest_obj.get("reward"))

        if quest_desc is None:
            print_log(f"WARNING: Quest description not found for quest: {quest_obj}", True)
            continue

        reward = reward if not None else ""

        existing_quest = find_existing_quest(quest_desc, current_story)

        # If the quest is not already in the list, add it
        if existing_quest is None:
            if quest_giver is None:
                print_log(f"WARNING: Quest giver not found for quest: {quest_obj}", True)
                continue

            if quest_status != "accepted":
                print_log(f"WARNING: Quest status not accepted for quest: {quest_obj}", True)
                continue

            quest_desc = remove_quest_prefixed_text(quest_desc).strip()
            quest_desc = add_dot_if_no_punctuation(quest_desc)
            quest_desc = capitalize_first_letter(quest_desc) 

            new_quest_obj = {
                "description": quest_desc,
                "quest_giver": quest_giver,
                "reward": reward
            }
            new_quests.append(new_quest_obj)
            quests_added_eval.append(new_quest_obj) # For eval msg
        # If a new reward is given, update the reward
        elif isinstance(existing_quest, dict) and reward != "" and existing_quest.get("reward", "") != reward:
            print_log(f"Updated reward for quest: {quest_desc.strip(' ,.!?')}. New reward: {reward}, old reward: {existing_quest.get('reward', 'none')}.")
            existing_quest["reward"] = reward # Should reference the same object as in the current_story
            updated_quest = True

    if len(new_quests) == 0 and not updated_quest:
        print_log(f"No new quests found that didn't already exist.")
    elif len(new_quests) > 0:
        print_log(f"New quests found: {new_quests}") 

def add_to_inventory_eval(quantity, name):
    global inventory_eval
    inventory_eval["added"].append(f"{quantity} {name}") # For eval msg

def remove_from_inventory_eval(quantity, name):
    global inventory_eval
    inventory_eval["removed"].append(f"{quantity} {name}") # For eval msg

def is_specific_currency(currency_name, currency):
    currency_types = [currency_name, currency_name + " pieces", currency_name + " piece", currency_name + " coins", currency_name + " coin"]

    for currency_type in currency_types:
        if currency_type in currency:
            return True

def add_or_remove_currency(current_currency, currency_abbr, quantity, is_added, cleaned_item_name):
    if is_added:
        current_currency[currency_abbr] += quantity
        print_log(f"Added {quantity} {currency_abbr}")
        add_to_inventory_eval(quantity, cleaned_item_name)
    else:
        current_currency[currency_abbr] -= quantity
        print_log(f"Removed {quantity} {currency_abbr}")
        remove_from_inventory_eval(quantity, cleaned_item_name)

def parse_currency(current_currency, cleaned_item_name, quantity, is_added):
    if cleaned_item_name == "pp" or is_specific_currency("platinum", cleaned_item_name):
        add_or_remove_currency(current_currency, "pp", quantity, is_added, cleaned_item_name)
    elif cleaned_item_name == "gp" or is_specific_currency("gold", cleaned_item_name):
        add_or_remove_currency(current_currency, "gp", quantity, is_added, cleaned_item_name)
    elif cleaned_item_name == "sp" or is_specific_currency("silver", cleaned_item_name):
        add_or_remove_currency(current_currency, "sp", quantity, is_added, cleaned_item_name)
    elif cleaned_item_name == "cp" or is_specific_currency("copper", cleaned_item_name):
        add_or_remove_currency(current_currency, "cp", quantity, is_added, cleaned_item_name)
    else:
        print(f"ERROR: Currency type not found: {cleaned_item_name}")

# Add or remove items from the inventory
def add_remove_from_inventory(current_inventory, current_currency, is_added_or_removed_from_inventory):        
    global inventory_eval

    # Convert the inventory items to their cleaned and lowercase format
    cleaned_inventory = [get_clean_item_name(item) for item in current_inventory]
    print_log(f"Initial Inventory: {', '.join(cleaned_inventory)}")

    if not is_added_or_removed_from_inventory or not isinstance(is_added_or_removed_from_inventory, list):
        return current_inventory

    for item in is_added_or_removed_from_inventory:
        if not isinstance(item, dict):
            print(f"ERROR: Item is not a dict: {item}")
            continue

        name = validate_unspecified(item.get("name"))
        status = validate_unspecified(item.get("status"))
        category = validate_unspecified(item.get("category"))
        quantity = extract_int(item.get("quantity"))

        if not name or not status or not quantity or not category:
            print(f"ERROR: Item is missing it's name, status, quantity or category field: {item}")
            continue

        if status not in ["added", "removed", "consumable_used"]:
            print(f"ERROR: Item has invalid status: {item}")
            continue

        if quantity <= 0:
            print(f"ERROR: Item counts lower than 0: {item}")
            continue

        is_currency = category == "currency"
        is_unique = category == "unique"
        is_added = status == "added"

        cleaned_item_name = get_clean_item_name(item)
        
        if is_currency:
            parse_currency(current_currency, cleaned_item_name, quantity, is_added)
            continue
        
        # Get the index of the item in cleaned_inventory, if it exists
        cleaned_item_index = next((i for i, item in enumerate(cleaned_inventory) if item == cleaned_item_name or singularize_name(item) == singularize_name(cleaned_item_name)), None)

        if cleaned_item_index is not None and is_added and is_unique:
            print_log(f"Unique item '{cleaned_item_name}' is already in the inventory. No addition performed.")
        elif is_added: # Added
            # If the item is already in the inventory, raise the quantity
            if cleaned_item_index is not None:
                current_item = current_inventory[cleaned_item_index]
                current_item["quantity"] = current_item["quantity"] + quantity
                print_log(f"Item '{item['name']}' already exists, raised quantity by {quantity}")
            else:
                # Add the new item to the inventory
                added_item = {
                    "name": name,
                    "quantity": quantity,
                    "description": item.get("description").strip(" .,!?") if item.get("description") else ""
                }

                current_inventory.append(added_item)
                cleaned_inventory.append(cleaned_item_name)
                print_log(f"Added item: {item}")

            add_to_inventory_eval(quantity, name)

        elif not is_added and cleaned_item_index is None: 
            print_log(f"Item '{cleaned_item_name}' not found in the inventory. No removal performed.")
        elif not is_added: # Removed
            current_item = current_inventory[cleaned_item_index]
            if current_item["quantity"] > quantity:
                current_item["quantity"] = current_item["quantity"] - quantity
                print_log(f"Removed {quantity} '{cleaned_item_name}', {current_item['quantity']} remaining")
            else:
                del current_inventory[cleaned_item_index]
                del cleaned_inventory[cleaned_item_index]
                print_log(f"Removed item: {cleaned_item_name}")

            remove_from_inventory_eval(quantity, name)

def update_inventory(response_content):                 
    inventory_obj = extract_json_from_response("GetInventory", response_content)
    if inventory_obj is None:
        return None
    
    print_log(f"Inventory prompt:{response_content}")

    global inventory_eval
    inventory_eval = {"added": [], "removed": [], "inventory": []}

    is_added_or_removed_from_inventory = validate_unspecified(inventory_obj.get("added_or_removed_from_inventory", []), True)

    # Add / remove items from the inventory
    current_story = get_current_story()

    # Update the inventory list and currency dictionary
    add_remove_from_inventory(current_story["inventory"], current_story["currency"], is_added_or_removed_from_inventory)#, removed_from_inventory)

    inventory_eval["inventory"] = current_story["inventory"]
    inventory_eval["currency"] = current_story["currency"]

def location_is_changed(location, current_location):
    if location is None:
        return False

    return location != "" and not any(location.lower().startswith(prefix) for prefix in ["unchanged", "unknown", "none"]) and location.lower() != current_location.lower()

def update_location(response_content):                 
    location_obj = extract_json_from_response("GetNewLocation", response_content)
    if location_obj is None:
        return None

    when_will_change_occur = validate_unspecified(location_obj.get("when_will_change_occur"))
    if when_will_change_occur == "future":
        print_log(f"Location not changed yet, only planned for now: {response_content}")
        return

    # See if a new main or sub logcation is found in the json obj
    new_main_location = validate_unspecified(location_obj.get("new_main_location"))
    new_sub_location = validate_unspecified(location_obj.get("new_sub_location"))

    if new_main_location is None and new_sub_location is None:
        print_log(f"No main location or sub location found in the text: {response_content}")
        return

    # Validate if the new main or sub location is unchanged

    current_story = get_current_story()

    new_main_location = new_main_location.strip(" .,!?").replace("\n", " ") if new_main_location is not None else None
    new_sub_location = new_sub_location.strip(" .,!?").replace("\n", " ") if new_sub_location is not None else None

    new_main_location_is_changed = location_is_changed(new_main_location, current_story.get("main_location", "")) 
    new_sub_location_is_changed = location_is_changed(new_sub_location, current_story.get("sub_location", "")) 

    if not new_main_location_is_changed and not new_sub_location_is_changed:
        print_log(f"Warning: Both main and sub location are unchanged in the text: {response_content}", True)
        return
    elif not new_main_location_is_changed:
        print_log(f"Main location unchanged in text")
    elif not new_sub_location_is_changed:
        print_log(f"Sub-location unchanged in text")
    
    # Create the new location message
    new_location_arr = []
    if new_main_location_is_changed:
        new_location_arr.append("new main location: " + new_main_location)
    if new_sub_location_is_changed:
        new_location_arr.append("new sub location: " + new_sub_location)
    new_location_msg = (", ".join(new_location_arr)).capitalize()

    if new_location_msg != "":
        print_log(f"{new_location_msg}. Found in prompt:{response_content}")

    # Validate if location changed for eval
    global location_eval
    location_eval = {
        "main_location": new_main_location if new_main_location_is_changed else None,
        "sub_location": new_sub_location if new_sub_location_is_changed else None
    }

def update_location_category(response_content, setup_dnd):                 
    location_obj = extract_json_from_response("GetLocationCategory", response_content)
    if location_obj is None:
        return None
    
    # See if a new main or sub logcation is found in the json obj
    location_category = validate_unspecified(location_obj.get("new_location_category"))
    is_interior = validate_bool(location_obj.get("is_interior"))
    
    if location_category is None:
        print(f"ERROR: Location category found in the text: {response_content}")
        return
    
    current_story = get_current_story()
    location_category = location_category.strip(" .,!?").replace("\n", " ")

    if not location_is_changed(location_category, current_story.get("location_category", "")) :
        print_log(f"Warning: Location category is unchanged in the text: {response_content}", True)
        return
    
    print_log(f"New location category: {location_category}. Found in prompt:{response_content}")
    current_story = get_current_story()
    
    # LOCATION CATEGORY
    categories = setup_dnd["location_categories"].split(", ")
    final_location_category = ""

    # If no location category was found, try to find a partial match
    if location_category not in categories:
        print_log(f"Warning: Location category {location_category} not found in list of available categories, trying fallback", True)
        fallback_location_category = find_partial_match(location_category, categories)

        if fallback_location_category is None:
            print(f"ERROR: Location category '{location_category}' not found in the list of categories.")
        else:
            final_location_category = fallback_location_category
    else:
        final_location_category = location_category

    global location_category_eval

    # Only change if a valid location category was found
    if final_location_category != "":
        print_log(f"New location category: {final_location_category}")

        location_category_eval = {
            "location_category": final_location_category,
            "is_interior": is_interior
        }

def update_important_characters(response_content, current_story):                 
    characters_obj = extract_json_from_response("GetImportantCharacters", response_content)
    if characters_obj is None:
        return None
    
    print_log(f"Found in prompt:{response_content}")

    side_characters = validate_unspecified(characters_obj.get("allied_characters", []), True)
    side_characters = side_characters if side_characters is not None else [] # Remove empty strings

    side_characters = [char.strip(" .,!?-") for char in side_characters if validate_unspecified(char) and current_story["char_name"] not in char] # Remove main char from important characters

    lowercase_side_characters = [char.lower() for char in side_characters]
    no_parenthesis_side_characters = [remove_parentheses(char) for char in lowercase_side_characters]

    global important_characters_eval
    important_characters_eval = {"side_characters_eval_only": None, "side_characters": None}

    current_side_characters = current_story.get("side_characters", [])
    lowercase_current_side_characters = [char.lower() for char in current_side_characters]
    no_parenthesis_current_side_characters = [remove_parentheses(char) for char in lowercase_current_side_characters]

    # Check if side characters have changed (don't take into account the parenthesis for eval)
    if len(side_characters) != len(current_side_characters) or not all(char in no_parenthesis_current_side_characters for char in no_parenthesis_side_characters):
        # Only add to eval if there were any new side chars
        important_characters_eval["side_characters_eval_only"] = side_characters

    # Check if side characters have changed (look if every characters in side_characters are present in current_side_Characters and vice versa)
    if len(side_characters) == len(current_side_characters) and all(char in lowercase_current_side_characters for char in lowercase_side_characters):
        print_log(f"Important characters unchanged in text")
        return

    print_log(f"Side characters: {side_characters}")

    # Will only update the side characters if there was any change
    important_characters_eval["side_characters"] = side_characters
    
def update_story_rest_changes(is_long_rest, is_short_rest, current_story, setup_dnd):
    eval_info = "" # text shown on screen

    if is_long_rest:
        current_story["hp"] = current_story["max_hp"]
        current_story["short_rests"] = 0
        current_story["remaining_hit_die"] = current_story["level"]

        eval_info = "#green#" + setup_dnd["long_rest_info"] + "#green# "
        is_spellcaster = current_story.get("spellcasting_ability") is not None

        if is_spellcaster:
            current_story["spell_slots"] = current_story["spells_per_day"][:]
            eval_info += setup_dnd["long_rest_info_with_spells"]

            if current_story.get("lay_on_hands_hp") is not None:
                current_story["lay_on_hands_hp"] = current_story.get("max_lay_on_hands_hp", 0)
                eval_info += setup_dnd["long_rest_info_lay_on_hands"]
            elif current_story.get("sorcery_points") is not None:
                current_story["sorcery_points"] = current_story.get("max_sorcery_points", 0)
                eval_info += setup_dnd["long_rest_info_sorcery_points"]
            elif current_story.get("bardic_inspiration") is not None:
                current_story["bardic_inspiration"] = current_story.get("max_bardic_inspiration", 0)
                eval_info += setup_dnd["long_rest_info_bardic_inspiration"]
            elif current_story.get("arcane_ward_hp") is not None:
                current_story["arcane_ward_hp"] = current_story.get("max_arcane_ward_hp", 0)
                eval_info += setup_dnd["long_rest_info_arcane_ward"]

        # If has rage feature
        elif current_story.get("rage_remaining") is not None and current_story.get("daily_max_rage_amount") is not None:
            current_story["rage_remaining"] = current_story["daily_max_rage_amount"]
            eval_info += setup_dnd["long_rest_info_with_rage"]

            # Skip frenzy exhaustion, since it's already fixed by the long rest
            _, _ = update_frenzy_status(current_story, fight_stopped=True)

            # Frenzy exhaustion
            if current_story.get("frenzy_used", False):
                current_story["frenzy_used"] = False
                eval_info += setup_dnd["rest_info_frenzy"]

            rage_info = stop_raging(current_story, setup_dnd)
            if rage_info:
                eval_info += "#message_separator#" + rage_info
                
        elif current_story.get("ki_points") is not None:
            current_story["ki_points"] = current_story["max_ki_points"]
            eval_info += setup_dnd["long_rest_info_with_ki_points"]
        else:
            eval_info += setup_dnd["long_rest_info_no_spells"]

        # Second wind or action surge
        if current_story.get("second_wind_used", False) or current_story.get("action_surge_used", False):
            eval_info += setup_dnd["short_rest_info_fighter"]
            current_story["second_wind_used"] = False
            current_story["action_surge_used"] = False

        # Recharge Death Ward
        if current_story.get("used_death_ward", False):
            current_story["used_death_ward"] = False

    elif is_short_rest:
        eval_info = "#green#" + setup_dnd["short_rest_info"] + "#green#"
        
        if current_story.get("ki_points") is not None:
            current_story["ki_points"] = current_story["max_ki_points"]
            eval_info += " " + setup_dnd["short_rest_info_with_ki_points"]
        
        # Second wind or action surge
        if current_story.get("second_wind_used", False) or current_story.get("action_surge_used", False):
            eval_info += setup_dnd["long_rest_info_fighter"]
            current_story["second_wind_used"] = False
            current_story["action_surge_used"] = False

        if current_story.get("bardic_inspiration") is not None:
            current_story["bardic_inspiration"] = current_story.get("max_bardic_inspiration", 0)
            eval_info += setup_dnd["long_rest_info_bardic_inspiration"]

        if current_story["hp"] < current_story["max_hp"] and current_story["remaining_hit_die"] > 0:
            current_hp, remaining_hit_die, rolls_text = use_hit_die(current_story)
            current_story["hp"] = current_hp
            current_story["remaining_hit_die"] = remaining_hit_die

            eval_info += f" Healing using available hit die: {rolls_text}\nRemaining hit die today: #bold#{remaining_hit_die}#bold#."
            print_log(eval_info)
        else:
            print_log("Max hp or no more hit die left")

        # Arcane recovery
        has_arcane_recovery = has_talent("arcane recovery", current_story) and current_story.get("spellcasting_ability") is not None

        if has_arcane_recovery and current_story.get("used_arcane_recovery_today", False):
            print_log(f"Arcane recovery already used today.")
            eval_info += "\n" + setup_dnd["arcane_recovery_already_used_today"]
        elif has_arcane_recovery:
            spell_slots, recovery_text = recover_spell_slots_arcane_recovery(current_story["spell_slots"], 
            current_story["spells_per_day"], current_story["level"])

            if spell_slots is None:
                print(f"ERROR: Arcane recovery failed, not enough spells slots to recover.")
                eval_info += "\n" + setup_dnd["arcane_recovery_failed_not_enough_spell_slots"]
            else:
                current_story["spell_slots"] = spell_slots
                current_story["used_arcane_recovery_today"] = True
                eval_info += "\n" + recovery_text

        # Stop rage on short rest
        if current_story.get("rage_remaining") is not None and current_story.get("daily_max_rage_amount") is not None:
            # Skip frenzy exhaustion, since it's already fixed by the short rest (see Frenzy exhaustion below)
            _, _ = update_frenzy_status(current_story, fight_stopped=True)

            # Frenzy exhaustion
            if current_story.get("frenzy_used", False):
                current_story["frenzy_used"] = False
                eval_info += setup_dnd["rest_info_frenzy"]

            rage_info = stop_raging(current_story, setup_dnd)
            if rage_info:
                eval_info += "#message_separator#" + rage_info

            # if current_story.get("used_relentless_rage", False):
            #     current_story["used_relentless_rage"] = False

        current_story["short_rests"] = current_story.get("short_rests", 0) + 1
        #eval_info = eval_info + "#green#"

    return eval_info

def update_rest(response_content, setup_dnd):     
    rest_obj = extract_json_from_response("GetIsRest", response_content)
    if rest_obj is None:
        return None

    is_short_rest = rest_obj.get("is_short_rest") == True
    is_long_rest = rest_obj.get("is_long_rest") == True
    when_will_rest_occur = validate_unspecified(rest_obj.get("when_will_rest_occur"))
    has_already_occured = when_will_rest_occur == "past"

    if not is_short_rest and not is_long_rest:
        print_log(f"No rest detected in text: {response_content}")
        return
    
    if not has_already_occured:
        print_log(f"Rest not occured yet, only planned for now: {response_content}")
        return
    
    global update_rest_eval
    update_rest_eval = {"is_long_rest": False, "is_short_rest": False}
    
    if is_long_rest:
        print_log(f"Long rest detected. Found in prompt:{response_content}")
        update_rest_eval["is_long_rest"] = True
    else:
        print_log(f"Short rest detected. Found in prompt:{response_content}")
        update_rest_eval["is_short_rest"] = True

    current_story = get_current_story()

    # IMPORTANT : Don't save the changes to the story here, only for test purposes.
        # This func will be called again in create_eval_convo where the story will be updated
    update_story_rest_changes(is_long_rest, is_short_rest, current_story, setup_dnd)

def process_info_text(info_section, separator_label):
    intro_messages = info_section.split(separator_label)

    for x, intro_message in enumerate(intro_messages):
        print_special_text(intro_message)
        time.sleep(0.5)

def print_roll_info(display_sections):
    # In case old format or something
    separator_label = "#message_separator#"

    for section in display_sections:
        intro_info_text = section.get("start_info", None)
        if intro_info_text:
            process_info_text(intro_info_text, separator_label)

        character_objs = section.get("characters", [])

        # Go through each character
        for x, character_obj in enumerate(character_objs):
            unique_actions_objs = character_obj.get("unique_actions", []) if character_obj is not None else []

            # Go through each type of attacks
            for unique_action_obj in unique_actions_objs:
                action_objs = unique_action_obj.get("actions", []) if unique_action_obj is not None else []

                text_first_part = unique_action_obj.get("info", "")
                print_special_text(text_first_part)
                
                # Go through each action
                for action_obj in action_objs:
                    spacing = "  "
                    action_text_part_1 = action_obj.get("start_info", "")
                    if action_text_part_1:
                        print_special_text(spacing + action_text_part_1)
                        spacing += "  "

                    action_text_part_2 = action_obj.get("info", "")
                    if action_text_part_2:
                        print_special_text(spacing + action_text_part_2)

                    time.sleep(0.5)

            # Don't wait for the last opponent's turn
            if x < len(character_objs) - 1:
                time.sleep(0.5) 

        end_info_text = section.get("info", None)
        if end_info_text:
            process_info_text(end_info_text, separator_label)

def get_emotion_dict(identifier, weapon_used, action_no, emotion, expression):
    return {
        "identifier": identifier,
        "weapon_used": weapon_used,
        "action_no": action_no,
        "emotion": emotion,
        "expression": expression
    }

def get_emotions_mc(response_content):
    roll_name = "GetEmotionsMC"
    json_obj = extract_json_from_response(roll_name, response_content)

    if json_obj is None:
        return None

    print_log(f'Emotions MC, found in prompt: {response_content}')

    emotion_objs = json_obj["emotional_state"]
    results = []
    
    for emotion_obj in emotion_objs:
        action_no = emotion_obj.get("attack_no", "")
        emotion = emotion_obj.get("emotion", "")
        expression = emotion_obj.get("expression", "")

        if emotion is None and expression is None:
            print(f"ERROR: Emotion and expression not found in the text: {emotion_obj}")
            continue

        results.append(get_emotion_dict("main_character", None, action_no, emotion, expression))

    return results

def get_emotions_combatants(response_content, is_opponent):
    roll_name = "GetEmotionsCombatants"
    json_obj = extract_json_from_response(roll_name, response_content)

    if json_obj is None:
        return None

    print_log(f'Emotions opponents, found in prompt: {response_content}')

    emotion_objs = json_obj["emotional_state"]
    results = []
    
    for emotion_obj in emotion_objs:
        opp_or_ally = "opponent" if is_opponent else "ally"
        identifier = emotion_obj.get(opp_or_ally + "_identifier", "")
        weapon_or_spell_used = emotion_obj.get("weapon_or_spell_used", "")
        action_no = emotion_obj.get("attack_no", "")

        emotion = emotion_obj.get("emotion", "")
        expression = emotion_obj.get("expression", "")

        results.append(get_emotion_dict(identifier, weapon_or_spell_used, action_no, emotion, expression))

    return results

def remove_from_start_text(text, text_to_remove):
    return text[len(text_to_remove):] if text.startswith(text_to_remove) else text

def remove_from_end_text(text, text_to_remove):
    return text[:-len(text_to_remove)] if text.endswith(text_to_remove) else text

def last_x_keep_first(arr, x):
    if len(arr) <= x+1:  # If the array has 9 or less elements, just return the whole array
        return arr
    else:  # Otherwise, keep the first element and the last 8 elements
        return [arr[0]] + arr[-x:]

def extract_reactions(reactions, is_emotion):
    final_reaction_objs = []
    reaction_text = "emotion" if is_emotion else "expression"
    reaction_text_cap = reaction_text.capitalize()

    for reaction_obj in reactions:
        segment_id = extract_int(reaction_obj.get("id"))
        if segment_id is None:
            print(f"ERROR: Segment ID not found in the text: {reaction_obj}")
            continue

        reaction = validate_unspecified(reaction_obj.get(reaction_text))
        if reaction is None:
            print_log(f"WARNING: {reaction_text_cap} not found in the text: {reaction_obj}")
            continue

        reaction_obj["segment_id"] = segment_id # Set the segment id as an int

        character = validate_unspecified(reaction_obj.get("character"))
        if character is None:
            print_log(f"Warning: Character not found in the text: {reaction_obj}", True)
            reaction_obj["character"] = "main" # Set to main if not found

        position = validate_unspecified(reaction_obj.get("position"))
        if position is None:
            print_log(f"WARNING: Position not found in the text: {reaction_obj}", True)
            reaction_obj["position"] = "all" # Set to all if not found

        # If somehow gave a list of reactions, add each one as a separate reaction obj
        if isinstance(reaction, list):
            print_log(f"WARNING: {reaction_text_cap} is a list, adding each {reaction_text} as a separate {reaction_text} obj", True)
            for react in reaction:
                new_reaction = copy.deepcopy(reaction_obj)
                new_reaction["emotion"] = react # Emotions = expressions or emotions in TTS
                final_reaction_objs.append(new_reaction)
        else:
            reaction_obj["emotion"] = reaction # Emotions = expressions or emotions in TTS
            final_reaction_objs.append(reaction_obj)

    return final_reaction_objs

# Determine if the last history msg is an assistant msg or not (user msg = default)
def is_last_msg_assistant(messages_history):
    return len(messages_history) > 0 and messages_history[-1]["role"] == "assistant"

def set_text_segments_emotions(response_content, msg_segments):
    text_segment_objs = convert_text_segments_to_objs(msg_segments)

    # Initialize with [], so tts doesn't wait if there is an error somewhere.
    for segment_obj in text_segment_objs:
        segment_obj["expressions"] = []

    root_obj = extract_json_from_response("GetEmotions", response_content)
    if not isinstance(root_obj, dict):
        print(f"ERROR: Reaction root obj not found in text: {response_content}")
        return text_segment_objs
    
    emotion_objs = root_obj.get("emotions", [])
    if not isinstance(emotion_objs, list):
        print_log(f"WARNING: Emotions not a list: {response_content}", True)
        return text_segment_objs
    
    expression_objs = root_obj.get("expressions", [])
    if not isinstance(expression_objs, list):
        print_log(f"WARNING: Expressions not a list: {response_content}", True)
        return text_segment_objs
    
    print_log(f"Reactions found in prompt:{response_content}")
    
    emotions = extract_reactions(emotion_objs, True)
    expressions = extract_reactions(expression_objs, False)

    final_emotions = emotions + expressions

    # Sort the reactions by segment_id
    final_emotions.sort(key=lambda x: x.get("segment_id"))
    
    #for segment_id in unique_segment_ids:
    for segment_obj in text_segment_objs:
        segment_id = segment_obj["segment_id"]
        segment_emotions = [emotion for emotion in final_emotions if emotion.get("segment_id") == segment_id]
        segment_expression_objs = []

        for emotion in segment_emotions:
            segment_expression_objs.append(create_expression_obj(emotion.get('character'), emotion.get('position'), emotion.get('emotion')))

        segment_obj["expressions"] = segment_expression_objs

    print_log(text_segment_objs)

    return text_segment_objs

def create_emotions(username, current_game, convo_obj_filepath, messages_history, current_story, extra_info = None):
    current_turn = current_story["current_turn"]
    current_msg_content = messages_history[-1]["content"]
    prefix = "assistant" if is_last_msg_assistant(messages_history) else "narrator" # Do it before the call, otherwise a new msg might have been added in the meantime.

    _, _, text_segment_objs = send_message("", username, current_game=current_game, custom_action="get_emotions", filename=convo_obj_filepath, override_messages_history=messages_history, override_current_story=current_story, extra_info = extra_info) # type: ignore

    convo_obj = read_json(convo_obj_filepath)

    if text_segment_objs is None:
        print(f"ERROR: No emotion obj found for message: {current_msg_content}")
        
        # Initialize with [], so tts doesn't wait if there is an error somewhere.
            # Text segments should already have been initialized previously
        text_segment_objs = convo_obj[prefix + "_segments"]
        for segment_obj in text_segment_objs:
            segment_obj["expressions"] = []

    # Write the emotions in the convo file
    convo_obj[prefix + "_segments"] = text_segment_objs
    write_json(convo_obj_filepath, convo_obj)

    # Write the emotions to the current_story
    generated_texts = get_generated_text_emotions()
    current_text = {
        "turn": current_turn,
        "text": remove_system_prefix(current_msg_content),
        "text_segment_objs": text_segment_objs
    }
    generated_texts.append(current_text)
    set_generated_text_emotions(generated_texts)

def create_emotions_thread(username, current_game, convo_obj_filepath, messages_history, current_story, config, extra_info = None):
    if config.get("add_emotions", False):
        threading.Thread(target=create_emotions, args=(username, current_game, convo_obj_filepath, messages_history, current_story, extra_info)).start()

def create_segment_obj(segment_id, text):
    return '{"segment_id": ' + str(segment_id) + ', "text": "' + text + '"}'

# Sepparate the msg into segments
def format_msg_segment_objs(msg_segments):
    obj_segments = []

    for x in range(len(msg_segments)):
        obj_segments.append(create_segment_obj(x, msg_segments[x]))

    return ", ".join(obj_segments)

def get_numbered_quests(current_story, skip_main_quest = False, skip_normal_quests = False, include_main_quests_condition = False): #, main_quest_multiple_parts = False):
    # Add main quest
    if not skip_main_quest: 
        quests = get_main_quests_arr(current_story, full_only=True, include_main_quests_condition=include_main_quests_condition) #When shown in diff parts, show each main quest as standalone]
    else:
        quests = []

    # Important : Keep in mind some quests are json obj and others not (main quests)
    if not skip_normal_quests:
        quests = quests + get_quests_text_arr(current_story["quests"])
    numbered_quests = [f"{i+1}: {quest}" for i, quest in enumerate(quests)]

    joined_numbered_quests = ". ".join(numbered_quests)
    joined_numbered_quests = joined_numbered_quests + "." if joined_numbered_quests != "" else ""

    return joined_numbered_quests


def get_currency_text(current_story, add_dot = False):
    currency_obj = current_story['currency']
    dot_text = "." if add_dot else ""

    currency_text = f"Currency : {currency_obj['pp']} pp, {currency_obj['gp']} gp, {currency_obj['sp']} sp, {currency_obj['cp']} cp" + dot_text

    return currency_text

def get_inventory(current_story, setup_dnd, is_update_inventory = False):
    inventory_text = get_inventory_text(current_story, add_dot=True)
    inventory_text = inventory_text + " " if inventory_text != "" else ""

    inventory_and_currency_text = inventory_text + get_currency_text(current_story, True)
    inventory_label = "initial_" if is_update_inventory else "current_"
    return setup_dnd[inventory_label + "inventory_message"].replace("#inventory#", inventory_and_currency_text)

def get_current_location(current_story, setup_dnd):
    locations = []
    if current_story.get("main_location", "") != "":
        locations.append(setup_dnd["main_location_message"].replace("#main_location#", current_story.get("main_location", "")))

    if current_story.get("sub_location", "") != "":
        locations.append(setup_dnd["sub_location_message"].replace("#sub_location#", current_story.get("sub_location", "")))

    location_msg = (", ".join(locations) + ".").capitalize() if len(locations) > 0 else ""

    return location_msg

def get_important_characters(current_story, setup_dnd, add_prefix = False):
    texts = []
    side_characters = current_story.get("side_characters", [])
    if len(side_characters) > 0:
        side_char_orig_text = setup_dnd["important_characters_message_side_characters"]
        side_char_text = "Existing " + side_char_orig_text.lower() if add_prefix else side_char_orig_text
        side_char_text += ", ".join(side_characters) + "."
        texts.append(side_char_text)

    return " ".join(texts)

def get_retrieved_from_inventory_text(current_story, setup_dnd, inventory, is_dnd_server = False):
    allowed_category = current_story.get("available_misc_objects")
    allowed_category_text = setup_dnd["retrieve_from_inventory_allowed_category"] + allowed_category if allowed_category is not None else ""
    detailed_previously = setup_dnd["as_detailed_previously"] if inventory != "" else ""
    retrieve_msg_name = "retrieve_from_inventory_dnd_server_message" if is_dnd_server else "retrieve_from_inventory_message"

    return setup_dnd[retrieve_msg_name].replace("#allowed_category#", allowed_category_text).replace("#as_detailed_previously#", detailed_previously)

def get_rage_message(current_story, setup_dnd):
    if current_story.get("is_frenzied", False):
        return setup_dnd["frenzied_message"]
    elif current_story.get("is_raging", False):
        return setup_dnd["is_raging_message"]
    elif current_story.get("frenzy_used", False):
        return setup_dnd["frenzy_used_message"]
    return None

def get_specialization_text(current_story, setup_dnd):
    specialization = current_story.get("specialization", "")
    if specialization == "":
        return ""
    
    char_class = get_char_classes(current_story)[0]

    specialization_text = setup_dnd.get("specialization_" + char_class, "")
    if specialization_text == "":
        print("ERROR: Specialization text not found for class: " + char_class)
        return ""

    return specialization_text.replace("#specialization#", specialization)

def create_current_memory_story_message(setup_dnd, config_dnd, current_story, skip_quests = False, skip_scenario = False, skip_inventory = False, chat_with_viewer = False, include_secret_info=False, skip_location=False, include_inventory_msg=False, skip_proficiencies = False, skip_char_description = False, skip_rage = False, add_personality = False, is_update_inventory = False): #, include_nb_attacks = False):
    memories = []

    if not skip_char_description:
        char_description = current_story["char_description"] 

        # Some characters have secret part to their description (not included in char sheet)
        if current_story.get("char_secret_description") is not None:
            char_description += f" {current_story['char_secret_description']}"

        if not chat_with_viewer:
            char_description += f" {current_story['char_physical_description']}"

        memories.append(char_description)

    memories.append(setup_dnd["extra_char_info"].replace("#alignment#", current_story["alignment"]).replace("#class#", current_story["class"]).replace("#specialization#", get_specialization_text(current_story, setup_dnd)))

    # Only add for get_emotions for now
    if add_personality and current_story.get("char_personality", "") != "":
        memories.append(current_story["char_personality"])  

    if current_story["proficiencies"] != "" and not skip_proficiencies:
        memories.append(current_story["proficiencies"])

    if not skip_scenario:
        memories.append(current_story["scenario"])

    # RAGE
    if not skip_rage:
        rage_msg = get_rage_message(current_story, setup_dnd)
        if rage_msg is not None:
            memories.append(rage_msg)

    if current_story.get("spellcasting_ability"):
        # Check if any spell slots remaining
        has_remaining_spell_slots = any([slot > 0 for slot in current_story["spell_slots"]])
        lowest_no_upcast_spell_slot = find_lowest_no_upcast_slot(current_story["spell_slots"])
        # Return the highest spell level (index + 1 with the a non zero value)
        max_spell_level = get_max_spell_level(current_story)

        if lowest_no_upcast_spell_slot is not None and lowest_no_upcast_spell_slot <= max_spell_level:
            memories.append(setup_dnd["no_spell_slots_above_level_remaining_message"].replace("#level#", str(lowest_no_upcast_spell_slot)))
        elif not has_remaining_spell_slots:
            memories.append(setup_dnd["no_spell_slots_remaining_message"])
        else:
            memories.append(setup_dnd["max_spell_level_message"].replace("#level#", str(max_spell_level)))

    # Lay on hands
    if current_story.get("lay_on_hands_hp") is not None and current_story.get("lay_on_hands_hp") == 0:
        memories.append(setup_dnd["lay_on_hands_no_hp_remaining_message"])
    elif current_story.get("lay_on_hands_hp") is not None:
        memories.append(setup_dnd["lay_on_hands_hp_remaining_message"].replace("#hp_left#", str(current_story["lay_on_hands_hp"])))

    # Fighter features
    has_second_wind = has_talent("second wind", current_story)
    has_used_second_wind = has_second_wind and current_story.get("second_wind_used", False)
    has_action_surge = has_talent("action surge", current_story)
    has_used_action_surge = has_action_surge and current_story.get("action_surge_used", False)

    # Second wind or action surge used
    if has_used_second_wind or has_used_action_surge:
        second_wind_text = "Second Wind"
        action_surge_text = "Action Surge"
        joined_text = join_with_and([second_wind_text, action_surge_text], "or")

        memories.append(setup_dnd["fighter_features_used_message"].replace("#used_features#", joined_text))

    if has_second_wind and not has_used_second_wind and current_story["hp"] >= current_story["max_hp"]:
        memories.append(setup_dnd["second_wind_full_health_message"])

    # Action surge not used (in case it's not clear it's available)
    if has_action_surge and not has_used_action_surge:
        memories.append(setup_dnd["action_surge_not_used_message"])

    # Monk features
    if current_story.get("ki_points") is not None and current_story.get("ki_points", 0) > 0:
        memories.append(setup_dnd["ki_points_available_message"].replace("#ki_points#", str(current_story["ki_points"])))
    elif current_story.get("ki_points") is not None:
        memories.append(setup_dnd["ki_points_not_available_message"])

    # Sorcerer features
    if current_story.get("sorcery_points") is not None and current_story.get("sorcery_points", 0) > 0:
        memories.append(setup_dnd["sorcery_points_available_message"].replace("#sorcery_points#", str(current_story["sorcery_points"])))
    elif current_story.get("sorcery_points") is not None:
        memories.append(setup_dnd["sorcery_points_not_available_message"])

    # Bard features
    if current_story.get("bardic_inspiration") is not None and current_story.get("bardic_inspiration", 0) > 0:
        memories.append(setup_dnd["bardic_inspiration_available_message"].replace("#bardic_inspirations#", str(current_story["bardic_inspiration"])))
    elif current_story.get("bardic_inspiration") is not None:
        memories.append(setup_dnd["bardic_inspiration_not_available_message"])

    # Health
    health_status = get_mc_health_status(current_story["hp"], current_story["max_hp"])
    health_text = setup_dnd.get(health_status, "")

    if health_text == "":
        print(f"ERROR: Health status not found: {health_status}")

    memories.append(health_text)

    # INVENTORY
    inventory = get_inventory(current_story, setup_dnd, is_update_inventory = is_update_inventory) 

    if not skip_inventory:
        inventory_texts = []
        if inventory != "":
            inventory_texts.append(inventory)

        if include_inventory_msg:
            inventory_texts.append(setup_dnd["add_to_inventory_message"])
            inventory_texts.append(get_retrieved_from_inventory_text(current_story, setup_dnd, inventory))

        memories.append(" ".join(inventory_texts))

    # Specify that monks uses martial arts as weapons (otherwise might use other kinds of weapons)
    char_classes = get_char_classes(current_story)
    if "monk" in char_classes:
        memories.append(setup_dnd["monk_wielded_weapon"])

    # CURRENT LOCATION
    if not skip_location:
        current_location = get_current_location(current_story, setup_dnd)
        if current_location != "":
            memories.append(current_location)

    # IMPORTANT CHARACTERS
    important_characters = get_important_characters(current_story, setup_dnd)#, skip_main_antagonist = skip_main_antagonist)
    if important_characters != "":
        memories.append(important_characters)

     # Add the current quests to the memories 
    quests_arr = get_quests_text_arr(current_story["quests"])
    if not skip_quests and len(quests_arr) > 0:
        # Work on most recent quest, unless concluding the story (in that case, focus on main quest)
        current_quest = quests_arr[-1] if current_story["current_turn"] < config_dnd["start_concluding_story_on_turn"] else ""
        
        if current_quest == "":
            current_quest = get_main_quests_sentence(current_story)

        memories.append("Current quest: " + current_quest)
        if not chat_with_viewer:
            memories.append(setup_dnd["quests_message"])
    
    # Add secret information to the goal achieved system message to make sure it's taken into consideration
    if include_secret_info and current_story["secret_info"] is not None and current_story["secret_info"] != "":
        memories.append(current_story["secret_info"]) 

    memories_text = " ".join(memories)

    if chat_with_viewer:
        has_setup_zero = os.path.isfile(f'{ai_config_path}setup_zero.json')
        streaming_or_playing = "streaming" if has_setup_zero else "playing"
        on_stream = " on youtube" if has_setup_zero else ""

        chat_with_viewer_text = setup_dnd["chat_with_viewer_message"].replace("#streaming_or_playing#", streaming_or_playing).replace("#on_stream#", on_stream)
        memories_text = chat_with_viewer_text + memories_text

    return format_msg_oai("user", memories_text)

def get_secret_info_memory(current_story, setup_dnd):
    return setup_dnd["secret_info_memory_message"].replace("#secret_info#", current_story["secret_info"])

def get_secret_info_conclusion(current_story, setup_dnd):
    return setup_dnd["secret_info_conclusion_message"].replace("#secret_info#", current_story["secret_info"])

def get_available_skills(common_skills, character_skills):
    # Combine the two lists
    combined_skills = common_skills + character_skills

    # Use a set to remove duplicates
    unique_skills = set(skill.lower() for skill in combined_skills)

    # Convert the set back to a list
    result_skills = ", ".join(list(unique_skills))

    return result_skills

def get_dnd_memory_and_author_note_additions(current_story, roll = None, is_game_lost = False, is_narrator_response = False):
    config_dnd = read_json(f'{ai_config_path}dnd_config.json')
    setup_dnd = read_json(f'{ai_config_path}dnd_setup.json')

    current_session = {
        "is_narrator_response": is_narrator_response,
    }

    current_turn = current_story["current_turn"]
    char_desc = current_story["char_description"] 
    current_memories = []

    set_secret_info_memory_on_turn = config_dnd["set_secret_info_memory_on_turn"]
    start_concluding_story_on_turn = config_dnd["start_concluding_story_on_turn"]

    # Only short char description if secret info is added
    if current_turn < set_secret_info_memory_on_turn:
        char_desc += " " + current_story["char_physical_description"] 

    char_desc += " " + setup_dnd["extra_char_info"].replace("#alignment#", current_story["alignment"]).replace("#class#", current_story["class"]).replace("#specialization#", get_specialization_text(current_story, setup_dnd))
    current_memories.append(char_desc) 

    if current_story["proficiencies"] != "":
        current_memories.append(current_story["proficiencies"])

    # Location
    if current_story["original_location"] != "":
        current_memories.append(setup_dnd["location_message"].replace("#location#", current_story["original_location"])) # Add location to the description (but don't show it to the viewers)

    # Scenario
    current_memories.append(current_story["scenario"]) 

    # RAGE
    rage_msg = get_rage_message(current_story, setup_dnd)
    if rage_msg is not None:
        current_memories.append(rage_msg)

    # CURRENT LOCATION
    current_location = get_current_location(current_story, setup_dnd)
    if current_location != "":
        current_memories.append(current_location)

    # IMPORTANT CHARACTERS
    important_characters = get_important_characters(current_story, setup_dnd)
    if important_characters != "":
        current_memories.append(important_characters)

    # Secret info (add to memory, unless we're reaching conclusion, in which case add to author's note
    if current_turn >= set_secret_info_memory_on_turn and current_turn < start_concluding_story_on_turn and current_story["secret_info"] is not None and current_story["secret_info"] != "":
        current_memories.append(get_secret_info_memory(current_story, setup_dnd))

    current_session["memory"] = " ".join(current_memories)
    current_session["current_story"] = current_story

    current_author_note_additions = []

    # Add the player character summary to make sure dnd doesn't forget it
    current_author_note_additions.append(setup_dnd["player_character"].replace("#character#", current_story["char_summary"]))

    # Add class, alignment and level
    char_level_info = setup_dnd["extra_char_info_author_note"].replace("#class#", current_story["class"]).replace("#alignment#", current_story["alignment"]).replace("#level#", str(current_story["level"])).replace("#specialization#", get_specialization_text(current_story, setup_dnd))
    current_author_note_additions.append(char_level_info)

    # Add current quest (override current quest when concluding story)
    quests_arr = get_quests_text_arr(current_story["quests"])
    if len(quests_arr) > 0:
        # Work on most recent quest, unless concluding the story (in that case, focus on main quest)
        current_quest = quests_arr[-1] if current_story["current_turn"] < start_concluding_story_on_turn else ""
        
        if current_quest == "":
            current_quest = get_main_quests_sentence(current_story)

        current_author_note_additions.append("Current quest: " + current_quest)

    # INVENTORY
    inventory = get_inventory(current_story, setup_dnd)
    inventory_texts = []

    if inventory != "":
        inventory_texts.append(inventory)

    inventory_texts.append(setup_dnd["add_to_inventory_dnd_server_message"])
    inventory_texts.append(get_retrieved_from_inventory_text(current_story, setup_dnd, inventory, True))

    current_author_note_additions.append(" ".join(inventory_texts))

    # Add secret info with more weight as we near the conclusion (moved it from memory to author's note)
    if current_turn >= start_concluding_story_on_turn and current_story["secret_info"] is not None and current_story["secret_info"] != "":
        current_author_note_additions.append(get_secret_info_conclusion(current_story, setup_dnd))

    battle_info = current_story.get("battle_info")
    if battle_info is not None and are_opponents_surprised(battle_info):
        current_author_note_additions.append(setup_dnd["opponents_surprised_author_note"])

    current_session["author_note_additions"] = " ".join(current_author_note_additions)
    current_session["roll"] = roll
    current_session["is_game_lost"] = is_game_lost
    current_session["battle_info_text"] = get_current_opponents_info_text(current_story, setup_dnd)

    return current_session

def replace_placeholders(main_text, setup_dnd, placeholders):
    for key in placeholders:
        if key in setup_dnd:
            main_text = main_text.replace(f"#{key}#", setup_dnd[key])
            main_text = main_text.replace(f"#CAP_{key}#", setup_dnd[key].capitalize()) # also replace capitalized version
    return main_text

# Replace all the given placeholders by empty strings
def empty_placeholders(main_text, placeholders):
    for key in placeholders:
        main_text = main_text.replace(f"#{key}#", "")
        main_text = main_text.replace(f"#CAP_{key}#", "") # also remove capitalized version
    return main_text

def stop_raging(current_story, setup_dnd):
    rage_info = None

    # Stop raging if currently raging
    if current_story.get("is_raging", False):
        current_story["is_raging"] = False
        current_story["started_rage_on_turn"] = None
        rage_info = setup_dnd["stopped_raging_eval"]

    # Just in case, stop frenzy if currently frenzied (should call update frenzy first to show the correct msg)
    if current_story.get("is_frenzied", False):
        current_story["is_frenzied"] = False
        current_story["frenzy_used"] = True
        print_log("WARNING: Stopped frenzy failsafe, should call update_frenzy first to manage it.", True)

    return rage_info

def get_can_start_raging(current_story, setup_dnd):
    frenzy_used = current_story.get("frenzy_used", False)
    char_name = current_story["char_name"]
    can_start_raging = True
    rage_text = ""
    rage_info = None
    
    # Can't rage if no rage remaining
    if current_story.get("rage_remaining", 0) == 0:
        print_log("WARNING: Tried to start raging, but no rage remaining", True)
        rage_info = setup_dnd["failed_to_rage_eval"]
        rage_text = char_name + setup_dnd["failed_to_rage_author_note"]
        can_start_raging = False
    elif frenzy_used:
        print_log("WARNING: Tried to start raging, but exhausted from frenzy.", True)
        rage_info = setup_dnd["failed_to_rage_frenzy_used_eval"]
        rage_text = char_name + setup_dnd["failed_to_rage_frenzy_used_author_note"]
        can_start_raging = False

    return can_start_raging, rage_text, rage_info

def start_raging(current_story, setup_dnd, attempt_to_start_raging = False):
    # If already raging, don't start again
    if current_story.get("is_raging", False) and attempt_to_start_raging:
        print_log("WARNING: Can't start raging if already raging.", True)
        return False

    # If not a barbarian or if already raging, don't start raging
    if current_story.get("is_raging", True):
        return False

    started_raging = True

    current_story["rage_remaining"] -= 1
    current_story["is_raging"] = True
    current_story["started_rage_on_turn"] = current_story["current_turn"]
    
    rage_info = setup_dnd["started_raging_eval"]
        
    return started_raging, rage_info

# Take the story_parameter name's (ex: special_abilities, has_animal_companion, etc.) and a list of placeholders, replace the placeholders with their corresponding value if the param exists in the story, otherwise replace them with empty strings
def replace_placeholders_for_story_param(story_parameter_name, placeholders, action_prompt, current_story, setup_dnd, is_talent = False):

    # Allow for both talents or current story params
    if is_talent:
        story_parameter = has_talent(story_parameter_name, current_story)
        story_parameter = story_parameter if story_parameter else None # Return None if False
    else: 
        story_parameter = current_story.get(story_parameter_name)

    if story_parameter is not None:
        action_prompt = replace_placeholders(action_prompt, setup_dnd, placeholders)
    else:
        action_prompt = empty_placeholders(action_prompt, placeholders)

    return action_prompt

def append_roll_text_to_history(roll_text, messages_history):
    if roll_text is not None:
        roll_info_message = f"[{roll_text}]"
        messages_history.append(format_msg_oai("roll_text", roll_info_message)) # Insert before the last narrator msg (before the ai answer)

def create_error_log(error_name, error_msg, response_message, username, is_game):
    print_log(error_msg)
    ring_alarm(is_new_message=False, repeat_x_times=2)

    error_obj = {"error": error_msg, "message": response_message}

    # Add error to logs
    log_filename = f'{error_name}-{datetime.now().strftime("%Y%m%d%H%M%S")}-{username}-{is_game}.json'
    log_filepath = f"logs/errors/{log_filename}"

    # Check if path exists, if not, create it
    if not os.path.exists("logs/errors"):
        os.makedirs("logs/errors")

    write_json(log_filepath, error_obj)

def add_emotions_to_msg(msg):
    # read generated_text_emotions.json
    generated_texts = get_generated_text_emotions()

    if generated_texts is None:
        return msg
        
    msg_content = remove_system_prefix(msg["content"])

    # Find the obj whose 'segments' field matches the last user message
    msg_emotion_objs = [obj for obj in generated_texts if obj.get('text') == msg_content]

    if len(msg_emotion_objs) == 0:
        print_log("WARNING: No matching emotion object found in generated_text_emotions.json", True)
        return msg
    elif len(msg_emotion_objs) > 1:
        print_log("WARNING: Multiple matching emotion objects found in generated_text_emotions.json", True)

    msg_emotion_obj = msg_emotion_objs[-1] # Get the last matching obj
    text = msg_emotion_obj.get('text', "")
    #separate_sentences = False # Emotions always from game, and separate sentence = False when from game

    segments = segment_text(text) #, separate_sentences)
    text_segment_objs = msg_emotion_obj.get('text_segment_objs', [])
    if len(text_segment_objs) == 0:
        print("ERROR: No text_segment_objs found in emotion object")
        return msg

    # Process the emotion segments
    final_segments = []
    prev_emotion_end = None

    # Add emotions segment by segment
    for x, segment in enumerate(segments):
        if x >= len(text_segment_objs):
            print(f"ERROR: Segment index {x} not found in text_segment_objs")
            continue

        emotion_objs = text_segment_objs[x]["expressions"]

        # If there are no emotions, just add the segment
        if emotion_objs is None or len(emotion_objs) == 0:
            if prev_emotion_end is None:
                final_segments.append(segment)
            else:
                # If there was an emotion at the end of the previous segment, add it to the start of the current segment
                final_segments.append(f"*{prev_emotion_end}* {segment}")
                
            continue
        
        emotion_start = None
        emotion_end = None

        for emotion_obj in emotion_objs:
            character = emotion_obj["character"]

            if character not in ["main", "both"]:
                continue

            position = emotion_obj["position"]
            emotion = emotion_obj["expression"]

            # Always overrite with the latest emotion (usually more interesting)
            if position in ["start", "all"]:
                emotion_start = emotion
            elif position == "end":
                emotion_end = emotion

        # If there was an emotion at the end of the previous segment, add it to the start of the current segment
        if emotion_start is None and prev_emotion_end is not None:
            emotion_start = prev_emotion_end
        
        # Clear every segment if unused
        prev_emotion_end = None 
        
        # Add the segment with the emotion
        if emotion_start is not None:
            final_segments.append(f"*{emotion_start}* {segment}")
        # Only directly add the emotion at the end if it's the last segment (to avoid having 2 emotions next to each other)
        elif emotion_end is not None and x == len(segments) - 1:
            final_segments.append(f"{segment} *{emotion_end}*")
        # If there was an emotion at the end of the segment, keep it for the next segment
        elif emotion_end is not None:
            final_segments.append(segment)
            prev_emotion_end = emotion_end
        # If there was no emotion, just add the segment
        else:
            final_segments.append(segment)

    # Combine the segments
    final_text = " ".join(final_segments)

    msg = format_msg_oai(msg["role"], final_text)
    return msg  

def end_battle(current_story, prev_battle_info, is_narrator):
    battles_history = get_previous_battles_history()
    battles_history.append(prev_battle_info)
    set_previous_battles_history(battles_history)

    del current_story["battle_info"]

    if is_narrator:
        global battle_end_eval
        battle_end_eval = True

def create_combatant_sheets(username, current_game, messages_history, current_story, combatants):
    if len(combatants) == 0:
        print("ERROR: No combatants found for creating combatant sheets.")
        return

    combatant_groups = get_groups_from_combatants(combatants)
    original_opp_sheets = get_combatant_sheets()
    original_opp_sheets = [] if original_opp_sheets is None else original_opp_sheets

    already_existing_combatant_sheets = []
    removed_combatant_groups = []

    # Go through original opp sheets and add them to existing_group_sheets if a group with that name exists
        # Remove the group after that from combatant_groups
    for group in combatant_groups:
        for opp_sheet in original_opp_sheets:
            if singularize_name(group["name"]).lower() == opp_sheet["name"].lower() and group["cr"] == opp_sheet["cr"]:
                already_existing_combatant_sheets.append(opp_sheet)
                removed_combatant_groups.append(group)
                print_log(f"combatant sheet already exists: {opp_sheet['name']} (CR {opp_sheet['cr']})")
                break

    # Remove the groups that already have a sheet
    for group in removed_combatant_groups:
        combatant_groups.remove(group)

    # If all combatant sheets already exist, return
    if len(combatant_groups) == 0:
        print_log("All combatant sheets already exists")
        return

    combatant_sheet_action_results = ["create_combatant_sheet_stats", "create_combatant_sheet_attacks", "create_combatant_sheet_spells"]
    args = []

    for group in combatant_groups:
        #group_info = f"{group['name']} (CR {group['cr']})"
        group_sheets = combatant_sheet_action_results[:] #clone

        # Only prompt the spells sheet if the group are spellcasters
        if not group.get("is_spellcaster", False):
            group_sheets[2] = "skip" # Will just skip the msg entirely

        extra_info = group

        for custom_action in group_sheets:
            args.append({'current_game': current_game, 'custom_action': custom_action, 'override_messages_history': messages_history, 'override_current_story': current_story, 'extra_info': extra_info})

    results = create_thread_send_message(username, args = args)

    if len(results) < len(combatant_groups) * len(combatant_sheet_action_results):
        print("ERROR: Wrong number of results for combatant sheets.")
        return

    group_infos = []

    # Create the combatants
    for x, group in enumerate(combatant_groups):
        # Get group sheet info from results
        start_index = x * len(combatant_sheet_action_results)

        stats = results[start_index][2]
        attacks = results[start_index + 1][2]
        spells = None

        if group.get("is_spellcaster", False):
            spells = results[start_index + 2][2]

        group_infos.append((group, stats, attacks, spells))
        
    combatant_sheets = process_combatant_sheets(group_infos)
    set_combatant_sheets(original_opp_sheets + combatant_sheets)

    # battle_info["combatants"] = combatants

# Remove all opponents except the first one in a group if sheet["is_named_npc"] = True
def post_process_battle_info(combatants, current_sheets):
    combatant_groups = get_groups_from_combatants(combatants)

    for combatant_group in combatant_groups:
        group_name = combatant_group["name"]
        group_cr = combatant_group["cr"]
        sheet = get_combatant_sheet(group_name, group_cr, current_sheets)

        if sheet is None:
            print(f"ERROR: Combatant sheet not found for group {group_name} in post process battle info.")
            continue

        # Fetch only the new combatants (hp = None), don't touch the old ones.
        combatants_in_group = [combatant for combatant in combatants if combatant["group_name"] == group_name and combatant["hp"] is None]
        nb_combatants_in_group = len(combatants_in_group)

        # If there are no new combatants, skip this group
        if nb_combatants_in_group == 0:
            continue

        # If the group has both ranged and melee attacks, randomly selects how many of them are melee (always first in the ordering)
        if sheet.get("is_melee", False) and sheet.get("is_ranged", False):
            nb_of_melee = get_binomial_dist_result(nb_combatants_in_group)
        else:
            nb_of_melee = nb_combatants_in_group if sheet.get("is_melee", False) else 0
       
        # Use the hp that matches the given combatant's cr
        if combatant_group["cr"] != sheet["cr"]:
            print_log(f"\nWARNING: CR mismatch for group {group_name}: {combatant_group['cr']} vs {sheet['cr']}. Using group's CR with new HP instead.\n", True)
            group_max_hp = get_monsters_hp(combatant_group["cr"], sheet)
        else:
            group_max_hp = sheet["hp"] # Use sheet's hp otherwise

        for x, combatant in enumerate(combatants_in_group):
            # As long as there are melee combatants left, combatant is melee
                # Reason: Lower combatant numbers = always melee, higher = ranged
            combatant["is_ranged"] = x >= nb_of_melee

            combatant["hp"] = group_max_hp
            combatant["max_hp"] = group_max_hp
            combatant["is_spellcaster"] = sheet.get("is_spellcaster", False) # In case it was changed in spells sheet

            # Try adding the race to the entry name if it didn't already include it (ex: "fighter" -> "fighter_dwarf")
            entry_name = sheet.get("entry_name")
            race = sheet.get("race")
            if entry_name is not None and race is not None:
                race_entry_name = entry_name + "_" + race 

                if race_entry_name is not None and has_matching_token_image(race_entry_name):
                    combatant["entry_name"] = race_entry_name

def get_available_spells_text(current_story):
    class_spells_dict, domains_spells_dict, _ = list_class_spells(current_story, False)
    spells_texts = []

    for spell_level, spell_list in class_spells_dict.items():
        domain_spells = domains_spells_dict.get(spell_level, [])
        # Remove all spells from the domain that are already in the class spell list
        for spell in spell_list:
            if spell in domain_spells:
                domain_spells.remove(spell)

        all_spells_list = spell_list + domain_spells
        spells_text = join_with_comma(all_spells_list)
        spells_texts.append(f"Level {spell_level}: {spells_text}")
    
    final_spells_text = "Available spells list: " + "\n".join(spells_texts)
    return final_spells_text

def add_status_to_battle_info(battle_info, username, current_game, messages_history, current_story):
    _, _, result_tuples = send_message("", username, current_game=current_game, custom_action="get_status_effects", override_current_story=current_story, override_messages_history=messages_history)

    if result_tuples is None:
        print("ERROR: No status effects found for battle info.")
        return
    
    for status_group, status in result_tuples:
        if status_group is None:
            continue

        status_group_lower = status_group.lower()
        for opponent in battle_info["opponents"]:
            group_name_lower = opponent["group_name"].lower()
            identifier_lower = opponent["identifier"].lower()
            
            # Check if the status group is in the opponent group/identifier or vice versa
            if status_group_lower in group_name_lower or group_name_lower in status_group_lower or status_group_lower in identifier_lower or identifier_lower in status_group_lower:
                opponent["status_effects"] = status

def add_allies_to_battle_info(battle_info, username, current_game, messages_history, current_story):
    _, _, result = send_message("", username, current_game=current_game, custom_action="get_allied_characters", override_current_story=current_story, override_messages_history=messages_history)

    if result is None:
        print_log("No results found for get_allied_characters in battle info.")
        return

    battle_info["allies"] = result

def add_frenzy_to_rage_info(frenzy_msg, rage_info):
    if not frenzy_msg:
        return rage_info

    return rage_info + "#message_separator#" + frenzy_msg if rage_info is not None else frenzy_msg

def add_to_roll_text(roll_text, text_to_add, insert_at_start = False):
    if roll_text and text_to_add:
        return roll_text + " " + text_to_add if not insert_at_start else text_to_add + " " + roll_text
    elif text_to_add:
        return text_to_add
    else:
        return roll_text

def add_to_roll_info(section_obj, info_to_add, insert_at_start = False):
    if section_obj is None:
        new_section = {
            "name": "turn_info",
            "info": info_to_add
        }
        return new_section

    if section_obj.get("info"):
        new_roll_info = info_to_add + "#message_separator#" + section_obj["info"] if insert_at_start else section_obj["info"] + "#message_separator#" + info_to_add # Add the new info before or after the existing roll info
        section_obj["info"] = new_roll_info
    else:
        section_obj["info"] = info_to_add

    return section_obj

def add_additional_opponents(battle_info, username, current_game, messages_history, current_story):
    _, _, additional_battle_info = send_message("", username, current_game=current_game, custom_action="get_battle_info_additional_opponents", override_current_story=current_story, override_messages_history=messages_history)

    if additional_battle_info is not None:
        battle_info["opponents"] = additional_battle_info["opponents"]
        
        # Run the status function for the additional opponents too if it's the first enemy turn
        status_function_args = (add_status_to_battle_info, [battle_info, username, current_game, messages_history, current_story], {}) if battle_info["enemy_turn"] == 0 else None 

        # Parallelize adding the current status to the new battle info and creating the opponent sheets
        functions_with_args = [
            (create_combatant_sheets, [username, current_game, messages_history, current_story, battle_info["opponents"]], {}),
            status_function_args
        ]
        run_tasks_in_parallel(functions_with_args)

        # Remove duplicated named npc that could have been added by accident as an additional opponent
        post_process_battle_info(battle_info["opponents"], get_combatant_sheets())

    return battle_info

def update_battle_info(current_story, username, current_game, messages_history, start_battle, is_narrator = False, can_add_additional_opponents = False): 
    battle_info = current_story.get("battle_info")

    # When the opponents are defeated in combat, battle status is not ongoing (victorious)
    if battle_info is not None and battle_info["battle_status"] != "ongoing":
        end_battle(current_story, battle_info, is_narrator)
        battle_info = None

    # Create battle info (only if ai or server intends to start it)
    if battle_info is None and start_battle:        
        _, _, battle_info = send_message("", username, current_game=current_game, custom_action="get_battle_info", override_messages_history=messages_history, override_current_story=current_story)

        # Add battle (no battle status when starting a new battle, only when continuing it)
        if battle_info is not None: # and battle_info["battle_status"] == "ongoing":
            last_battle_id = current_story.get("last_battle_id") if current_story.get("last_battle_id") is not None else 0 
            # Increment the battle id in battle_info
            new_battle_id = last_battle_id + 1
            battle_info["id"] = new_battle_id 

            current_story["last_battle_id"] = new_battle_id
            current_story["battle_info"] = battle_info

            #create_combatant_sheets(username, current_game, messages_history, current_story, battle_info)

            # Parallelize adding the current status to the new battle info and creating the opponent sheets
            functions_with_args = [
                (add_allies_to_battle_info, [battle_info, username, current_game, messages_history, current_story], {}),
                (add_status_to_battle_info, [battle_info, username, current_game, messages_history, current_story], {}),
                (create_combatant_sheets, [username, current_game, messages_history, current_story, battle_info["opponents"]], {})
            ]
            run_tasks_in_parallel(functions_with_args)

            # Remove duplicated named npc that could have been added by accident
            post_process_battle_info(battle_info["opponents"], get_combatant_sheets())

            # Add allies sheets and perform post processing on them
            allies = battle_info.get("allies", [])
            if len(allies) > 0:
                create_combatant_sheets(username, current_game, messages_history, current_story, allies)

                post_process_battle_info(allies, get_combatant_sheets())
                
            print_hp_info(current_story, True, True, True)

    # Update the current battle info
    elif battle_info is not None:
        # Update the status (ex: surprise), but only for the first enemy turn
            # Reason: The enemy might be considered initially surprised (before the mc do a skill check), but then notices the mc before they start their turn (ex: mc failed stealth check)
        status_function_args = (add_status_to_battle_info, [battle_info, username, current_game, messages_history, current_story], {}) if battle_info["enemy_turn"] == 0 else None 

        functions_with_args = [
            (send_message, [username], {"current_game": current_game, "custom_action": "get_updated_battle_info", "override_current_story": current_story, "override_messages_history": messages_history}),
            status_function_args
        ]
        results = run_tasks_in_parallel(functions_with_args)
        result_update_battle_info = None

        if len(results) > 0 and len(results[0]) == 3:
            _, _, result_update_battle_info = results[0] # First result is the updated battle info
        else:
            print("ERROR: Updated battle info results not found.")

        updated_battle_info = None
        additional_opponents = None

        if result_update_battle_info is not None:
            updated_battle_info, additional_opponents = result_update_battle_info

        # Stop battle : Battle over when status is diff than ongoing, add to prev battle infos list.
        if updated_battle_info is not None and updated_battle_info["battle_status"] != "ongoing":
            battle_info["battle_status"] = updated_battle_info["battle_status"]
            end_battle(current_story, battle_info, is_narrator)
            battle_info = None
            
        # Continue battle
        elif can_add_additional_opponents:
            if additional_opponents is not None and len(additional_opponents) > 0:
                _, _, additional_battle_info = send_message("", username, current_game=current_game, custom_action="get_battle_info_additional_opponents", override_current_story=current_story, override_messages_history=messages_history, extra_info=additional_opponents)

                if additional_battle_info is not None:
                    battle_info["opponents"] = additional_battle_info["opponents"]
                    
                    # Run the status function for the additional opponents too if it's the first enemy turn
                    status_function_args = (add_status_to_battle_info, [battle_info, username, current_game, messages_history, current_story], {}) if battle_info["enemy_turn"] == 0 else None 

                    # Parallelize adding the current status to the new battle info and creating the opponent sheets
                    functions_with_args = [
                        (create_combatant_sheets, [username, current_game, messages_history, current_story, battle_info["opponents"]], {}),
                        status_function_args
                    ]
                    run_tasks_in_parallel(functions_with_args)

                    # Remove duplicated named npc that could have been added by accident as an additional opponent
                    post_process_battle_info(battle_info["opponents"], get_combatant_sheets())

    return battle_info

def get_current_allies_info_text(current_story, setup_dnd):
    battle_info = current_story.get("battle_info", None)
    allies = battle_info.get("allies", []) if battle_info is not None else []

    if battle_info is not None and len(allies) > 0:
        
        active_allies = [ally for ally in allies if ally.get("hp") is not None and ally["hp"] > 0]

        # Count ally by groupname
        active_ally_counter = Counter([ally["group_name"].lower() for ally in active_allies])

        battle_info_text = setup_dnd["valid_targets_text"].replace("#char_name#", current_story["char_name"])

        # groups = battle_info["groups"]

        group_texts = []
        
        for group_name in active_ally_counter:
            first_matching_ally = next((ally for ally in active_allies if ally["group_name"].lower() == group_name.lower()), None)
            group = get_group_from_combatant(first_matching_ally)

            if group is None:
                print(f"ERROR: Group {group_name} not found in battle info.")
                continue

            # ally count + lowercase if not a named npc
            group_count = active_ally_counter[group_name]
            group_count_text = f"{group['name']}" if group.get("is_named_npc", False) else f"{group_count} {group_name}"
            
            group_texts.append(group_count_text)

        battle_info_text += ", ".join(group_texts) + "."

        return battle_info_text
    
    return ""

def get_current_opponents_info_text(current_story, setup_dnd):
    battle_info = current_story.get("battle_info", None)
    battle_info_text = ""

    if battle_info is not None:
        opponents = battle_info["opponents"]
        # opponents still in battle
        active_opponents = [opponent for opponent in opponents if opponent["hp"] > 0]
        unconsious_opponents = [opponent for opponent in opponents if opponent["hp"] <= 0]

        # Count opponent by groupname
        active_opponent_counter = Counter([opponent["group_name"].lower() for opponent in active_opponents])
        unconsious_opponents_counter = Counter([opponent["group_name"].lower() for opponent in unconsious_opponents])

        battle_info_texts = []

        # Output the opponent groups, including the CR of the first memeber and the number of opponents in the group
        if len(active_opponent_counter) > 0:
            group_texts = []
            
            for group_name in active_opponent_counter:
                first_matching_opponent = next((opponent for opponent in active_opponents if opponent["group_name"].lower() == group_name.lower()), None)
                group = get_group_from_combatant(first_matching_opponent)

                if group is None:
                    print(f"ERROR: Group {group_name} not found in battle info.")
                    continue

                # Opponent count + lowercase if not a named npc
                group_count = active_opponent_counter[group_name]
                group_count_text = f"{group['name']}" if group.get("is_named_npc", False) else f"{group_count} {group_name}"
                
                is_spellcaster = group.get("is_spellcaster", False)
                is_spellcaster_text = "spellcaster" if is_spellcaster else "not spellcaster"

                group_text = f"{group_count_text} (CR {group['cr']}, {is_spellcaster_text})"
                group_texts.append(group_text)

            if len(group_texts) > 0:
                battle_info_texts.append(setup_dnd["active_opponents_text"] + ", ".join(group_texts) + ".")

        # Unconscious opponents
        if len(unconsious_opponents_counter) > 0:
            unconscious_texts = []
            for group_name in unconsious_opponents_counter:
                unconscious_texts.append(f"{unconsious_opponents_counter[group_name]} {group_name}")

            battle_info_texts.append(setup_dnd["incapacitated_opponents_text"] + ", ".join(unconscious_texts) + ".")

        battle_info_text = " ".join(battle_info_texts)
        
    return battle_info_text

def add_spell_list_to_action_prompt(action_prompt, sheet, opponent):
    spells = sheet.get("spells", [])

    # Get the spell list
    if len(spells) > 0:
        max_spell_level = spells[-1]["level"]
        used_spells = opponent.get("used_spells", [])

        # Spells the opponent can't use because they used them too many times
        available_spells = [spell for spell in spells if can_use_spell(spell, max_spell_level, used_spells)]

        spell_list_text = join_with_and([spell["name"] for spell in available_spells])
        print_log(f"Spell list: {spell_list_text}")
        action_prompt = action_prompt.replace("#spell_list#", spell_list_text)

    return action_prompt

def choose_combatants_actions(username, current_game, current_story, setup_dnd, combatant_sheets, battle_info, messages_history, is_opponent):
    active_combatants, _ = get_incapacitated_combatants(battle_info, is_opponent, True)
    args = []
    
    for combatant in active_combatants:
        extra_info = (combatant, is_opponent)
        args.append({'current_game': current_game, 'custom_action': "choose_combatant_action", 'override_messages_history': messages_history, 'override_current_story': current_story, 'extra_info': extra_info})

    results = create_thread_send_message(username, args = args)

    if len(results) < len(active_combatants):
        print("ERROR: Wrong number of results for choose combatants actions.")
        return
    
    # Get the action results (result is always the third argument in send_msg)
    actions_results = [result[2] for result in results]
    combatant_containers = []

    for x, combatant in enumerate(active_combatants):
        combatant_action_obj: Combatant_Action_Object = actions_results[x]
        combatant_containers.append({"combatant": combatant, "action": combatant_action_obj})

    return combatant_containers
    #return process_combatant_turn(current_story, setup_dnd, combatant_sheets, combatant_containers, is_opponent)

def get_new_convo_filename(is_game, is_chat_dnd, current_story, filename_arg = None, custom_action = None):
    suffix = ""

    if filename_arg is None:
        # Add info to filename when playing dnd
        if is_game or is_chat_dnd:
            story_id_str = "{:03d}".format(current_story["id"])
            current_turn_str = "{:03d}".format(current_story["current_turn"])
            suffix = f"{story_id_str}_{current_turn_str}_"
            suffix = suffix if not is_chat_dnd else suffix + "chat_"
            suffix = suffix if custom_action is None else suffix + custom_action + "_"

        suffix += str(no_gen)
        filename = f'{datetime.now().strftime("%Y%m%d%H%M%S")}_{suffix}.json' 
    else:
        filename = os.path.basename(filename_arg) # Get the filename from the path, if it's a path

    filepath = f'{current_convo_path}{filename}'
    return filepath, filename

# Run functions in parallel
def run_tasks_in_parallel(functions_with_args):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []

        # Remove all functions that are None
        functions_with_args = [func_args for func_args in functions_with_args if func_args is not None]
        
        # Submit functions one by one
        for func, args, kwargs in functions_with_args:
            futures.append(executor.submit(func, *args, **kwargs))

        results = [] 
        # Collect results in the order they were submitted (so the order is preserved)
            # Will still be done in parallel
        for future in futures:
            try:
                # This blocks until the future is completed
                result = future.result()
                results.append(result)
            except Exception as e:
                # Append None or a custom error message to results if there's an exception
                print(f"Error occurred: {traceback.format_exc()}")
                results.append(None)

    return results

def add_class_features_to_action_prompt(action_prompt, current_story, setup_dnd, is_get_roll):
    class_text_postfix = "_get_roll" if is_get_roll else ""
    is_raging = current_story.get("is_raging")
    uses_class_json = uses_class_text = ""

    # Add smite or lay on hands feature to get_roll if there are any
    if has_talent("divine smite", current_story) or has_talent("lay on hands", current_story):
        uses_class_json = setup_dnd["uses_paladin_json"]
        uses_class_text = setup_dnd["uses_paladin_text" + class_text_postfix]
    # Add action surge or second wind feature to get_roll if there are any
    elif has_talent("action surge", current_story) or has_talent("second wind", current_story):
        uses_class_json = setup_dnd["uses_fighter_json"]
        uses_class_text = setup_dnd["uses_fighter_text" + class_text_postfix]
    # Add ki points feature to get_roll if there are any
    elif has_talent("ki points", current_story):
        uses_class_json = setup_dnd["uses_monk_json"]
        uses_class_text = setup_dnd["uses_monk_text" + class_text_postfix]
    # Add metamagic feature to get_roll if there are any
    elif current_story.get("max_sorcery_points") is not None:
        uses_class_json = setup_dnd["uses_sorcerer_json"]
        uses_class_text = setup_dnd["uses_sorcerer_text" + class_text_postfix]
    elif current_story.get("bardic_inspiration") is not None:
        uses_class_json = setup_dnd["uses_bard_json"]
        uses_class_text = setup_dnd["uses_bard_text" + class_text_postfix]
    # Add rage or reckless attack feature if there are any, unless it's get roll
    elif not is_get_roll and is_raging is not None:
        start_or_stop_text = "stop" if is_raging else "start"
        start_stop_postfix = "_stop_rage" if is_raging else "_start_rage"

        uses_class_json = setup_dnd["uses_barbarian_json"].replace("#start_or_stop#", start_or_stop_text)
        uses_class_text = setup_dnd["uses_barbarian_text" + start_stop_postfix]

    action_prompt = action_prompt.replace("#uses_class_json#", uses_class_json).replace("#uses_class_text#", uses_class_text)

    return action_prompt

def add_special_ability_get_roll(action_prompt, current_story, setup_dnd):
    special_abilities = current_story.get("special_abilities", [])
    if len(special_abilities) == 0:
        return action_prompt.replace("#special_ability_text#", "").replace("#special_ability_json#", "")

    special_abilities_names = join_with_and(special_abilities, "or")
    ability_text = "ability" if len(special_abilities) <= 1 else "abilities"

    special_ability_text = setup_dnd["uses_special_ability_text_get_roll"].replace("#special_abilities#", special_abilities_names).replace("#ability#", ability_text)

    special_abilities_json = ""
    special_abilities_json_names = get_special_abilities_json_names(special_abilities)

    for special_abilities_json_name in special_abilities_json_names:
        special_abilities_json += setup_dnd["uses_special_ability_json"].replace("#special_ability#", special_abilities_json_name)
    
    return action_prompt.replace("#special_ability_text#", special_ability_text).replace("#special_ability_json#", special_abilities_json)

# Choose one of the two actions (can't use both at the same time)
def choose_between_two_actions(using_action1, decided_using_action1, using_action2, decided_using_action2):
    # Prioritise when both are used, and action 1 over action 2 if both true
    if using_action1 and decided_using_action1: 
        return True, False
    elif using_action2 and decided_using_action2:
        return False, True
    elif using_action1 or decided_using_action1:
        return True, False
    elif using_action2 or decided_using_action2:
        return False, True
    
    return False, False

def process_rage_status(current_story, setup_dnd, battle_info, was_already_in_battle, switch_rage_status, chosen_action, is_narrator) -> Tuple[Any, Any, Any]:
    started_raging = False
    rage_text = None
    rage_info = None

    # Update rage status (only applies during battle)
    if battle_info is not None and has_talent("rage", current_story):
        can_start_raging, attempt_start_raging_text, attempt_start_raging_info = get_can_start_raging(current_story, setup_dnd)

        current_turn = current_story["current_turn"]
        rage_time_over = current_story.get("started_rage_on_turn") is not None and current_turn - current_story["started_rage_on_turn"] >= 10

        # Manually start or stop raging
        if current_story.get("is_raging", False) and not current_story.get("is_frenzied") and (switch_rage_status or rage_time_over): # can't manually stop frenzy
            rage_info = stop_raging(current_story, setup_dnd)
        elif not current_story.get("is_raging", False) and switch_rage_status:
            # If can start raging, start it, otherwise say why can't
            if can_start_raging:
                started_raging, rage_info = start_raging(current_story, setup_dnd)
            else:
                rage_text = attempt_start_raging_text
                rage_info = attempt_start_raging_info

        # If either started raging, or could start raging and it's the first turn of a new battle, then check if start frenzy
        if started_raging or (can_start_raging and not was_already_in_battle and battle_info is not None):
            frenzy_msg, frenzy_text = update_frenzy_status(current_story, fight_started=True)

            # If started to frenzy, then start raging
            if frenzy_msg is not None and not started_raging:
                started_raging, rage_info = start_raging(current_story, setup_dnd)

            rage_info = add_frenzy_to_rage_info(frenzy_msg, rage_info)
            rage_text = frenzy_text

        # Override chosen action in frenzy
        if current_story.get("is_frenzied") and chosen_action != "attacking" and not is_narrator:
            chosen_action = "attacking"
            compelled_to_attack_text = current_story["char_name"] + setup_dnd["char_is_frenzied_text"]
            rage_text = f"{rage_text} {compelled_to_attack_text}" if rage_text is not None else compelled_to_attack_text
    
    # Stop rage the turn after the battle ends when raging
    elif battle_info is None and has_talent("rage", current_story) and not was_already_in_battle and current_story.get("is_raging", False):
        # Stop raging when battle is over (status != ongoing or battle info = None), unless the enemies were just defeated (can do multiple battle in a row potentially).
        rage_info = stop_raging(current_story, setup_dnd)

        frenzy_msg, frenzy_text = update_frenzy_status(current_story, fight_stopped=True)
        rage_info = add_frenzy_to_rage_info(frenzy_msg, rage_info)

        rage_text = frenzy_text

    return rage_text, rage_info, chosen_action

def update_roll_with_rage_text_and_info(main_section_obj, roll_text, rage_info, rage_text):
    if rage_info:
        main_section_obj = add_to_roll_info(main_section_obj, rage_info, True)

    # Add rage/frenzy to the roll text if it was used
    if rage_text:
        roll_text = add_to_roll_text(roll_text, rage_text, True)

    return main_section_obj, roll_text

def print_hp_info(current_story, print_mc_hp = False, print_allies_hp = False, print_opponents_hp = False):
    if not print_mc_hp and not print_allies_hp and not print_opponents_hp:
        return
    
    print_special_text("\n#bold#HP:#bold#")
    
    if print_mc_hp: # Only print if the hp changed or if in battle
        print(f"{current_story['char_name']}: {current_story['hp']}/{current_story['max_hp']}")
        
    battle_info = current_story.get("battle_info")
    
    if battle_info is None:
        return
				
    if print_allies_hp:
        for ally in battle_info["allies"]:
            print(f"{ally['identifier']} HP: {ally['hp']}/{ally['max_hp']}")
            
    if print_opponents_hp:
        if print_mc_hp or print_allies_hp:
            print_special_text("\n#bold#HP Opponents:#bold#")
        
        for opponent in battle_info["opponents"]:
            print(f"{opponent['identifier']} HP: {opponent['hp']}/{opponent['max_hp']}")

def get_formatted_spell_slots(spell_slots_arr):
    spell_slots_text = [str(slot) for slot in spell_slots_arr]
    return  "/".join(spell_slots_text)

def print_limited_resources(current_story):
    limited_resources = get_limited_resources_triples(current_story)
    
    if len(limited_resources) > 0 or current_story.get("spell_slots") is not None:
        print_special_text("\n#bold#Available abilities:#bold#")
        for name, part1, part2 in limited_resources:
            # If part2 is a number
            if isinstance(part2, int) or isinstance(part2, float):
                print(f"{name}: {part1}/{part2}")
            # If part2 is a color
            else:
                print_special_text(f"{name}: #{part2}#{part1}#{part2}#")
            
        if current_story.get("spell_slots") is not None:
            spell_slots, _ = get_available_spell_slots(current_story)
            spell_slots_text = get_formatted_spell_slots(spell_slots)
            print("Spell slots: " + spell_slots_text)
            
def print_story_properties(current_story):
    current_quest = get_current_quest_text(current_story)
    if current_quest:
        print_special_text("\n#bold#Quest:#bold#")
        print(current_quest)
        
    main_quest_text = get_main_quests_sentence(current_story)
    if main_quest_text:
        print_special_text("\n#bold#Main quest:#bold#")
        print(main_quest_text + ".")
    
    inventory_text = get_complete_inventory_text(current_story)
    if inventory_text:
        print_special_text("\n#bold#Inventory:#bold#")
        print(inventory_text)
        
    location_text = current_story.get("main_location", "")
    if location_text:
        print_special_text("\n#bold#Location:#bold#")
        
        sub_location = current_story.get("sub_location", "")
        print(location_text + (f" ({sub_location})" if sub_location else ""))

    print_limited_resources(current_story)
    
    print_hp_info(current_story, True, True, True)   

# Get the last x*2 messages from chat_messages_history, where x is either unrelated_or_refused_retries or the nb of messages to include after game won or lost
def get_current_turn_chat_messsages(chat_messages_history, nb_chat_turns_to_include):
    return chat_messages_history[-(nb_chat_turns_to_include * 2):] if nb_chat_turns_to_include > 0 else []

def process_previous_chat_msg(current_story, setup_dnd):
    nb_chat_turns_to_add = current_story.get("unrelated_or_refused_retries", 0) + 1 # only 1 turn if no retries

    chat_messages_history = get_messages_history(dnd_with_chat_history_file)
    previous_messages = get_current_turn_chat_messsages(chat_messages_history, nb_chat_turns_to_add)

    chat_msg_recollections = []

    for x in range(nb_chat_turns_to_add):
        is_last_turn = x == nb_chat_turns_to_add - 1
        user_msg_index = x*2
        user_msg_answer_index = user_msg_index + 1

        user_msg_content = previous_messages[user_msg_index]["content"]
        user_msg_answer_content = previous_messages[user_msg_answer_index]["content"]

        # Remove all mentions of the user in the previous messages (should seem to come from the ai)
        user_username = extract_username_from_prefix(user_msg_content)
        user_msg_text = remove_all_asterisks(remove_username_prefix(user_msg_content))

        # Remove the user's emotions (inside hashtags at the start) and the user's username from the previous AI message
        _, ai_answer_no_usr_emotions = process_user_msg_emotion(user_msg_answer_content)
        user_msg_answer_unformatted = remove_all_asterisks(remove_username_inside_text(ai_answer_no_usr_emotions, user_username))

        is_unrelated, user_msg_answer_text = process_unrelated(user_msg_answer_unformatted)
        is_refused, user_msg_answer_text = process_refused(user_msg_answer_text)

        # Skip the recall if the user's last message was unrelated or refused
        if is_last_turn and (is_unrelated or is_refused):
            chat_msg_recollections = []
        # Skip msg if unrelated (but keep it if refused)
        elif not is_unrelated:
            chat_msg_recollections.append((user_msg_text, user_msg_answer_text))

    # If there's only one chat message, then use the default msg recall text
    if len(chat_msg_recollections) <= 1:
        last_user_msg, last_user_msg_answer = chat_msg_recollections[0] if len(chat_msg_recollections) == 1 else (None, None)
        chat_msg_recall_text = setup_dnd["chat_msg_recall_text"].replace("#user_msg#", last_user_msg).replace("#ai_answer#", last_user_msg_answer) if len(chat_msg_recollections) == 1 else None
        return chat_msg_recall_text

    # If there's more than one chat msg to show, then combine them

    user_msg_step_1, user_msg_answer_step_1 = chat_msg_recollections[0]
    chat_msg_step_1 = setup_dnd["chat_msg_recall_step_1"].replace("#user_msg#", user_msg_step_1).replace("#ai_answer#", user_msg_answer_step_1)

    chat_msg_texts = []
    # Combine all the chat messages except the first and the last
    for chat_msg_recollection in chat_msg_recollections[1:-1]:
        chat_msg_texts.append(setup_dnd["chat_msg_recall_step_2"].replace("#user_msg#", chat_msg_recollection[0]).replace("#ai_answer#", chat_msg_recollection[1]))

    chat_msg_step_2 = " " + " ".join(chat_msg_texts) if len(chat_msg_texts) > 0 else ""

    user_msg_step_3, user_msg_answer_step_3 = chat_msg_recollections[-1]
    chat_msg_step_3 = setup_dnd["chat_msg_recall_step_3"].replace("#user_msg#", user_msg_step_3).replace("#ai_answer#", user_msg_answer_step_3)

    chat_msg_recall_text = f"{chat_msg_step_1}{chat_msg_step_2} {chat_msg_step_3}"

    return chat_msg_recall_text

def process_mc_roll_skill(username, current_game, current_story, setup_dnd, messages_history, using_special_ability):
    custom_action_skill = "get_roll_skill" if not using_special_ability else "get_roll_skill_special_ability"

    _, _, roll_results = send_message("", username, current_game=current_game, custom_action=custom_action_skill, override_messages_history=messages_history, override_current_story=current_story)
    roll_text, main_section_obj = process_roll_skill(roll_results, current_story, setup_dnd, using_special_ability)
    emotion_action_type = "skill"

    return roll_text, main_section_obj, emotion_action_type

def process_magic_target_oob(magic_obj: Cast_Spell_Object, current_story, username, current_game, messages_history):
    # If doesn't need a target, then return None
    if magic_obj is None or magic_obj.is_healing or not "creature" in magic_obj.target or magic_obj.target_identity is None:
        return None
    
    # When in battle, potentially create a virtual opponent if the target is not found
    if current_story.get("battle_info") is not None:
        is_targeting_opponents = not magic_obj.is_healing
        targeted_combatants, _, is_targeting_mc, is_targeting_self = get_battle_info_combatants(current_story, magic_obj.target_identity, magic_obj.target_number, is_targeting_opponents, is_empty_if_no_target_found = True) 

        # If a target is found, don't create a virtual combatant
        if len(targeted_combatants) > 0 or is_targeting_mc or is_targeting_self:
            return None

    group = create_group(magic_obj.target_identity, None, None, None, None, None, None)
    
    _, _, sheet_stat_obj = send_message("", username, current_game=current_game, custom_action="create_combatant_sheet_stats", override_messages_history=messages_history, override_current_story=current_story, extra_info=group)

    if sheet_stat_obj is not None:
        print_log(f"Create new virtual combatant for spell target: {magic_obj.target_identity}")
        return sheet_stat_obj.extract_json()

    return None

def process_mc_action(chosen_action, username, current_game, current_story, setup_dnd, combatant_sheets, messages_history, using_skill, using_smite, using_lay_on_hands, using_flurry_of_blows, using_patient_defense, using_action_surge, using_reckless_attack, using_special_ability, using_heightened_spell, using_twinned_spell, using_bardic_inspiration, using_unsettling_words):
    roll_text = roll_info = emotion_action_type = main_section_obj = None
    last_attacked_opponents = []
    targeted_opponents = []
    is_in_battle = current_story.get("battle_info") is not None

    # Patient defense
    if using_patient_defense:
        if current_story.get("ki_points", 0) > 0:
            current_story["ki_points"] -= 1
        else:
            using_patient_defense = False

    # Bardic inspiration
    if using_bardic_inspiration and is_in_battle:
        if current_story.get("bardic_inspiration") > 0:
            current_story["bardic_inspiration"] -= 1
        else:
            using_bardic_inspiration = False

    # Process the chosen action
    if chosen_action == "spell":
        # Don't cast spell if no spellcasting ability
        if current_story.get("spellcasting_ability") is not None:
            _, _, cast_spell_results = send_message("", username, current_game=current_game, custom_action="cast_spell", override_messages_history=messages_history, override_current_story=current_story)
            can_cast_spell = True
        else:
            cast_spell_results = None
            can_cast_spell = False

        virtual_target_sheet = process_magic_target_oob(cast_spell_results, current_story, username, current_game, messages_history)

        roll_text, main_section_obj, targeted_opponents, last_attacked_opponents = process_cast_spell(cast_spell_results, can_cast_spell, current_story, setup_dnd, combatant_sheets, using_heightened_spell, using_twinned_spell, using_lay_on_hands, using_unsettling_words, virtual_target_sheet)
        emotion_action_type = "spell"

    elif chosen_action == "attacking":
        _, _, roll_results = send_message("", username, current_game=current_game, custom_action="get_roll_attack", override_messages_history=messages_history, override_current_story=current_story)
        roll_text, main_section_obj, target_location_unknown, targeted_opponents, last_attacked_opponents = process_roll_attack(roll_results, current_story, setup_dnd, combatant_sheets, using_smite, using_action_surge, using_reckless_attack, using_flurry_of_blows, using_patient_defense, using_bardic_inspiration) # Only melee attacks can be reckless
        emotion_action_type = "attacks"
        
        # When attack failed due to location being unknown, use skill instead if was detected as using skill anyways
        if target_location_unknown and using_skill:
            roll_text, main_section_obj, emotion_action_type = process_mc_roll_skill(username, current_game, current_story, setup_dnd, messages_history, using_special_ability)

    elif chosen_action == "consumable_magic_item":
        _, _, roll_results = send_message("", username, current_game=current_game, custom_action="use_item", override_messages_history=messages_history, override_current_story=current_story)

        virtual_target_sheet = process_magic_target_oob(roll_results, current_story, username, current_game, messages_history)

        roll_text, main_section_obj, item_name_not_in_inventory, targeted_opponents, last_attacked_opponents = process_use_item(roll_results, current_story, setup_dnd, combatant_sheets, virtual_target_sheet=virtual_target_sheet)
        emotion_action_type = "item use"

        if item_name_not_in_inventory:
            # Remove the prev msg from the history first, otherwise will just automatically add whatever item they tried to use.
            #This is to fix the issue where the item is in the vicinity, but not in the inventory
            _, _, allow_item_not_in_inventory = send_message("", username, current_game=current_game, custom_action="item_is_within_reach", override_messages_history=messages_history[:-1], override_current_story=current_story, extra_info=item_name_not_in_inventory)

            # Reprocess use_item, taking into account that the item don't need to be in the inventory this time.
            if allow_item_not_in_inventory:
                roll_text, main_section_obj, _, targeted_opponents, last_attacked_opponents = process_use_item(roll_results, current_story, setup_dnd, combatant_sheets, allow_item_not_in_inventory = allow_item_not_in_inventory)

    elif chosen_action == "skill":
        roll_text, main_section_obj, emotion_action_type = process_mc_roll_skill(username, current_game, current_story, setup_dnd, messages_history, using_special_ability)

    if using_patient_defense:
        main_section_obj = add_to_roll_info(main_section_obj, roll_info, setup_dnd["patient_defense_info"])

    return roll_text, main_section_obj, emotion_action_type, targeted_opponents, last_attacked_opponents, using_patient_defense, using_bardic_inspiration

def get_action_emotion(emotions, character_obj, nb_characters, unique_action_obj, nb_unique_actions, action_index, nb_actions):
    current_emotion_obj = None
    opponent_identifier = character_obj["name"] if character_obj is not None else "main"
    opponent_identifier = opponent_identifier.lower() if opponent_identifier is not None else ""

    unique_action_name = unique_action_obj["name"] if unique_action_obj is not None else "main"
    unique_action_name = unique_action_name.lower() if unique_action_name is not None else ""

    for emotion_obj in emotions:
        # Skip if the opponent identifier is not the same (or if it's not set, meaning it's not roll response)
            # Don't skip if nb_characters is 1, no ambiguity there
        emotion_opponent_identifier = emotion_obj.get("identifier", None)
        if emotion_opponent_identifier is not None and opponent_identifier != emotion_opponent_identifier.lower() and nb_characters > 1:
            continue

        # Skip if the weapon used is not the same (or if it's not set, meaning it's not roll response)
            # Don't skip if nb_unique_actions is 1, no ambiguity there
        emotion_weapon_used = emotion_obj.get("weapon_used", None)
        if emotion_weapon_used is not None and unique_action_name != emotion_weapon_used.lower() and nb_unique_actions > 1:
            continue

        # Skip if the action index is not the same 
            # Don't skip if nb_actions is 1, no ambiguity there
        emotion_action_no = extract_int(emotion_obj["action_no"])
        if (emotion_action_no is None or emotion_action_no != action_index + 1) and nb_actions > 1:
            continue

        current_emotion_obj = emotion_obj
        break

    expression_objs= []

    # Return as expression tuples
    if current_emotion_obj is not None:
        if current_emotion_obj["emotion"] is not None:
            expression_objs.append(create_expression_obj("main", "all", current_emotion_obj["emotion"]))

        if current_emotion_obj["expression"] is not None:
            expression_objs.append(create_expression_obj("main", "all", current_emotion_obj["expression"]))

    return expression_objs

def add_emotion_to_section(section, emotions):
    if section is None:
        return
    
    for character in section.get("characters", []):
        for unique_action in character.get("unique_actions", []):
            for action_index, action in enumerate(unique_action.get("actions", [])):
                action["expressions"] = get_action_emotion(emotions, character, len(section["characters"]), unique_action, len(character["unique_actions"]), action_index, len(unique_action["actions"]))
        

def run_battle_turn(ai_new_msg, username, current_game, convo_obj_filepath, messages_history, current_story, setup_dnd, config, config_dnd, generate_next_convo_arg, has_valid_prev_chat_msg, start_battle_assistant = False):
    log_current_story(current_story, "start_run_battle_turn")

    # Add assistant emotions
    create_emotions_thread(username, current_game, convo_obj_filepath, messages_history, current_story, config)

    dnd_server_text = ""
    roll_text = None
    initial_hp = current_story["hp"]

    # Parallelize the following functions
    functions_with_args = [
        # get_roll()
        (send_message, ['', username], {'current_game': current_game, 'custom_action': 'get_roll', 'override_messages_history': messages_history, 'override_current_story': current_story}),
        # update_battle_info()
        (update_battle_info, [current_story, username, current_game, messages_history, start_battle_assistant], {})
    ]

    # Detect whether using something like action surge or second wind.
    if has_valid_prev_chat_msg and current_story["class"].lower() in ["fighter", "paladin", "barbarian", "monk", "sorcerer", "bard"]:
        functions_with_args.append((send_message, ['', username], {'current_game': current_game, 'custom_action': 'get_answer_to_viewer_decisions', 'override_messages_history': messages_history, 'override_current_story': current_story}))

    results = run_tasks_in_parallel(functions_with_args)
    
    # Check if the results are correct
    if len(results[0]) != 3:
        print("ERROR: Wrong number of results from concurrent call of get_roll and update_battle_info in battle turn.")
        return
    elif len(results[0]) != 3:
        print("ERROR: Wrong number nb of values in the get_roll tuple for battle turn.")
        return
    elif len(results) > 2 and len(results[2]) != 3:
        print("ERROR: Wrong number nb of values in the get_answer_to_viewer_decisions tuple for battle turn.")
        return

    # Get roll results
    roll_results = results[0][2]

    # Get the chosen action, if any
    chosen_action = using_skill = using_action_surge = using_second_wind = using_smite = using_lay_on_hands = using_flurry_of_blows = using_patient_defense = switch_rage_status = using_reckless_attack = using_special_ability = using_heightened_spell = using_twinned_spell = using_bardic_inspiration = using_unsettling_words = None
    if roll_results is not None:
        chosen_action, using_skill, using_action_surge, using_second_wind, using_smite, using_lay_on_hands, using_flurry_of_blows, using_patient_defense, using_special_ability, using_heightened_spell, using_twinned_spell, using_bardic_inspiration, using_unsettling_words = roll_results.extract()

    # Get the answer to viewer decisions
    if len(results) > 2 and len(results[2]) == 3:
        answer_to_viewer_decisions = results[2][2]
        if answer_to_viewer_decisions is not None:
            decided_using_action_surge, decided_using_second_wind, decided_using_smite, decided_using_lay_on_hands, decided_using_flurry_of_blows, decided_using_patient_defense, switch_rage_status, using_reckless_attack, decided_using_heightened_spell, decided_using_twinned_spell, decided_using_bardic_inspiration, decided_using_unsettling_words = answer_to_viewer_decisions.extract()

            # Fighter actions
            using_action_surge = using_action_surge or decided_using_action_surge
            using_second_wind = using_second_wind or decided_using_second_wind
            # Paladin actions
            using_smite, using_lay_on_hands = choose_between_two_actions(using_smite, decided_using_smite, using_lay_on_hands, decided_using_lay_on_hands) #can only be one or the other
            # Monk actions
            using_flurry_of_blows, using_patient_defense = choose_between_two_actions(using_flurry_of_blows, decided_using_flurry_of_blows, using_patient_defense, decided_using_patient_defense)
            # Sorcerer actions
            using_twinned_spell, using_heightened_spell = choose_between_two_actions(using_twinned_spell, decided_using_twinned_spell, using_heightened_spell, decided_using_heightened_spell)
            # Bard actions
            using_unsettling_words, using_bardic_inspiration = choose_between_two_actions(using_unsettling_words, decided_using_unsettling_words, using_bardic_inspiration, decided_using_bardic_inspiration)

    if using_lay_on_hands and chosen_action != "spell":
        print_log(F"Chosen action ({chosen_action}) overwritten by 'spell', using lay on hands")
        chosen_action = "spell"
    elif using_smite and chosen_action != "attacking":
        print_log(F"Chosen action ({chosen_action}) overwritten by 'attacking', using smite")
        chosen_action = "attacking"

    was_already_in_battle = current_story.get("battle_info") is not None

    battle_info = results[1]
    combatant_sheets = get_combatant_sheets()

    # Update rage info for AI
    rage_text, rage_info, chosen_action = process_rage_status(current_story, setup_dnd, battle_info, was_already_in_battle, switch_rage_status, chosen_action, False)

    log_current_story(current_story, "assistant_battle_info_updated")

    oppponents_before_assistant_turn = copy.deepcopy(battle_info["opponents"]) if battle_info is not None else None
    emotion_action_type = None

    # MC TURN

    roll_text_mc_emotions = roll_text_for_allies_emotions = None

    # Parallelize the following functions
    functions_with_args = [
        (process_mc_action, [chosen_action, username, current_game, current_story, setup_dnd, combatant_sheets, messages_history, using_skill, using_smite, using_lay_on_hands, using_flurry_of_blows, using_patient_defense, using_action_surge, using_reckless_attack, using_special_ability, using_heightened_spell, using_twinned_spell, using_bardic_inspiration, using_unsettling_words], {})
    ]

    # Allies actions
    if battle_info is not None and len(battle_info.get("allies", [])) > 0:
        functions_with_args.append((choose_combatants_actions, [username, current_game, current_story, setup_dnd, combatant_sheets, battle_info, messages_history, False], {}))

    results = run_tasks_in_parallel(functions_with_args)

    # Get new command from dnd
    roll_text, main_section_obj, emotion_action_type, targeted_opponents, last_successfully_attacked_opponents, using_patient_defense, using_bardic_inspiration = results[0]

    mc_turn_sections = [main_section_obj] if main_section_obj is not None else []
    ally_section_obj = None

    roll_text_mc_emotions = roll_text
    is_potentially_damaging_opponents = False

    # BATTLE TURN MC
    if battle_info is not None:

        has_attacking_allies = False

        # Add the allies actions if there are any
        if len(results) >= 2:
            combatant_containers = results[1]
            allies_roll_text, ally_section_obj, _, last_successfully_attacked_opponents = process_combatant_turn(current_story, setup_dnd, combatant_sheets, combatant_containers, False, using_bardic_inspiration=using_bardic_inspiration) # Process the allies turn outside of the parallelized functions, to avoid overwriting the opponents health in current story

            roll_text_for_allies_emotions = allies_roll_text
            roll_text = add_to_roll_text(roll_text, allies_roll_text)

            if ally_section_obj is not None:
                mc_turn_sections.append(ally_section_obj)
            
            has_attacking_allies = any([container["action"] in ["attacking", "casting_a_spell"] for container in combatant_containers])

            # Set to empty if allies, don't really need to overcomplicate things for now
            targeted_opponents = []

        # Determine if all targeted opponents are defeated
        all_opponent_defeated_msg = process_are_opponents_defeated(setup_dnd, targeted_opponents, battle_info)
        if all_opponent_defeated_msg is not None:
            roll_text = add_to_roll_text(roll_text, all_opponent_defeated_msg)
        else:
            # Add and explanation of the current opponent's health after the last attack if any attacks were successful vs this opponent, but it was not defeated.
            opponent_health_explanation_text = add_explanation_last_opponent_health(last_successfully_attacked_opponents, battle_info, setup_dnd)
            if opponent_health_explanation_text is not None:
                roll_text = add_to_roll_text(roll_text, opponent_health_explanation_text)

        is_potentially_damaging_opponents = chosen_action in ["spell", "attacking", "consumable_magic_item", "special_ability"] or has_attacking_allies

        if is_potentially_damaging_opponents:
            # Remaining opponents texts
            remaining_opponents_texts = get_remaining_opponents_text(battle_info, setup_dnd)
            if remaining_opponents_texts != "":
                roll_text = add_to_roll_text(roll_text, remaining_opponents_texts)

    log_current_story(current_story, "assistant_action_done")

    # Increase ally turn by 1 when in battle
    if battle_info is not None:
        battle_info["ally_turn"] += 1

    # Use second wind if hp < 50% (1d10 + fighter lvl), can also be used manually
    has_second_wind = has_talent("second wind", current_story)
    if has_second_wind and not current_story.get("second_wind_used", False) and ((current_story["hp"] < current_story["max_hp"] / 2) or (using_second_wind and current_story["hp"] < current_story["max_hp"])):
        level_bonus = current_story["level"] if not has_talent("multiclass", current_story) else 1
        hp_healed = rd.randint(1, 10) + level_bonus

        current_story["hp"] = min(current_story["hp"] + hp_healed, current_story["max_hp"])

        second_wind_intro_text = setup_dnd["second_wind_message_intro"] if using_second_wind else setup_dnd["second_wind_message_automatic_intro"]
        second_wind_text = setup_dnd["second_wind_message"] if using_second_wind else setup_dnd["second_wind_message_automatic"]
        second_wind_text = second_wind_text.replace("#hp_healed#", f"#green#{hp_healed}#green#")

        current_story["second_wind_used"] = True

        second_wind_char_obj = get_char_obj_healing(battle_info, current_story, "second wind", False, "main_second_wind", second_wind_intro_text, second_wind_text, is_opponent = False)

        main_section_obj.get("characters", [])
        main_section_obj["characters"].append(second_wind_char_obj)

    main_section_obj, roll_text = update_roll_with_rage_text_and_info(main_section_obj, roll_text, rage_info, rage_text)

    # Print roll_text
    if len(mc_turn_sections) > 0:
        print_special_text("\n#bold#Your turn:#bold#")
        print_roll_info(mc_turn_sections)

    if roll_text:
        print_log("\n" + roll_text + "\n")
    
    # print the opponents health
    if is_potentially_damaging_opponents:
        print_hp_info(current_story, print_opponents_hp=True)

    emotion_custom_action = "get_emotions_mc" if len(mc_turn_sections) > 0 else "skip"

    # Add the rolltext to the history for emotions, otherwise it wouldn't be included
        # Only include the mc roll text, not the allies
    emotion_mc_history = copy.deepcopy(messages_history)
    append_roll_text_to_history(roll_text_mc_emotions, emotion_mc_history)

    # Parallelize the following functions
    functions_with_args = [
        # send_text_command_dnd
        (send_text_command_dnd, [[ai_new_msg], get_dnd_memory_and_author_note_additions(current_story, (roll_text, mc_turn_sections, chosen_action))], {}),
        # get_emotions_mc
        (send_message, ['', username], {'current_game': current_game, 'custom_action': emotion_custom_action, 'override_messages_history': emotion_mc_history, 'override_current_story': current_story, 'extra_info': emotion_action_type})
    ]

    # Add the emotions for the allies turn if there are any.
    if roll_text_for_allies_emotions is not None:
        emotion_allies_history = copy.deepcopy(messages_history)
        append_roll_text_to_history(roll_text_for_allies_emotions, emotion_allies_history)

        functions_with_args.append((send_message, ['', username], {'current_game': current_game, 'custom_action': "get_emotions_allies", 'override_messages_history': emotion_allies_history, 'override_current_story': current_story}))

    results = run_tasks_in_parallel(functions_with_args)
    
    if len(results) < 2:
        print("ERROR: Wrong number of results from concurrent call of send_text_command_dnd and get_emotions_mc in battle turn.")
        return

    # Get new command from dnd
    dnd_server_text, start_battle_narrator, add_additional_opponents_narrator, has_escaped_battle = results[0]
    convo_user_msg = dnd_server_text
    
    if has_escaped_battle and battle_info is not None:
        battle_info["battle_status"] = "retreated"
        
    # Add the emotions to the main convo's roll_info
    mc_roll_info_emotions = results[1][0] if results[1][0] is not None else [] # First element of the send_message result is the emotions
    add_emotion_to_section(main_section_obj, mc_roll_info_emotions)
    
    allies_roll_info_emotions = results[2][0] if len(results) >= 3 and results[2][0] is not None else []
    add_emotion_to_section(ally_section_obj, allies_roll_info_emotions)

    convo_user_msg_no_prefix = remove_system_prefix(convo_user_msg)

    print_special_text("\n#bold#Narrator:#bold#")
    print(convo_user_msg_no_prefix)

    # Write the narrator msg for next dnd msg once ready
    convo_obj = read_json(convo_obj_filepath)
    convo_obj["user_msg"] = convo_user_msg_no_prefix
    # [] == don't wait for sections anymore
    convo_obj["display_sections"] = mc_turn_sections if mc_turn_sections is not None else []

    # Add narrator fields (hp, spell slots, limited resources, etc.) to convo obj
    add_narrator_fields_to_convo(convo_obj, current_story, initial_hp)

    # Add updated battle info to convo obj
    convo_obj = add_battle_info_to_convo_obj(convo_obj, current_story, oppponents_before_assistant_turn)

    write_json(convo_obj_filepath, convo_obj)

    print_log("Updated convo obj for next dnd msg.")

    # User Msg
    if convo_user_msg != "":
        # If a roll occured, include the roll info right before the first narrator msg
        append_roll_text_to_history(roll_text, messages_history)

        messages_history.append(format_msg_oai("user", convo_user_msg))

    # Get the narrator dnd msg emotions
    create_emotions_thread(username, current_game, convo_obj_filepath, messages_history, current_story, config)

    battle_info = current_story.get("battle_info")
    battle_just_started = battle_info is None

    was_already_in_battle = current_story.get("battle_info") is not None

    battle_info = update_battle_info(current_story, username, current_game, messages_history, start_battle_narrator, is_narrator=True, can_add_additional_opponents=add_additional_opponents_narrator)
    combatant_sheets = get_combatant_sheets()

    log_current_story(current_story, "narrator_battle_info_updated")

    # Update rage info
    rage_text, rage_info, _ = process_rage_status(current_story, setup_dnd, battle_info, was_already_in_battle, False, None, True)

    # Different narrator prompt depending of in battle or not (save only when not in battle, no save when in battle (except spells))
    has_narrator_roll = False
    chosen_situation = None

    if battle_info is not None:
        
        # Determine if surprised and isn't already surprised.
        enemy_is_surprised = are_opponents_surprised(battle_info) and not battle_info.get("enemy_is_surprised", False)

        # Only surprised once
        if enemy_is_surprised:
            battle_info["enemy_is_surprised"] = True
            print_log("\nIMPORTANT: Opponents are surprised!\n")
        else:
            # Remove surprised status if it was set before
            if battle_info.get("enemy_is_surprised", False):
                battle_info["enemy_is_surprised"] = False

            # opponents without status effect
            active_opponents, _ = get_incapacitated_combatants(battle_info, True)

            if len(active_opponents) > 0:
                has_narrator_roll = True
                chosen_situation = "choose_opponents_actions"

        # Stay on turn 0 if the battle just started and the enemy is surprised (they take their first turn after the ai in that case).
            # battle_just_started = if the assistant hasn't acted in battle yet.
        if not (battle_just_started and enemy_is_surprised):
            battle_info["enemy_turn"] += 1

        # Remove status effects from all opponents
        if battle_info["enemy_turn"] == 1:
            for opponent in battle_info["opponents"]:
                opponent["status_effects"] = None

    else:
        _, _, result_obj = send_message("", username, current_game=current_game, custom_action="get_roll_narrator_saving_throw", override_current_story=current_story, override_messages_history=messages_history)
        chosen_situation = result_obj["chosen_situation"] if result_obj is not None else None
        has_narrator_roll = chosen_situation is not None
        
    allies_before_assistant_turn = copy.deepcopy(battle_info.get("allies", [])) if battle_info is not None else None

    if has_narrator_roll:
        narrator_roll_text = total_dmg = None
        original_hp = current_story["hp"]
        emotion_opponents_action_type = opponent_section_obj = None

        if chosen_situation == "choose_opponents_actions":
            combatant_containers = choose_combatants_actions(username, current_game, current_story, setup_dnd, combatant_sheets, battle_info, messages_history, True)

            narrator_roll_text, opponent_section_obj, total_dmg, last_attacked_allies = process_combatant_turn(current_story, setup_dnd, combatant_sheets, combatant_containers, True, using_reckless_attack, using_patient_defense, using_bardic_inspiration)

            emotion_opponents_action_type = "attacks" # Always attacks during battle, even if they cast spells

        elif chosen_situation == "saving_throw_required":
            _, _, narrator_roll_results = send_message("", username, current_game=current_game, custom_action="get_roll_saving_throw", override_messages_history=messages_history, override_current_story=current_story)
            narrator_roll_text, opponent_section_obj, total_dmg = process_roll_saving_throw(narrator_roll_results, current_story, setup_dnd, combatant_sheets)
            emotion_opponents_action_type = "saving throw"

        # Update narrator roll with rage text and info
        opponent_section_obj, narrator_roll_text = update_roll_with_rage_text_and_info(opponent_section_obj, narrator_roll_text, rage_info, rage_text)

        # Only generate next convo if there's not a narrator roll
        convo_obj = read_json(convo_obj_filepath)
        convo_obj["generate_next_convo"] = narrator_roll_text is None # None if no roll
        write_json(convo_obj_filepath, convo_obj)

        if narrator_roll_text is not None:
            #previous_roll_text = roll_text
            is_game_lost = False

            # Update story with new hp and previous roll text
            if total_dmg is not None and total_dmg > 0:

                # arcane ward (breaks at 0, dissipating any extra dmg)
                if current_story.get("arcane_ward_hp", 0) > 0:
                    current_story["arcane_ward_hp"] = max(0, current_story["arcane_ward_hp"] - total_dmg)

                # death ward (prevent death once)
                if current_story["hp"] == 0 and has_talent("death ward", current_story, partial_match=True) and not current_story.get("used_death_ward", False):
                    current_story["hp"] = 1
                    narrator_roll_text = f"{narrator_roll_text} However, their death ward allowed them to stay alive, barely."
                    opponent_section_obj = add_to_roll_info(opponent_section_obj, "Avoided death using Death Ward, dropped to 1 hp instead.")
                    current_story["used_death_ward"] = True

                is_game_lost = current_story["hp"] <= 0
                current_story["is_game_lost"] = is_game_lost
                if is_game_lost:
                    current_story["game_over_quest"] = "" # Empty string = died

            emotion_custom_action = "get_emotions_opponents" if narrator_roll_text is not None else "skip"

            # Add the rolltext to the history for emotions, otherwise it wouldn't be included
            opponents_emotion_history = copy.deepcopy(messages_history)
            append_roll_text_to_history(narrator_roll_text, opponents_emotion_history)

            opponents_sections_objs = [opponent_section_obj] if opponent_section_obj is not None else []

            text_prefix = "Opponents turn" if battle_info is not None else "Environment"

            # Print roll_text
            print_special_text(f"\n#bold#{text_prefix}:#bold#")
            print_roll_info(opponents_sections_objs)

            # print mc health and allies
            should_print_mc_hp = original_hp != current_story["hp"] or battle_info is not None
            
            print_hp_info(current_story, print_mc_hp = should_print_mc_hp, print_allies_hp=True)

            if narrator_roll_text:
                print_log("\n" + narrator_roll_text + "\n")

            # Parallelize the following functions
            functions_with_args = [
                # send_text_command_dnd
                (send_text_command_dnd, [[ai_new_msg, dnd_server_text], get_dnd_memory_and_author_note_additions(current_story, (narrator_roll_text, opponents_sections_objs, chosen_situation), is_game_lost, is_narrator_response=True)], {}),
                # get_emotions_opponents
                (send_message, ['', username], {'current_game': current_game, 'custom_action': emotion_custom_action, 'override_messages_history': opponents_emotion_history, 'override_current_story': current_story, 'extra_info': emotion_opponents_action_type})
            ]

            results = run_tasks_in_parallel(functions_with_args)
            
            if len(results) != 2:
                print("ERROR: Wrong number of results from concurrent call of send_text_command_dnd and get_emotions_opponents in battle turn.")
                return

            # Dnd msg
            dnd_narrator_roll_response, _, add_additional_opponents_roll_response, _ = results[0]
            dnd_narrator_roll_response_no_prefix = remove_system_prefix(dnd_narrator_roll_response)

            print_special_text("\n#bold#Narrator:#bold#")
            print(dnd_narrator_roll_response_no_prefix)

            emotions_opponents_roll_info = results[1][0] # First element of the send_message result is the emotions

            # Write the narrator msg for next dnd msg once ready
            file_root, file_ext = os.path.splitext(convo_obj_filepath)
            roll_response_convo_obj_filepath = file_root + "_roll_response" + file_ext

            generate_next_convo = generate_next_convo_arg # Now that we're doing the narrator roll, we can set the generate_next_convo to the correct value
            emotions_opponents_roll_info = emotions_opponents_roll_info if emotions_opponents_roll_info is not None else []
            add_emotion_to_section(opponent_section_obj, emotions_opponents_roll_info)

            roll_response_convo_obj = create_convo_obj("", dnd_narrator_roll_response_no_prefix, username if username is not None else "system", current_game, generate_next_convo, \
                        current_story, config_dnd["win_count"] if config_dnd is not None else 0, config_dnd["lose_count"] if setup_dnd is not None else 0, \
                        display_sections = opponents_sections_objs, main_quests_text = get_main_quests_sentence(current_story), convo_type = "roll_response")

            # The initial hp for the convo should be the same as it was at the start, the damages will be applied in run_roll_info in tts.
            roll_response_convo_obj["hp"] = original_hp
            roll_response_convo_obj["narrator_hp"] = current_story["hp"]

            if add_additional_opponents_roll_response:
                battle_info = add_additional_opponents(battle_info, username, current_game, messages_history, current_story)

            # Add updated battle info to convo obj
            roll_response_convo_obj = add_battle_info_to_convo_obj(roll_response_convo_obj, current_story, allies_before = allies_before_assistant_turn)

            write_json(roll_response_convo_obj_filepath, roll_response_convo_obj)

            # Add roll text right before 2nd narrator msg
            append_roll_text_to_history(narrator_roll_text, messages_history)

            messages_history.append(format_msg_oai("user", dnd_narrator_roll_response))

            convo_obj_filepath = roll_response_convo_obj_filepath # Return the last convo object filename

            # Get narrator roll emotions
            create_emotions_thread(username, current_game, convo_obj_filepath, messages_history, current_story, config)

    else:
        # Only generate the next msg if the narrator roll msg doesnt follow
            # Always needs to set this, because it would be null otherwise in ai dungeon game (will be stuck in tts)
        convo_obj = read_json(convo_obj_filepath)
        convo_obj["generate_next_convo"] = True
        write_json(convo_obj_filepath, convo_obj)

def send_message(new_user_msg_arg: str, username_arg: str = None, start_send_message_timestamp = None, history_file_arg = None, current_game=None, custom_action=None, custom_prefix=None, generate_next_convo_arg=True, state_switch=None, filename=None, moderate_user_msg=False, override_messages_history=None, override_current_story=None, force_gpt4 = False, add_music = False, extra_info = None) -> Tuple[Any, Any, Any]:
    global no_gen

    # Always need a start send msg
    if start_send_message_timestamp is None:
        start_send_message_timestamp = time.time()

    # Skip the msg entirely (ex: skip opponent spell sheet if not a spellcaster)
    if custom_action == "skip":
        return None, None, None
    
    # Hardcode the username to a specific value if it was set
    username = username_arg if username_arg == "system" or hardcode_username is None else hardcode_username
    if username is None:
        username = "user"

    #auto_mode = username is None
    #is_dnd = current_game == "dnd"
    is_game = current_game is not None and current_game != ""
    is_chat_dnd = state_switch == "dnd" 
    is_game_dnd = is_game and state_switch == "chat"

    setup_dnd = read_json(f'{ai_config_path}dnd_setup.json')
    config_dnd = read_json(f'{ai_config_path}dnd_config.json')

    current_story = override_current_story
    if current_story is None:
        current_story = get_current_story() if is_game or is_chat_dnd else None
        print_log("Initial current_story")
        log_current_story(current_story, "Init")

    roll_actions = ["get_roll", "get_roll_attack", "get_roll_skill", "get_roll_skill_special_ability", "get_roll_narrator_saving_throw", "cast_spell", "use_item", "item_is_within_reach", "get_roll_saving_throw", "get_battle_info", "get_updated_battle_info", "get_battle_info_additional_opponents", "get_allied_characters", "get_status_effects", "create_combatant_sheet_stats", "create_combatant_sheet_attacks", "create_combatant_sheet_spells", "choose_combatant_action", "get_answer_to_viewer_decisions"]

    initial_ai_turn_actions = ["get_roll", "get_roll_attack", "get_roll_skill", "get_roll_skill_special_ability", "get_roll_narrator_saving_throw", "cast_spell", "use_item", "get_roll_saving_throw"]
    
    add_current_story_to_system = custom_action in ["is_main_quest_completed", "is_quest_completed", "is_quest_given", "update_inventory", "update_location", "update_location_category", "update_important_characters", "get_emotions", "get_emotions_opponents", "get_emotions_allies", "get_emotions_mc"] + roll_actions if is_game and extra_info != "skip_memory" else False # Removed: is_quest_failed

    #new_user_msg = preprocess_message(prompt_arg)
    new_user_msg = new_user_msg_arg if new_user_msg_arg is not None else ""

    # Actual game over msg (won or lost) in 2 parts
        # Will be true for both the in char dnd part and post mortem analysis chat msg parts
    is_game_won_or_lost_msg = current_story is not None and (current_story["is_game_won"] or current_story["is_game_lost"]) and new_user_msg == "" and custom_action is None

    is_user_convo_chat_dnd = is_chat_dnd and not is_game_won_or_lost_msg
    is_normal_game_turn_dnd = is_game_dnd and not is_game_won_or_lost_msg
    is_json_mode = is_user_convo_chat_dnd or is_normal_game_turn_dnd or custom_action is not None #(custom_action is not None and custom_action not in ["choose_music"])

    convo_obj_filepath, _ = get_new_convo_filename(is_game, is_chat_dnd, current_story, filename, custom_action)

    if current_game == "dnd" or state_switch == "dnd":
        history_file = dnd_history_file # if not custom_action == "get_emotions" else get_emotions_history_file
    elif history_file_arg is not None:
        history_file = history_file_arg
    else:
        history_file = chat_history_file

    messages_history = get_messages_history(history_file) if override_messages_history is None else copy.deepcopy(override_messages_history) # Always clone when overriding, otherwise will modify the original)
    config = get_ai_config()

    # Use setup zero if it exists.
    has_setup_zero = False

    if os.path.isfile(f'{ai_config_path}setup_zero.json'):
        setup = read_json(f'{ai_config_path}setup_zero.json')
        has_setup_zero = True
    else:
        setup = read_json(f'{ai_config_path}setup.json')

    # Current stream stats
    stream_statistics_path = f"{stream_path}/info/stream_statistics.json"
    if os.path.isfile(stream_statistics_path):
        stream_statistics = read_json(stream_statistics_path)
    
    # Decide if we use gpt4 or not
    if is_game:
        is_gpt_4 = config["ai_dnd_game_rp_model_vers"] == 4 # AI side of the game (doesn'T include server, is in it's own file (dnd_server_setup.json))
    elif is_chat_dnd:
        is_gpt_4 = config["ai_dnd_chat_model_vers"] == 4 # AI talking to chat
    else:
        is_gpt_4 = config["ai_full_chat_model_vers"] == 4

    custom_actions_using_gpt4 = config["custom_actions_using_gpt4"]

    # Never allow gpt4 for custom actions, unless explicitly specified
    if custom_action is not None and custom_action not in custom_actions_using_gpt4:
        is_gpt_4 = False
    elif force_gpt4:
        is_gpt_4 = True

    #messages = messages_history.copy() # Temporarily copy the history
    messages = []
    msg_segments = [] # Only used in get_emotions custom action

    # setup max user message length if exist, default from file if not.
    if custom_action:
        max_response_length = config["max_response_length_custom_action"] # Allow longer messages for custom actions (ex : music)
    elif is_game:
        max_response_length = config["max_response_length_dnd"]
    else :
        max_response_length = config["max_response_length_chat"]

    prompt = ""
    user_current_story_message = None

    if not is_game:
        # setup prompt and system, use func argument of exist, default from file if not.
        prompt = custom_prefix if custom_prefix is not None else ""
        system_current = current_date_prefix() # Add things like curent date and current events

        # Don't add current events to system messages and custom actions
        if not auto_mode and custom_action is None and not is_chat_dnd and new_user_msg != "":
            system_current = system_current + " " + get_current_event_prompt(new_user_msg, setup, state_switch == "dnd") # Skip some events when coming from ai dungeon
        else:
            global previous_user_prompt_web_info
            previous_user_prompt_web_info = "" # Clear up previous web info when we switch to system.

        # Add stream info to system messages
        if is_stream:
            info_up_to_date = stream_statistics["last_updated"] > time.time() - 180 # 3 minutes
            if info_up_to_date:
                concurrent_viewers = stream_statistics["concurrent_viewers"]
                if concurrent_viewers > 0:
                    system_current = system_current + f" There are currently {concurrent_viewers} viewers watching the stream."
            else:
                system_current = system_current + f" There are currently an unknown number of viewers watching the stream."

        system_current_message = format_msg_oai("system", system_current)

        # Add the system msg about current events : 
        messages.append(system_current_message)

        # Nb of messages already made by the user
        current_chat_messages_history = get_messages_history(dnd_with_chat_history_file) if is_chat_dnd else messages_history
        nb_messages_by_user = count_username_instances(current_chat_messages_history, username)

        if not has_setup_zero:
            system = setup["system"]
            messages.append(format_msg_oai("system", system))
        else:
            # First system msg
            system = setup["system"]

            # Game hair color
            game_hair_color_text = ""
            if is_chat_dnd and current_story is not None:
                hair_preset = current_story.get("hair_preset", "")
                hair_preset = hair_preset if hair_preset != "default" and not hair_preset.startswith("pink") else ""

                if hair_preset != "":
                    split_hair_preset = hair_preset.split("_")
                    # combination of the first 2 elements of hair preset if the first element in "light" or dark", otherwise just the first element
                    current_hair_color = split_hair_preset[0] + " " + split_hair_preset[1] if len(split_hair_preset) > 1 and split_hair_preset[0] in ["light", "dark"] else split_hair_preset[0]

                    game_hair_color_text = setup["game_hair_color"].replace("#hair_color#", current_hair_color)
            else:
                game_hair_color_text = ""
            system = system.replace("#game_hair_color#", game_hair_color_text)

            system += " " + setup["system_chat_only_postfix"] if not is_game_won_or_lost_msg else ""

            system_message = format_msg_oai("system", system)
            messages.append(system_message)

            # Skip base system2 when first game won or lost messages
            if not is_game_won_or_lost_msg:
                messages.append(format_msg_oai("system", setup["system_2"]))

            messages.append(format_msg_oai("system", setup["system_3"]))
            messages.append(format_msg_oai("system", setup["system_3_chat_only_part_1"]))
            messages.append(format_msg_oai("system", setup["ai_personality"]))
            messages.append(format_msg_oai("system", setup["system_simulation"]))

            # Determine whether to include the user's name or not in the answer
            add_name_instruction = ""
            if nb_messages_by_user == 0 or is_chat_dnd:
                pass # Ai itself decide whether to add name or not for now
            else:
                add_name_instruction = " " + setup["dont_add_name_instruction"]

            # Remove emotion user msg in hashtags for dnd user msg (uses json instead)
            emotion_user_msg_hashtags = setup["emotion_user_msg_hashtags"] if not is_chat_dnd else ""
            emotion_user_msg_hashtags += add_name_instruction

            messages.append(format_msg_oai("system", setup["system_3_chat_only_part_2"].replace("#emotion_user_msg_hashtags#", emotion_user_msg_hashtags)))

        if state_switch == "dnd":
            messages.append(create_current_memory_story_message(setup_dnd, config_dnd, current_story, chat_with_viewer=True))
            uplifting_note = setup_dnd["game_end_uplifting_note"]

            is_game_won = current_story["is_game_won"]
            is_game_lost = current_story["is_game_lost"]
            is_game_won_or_lost = is_game_won or is_game_lost

            is_before_game_won = is_game_won and current_story.get("game_over_time") is None
            is_before_game_lost = is_game_lost and current_story.get("game_over_time") is None
            is_before_game_won_or_lost = is_before_game_won or is_before_game_lost
            is_time_up_game_won_or_lost_speak_viewers = is_time_up_speak_viewers(current_story, config_dnd)

            # Post mortem analysis of game over msg
            if is_game_won_or_lost_msg and is_game_lost: # Initial game lost msg when no user msg
                prompt = setup_dnd["dnd_game_lost_prompt_2"].replace("#uplifting_note#", uplifting_note)
            elif is_game_won_or_lost_msg and is_game_won: # Initial game won msg when no user msg
                prompt = setup_dnd["dnd_game_won_prompt_2"].replace("#uplifting_note#", uplifting_note)
            else:
                # INTRO
                # After game discussion intro
                if is_before_game_won_or_lost:
                    game_status_text = setup_dnd["game_status_won"] if is_before_game_won else setup_dnd["game_status_lost"]
                    state_switch_prompt = setup_dnd["state_switch_from_dnd_prompt_intro"] + " " + game_status_text
                # Same intro for game about to end or ongoing game (just a diff status)
                elif is_game_won_or_lost:
                    state_switch_prompt = setup_dnd["state_switch_from_dnd_after_game_prompt_intro"]
                else:
                    state_switch_prompt = setup_dnd["state_switch_from_dnd_prompt_intro"] + " " + setup_dnd["game_status_ongoing"]

                state_switch_prompt = state_switch_prompt.replace("#char_name#", current_story["char_name"])

                # Put part 1 together
                state_switch_prompt = f"{state_switch_prompt} {setup_dnd['state_switch_from_dnd_prompt_part_1']}"

                # PART 2
                # Text telling the AI what to do if the viewer msg is related to the game
                if is_before_game_won_or_lost:
                    related_to_game_text = setup_dnd["related_to_game_won_or_lost"].replace("#won_or_lost#", "won" if is_game_won else "lost")
                elif is_game_won_or_lost:
                    related_to_game_text = setup_dnd["related_to_after_game"] 
                    
                    if is_time_up_game_won_or_lost_speak_viewers:
                        related_to_game_text = related_to_game_text + " " + setup_dnd["next_game_start_soon"]                    
                else:
                    related_to_game_text = setup_dnd["related_to_game_ongoing"]

                # Determine whether to move on if unrelated
                move_on_if_unrelated_text = " " + setup_dnd["move_on_if_unrelated"] if current_story.get("unrelated_or_refused_retries", 0) == config_dnd["max_unrelated_or_refused_nb_retry"] else ""

                # Specify not to add the viewer's name to the response
                add_name_instruction = " " + setup_dnd["dont_add_name_instruction_dnd"] if nb_messages_by_user > 0 else "" # Don't name the viewer
                
                # End json
                state_switch_prompt_json = setup_dnd["state_switch_from_dnd_prompt_json"].replace("#produce_json_short#", setup_dnd["produce_json_short"])

                # Add the part 2 to the prompt
                state_switch_prompt = f"{state_switch_prompt} {related_to_game_text} {setup_dnd['state_switch_from_dnd_prompt_part_2']}{move_on_if_unrelated_text}{add_name_instruction} {state_switch_prompt_json}"

                # Viewer when in zero mode, user otherwise
                the_user_or_viewers = "your viewers" if has_setup_zero else "the user"
                user_or_viewer = "viewer" if has_setup_zero else "user"
                state_switch_prompt = state_switch_prompt.replace("#the_user_or_viewers#", the_user_or_viewers).replace("#user_or_viewer#", user_or_viewer)

                prompt = prompt + state_switch_prompt

    elif is_game and custom_action is None: 

        # Set up the prompt
        prompt = setup_dnd["dnd_prompt"]

        # Can only start a battle if not already in one
        allow_battle_start = current_story.get("battle_info") is None

        # Add or remove the json for the intend to start battle (only when not already in battle)
        intend_start_battle_text = setup_dnd["intend_start_battle_text"] if allow_battle_start else setup_dnd["dont_intend_start_battle_text"]
        intend_start_battle_json = setup_dnd["intend_start_battle_json"] if allow_battle_start else ""
        prompt = prompt.replace("#intend_start_battle_text#", intend_start_battle_text).replace("#intend_start_battle_json#", intend_start_battle_json)
        
        # Replace the prompt with the game over prompt if the game is over
        if is_game_won_or_lost_msg:
            game_end_prefix = setup_dnd["game_end_prefix"]
            game_over_quest = current_story["game_over_quest"]

            if current_story["is_game_lost"]: # Initial game lost msg when in character
                # Char dropped to 0 hp when game_over_quest is empty
                if game_over_quest != "" and game_over_quest is not None:
                    prompt = setup_dnd["dnd_game_lost_main_quest_prompt_1"].replace("main_quest", game_over_quest)
                else:
                    prompt = setup_dnd["dnd_game_lost_killed_prompt_1"]

            elif current_story["is_game_won"]: # Initial game won msg when in character
                # Shouldn't happen, but use as backup just in case
                if game_over_quest is None or game_over_quest == "":
                    game_over_quest = combine_array_as_sentence(current_story["main_quests_archive"])

                prompt = setup_dnd["dnd_game_won_prompt_1"].replace("main_quest", game_over_quest)

            prompt = prompt.replace("#game_end_prefix#", game_end_prefix)
            
        dnd_system1 = setup_dnd["system_dnd_1"].replace("#character_name#", current_story["char_name"])
        messages.append(format_msg_oai("system", dnd_system1))
        #system3 += " " + setup["ai_personality"] # Don't add zero personnality to ai dungeon, will just clash
        
        dnd_system2 = setup_dnd["system_dnd_2"].replace("#genre#", current_story["genre"])

        # RP Tags (modifies how the character acts in battle)
        rp_tags = current_story.get("rp_tags", [])

        if "pacifist" in rp_tags:
            dnd_system2 += setup_dnd["pacifist_text"]
        elif "non_combatant" in rp_tags:
            dnd_system2 += setup_dnd["non_combatant_text"]
        else:
            dnd_system2 += setup_dnd["combatant_text"]

        # If the character can be evil or not
        if "evil" in rp_tags:
            dnd_system2 += setup_dnd["evil_text"]

        messages.append(format_msg_oai("system", dnd_system2))

        dnd_system3 = setup_dnd["system_dnd_3"].replace("#genre#", current_story["genre"])
        messages.append(format_msg_oai("system", dnd_system3))

        # Create system msg for current story
        user_current_story_message = create_current_memory_story_message(setup_dnd, config_dnd, current_story, include_inventory_msg=True) 

    elif is_game and custom_action is not None:

        if add_current_story_to_system:
            skip_quests = custom_action in ["is_main_quest_completed", "is_quest_completed", "is_quest_given", "update_inventory"] + roll_actions # Quests are included in the prompt for quest actions + including quest in inventory confuses it if there's a reward (think it should add it now if there's a currency reward) (Removed : , "is_quest_failed")
            skip_scenario = custom_action in ["is_quest_given", "update_inventory"] # Don't include the scenario for quest given, have a tendency to always add it as a quest. Should include scenario for things like battle info, since it might be unclear otherwise who are the allies and who are the enemies.

            is_update_location = custom_action in ["update_location", "update_location_category"]

            skip_proficiencies = custom_action in ["choose_combatant_action"] # Skip proficiencies for opponent actions (not relevant + can cause issue with spell choice if spells are mentioned in proficiencies (ex : thessara))

            add_personality = custom_action in ["get_emotions", "get_emotions_opponents", "get_emotions_allies", "get_emotions_mc"]

            is_update_inventory = custom_action == "update_inventory"

            skip_char_description = skip_rage = False

            # Remove any mention of frenzy/barbarian attributes when deciding if attacking recklessly or not, since would then always attack recklessly when raging
            if has_talent("rage", current_story) and custom_action == "get_answer_to_viewer_decisions":
                skip_proficiencies = skip_char_description = skip_rage = True

            user_current_story_message = create_current_memory_story_message(setup_dnd, config_dnd, current_story, skip_quests, skip_scenario, include_secret_info=False, skip_location=is_update_location, skip_proficiencies = skip_proficiencies, skip_char_description=skip_char_description, skip_rage=skip_rage, add_personality=add_personality, is_update_inventory=is_update_inventory)
            messages.insert(0, user_current_story_message)

            # Add current location as sepparate user msg (makes it obvious that's the location at the begining of the messages)
            if is_update_location:
                current_location = get_current_location(current_story, setup_dnd)
                if current_location != "":
                    location_msg = format_msg_oai("user", current_location)
                    messages.insert(1, location_msg)
                    
    # Set where there actual messages start
    start_msg_index = len(messages)

    chat_messages_history = [] 
    
    # Whether to include chat messages in the history (either here or in the message history loop further down below)
    if current_story is not None and (is_chat_dnd or custom_action == "get_answer_to_viewer_decisions"):
        chat_messages_history = get_messages_history(dnd_with_chat_history_file)
        
        # How many time the user msg has been refused or found to be unrelated in a row
        unrelated_or_refused_retries = current_story.get("unrelated_or_refused_retries", 0)

        is_discussion_after_game_won_or_lost = (current_story.get("is_game_won", False) or current_story.get("is_game_lost", False)) and current_story.get("game_over_time") is not None

        nb_chat_turns_to_add = 0

        # Include retry message if the last message was unrelated or refused
        if is_chat_dnd and unrelated_or_refused_retries >= 1:
            nb_chat_turns_to_add = unrelated_or_refused_retries
        # How many back and forth chat msg to include after game won or lost
        elif is_chat_dnd and is_discussion_after_game_won_or_lost:
            nb_chat_turns_to_add = config_dnd["nb_chat_msg_duo_included_after_game_discussion"]
        # Include the current turn chat messages for get_answer_to_viewer_decisions
        elif not is_chat_dnd: 
            nb_chat_turns_to_add = unrelated_or_refused_retries + 1

        if nb_chat_turns_to_add > 0:
            last_chat_messages = get_current_turn_chat_messsages(chat_messages_history, nb_chat_turns_to_add)
            
            # Append the last x*2 messages to messages
            for chat_msg in last_chat_messages:
                messages.append(chat_msg)
                chat_messages_history.remove(chat_msg)

    new_message = None
 
    # Set the message to send to gpt
    if custom_action is None:
         # Set the use msg to message to send to gpt (only uses history when is_game = true)
        if new_user_msg != "" and not is_game:
            # For ai dungeon, the prompt is the prefix
            new_message_text = "System: " + new_user_msg if auto_mode else username + ": " + new_user_msg
            #new_message_text = new_message_text_no_prefix if not prompt else prompt + "; " + new_message_text_no_prefix

            new_message = format_msg_oai("user", new_message_text)
            
            # Append prompt message to messages
            messages.append(new_message)

    else:
        main_char_name = current_story["char_name"] if current_story is not None else "Zero" # Don't crash in ai convo mode

        # MUSIC
        if custom_action == "choose_music":
            folders = enumerate_folders(root_music_path, True)
            prompt = setup_dnd["music_choice_prompt"].replace("#themes#", folders)
        else:
            action_prompt = setup_dnd.get(custom_action + "_prompt", None)

            # Set the emotions prompt
            if custom_action == "get_emotions":
                #separate_sentences = not is_game 
                msg_segments = segment_text(remove_system_prefix(messages_history[-1]['content'])) if len(messages_history) > 0 else [] # , separate_sentences)
                action_prompt = action_prompt.replace("#last_message#", "your last message" if is_last_msg_assistant(messages_history) else "the last user message")
            elif custom_action in ["get_emotions_opponents", "get_emotions_allies", "get_emotions_mc"]:
                action_prompt = setup_dnd.get("get_emotions_combatants_or_mc_prompt", None)
                emotion_text = emotion_json = emotion_only_one_result_text = ""

                action_types = extra_info
                attack_no_json = ""
                battle_info = current_story.get("battle_info", None)

                if extra_info is None:
                    print_log("WARNING: No extra info for get_emotions_mc or get_emotions_combatants, defaulting to attacks.", True)
                    action_types = "attacks"

                # Include the attack no for spells in battle too
                if action_types == "attacks" or (action_types == "spell" and battle_info is not None):
                    attack_no_json = setup_dnd["emotion_attack_no_json"]
                    emotion_text = setup_dnd["emotion_attack_no_text"]

                    if action_types == "spell":
                        action_types = "spell attacks"

                    # Replace the placeholders for combatants when in battle
                    if custom_action in ["get_emotions_opponents", "get_emotions_allies"]:
                        is_opponent = custom_action == "get_emotions_opponents"
                        opp_or_ally = "opponent" if is_opponent else "ally"
                        opps_or_allies_cap = "Opponents" if is_opponent else "Allies"
                        combatants = battle_info["opponents"] if is_opponent else battle_info["allies"]
                        combatant_identifiers = [combatant["identifier"] for combatant in combatants]
                        combatant_identifiers_text = join_with_and(combatant_identifiers)

                        emotion_text = setup_dnd["emotion_combatants_text"].replace("#opp_or_ally#", opp_or_ally).replace("#opps_or_allies_cap#", opps_or_allies_cap).replace("#combatant_list#", combatant_identifiers_text)
                        emotion_json = setup_dnd["emotion_combatants_json"].replace("#opp_or_ally#", opp_or_ally)
                else:
                    emotion_only_one_result_text = setup_dnd["emotion_only_one_result_text"].replace("#action_types#", action_types)

                action_prompt = action_prompt.replace("#emotion_text#", emotion_text).replace("#emotion_combatants_json#", emotion_json).replace("#emotion_attack_no_json#", attack_no_json).replace("#action_types#", action_types).replace("#emotion_only_one_result_text#", emotion_only_one_result_text)

            elif custom_action in ["is_quest_given", "is_quest_completed"]:
                skip_main_quest = custom_action == "is_quest_completed" # Only show normal quests

                numbered_quests = get_numbered_quests(current_story, skip_main_quest=skip_main_quest) #, include_main_quests_condition=include_main_quests_condition)
                current_quests_list_message = " Current quests: " + numbered_quests if numbered_quests != "" else ""
                action_prompt = action_prompt.replace("#current_quests_message#", current_quests_list_message)

            elif custom_action == "is_main_quest_completed":
                force_quest_order = current_story.get("force_quest_order", False)

                # Only show main quests
                main_quests = get_main_quests_arr(current_story, full_only=True)
                is_last_main_quest = len(main_quests) == 1

                # Show multiple quest parts if force_quest_order is False
                main_quest_objectives = ""
                if len(main_quests) > 0:
                    main_quest_objectives = main_quests[0] + "." if force_quest_order else get_numbered_quests(current_story, skip_normal_quests=True)

                # Can only complete the first main quest
                current_quests_list_message = " Current main quest objective: " + main_quest_objectives if len(main_quests) > 0 else "" 
                concludes_main_quest_text = concludes_main_quest_json = concludes_main_quest_text_2 = ""

                # Only say that story will conclude for the last main quest
                if is_last_main_quest:
                    concludes_main_quest_text = setup_dnd["concludes_main_quest_text"]
                    concludes_main_quest_json = setup_dnd["concludes_main_quest_json"] 
                    concludes_main_quest_text_2 = setup_dnd["concludes_main_quest_text_2"] 

                any_of_text = "" if force_quest_order else " any of"

                # Replace the placeholders in the prompt
                action_prompt = action_prompt.replace("#concludes_main_quest_text#", concludes_main_quest_text).replace("#concludes_main_quest_json#", concludes_main_quest_json).replace("#concludes_main_quest_text_2#", concludes_main_quest_text_2).replace("#current_quests_message#", current_quests_list_message).replace("#any_of_text#", any_of_text)

            elif custom_action == "update_location_category":
                action_prompt = action_prompt.replace("#location_categories#", setup_dnd["location_categories"])
                action_prompt = action_prompt.replace("#current_location#", get_current_location(current_story, setup_dnd))
            elif custom_action == "update_important_characters":
                current_important_characters = get_important_characters(current_story, setup_dnd, True)
                current_important_characters = " " + current_important_characters if current_important_characters != "" else ""
                action_prompt = action_prompt.replace("#important_characters#", current_important_characters)
            elif custom_action == "get_status_effects":
                battle_info = current_story.get("battle_info", None)
                opponents = battle_info.get("opponents", None) if battle_info is not None else None
                current_groups_text = ""

                if opponents is not None:
                    opponents_groups = get_groups_from_combatants(opponents)
                    groups_names = [group["name"] for group in opponents_groups]
                    current_groups_text = join_with_and(groups_names)
                    
                action_prompt = action_prompt.replace("#enemy_groups#", current_groups_text)

            elif custom_action in ["get_battle_info", "get_battle_info_additional_opponents"]:
                is_additional_opponents = custom_action == "get_battle_info_additional_opponents"

                group_label = potential_entry_names_text = ""

                char_lvl = current_story.get("level", 1)
                difficulty_level = current_story.get("difficulty_level") 
                battle_info = current_story.get("battle_info", None)

                # Set the prompt based on whether it's the additional opponent version or not
                if is_additional_opponents:
                    action_prompt = setup_dnd["get_battle_info_prompt"] # Need to set it, since a prompt doesn't exist for _additional_opponents custom action

                    additional_opponents_following_types = ""

                    # Add the detected group names, if there are any (will be empty for narrator_roll call)
                    if extra_info is not None:
                        additional_opponent_groups = extra_info
                        additional_opponent_groups_names = join_with_and(additional_opponent_groups)

                        additional_opponents_following_types = setup_dnd["battle_info_additional_opponents_following_types"].replace("#additional_opponent_groups_names#", additional_opponent_groups_names)

                    battle_info_intro = setup_dnd["battle_info_additional_opponents_intro"].replace("#additional_opponents_following_types#", additional_opponents_following_types)

                    group_label = "additional_"

                    max_additional_opponents = config_dnd["max_additional_opponents"]
                    opponents = battle_info.get("opponents", []) if battle_info is not None else []

                    # Get the max cr of the additional opponents
                    normalized_max_cr_obj = get_max_cr_additional_opponents(char_lvl, difficulty_level, opponents, max_additional_opponents)
                    have_non_zero_cr = any(cr_value > 0 for cr_value in normalized_max_cr_obj.values())

                    # If already at max difficulty, avoid adding more difficult opponents
                    if not have_non_zero_cr:
                        opponents_info_text = setup_dnd["battle_info_already_difficult_text"]
                    else:
                        # Otherwise, add additional opponents within the max cr range
                        cr_texts = []
                        for cr in normalized_max_cr_obj:
                            or_below_text = " or below" if normalized_max_cr_obj[cr] == max_additional_opponents else ""
                            if normalized_max_cr_obj[cr] > 0:
                                cr_texts.append(f"{normalized_max_cr_obj[cr]} opponents of cr {cr}{or_below_text}")

                        cr_text_joined = join_with_and(cr_texts, "or")
                        opponents_info_text = setup_dnd["battle_info_additional_opponents_info"].replace("#monsters_cr_text#", cr_text_joined)

                else:
                    battle_info_intro = setup_dnd["battle_info_intro"]

                    # Get the appropriate monsters for the battle given the character level and difficulty level
                    max_opponents = config_dnd["max_opponents"]
                    monsters_cr_text, _ = get_combatants_cr(char_lvl, difficulty_level, max_opponents)
                    opponents_info_text = setup_dnd["battle_info_opponents_info"].replace("#level#", str(char_lvl)).replace("#monsters_cr_text#", monsters_cr_text)#.replace("#monsters_hp_text#", monsters_hp_text)

                previous_two_messages = messages_history[-2:] if len(messages_history) >= 2 else []
                previous_two_messages_text = " ".join([msg["content"] for msg in previous_two_messages])
                potential_entry_names = find_entry_names_in_text(previous_two_messages_text)

                if len(potential_entry_names) > 0:
                    potential_entry_names_text = setup_dnd["battle_info_potential_entry_names"].replace("#potential_entry_names#", join_with_and(potential_entry_names))
                    
                action_prompt = action_prompt.replace("#battle_info_intro#", battle_info_intro).replace("#group_label#", group_label).replace("#potential_entry_names_text#", potential_entry_names_text)

                action_prompt = action_prompt.replace("#opponents_info#", opponents_info_text)

            elif custom_action in ["get_allied_characters"]:
                char_lvl = current_story.get("level", 1)
                difficulty_level = current_story.get("difficulty_level")

                # Get the appropriate monsters for the battle given the character level and difficulty level
                max_allies = config_dnd["max_allies"]
                allies_cr_text, _ = get_combatants_cr(char_lvl, difficulty_level, max_allies)
                allies_info_text = setup_dnd["battle_info_allies_info"].replace("#level#", str(char_lvl)).replace("#allies_cr_text#", allies_cr_text)

                action_prompt = action_prompt.replace("#allies_info#", allies_info_text)

            elif custom_action in roll_actions:
                
                # USE ITEM / SPECIAL ABILITY
                if custom_action == "use_item":
                    # Don't need misc object in inventory to use them if in a category specifically allowed for the char
                    misc_objects = current_story.get("available_misc_objects") 
                    misc_objects_json_name = current_story.get("available_misc_objects_json_name")
                    misc_objects_placeholders = ["is_available_misc_objects_text", "is_available_misc_objects_json"]

                    # Don't include misc obj check if either object list or the json is empty (json empty for Eris since all allowed, don't need any check)
                    if custom_action == "use_item" and misc_objects is not None and misc_objects_json_name is not None:
                        action_prompt = replace_placeholders(action_prompt, setup_dnd, misc_objects_placeholders)

                        action_prompt = action_prompt.replace("#available_misc_objects#", misc_objects) # Replace the text within the parent wildcard too
                        action_prompt = action_prompt.replace("#misc_obj_json_name#", misc_objects_json_name)
                    else:
                        action_prompt = empty_placeholders(action_prompt, misc_objects_placeholders)
                elif custom_action == "item_is_within_reach":
                    action_prompt = action_prompt.replace("#item_name#", extra_info if extra_info is not None else "")
                elif custom_action == "get_roll_skill_special_ability":
                    special_abilities = current_story.get("special_abilities", [])
                    special_ability_skill = current_story.get("special_ability_skill", None)
                    special_ability_stat = get_use_special_ability_stat(current_story)
            
                    # Normal skill
                    if special_ability_skill is None:
                        print("ERROR: No special ability skill provided.")
                        return None, None, None
                    elif len(special_abilities) == 0:
                        print("ERROR: No special abilities available.")

                    special_ability_texts = [f"'{ability}'" for ability in special_abilities]
                    joined_special_abilities = "either " + join_with_and(special_ability_texts, "or") if len(special_ability_texts) > 1 else special_ability_texts[0]

                    special_ability_skill_text_intro = "This ability uses" if len(special_ability_texts) == 1 else "These abilities use"
                    special_ability_skill_text = special_ability_skill_text_intro + " the " + special_ability_skill

                    action_prompt = action_prompt.replace("#special_abilities#", joined_special_abilities).replace("#special_ability_skill_text#", special_ability_skill_text).replace("#special_ability_stat#", special_ability_stat)

                elif custom_action == "get_roll_attack":
                    # sneak attack
                    if has_talent("sneak attack", current_story):
                        placeholders = ["is_sneak_attack_text", "is_sneak_attack_json"]
                        action_prompt = replace_placeholders(action_prompt, setup_dnd, placeholders)
                    else:
                        action_prompt = action_prompt.replace("#is_sneak_attack_text#", "").replace("#is_sneak_attack_json#", "")

                    # favored enemy
                    favored_enemy_talent = get_talent("favored enemy", current_story, partial_match=True)

                    if favored_enemy_talent is not None:
                        placeholders = ["opponent_is_favored_enemy_text", "opponent_is_favored_enemy_json"]
                        action_prompt = replace_placeholders(action_prompt, setup_dnd, placeholders)

                        favored_enemy_name = extract_text_in_parenthesis(favored_enemy_talent)
                        action_prompt = action_prompt.replace("#favored_enemy_name#", favored_enemy_name)
                    else:
                        action_prompt = action_prompt.replace("#opponent_is_favored_enemy_text#", "").replace("#opponent_is_favored_enemy_json#", "")
                
                elif custom_action == "get_updated_battle_info":
                    last_message_role = messages_history[-1]["role"] if len(messages_history) > 0 else ""
                    outcome_text = outcome_json = last_message_text = ""
                    if last_message_role == "assistant":
                        outcome_text = setup_dnd["do_not_assume_outcome_text"]
                        outcome_json = setup_dnd["outcome_is_known_json"]
                        last_message_text = "your last message"
                    else:
                        last_message_text = "the last user message"

                    action_prompt = action_prompt.replace("#do_not_assume_outcome#", outcome_text).replace("#outcome_is_known_json#", outcome_json).replace("#last_message#", last_message_text)

                elif "choose_combatant_action" in custom_action:

                    # Up to date current story should now be included in send_message
                    battle_info = current_story.get("battle_info", None)

                    combatant, is_opponent = extra_info
                    if combatant is None:
                        print("\nERROR: No combatant info provided for choose_combatant_action custom action.\n")
                        return None, None, None

                    #groups = battle_info["groups"]

                    # group = find_combatant_group(combatant, groups)
                    # group_name, cr, action_prompt = get_group_info(group, action_prompt)
                    group_name = combatant["group_name"]
                    cr = combatant.get("cr", "1")

                    if group_name is None or cr is None:
                        print("\nERROR: No group name or cr provided for choose_combatant_action custom action.\n")
                        return None, None, None
                    
                    action_prompt = action_prompt.replace("#combatant_cr#", str(cr)).replace("#combatant_identifier#", combatant["identifier"])

                    # Use different text depending on the last message's role
                    last_msg_role = messages_history[-1]["role"] if len(messages_history) > 0 else "user"
                    last_msg_role_text = "the last user" if last_msg_role == "user" else "your last message"
                    action_prompt = action_prompt.replace("#last_x#", last_msg_role_text)

                    combatant_sheets = get_combatant_sheets()
                    sheet = get_combatant_sheet(group_name, cr, combatant_sheets)

                    # Weapon list
                    attacks = sheet.get("attacks", [])
                    combatant_is_ranged = combatant.get("is_ranged", False)

                    # Only get attacks that matches the combatant's type (ranged or melee)
                    weapon_list = [attack["weapon"] for attack in attacks if combatant_is_ranged == attack.get("is_ranged", False)]
                    weapon_list = weapon_list if len(weapon_list) > 0 else [attack["weapon"] for attack in attacks] # If no weapon of the same type, get all weapons instead

                    action_prompt = action_prompt.replace("#weapon_list#", combine_array_as_sentence(weapon_list))

                    # Spell placeholders
                    casting_spell_name = casting_spell_detail = casting_spell_instructions = casting_spell_json_action = casting_spell_json_detail = ""

                    if combatant.get("is_spellcaster", False):
                        casting_spell_name = setup_dnd["choose_action_casting_spell_name"]
                        casting_spell_detail = setup_dnd["choose_action_casting_spell_detail"]
                        casting_spell_instructions = setup_dnd["choose_action_casting_spell_instructions"]
                        casting_spell_json_action = setup_dnd["choose_action_casting_spell_json_action"]
                        casting_spell_json_detail = setup_dnd["choose_action_casting_spell_json_detail"]

                    action_prompt = action_prompt.replace("#casting_spell_name#", casting_spell_name).replace("#casting_spell_detail#", casting_spell_detail).replace("#casting_spell_instructions#", casting_spell_instructions).replace("#casting_spell_json_action#", casting_spell_json_action).replace("#casting_spell_json_detail#", casting_spell_json_detail)

                    # Spell list (need the placeholders first)
                    if combatant.get("is_spellcaster", False):
                        action_prompt = add_spell_list_to_action_prompt(action_prompt, sheet, combatant)

                elif "create_combatant_sheet" in custom_action:
                    # Up to date current story should now be included in send_message
                    battle_info = current_story.get("battle_info", None)
                    group = extra_info

                    if group is not None:
                        # group_name, cr, action_prompt = get_group_info(group, action_prompt)
                        group_name = group["name"]
                        cr = group["cr"]
                        action_prompt = action_prompt.replace("#combatant_name#", singularize_name(group_name))

                        combatant_cr_text = main_ability_score_text = ac_range_text = multiattack_range_text = max_spell_level_text = ""

                        # Can be None in some case (cast spell or use items with target + out of battle)
                        if cr is not None:
                            combatant_cr_text = f" (CR {cr})" if custom_action == "create_combatant_sheet_stats" else f" with a CR of '{cr}'"
                            
                            stat_range = get_monsters_attribute_text(cr, "main_stat_mod_range")
                            main_ability_score_text = setup_dnd["main_ability_score_text"].replace("#stat_range#", stat_range)

                            ac_text = get_monsters_attribute_text(cr, "ac_range")
                            ac_range_text = f" (should be {ac_text}, pick one)" 

                            multiattack_range = get_monsters_attribute_text(cr, "nb_multiattack")
                            multiattack_range = multiattack_range if multiattack_range != "1" else "only one attack"
                            multiattack_range_text = f" ({multiattack_range})"

                            cl = get_monsters_single_value(cr, "level")
                            cl = extract_int(cl)
                            max_spell_level = get_opponent_max_spell_level(cl)
                            max_spell_level_text = setup_dnd["max_spell_level_text"].replace("#max_spell_level#", str(max_spell_level))

                        action_prompt = action_prompt.replace("#combatant_cr_text#", combatant_cr_text).replace("#main_ability_score_text#", main_ability_score_text).replace("#multiattack_range_text#", multiattack_range_text).replace("#ac_range_text#", ac_range_text).replace("#max_spell_level_text#", max_spell_level_text)

                elif "get_answer_to_viewer_decisions" in custom_action:
                    action_prompt = add_class_features_to_action_prompt(action_prompt, current_story, setup_dnd, False)
                    action_prompt = action_prompt.replace("#user_or_viewer#", "viewer" if has_setup_zero else "user")

                # Add the special abilities to get_roll if there are any
                if custom_action == "get_roll":
                    action_prompt = add_class_features_to_action_prompt(action_prompt, current_story, setup_dnd, True)
                    action_prompt = action_prompt.replace("#user_or_viewer#", "viewer" if has_setup_zero else "user")

                    action_prompt = add_special_ability_get_roll(action_prompt, current_story, setup_dnd)

                    # Replace has_animal_companion_json in the get_roll prompt (Should empty the placeholder for everyone except juniper)
                    has_animal_companions_placeholders = ["has_animal_companion_json"]
                    action_prompt = replace_placeholders_for_story_param("animal companion", has_animal_companions_placeholders, action_prompt, current_story, setup_dnd, is_talent=True)

                    # Add focus item special text for any char that has one
                        # Only pure class wizards or cleric have a focus item
                    focus_item_id = None
                    if "wizard" in current_story["class"] or "sorcerer" in current_story["class"]:
                        focus_item_id = "arcane_focus"
                    elif "cleric" in current_story["class"]:
                        focus_item_id = "holy_symbol"

                    # find focus item in inventory
                    focus_item = next((item for item in current_story["inventory"] if item.get("magic_focus_bonus") is not None and item.get("is_equipped")), None)

                    # If the char has a focus item, add the special text for it
                    if focus_item_id is not None and focus_item is not None:
                        action_prompt = action_prompt.replace("#spell_channeled_text#", setup_dnd["spell_channeled_" + focus_item_id])

                        focus_item_json = setup_dnd["is_casting_spell_with_focus_json"].replace("#focus_name#", focus_item_id)
                        action_prompt = action_prompt.replace("#is_casting_spell_with_focus_json#", focus_item_json)
                    else:
                        action_prompt = action_prompt.replace("#spell_channeled_text#", setup_dnd["spell_channeled_generic"])
                        action_prompt = action_prompt.replace("#is_casting_spell_with_focus_json#", "")

                # Replace all the given placeholders with the corresponding values (needs to have the same key in setup_dnd)
                placeholders = ["abilities", "dc_scale", "scale_for_abilities", "estimate_challenge_rating", "never_include_unknown"]
                action_prompt = replace_placeholders(action_prompt, setup_dnd, placeholders)

            # If prompt doesn't exist, return an error
            if action_prompt is None:
                print("ERROR: No prompt found for custom action: " + custom_action)
                return None, None, None

            # Global placeholders, always try to replace those
            placeholders = ["produce_json_short", "produce_json", "provide_short_summary", "provide_full_summary", "provide_short_summary_ai_side", "provide_full_summary_ai_side", "provide_short_summary_multiple_msg"]
            action_prompt = replace_placeholders(action_prompt, setup_dnd, placeholders)

            prompt = action_prompt.replace("#character_name#", main_char_name)

    assistant_msg_nb_limit = None
    history_msg_nb_limit = None

    # When evaluating, we need to limit the number of messages to evaluate
    if custom_action:
        # More context to make sure it understands if the main quest is completed, or what the battle looks like
            # Also, give a bit more context to understand who the allies are
        if custom_action in ["is_main_quest_completed", "get_allied_characters"]: 
            assistant_msg_nb_limit = 4
        # if custom_action in ["get_battle_info", "get_updated_battle_info", "get_battle_info_additional_opponents"]: 
        #     assistant_msg_nb_limit = 2
        elif custom_action in ["update_inventory", "update_rest"]:
            assistant_msg_nb_limit = 1
        else:
            assistant_msg_nb_limit = 2 # Includes quest eval, to give a bit more context (might miss them otherwise)

        if custom_action in roll_actions and custom_action in initial_ai_turn_actions: # Only last 3 needed for those
            history_msg_nb_limit = 3

    repeat_last_msg = False

    # Decide whether to repeat the last message or not (to make sure the ai doesn't consider the msg before as the main action)
    if is_game:
        allowed_repeat_actions = ["get_roll", "use_item"] # Assistant only for now (don't raise assistant_msg_nb_limit lower down if I add a non assistant roll)
        minimum_msg_length_before_repeat = config_dnd["minimum_msg_length_before_repeat_for_roll"] # Minimum length of the message before repeating it (to avoid repeating short messages, only for get_roll for now)
        msg = messages_history[-1] if len(messages_history) > 0 else None
        
        if custom_action in allowed_repeat_actions and msg is not None and len(msg["content"]) <= minimum_msg_length_before_repeat:
            repeat_last_msg = True
            # Repeat last msg, but keep everything else the same
            history_msg_nb_limit += 1 
            assistant_msg_nb_limit += 1 # Repeated msg is always an assistant msg, so need to raise the limit by 1

    if not auto_mode:
        max_token_length = config["max_game_conversation_token_length"] if is_game else config["max_conversation_token_length"] 
    else:
        max_token_length = config["max_system_conversation_token_length"] 
    
    total_length = count_tokens(messages) + max_response_length # Total current length of messages + max possible length of the response
    
    if user_current_story_message is not None and is_game and custom_action is None:
        total_length += count_tokens([user_current_story_message])

    # Count the prompt in the length
    if prompt is not None and prompt != "":
        total_length += count_tokens([format_msg_oai("user", prompt)])

    # Copy the array so we can remove a message one by one
    remaining_messages_history = messages_history[:]
    inserted_messages_count = 0
    nb_assistant_msg = 0
    
    has_roll_text_msg = False
    is_first_loop = True

    can_add_chat_convo_msg = is_chat_dnd and len(chat_messages_history) > 0
    max_added_chat_convo_msg_nb = 3
    added_chat_convo_msg_nb = 0

    # Add messages from history to the current convo until we reach the max token length
        # Alternatively, continue until the x last assistant msg or the x last history msg
    while len(remaining_messages_history) > 0 and (assistant_msg_nb_limit is None or nb_assistant_msg < assistant_msg_nb_limit) \
        and (history_msg_nb_limit is None or inserted_messages_count < history_msg_nb_limit):
        if is_first_loop and repeat_last_msg:
            msg = messages_history[-1] # Repeat the last message
        else:
            msg = remaining_messages_history.pop()

        nb_assistant_msg = nb_assistant_msg + 1 if msg["role"] == "assistant" else nb_assistant_msg

        if custom_action is not None and custom_action in roll_actions:
            # Convert the roll text message to specify that it's a roll action
            if msg["role"] == "roll_text":
                has_roll_text_msg = True

                msg = format_msg_oai("assistant", msg["content"]) # clone the message to remove the roll_text role without modifying the original message

                # Keep the first 2 msg + the roll text + the previous msg (if there is a roll in the 3rd position).
                    # Happens for get_roll with a narrator roll before (want to include the answer to the prev ai msg)
                if inserted_messages_count == 2 and not repeat_last_msg:
                    history_msg_nb_limit = 4 
                # Keep 1 more msg and shift the roll position to the 3rd position when repeating the last msg
                elif inserted_messages_count == 3 and repeat_last_msg:
                    history_msg_nb_limit = 5

            # Specify what is the last msg and what is the history, otherwise focuses on the history instead of the last msg
                # Both the prefix and the square brackets are important, otherwise will have difficulty to sepparate the last msg from the history
            elif msg["role"] in ["user", "assistant"]:
                if is_first_loop:
                    text = "Your last message" if msg["role"] == "assistant" else "Last user message"
                else:
                    text = "Message history"

                formatted_content = remove_message_history_prefix(remove_system_prefix(msg["content"])) 

                # Remove the first char if it's a [ and the last char if it's a ] (if added by mistake during tests)
                if formatted_content.startswith("[") and formatted_content.endswith("]"):
                    formatted_content = formatted_content[1:-1]

                text = f"{text}: [" + formatted_content + "]"

                msg = format_msg_oai(msg["role"], text)

        elif custom_action is not None and custom_action == "get_emotions" and is_first_loop:
            # Last msg is segments for emotions
            prefix = "Your last message" if msg["role"] == "assistant" else "Last user message"
            text = f"{prefix} segments: [{format_msg_segment_objs(msg_segments)}]"
            msg = format_msg_oai(msg["role"], text)
        elif custom_action is not None and custom_action in ["get_emotions_opponents", "get_emotions_allies", "get_emotions_mc"] and is_first_loop:
            text = msg["content"]

            # Remove the first char if it's a [ and the last char if it's a ]
            if text.startswith("[") and text.endswith("]"):
                text = text[1:-1]
            
            msg = format_msg_oai("user", text)
        # Add emotions to the first batch of msg
        elif nb_assistant_msg == 0 and is_chat_dnd and msg["role"] in ["user", "assistant"]:
            # Add emotions to the current msg
            try:
                msg = add_emotions_to_msg(msg)
            except Exception as e:
                print(f"ERROR: Couldn't add emotions to message. EXCEPTION: {e}")
                print_log(f"Message that emotion couldn't be added to: {msg}")

        # Never send messages to oai if the role is not user, system or assistant, unless it's for roll_action (where it's processed a little bit later)
        if msg["role"] != "system" and msg["role"] != "user" and msg["role"] != "assistant":
            continue

        new_total_length = total_length + count_tokens([msg])
        
        if new_total_length >= max_token_length:
            break
        else:
            messages.insert(start_msg_index, msg) # Always insert right after the system (since we start by the last msg and work our way backwards)
            total_length = new_total_length
            inserted_messages_count += 1

        # Add dnd chat msg to the convo, as long as max limit not reached or the last msg was not refused or unrelated
            # Only insert them for assistant msg (to avoid having the viewer msg in the middle of the convo)
        if can_add_chat_convo_msg and len(chat_messages_history) >= 2 and msg["role"] == "assistant":
            ai_answer = copy.deepcopy(chat_messages_history.pop())
            user_question = copy.deepcopy(chat_messages_history.pop())

            new_total_length = total_length + count_tokens([ai_answer, user_question])

            if "$unrelated$" in ai_answer["content"] or "$refused$" in ai_answer["content"] or new_total_length >= max_token_length or added_chat_convo_msg_nb >= max_added_chat_convo_msg_nb:
                can_add_chat_convo_msg = False
            else:
                messages.insert(start_msg_index, ai_answer)
                messages.insert(start_msg_index, user_question)
                added_chat_convo_msg_nb += 1

        is_first_loop = False

    # Include memory 6 msg behind the last msg
    if user_current_story_message is not None and is_game and custom_action is None:
        memory_insert_idx = len(messages) -6
        if memory_insert_idx < start_msg_index:
            memory_insert_idx = start_msg_index

        messages.insert(memory_insert_idx, user_current_story_message)

    # Remove the extra msg if there were no roll text in the current roll action messages (only keep 2 last msg in that case)
        # Don't do it if it's the first few messages (will keep only 1 msg)
    if custom_action in roll_actions and not has_roll_text_msg and inserted_messages_count > 2:
        del messages[start_msg_index]

    # Add spell list msg
    if is_chat_dnd and current_story.get("spellcasting_ability"):
        available_spells_text = get_available_spells_text(current_story)
        spell_index = start_msg_index - 1 if start_msg_index > 0 else start_msg_index
        messages.insert(spell_index, format_msg_oai("user", available_spells_text))

    # Add skills for get_roll
    if custom_action in ["get_roll", "get_roll_skill", "get_roll_skill_special_ability", "choose_combatant_action"]:

        common_skills = setup_dnd["common_skills"]
        available_skills = get_available_skills(common_skills, current_story["skills"])
        skill_msg = f"[{setup_dnd['all_possible_skills']}: {available_skills}.]"

        messages.insert(start_msg_index, format_msg_oai("user", skill_msg))

    # Add msg for get_roll containing clarifications
    if custom_action == "get_roll":
        roll_clarifications = []

        # Add roll clarifications for the char
        story_roll_clarifications = current_story.get("roll_clarifications", "")
        if story_roll_clarifications is not None:
            roll_clarifications.append(story_roll_clarifications)

        # If has rage feature and not currently raging, detect if should start raging
        is_raging = current_story.get("is_raging")
        if is_raging is not None and not is_raging:
            is_raging_text = setup_dnd["is_raging_clarifications"]
            roll_clarifications.append(is_raging_text)

        # Animal companion
        if has_talent("animal companion", current_story):
            roll_clarifications.append(setup_dnd["has_animal_companion_clarifications"])

        # Magic items
        roll_clarifications.append(setup_dnd["magic_item_clarifications"])

        messages.insert(start_msg_index, format_msg_oai("user", f"[Clarifications: {' '.join(roll_clarifications)}]"))

    # Include battle info for narrator rolls
    if custom_action in ["get_roll_attack", "cast_spell", "use_item", "get_updated_battle_info", "get_battle_info_additional_opponents", "choose_combatant_action"] and current_story.get("battle_info") is not None:
        is_combatant_action = is_opponent_combatant_action = False
        battle_info_texts = []

        if custom_action == "choose_combatant_action":
            is_combatant_action = True
            is_opponent_combatant_action = len(extra_info) > 1 and extra_info[1] == True

        # Only include spellcaster opponent when target of spell, no restriction otherwise (casters can attack in melee too)   
        if not is_combatant_action or not is_opponent_combatant_action:
            opponents_battle_info_text = get_current_opponents_info_text(current_story, setup_dnd)
            if opponents_battle_info_text:
                battle_info_texts.append(opponents_battle_info_text)

        # Add allies to the battle info, even if not opponent turn (ex : target allies for healing spell)
        if not custom_action in ["get_roll_attack", "get_battle_info_additional_opponents"] and (not is_combatant_action or is_opponent_combatant_action):
            allies_battle_info_Text = get_current_allies_info_text(current_story, setup_dnd)
            if allies_battle_info_Text:
                battle_info_texts.append(allies_battle_info_Text)

        battle_info_text = " ".join(battle_info_texts)

        messages.insert(len(messages) - 1, format_msg_oai("user", battle_info_text))

    # Include available emotions list 1 msg behind the last msg
    if custom_action in ["get_emotions", "get_emotions_opponents", "get_emotions_allies", "get_emotions_mc"]:
        available_emotions = setup_dnd["available_emotions"]
        messages.insert(len(messages) - 1, format_msg_oai("user", available_emotions))

        available_expressions = setup_dnd["available_expressions"]
        messages.insert(len(messages) - 1, format_msg_oai("user", available_expressions))

    has_valid_prev_chat_msg = False

    # Include previous chat convo as a message for the initial ai turn (in case that info is not repeated in the ai dnd message)
    if is_game and (custom_action in initial_ai_turn_actions or is_game_dnd):
        chat_msg_recall_text = process_previous_chat_msg(current_story, setup_dnd)

        if chat_msg_recall_text is not None:
            chat_msg_recall = format_msg_oai("user", chat_msg_recall_text)
            has_valid_prev_chat_msg = True

            if is_game_dnd:
                messages.append(chat_msg_recall)
            else:
                msg_index = -2 if repeat_last_msg else -1
                # insert before last message
                messages.insert(msg_index, chat_msg_recall)

            # Specify to follow the decision related to the chat message
            if prompt is not None:
                state_switch_from_chat_msg = setup_dnd["state_switch_from_chat_msg"]
                prompt = prompt.replace("#state_switch_from_chat_msg#", state_switch_from_chat_msg)

        # Remove the hashtag from the prompt if not used.
        elif prompt is not None:
            prompt = prompt.replace("#state_switch_from_chat_msg#", "")

    # Add the prompt to the messages
    if prompt is not None and prompt != "":
        messages.append(format_msg_oai("user", prompt))

    # Decide gpt models + settings
    model_name = config["gpt4_model"] if is_gpt_4 else config["gpt3_model"]
    backup_model_name = config["gpt4_backup_model"] if is_gpt_4 else config["gpt3_backup_model"]
    
    # Define the call's timeout
    if custom_action:
        timeout = config["custom_action_timeout"]
    else:
        timeout = config["gpt4_timeout"] if is_gpt_4 else config["gpt3_timeout"]

    timeout = timeout + 2 if auto_mode else timeout

    temperature = config["ai_temperature"] if custom_action is None else config["custom_action_temperature"]
    presence_frequency = config["ai_presence_penalty"] if custom_action is None else config["custom_action_presence_penalty"]
    frequency_penalty = config["ai_frequency_penalty"] if custom_action is None else config["custom_action_frequency_penalty"]

    # Different top_p depending on the level of creativity required
    if custom_action is None:
        top_p = config["ai_top_p"]
    elif custom_action in config["creative_custom_actions"]:
        top_p = config["custom_action_creative_top_p"]
    else:
        top_p = config["custom_action_top_p"]

    current_turn = current_story.get("current_turn") if current_story is not None else None

    # Send msg to gpt, retries if there's a problem.
    response_message = send_open_ai_gpt_message(max_response_length, messages, model_name, backup_model_name, timeout, no_gen, temperature, top_p, presence_frequency, frequency_penalty, custom_action = custom_action, json_mode = is_json_mode, is_chat_dnd = is_chat_dnd, current_turn=current_turn)

    is_unrelated = False
    suggestion_refused = False
    start_battle_assistant = False

    # Transform back to normal format when using json_mode in dnd chat (no jsonmode in any game won or over mode, so can't just use 'is_chat_dnd')
    if is_user_convo_chat_dnd:
        chat_obj = extract_json_from_response("chat_dnd_msg", response_message['content'])

        if chat_obj is None:
            print_log(f"WARNING: chat_dnd_msg object not found in response. Response: {response_message['content']}", True)
            return -1, convo_obj_filepath, None

        # Shouldn't happen (is_user_convo_chat_dnd = false when game is over), but just in case
        is_game_won_or_lost = current_story.get("is_game_won", False) or current_story.get("is_game_lost", False)

        user_or_viewer = "viewer" if has_setup_zero else "user"

        user_emotion = chat_obj[f"emotion_{user_or_viewer}_message"].strip(" ,.!?*#") # Remove unecessary characters from emotion (added * around the emotion once, so need to remove it)
        answer = chat_obj[f"answer_to_{user_or_viewer}"]

        # Determine if answer is unrelated or suggestion refused
            # Only when game is not already over, otherwise it's not relevant
        is_unrelated = chat_obj["is_unrelated_to_game_or_character"] and not is_game_won_or_lost
        suggestion_refused = chat_obj["suggestion_is_rejected"] and not is_game_won_or_lost

        if is_unrelated:
            print_log("WARNING: Chat's answer is unrelated to game or character.", True)

        if suggestion_refused:
            print_log("WARNING: Chat's sugestion was refused.", True)

        if user_emotion is not None:
            user_emotion_prefix = f"#{user_emotion}#\n"
        else:
            user_emotion_prefix = ""
            print_log("WARNING: User emotion not found in chat_dnd_msg", True)

        response_message['content'] = user_emotion_prefix + answer + (" $unrelated$" if is_unrelated else "") + (" $refused$" if suggestion_refused else "")
    elif is_normal_game_turn_dnd:
        game_obj = extract_json_from_response("game_dnd_msg", response_message['content'])

        if game_obj is None:
            print_log(f"WARNING: game_dnd_msg object not found in response. Response: {response_message['content']}", True)
            return -1, convo_obj_filepath, None
        
        start_battle_assistant = validate_bool(game_obj.get("attempt_to_start_battle", False)) # Field won't be included when already in battle, False in that case
        response_message['content'] = game_obj["answer"]

    response_message['content'] = response_message['content'].strip("\n ") 
    response_content = response_message['content']

    # Canned response when GPT refuses the request
    if response_content == "" or response_content == "I'm sorry, but I can't fulfill this request.":
        type_name = "empty" if response_content == "" else "refused"
        error_msg = f"ERROR: GPT {type_name} the request. Message: {response_content}"
        create_error_log("send_message_" + type_name, error_msg, response_content, username, is_game)

        return -1, convo_obj_filepath, None

    # Only send to moderation text that will actually be shown / spoken to users (no hashtags or asterisks)
    visible_content_only = response_content
    if custom_action is None and not is_game:
        _, visible_content_only = process_user_msg_emotion(visible_content_only)
        _, visible_content_only = process_unrelated(visible_content_only) # Remove $unrelated$ from the message
        _, visible_content_only = process_refused(visible_content_only) # Remove $refused$ from the message

    visible_content_only = remove_all_asterisks(visible_content_only).strip()

    # Check if the message is flagged for moderation (except for some custom message)
    if custom_action is None or custom_action in ["update_inventory", "update_location", "update_important_characters", "is_quest_given"]:
        messages_to_moderate = [visible_content_only]

        if moderate_user_msg: # Don't moderate the prompt (usr_msg) unless specified (should always be moderated wherever the prompt was generated from)
            messages_to_moderate.insert(0, new_user_msg)

        is_flagged = is_moderation_flagged(messages_to_moderate, username, "send_message", is_game, is_chat_dnd=is_chat_dnd, custom_action=custom_action)
        if is_flagged:
            print("Message flagged for moderation")
            return -1, convo_obj_filepath, None

    # Return the result of all custom actions
    if not custom_action is None:
        if custom_action == "get_emotions":
            text_segment_objs = set_text_segments_emotions(response_content, msg_segments)
            return response_content, convo_obj_filepath, text_segment_objs
        elif custom_action == "choose_music":
            set_music(response_content, convo_obj_filepath, current_game)
        elif custom_action == "is_main_quest_completed":
            validate_is_main_quest_completed(response_content)
        elif custom_action == "is_quest_completed":
            validate_is_quest_completed(response_content)
        elif custom_action == "is_quest_given":
            validate_quest_given(response_content)
        elif custom_action == "update_inventory":
            update_inventory(response_content)
        elif custom_action == "update_location":
            update_location(response_content)
        elif custom_action == "update_location_category":
            update_location_category(response_content, setup_dnd)
        elif custom_action == "update_important_characters":
            update_important_characters(response_content, current_story)
        elif custom_action == "update_rest":
            update_rest(response_content, setup_dnd)
        elif custom_action == "get_emotions_mc":
            return get_emotions_mc(response_content), convo_obj_filepath, None
        elif custom_action == "get_emotions_opponents":
            return get_emotions_combatants(response_content, True), convo_obj_filepath, None
        elif custom_action == "get_emotions_allies":
            return get_emotions_combatants(response_content, False), convo_obj_filepath, None
        elif custom_action in roll_actions:
            return get_roll_from_action(custom_action, response_content, convo_obj_filepath, current_story, setup_dnd, config_dnd)
        # Return whatever was generated by the ai (ex: game over, events, etc.)
        return response_content, convo_obj_filepath, None

    # When chatting with chat during ai dungeon game, add the history to special file instead of adding it to ai dungeon main history.
    if state_switch == "dnd":
        history_file = dnd_with_chat_history_file # Important, need to overwrite history_file so that it saves the chat history in the correct file (not the dnd story one)
        messages_history = get_messages_history(history_file)

    # SEND CONVO TO TTS
    new_msg_content = response_content

    # Write the user msg emotion (located at the start of the ai answer) to file in chat mode and remove it from the ai answer
    if not is_game:
        user_msg_emotion, new_msg_content = process_user_msg_emotion(new_msg_content)

        # Skip the answer to the chat msg if it's accepted
        skip_accepted_chat_answers = config["skip_accepted_chat_answers"]
        if not suggestion_refused and not is_unrelated and skip_accepted_chat_answers:
            new_msg_content = None
        else:
            _, new_msg_content = process_unrelated(new_msg_content) # Remove $unrelated$ from the message
            _, new_msg_content = process_refused(new_msg_content) # Remove $refused$ from the message

        if user_msg_emotion is None and new_user_msg != "": # Don't show warning if no user msg, normal that no emotions was found
            print_log("WARNING: User msg emotion not found!", True)
    else:
        user_msg_emotion = ""

    if user_msg_emotion:
        print_special_text(f"\n#bold#Reaction:#bold# {user_msg_emotion}")

    # Write response in console
    if current_game == "dnd":
        print_special_text("\n#bold#Your character:#bold#")
        print(new_msg_content)
    else:
        print_special_text(f"\n#bold#{response_message['role'].capitalize()}:#bold#")
        print(f"{Fore.LIGHTMAGENTA_EX}{new_msg_content}{Style.RESET_ALL}") 

    # Don't add user_msg to ai dungeon, we want to add the following dnd_msg, not the preceding one (also, don't set to "", or else won't be processed correctly)
    convo_user_msg = new_user_msg if not is_game or is_game_won_or_lost_msg else None

    # Don't decide yet whether there will be a next convo or not (depends on whether there wll be a roll msg after or not), unless we already know it's going to be False
    generate_next_convo = generate_next_convo_arg if not is_game or generate_next_convo_arg == False else None 
    
    # Extra convo info
    show_info_game_won_or_lost = is_game_won_or_lost_msg and is_chat_dnd # Decide whether to show the info about the game being won or lost
    win_count = config_dnd["win_count"] if config_dnd is not None else 0
    lose_count = config_dnd["lose_count"] if config_dnd is not None else 0
    main_quests_text = get_main_quests_sentence(current_story) if current_story is not None else ""

    convo_obj = create_convo_obj(new_msg_content, convo_user_msg, username if username is not None else "system", current_game, generate_next_convo, \
                    current_story, win_count, lose_count, is_dnd_chat = state_switch == "dnd", main_quests_text = main_quests_text, \
                    show_info_game_won_or_lost = show_info_game_won_or_lost, convo_type="main")
    
    # User emotion is already decided, so add it to the first segment
    narrator_segments = convo_obj["narrator_segments"]
    if user_msg_emotion and narrator_segments is not None and len(narrator_segments) > 0:
        narrator_segments[0]["expressions"] = [create_expression_obj("main", "all", user_msg_emotion)]

    # Will wait for the display_sections + emotions to be added before continuing in TTS if roll_info = None (default = (None, None, None))
    if current_game == "dnd" and not is_game_won_or_lost_msg:
        convo_obj["display_sections"] = None 

    write_json(convo_obj_filepath, convo_obj)

    if current_game == "dnd" and add_music and config.get("add_music", False):
        # Add music async to current convo file once the assistant msg has been sent
        create_thread_custom_action("choose_music", username, current_game, convo_obj_filepath, messages_history, override_current_story=current_story)

    if current_game == "dnd" and not is_game_won_or_lost_msg: # Just add the message to history when initial game won or lost.
        # AI Answer
        new_msg_content = remove_parentheses(response_content) # Remove speaking to chat from past messages

        # Add ai answer to history
        new_msg = {
            "role": "assistant", 
            "content" : new_msg_content 
        }
        messages_history.append(new_msg)

        # Remove asterisks + parenthesis when sending to ai dungeon (manually for now) (keep prefix for now)
            # Need to remove parenthesis, or else will be added by dnd
        ai_new_msg = remove_all_asterisks(remove_parentheses(new_msg_content))
        print_log(f"FOR AI DUNGEON: {ai_new_msg}") 

        run_battle_turn(ai_new_msg, username, current_game, convo_obj_filepath, messages_history, current_story, setup_dnd, config, config_dnd, generate_next_convo_arg, has_valid_prev_chat_msg, start_battle_assistant)

        # If the roll_info is still None (most likely due to an error), set it to it's default value (to not block the tts)
        convo_obj = read_json(convo_obj_filepath)
        if convo_obj["display_sections"] is None:
            convo_obj["display_sections"] = [] # [] == don't wait for sections anymore
            write_json(convo_obj_filepath, convo_obj)

    # Skip all the rolls when initial game won or lost msg
    elif current_game == "dnd" and is_game_won_or_lost_msg:
        messages_history.append(response_message)

        # Add emotions for the initial game won or lost msg
        create_emotions_thread(username, current_game, convo_obj_filepath, messages_history, current_story, config)

    # Chat mode
    else:
        #Save the user prompt message (without prefix) to history
            # Order = user_msg => ai_answer
        if not auto_mode and new_message is not None:
            messages_history.append(new_message)
            
        messages_history.append(response_message)

        # Add music async to current convo file once it's full text has been set.
        if add_music:
            create_thread_custom_action("choose_music", username, current_game, convo_obj_filepath, messages_history, override_current_story=current_story)

    if custom_action is None:
        no_gen += 1

    # Save new history
    set_messages_history(history_file, messages_history)

    # Save the current story
    set_current_story(current_story)

    print_log("Main processing done")

    return response_message, convo_obj_filepath, None

def set_is_stream(is_stream_arg):
    global is_stream
    is_stream = is_stream_arg

def set_next_message_direct(msg_text: str):
    global next_msg_direct_mode
    next_msg_direct_mode = msg_text

def get_next_message_direct() -> Tuple[Any, Any, Any]:
    global next_msg_direct_mode
    next_msg_text = next_msg_direct_mode
    next_msg_direct_mode = None

    if next_msg_text is None:
        #print("ERROR: No new message")
        return None, None, None
    
    config = get_ai_config()
    username = config.get("username")

    write_to_show_text(username + ": " + next_msg_text if username else next_msg_text, is_next_msg = True, lock = True, is_text_only = True)
    #clear_next_messages()

    return next_msg_text, username, None

# Wait until all threads are processed until continuing
def create_thread_send_message(username, args):
    # Create a ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit tasks one by one
        futures = [executor.submit(send_message, '', username, **arg) for arg in args]

        results = [] 
        # Collect results in the order they were submitted (so the order is preserved)
            # Will still be done in parallel
        for future in futures:
            try:
                # This blocks until the future is completed
                result = future.result()
                results.append(result)
            except Exception as e:
                # Append None or a custom error message to results if there's an exception
                print(f"Error occurred: {traceback.format_exc()}")
                results.append(None)

        return results  # Return the list of results

def create_thread_custom_action(custom_action, username, current_game, convo_obj_filepath = None, override_messages_history = None, override_current_story = None):
    args = [{'current_game': current_game, 'custom_action': custom_action, 'filename': convo_obj_filepath, 'override_messages_history': override_messages_history, 'override_current_story': override_current_story}]
    create_thread_send_message(username, args)

def write_and_send_chat_msg(generate_next_convo=True, state_switch = None, switched_scene=False):
    start_send_message_timestamp = time.time()
    get_user_message = True
    has_sent_msg = False
    convo_obj_filepath = None

    is_game = state_switch == "dnd"

    setup_dnd = read_json(f'{ai_config_path}dnd_setup.json')
    config_dnd = read_json(f'{ai_config_path}dnd_config.json')

    max_unrelated_or_refused_nb_retry = config_dnd["max_unrelated_or_refused_nb_retry"] if config_dnd is not None else None
    
    while True:
        # Only get new message if it's the first time or the message was flagged (not on retry)
        if get_user_message == True:
            next_prompt, username, custom_prefix = get_next_message_direct() if not is_stream else get_next_message_stream()
            # If no new messages (has_sent_msg = False)
            if next_prompt is None:
                return False 
            elif next_prompt == -1: # Error
                return -1 
            elif "#continue" in next_prompt: # Continue without user msg
                return -2

            global no_gen
            print_log(f"Answer to user: {username if username is not None else 'System'}")
            print_log(f"{no_gen}:{next_prompt}")

        get_user_message = True

        # Add music if not playing ai dungeon, and only every 4 messages (unless we just switched scene)
        add_music = not is_game and ((no_gen-1) % 4 == 0 or switched_scene)

        # try:
        response, convo_obj_filepath, _  = send_message(next_prompt, username, start_send_message_timestamp=start_send_message_timestamp, custom_prefix=custom_prefix, generate_next_convo_arg=generate_next_convo, state_switch=state_switch, add_music=add_music) #No prefix + no user

        current_story = get_current_story() if is_game else None
        unrelated_or_refused_retries = current_story.get("unrelated_or_refused_retries", 0) if is_game and current_story is not None else 0

        if response != -1 and is_game and max_unrelated_or_refused_nb_retry is not None and unrelated_or_refused_retries <= max_unrelated_or_refused_nb_retry:
            # if content contains $unrelated$ or $refused$
            is_unrelated = response["content"].find("$unrelated$") != -1 
            is_refused = response["content"].find("$refused$") != -1
            roll_info_text = ""
            suffix = ""
            retry_limit_reached = unrelated_or_refused_retries == max_unrelated_or_refused_nb_retry # Only show the warning when retry limit is reached, exit loop after

            if is_unrelated:
                roll_info_text = setup_dnd["warning_unrelated"] if not retry_limit_reached else setup_dnd["warning_unrelated_limit_reached"] # Centered text
                print_special_text(roll_info_text) # color already in the text
                suffix = "_unrelated"
            elif is_refused:
                roll_info_text = setup_dnd["warning_refused"] if not retry_limit_reached else setup_dnd["warning_refused_limit_reached"]
                print_special_text(roll_info_text) # color already in the text
                suffix = "_refused"

            # Keep looking for a new user message if the message was flagged as being unrelated or refused by the AI
            if is_unrelated or is_refused:
                sections = [create_section_obj(roll_info_text, section_name="chat_dnd_warning")]
                # Write the roll info in the convo file
                convo_obj = create_convo_obj("", "", "system", "dnd", False, current_story, config_dnd["win_count"], config_dnd["lose_count"], main_quests_text=get_main_quests_sentence(current_story), display_sections=sections, command="show_roll_info", convo_type="eval")

                # Need to add _rest to the convo obj path, because when called from the eval loop, it has the same name as the original convo obj (not the case when testing the action in a manual test call)
                    # Would overwrite the original convo obj without this change
                filepath_without_ext, ext = os.path.splitext(convo_obj_filepath)
                write_json(filepath_without_ext + suffix + ext, convo_obj)

                # Continue to loop if the retry limit is not reached, only show the warning and exit otherwise
                if not retry_limit_reached:
                    current_story["unrelated_or_refused_retries"] = unrelated_or_refused_retries + 1 # Don't do += 1, in case it's not defined yet
                    set_current_story(current_story)

                    unlock_next_msg() # send message failed, unlock next msg

                    continue

        # Message sent: Exit loop if not flagged for moderation (result == -1), get new user message on flag
        if response != -1:
            has_sent_msg = True
            if is_stream:
                del_all_expired_messages() # Delete all expired messages (all past msg if in game) after the final next msg is chosen

            break
            #return True #Exit loop

        unlock_next_msg() # send message failed, unlock next msg

    return has_sent_msg

def create_eval_convo(setup_dnd, config_dnd):
    global location_eval, location_category_eval, important_characters_eval, main_quests_completed_eval, quests_completed_eval, quests_added_eval, inventory_eval, update_rest_eval, battle_end_eval

    # Store inventoiry eval in story, so it can be added from both normal eval and use item
    current_story = get_current_story() 
    evals_to_show = []

    if update_rest_eval is not None:
        is_short_rest = update_rest_eval["is_short_rest"]
        is_long_rest = update_rest_eval["is_long_rest"]

        # Will update the story with rest changes + return the eval info
        eval_info = update_story_rest_changes(is_long_rest, is_short_rest, current_story, setup_dnd)
        evals_to_show.append(eval_info)

        update_rest_eval = None

    # Add eval location changes
    if location_eval is not None:
        new_main_location = location_eval["main_location"]
        if new_main_location is not None:
            evals_to_show.append("New main location: " + new_main_location)
            current_story["main_location"] = new_main_location

        new_sub_location = location_eval["sub_location"]
        if new_sub_location is not None:
            evals_to_show.append("New sub location: " + new_sub_location)
            current_story["sub_location"] = new_sub_location
        elif new_main_location is not None:
            current_story["sub_location"] = "" # Reset sub location when the main location changes

        location_eval = None

    # Update location category in story (don't need to show in eval, since it's only use to choose the current img)
    if location_category_eval is not None:
        new_location_category = location_category_eval["location_category"]

        if new_location_category is not None:
            current_story["location_category"] = new_location_category
            current_story["location_category_is_interior"] = location_category_eval["is_interior"]

        location_category_eval = None

    # Add eval important characters changes
    if important_characters_eval is not None:
        # Show eval only if the characters themselves have changed (ignore parenthesis changed)
        side_characters_eval_only = important_characters_eval["side_characters_eval_only"]
        if side_characters_eval_only is not None and len(side_characters_eval_only) > 0: # Don't show if no side characters, not really important
            evals_to_show.append("Side characters: " + combine_array_as_sentence(side_characters_eval_only))

        # Update side characters even if only the parenthesis have changed
        side_characters = important_characters_eval["side_characters"]
        if side_characters is not None:
            current_story["side_characters"] = side_characters

        important_characters_eval = None

    if quests_added_eval is not None and len(quests_added_eval) > 0:
        evals_to_show.append("Quests added: " + join_quests_semicolon(quests_added_eval))
        current_story["quests"] = current_story["quests"] + quests_added_eval
        quests_added_eval = None

    # Main quests completed
    if main_quests_completed_eval is not None:
        main_quests_completed = main_quests_completed_eval
        if len(main_quests_completed) > 0:
            quest_state = "fully" if len(current_story["main_quests"]) == 0 else "partially"
            evals_to_show.append(f"Main quests {quest_state} completed: #green#" + join_quests_semicolon(main_quests_completed) + "#green#")

            # Complete main quests in the current story + end the game if all main quests are completed
            update_story_main_quest_completed(main_quests_completed, current_story)

        main_quests_completed_eval = None

    # Quests completed
    if quests_completed_eval is not None:
        quests_completed = quests_completed_eval

        if len(quests_completed) > 0:
            evals_to_show.append("Quests completed: #green#" + join_quests_semicolon(quests_completed) + "#green#")

            # Add completed quests to the current story
            current_story["completed_quests"] += quests_completed
            current_story["quests"] = [quest for quest in current_story["quests"] if quest not in quests_completed]

        quests_completed_eval = None

    # Add eval inventory changes
        # Store in current story, to take into account the case where the inventory was updated by the use item roll before the eval
    if inventory_eval is not None:
        added_to_inventory = inventory_eval["added"]
        if len(added_to_inventory) > 0:
            evals_to_show.append("Added to inventory: #green#" + combine_array_as_sentence(added_to_inventory) + "#green#")
        
        removed_from_inventory = inventory_eval["removed"]
        if len(removed_from_inventory) > 0:
            evals_to_show.append("Removed from inventory: #red#" + combine_array_as_sentence(removed_from_inventory) + "#red#")

        current_story["inventory"] = inventory_eval["inventory"]
        current_story["currency"] = inventory_eval["currency"]

        inventory_eval = None

    # Enemy skipped their turn because they were surprised
        # Only skip enemy turn once (either the first turn if they acted first, or the turn after the player if they acted second)
    battle_info = current_story.get("battle_info")
    if battle_info is not None and battle_info.get("enemy_is_surprised", False):
        enemy_text = "enemies were" if len(battle_info["opponents"]) > 1 else "enemy was"
        evals_to_show.append(f"The {enemy_text} taken by surprise and skipped their turn.")

    # Create eval convo if there are any evals to show, or if battle just ended (otherwise battle won't end until next turn)
    if len(evals_to_show) > 0 or battle_end_eval is not None:
        battle_end_eval = None
        roll_info_text = ""
        
        if len(evals_to_show) > 0:
            print_special_text("\n#bold#nInfo:#bold#")
            print("\n".join(evals_to_show)) # print evals
            roll_info_text = "#message_separator#".join(evals_to_show)
            
        sections = [create_section_obj(roll_info_text, section_name="eval")]

        # Write the roll info in the convo file
        convo_obj = create_convo_obj("", "", "system", "dnd", False, current_story, config_dnd["win_count"], config_dnd["lose_count"], main_quests_text=get_main_quests_sentence(current_story), display_sections=sections, command="show_roll_info", convo_type="eval") 

        global no_gen
        no_gen += 1 # Increase no by 1, since it should be it's own msg (don't use existing convo filepath, otherwise will be in front of the 'roll_response' convo obj in the list (can cause issue when replaying convos in tts)
        convo_obj_filepath, _ = get_new_convo_filename(True, False, current_story, custom_action="eval") 
        write_json(convo_obj_filepath, convo_obj) 

    # Print the current limited resources
    # print_limited_resources(current_story)

    # Save any changes to the current story
        # Don't do it in the func themselves to avoid race conditions
    set_current_story(current_story)

def save_story_debug_folder(current_story, is_final = False):
    debug_story_folder = f"{root_path}current_story_debug"

    current_turn = current_story["current_turn"]
    char_name = current_story["char_name"].replace("'", "").replace(" ", "_")

    # Remove anything in parenthesis from the name
    char_name = re.sub(r'\([^)]*\)', '', char_name).strip()

    # Save the current story in the debug folder
    folder_name = f'{datetime.now().strftime("%Y%m%d%H%M%S")}_{current_story["id"]}_{char_name}_{current_turn}' 

    if is_final:
        folder_name += "_final"

    # create a folder with the current turn as the name
    if not os.path.exists(f"{debug_story_folder}/{folder_name}"):
        os.makedirs(f"{debug_story_folder}/{folder_name}")

    # Copy all files in the current_story folder to the debug folder
    for file_name in os.listdir(current_story_path):
        original_file_path = os.path.join(current_story_path, file_name)
        new_file_path = os.path.join(debug_story_folder, folder_name, file_name)
        shutil.copy2(original_file_path, new_file_path)

def prepare_game_won_or_lost(current_story, is_game_won, is_game_lost):
    # In character conclusion
    send_message("", "system", current_game="dnd", start_send_message_timestamp=time.time(), generate_next_convo_arg=False, force_gpt4 = True, add_music=True) 

    # ooc conclusion
    send_message("", "system", start_send_message_timestamp=time.time(), state_switch="dnd") # Generate next msg at this point

    # Update the win lost count
    config_dnd = read_json(f'{ai_config_path}dnd_config.json')
    config_dnd["win_count"] += 1 if is_game_won else 0
    config_dnd["lose_count"] += 1 if is_game_lost else 0
    write_json(f"{ai_config_path}dnd_config.json", config_dnd) 

    current_story["current_turn"] += 1
    current_story["game_over_time"] = time.time()
    set_current_story(current_story)

    # Save the final story state in the debug folder
    save_story_debug_folder(current_story, True)

def story_first_turn(current_game, username, current_story, config, config_dnd):
    print_story_properties(current_story)
    
    story_init_text = current_story["char_description"] #+ "#doublenewline#" + current_story["scenario"]
    print(f"\n{story_init_text}\n")

    # Create the history for the init convo
    messages_history_init = get_messages_history(dnd_history_file)
    messages_history_init.append(format_msg_oai("user", "system: " + story_init_text))

    # Create init convo obj
    convo_obj_init = create_convo_obj("", story_init_text, "system", current_game, True, current_story, win_count = config_dnd["win_count"] if config_dnd is not None else 0, \
                                    lose_count = config_dnd["lose_count"] if config_dnd is not None else 0, main_quests_text = get_main_quests_sentence(current_story), convo_type="init")
    
    # Create scenario convo obj (clone init)
    convo_obj_scenario = copy.deepcopy(convo_obj_init)
    story_scenario_text = current_story["scenario"]
    print(f"{story_scenario_text}")

    convo_obj_scenario["user_msg"] = story_scenario_text
    convo_obj_scenario["convo_type"] = "scenario"
    convo_obj_scenario["narrator_segments"] = create_text_segment_objs(story_scenario_text) # Overwrite the segments created in nit

    # Get the filepaths for convos (init and scenario convos both have the same filename, except that init has _init at the end)
    convo_obj_filepath_init, _ = get_new_convo_filename(True, False, current_story, custom_action="init")

    write_json(convo_obj_filepath_init, convo_obj_init)

    # Set emotions for intro msg
    create_emotions_thread(username, current_game, convo_obj_filepath_init, messages_history_init, current_story, config, extra_info = "skip_memory")

    # global last_filename
    # last_filename = convo_obj_filename

    # Clone init history and add scenario msg
    messages_history_story_both = copy.deepcopy(messages_history_init)
    messages_history_story_both.append(format_msg_oai("user", "system: " + story_scenario_text))

    # Write convo obj scenario
    convo_obj_filepath_scenario, _ = get_new_convo_filename(True, False, current_story, custom_action="scenario")

    write_json(convo_obj_filepath_scenario, convo_obj_scenario)

    # Set emotions for scenario msg
    create_emotions_thread(username, current_game, convo_obj_filepath_scenario, messages_history_story_both, current_story, config)
    
    # Finally, add the scenario to the final history (start from scratch, final history has no init msg)
    messages_history = get_messages_history(dnd_history_file)
    messages_history.append(format_msg_oai("user", "system: " + story_scenario_text)) # Only place the scenario in the history (that's what's in dnd server)
    set_messages_history(dnd_history_file, messages_history)

    current_story["current_turn"] = 1
    set_current_story(current_story)

    # Choose the starting music (do it for first convo msg so it plays at the start)
        # Will use both history even if on second convo, because that's what was saved on the history file abpve
    if config.get("add_music", False):
        send_message("", username, current_game=current_game, custom_action="choose_music", filename = convo_obj_filepath_init)

    update_char_sheet_doc(current_story)

def is_time_up_speak_viewers(current_story, config_dnd):
    return (current_story["is_game_won"] or current_story["is_game_lost"]) and current_story.get("game_over_time") is not None and time.time() - current_story.get("game_over_time", 0) >= config_dnd["speak_to_chat_after_gameover_time"]

def process_test_rolls(custom_action, roll_results, current_story, setup_dnd):
    roll_text = section_obj = None
    combatant_sheets = get_combatant_sheets()

    if custom_action == "get_roll_attack":
        roll_text, section_obj, _, _, _ = process_roll_attack(roll_results, current_story, setup_dnd, combatant_sheets)
    elif custom_action == "cast_spell":
        roll_text, section_obj, _, _ = process_cast_spell(roll_results, True, current_story, setup_dnd, combatant_sheets)
    elif custom_action in ["get_roll_skill", "get_roll_skill_special_ability"]:
        is_using_special_ability = custom_action == "get_roll_skill_special_ability"
        roll_text, section_obj = process_roll_skill(roll_results, current_story, setup_dnd, is_using_special_ability)
    elif custom_action == "use_item":
        roll_text, section_obj, _, _, _  = process_use_item(roll_results, current_story, setup_dnd, combatant_sheets)
    elif custom_action == "get_roll_saving_throw":
        roll_text, section_obj, _ = process_roll_saving_throw(roll_results, current_story, setup_dnd, combatant_sheets)
    else: 
        return # No custom action processing

    print_log(f"Roll text: {roll_text}, Display section: {section_obj}")

def get_custom_action_extra_info(custom_action, battle_info, specific_extra_info = None):
    extra_info = specific_extra_info

    if extra_info is not None:
        return extra_info

    # Add group info for some prompts (includes any custom action that starts with 'create_combatant_sheet' (ex : create_combatant_sheet_stats))
    if custom_action == "choose_combatant_action" or "create_combatant_sheet" in custom_action:
        opponent = battle_info["opponents"][0] if battle_info is not None and len(battle_info["opponents"]) > 0 else None
        if opponent is None:
            print(f"\nERROR: No opponent in battle info for {custom_action}\n")
        
        if custom_action == "choose_combatant_action":
            extra_info = (opponent, True)
        else:
            extra_info = get_group_from_combatant(opponent)

    return extra_info

def write_and_send_message_dnd(custom_action_test = None, allow_continue_without_user_msg = False, switched_scene=False, specific_extra_info=None, process_tests = False):
    username = "system"
    current_game = "dnd"

    config = get_ai_config()
    update_print_log_settings(config)

    setup_dnd = read_json(f'{ai_config_path}dnd_setup.json')
    config_dnd = read_json(f'{ai_config_path}dnd_config.json')

    # Create a story if it doesn't already exist
    if not os.path.exists(current_story_path + "current_story.json"):
        create_story()

    current_story = get_current_story()
    current_turn = current_story["current_turn"] # Always read current turn from file, in case I want to change it manually

    allow_chat_msg_dnd = config_dnd["allow_chat_msg_dnd"]
    check_chat_max_every_x_turns = config_dnd["check_chat_max_every_x_turns"]
    prev_messages_to_send = None

    # Play the init narrator msg on the first turn or after game over + enough time has elapsed.
    if current_turn == 0:
        story_first_turn(current_game, username, current_story, config, config_dnd)
        return True # Treated the same way as any other msg (bark wait for response)
    
    # Game won when all parts of the main quest are completed
        # Just in case the main quest is done and the game was not set to won correctly
    if len(current_story["main_quests"]) == 0 and not current_story["is_game_lost"]:
        current_story["is_game_won"] = True
        set_current_story(current_story)

    is_game_won_or_lost = current_story["is_game_won"] or current_story["is_game_lost"]
    is_game_won_or_lost_speak_viewers = is_game_won_or_lost and current_story.get("game_over_time") is not None
    is_time_up_game_won_or_lost_speak_viewers = is_time_up_speak_viewers(current_story, config_dnd)

    # Check chat msg if allowed and not turn 0 (nothing to comment on) and haven't actually sent a chat msg since x turns
    if allow_chat_msg_dnd and current_turn >= 1 and ((current_turn - 1) % check_chat_max_every_x_turns == 0 or switched_scene or is_game_won_or_lost):
        generate_next_convo = is_game_won_or_lost_speak_viewers and not is_time_up_game_won_or_lost_speak_viewers # Only generate next convo in chat mode when game won or lost and game over started
        has_sent_msg = write_and_send_chat_msg(generate_next_convo, "dnd") # Don't generate the next convo file after receiving an answer from bark (wait until dnd to do that)
        
        # Received error, exiting
        if has_sent_msg == -1:
            return -1 # Exit loop

        if has_sent_msg == True:
            prev_messages_to_send = "chat" # Send previous chat messages to system

            # During game over, only talk to chat (no dnd messages)
            if generate_next_convo:
                return True
        elif has_sent_msg == -2: # Continue without chat msg, even in dnd mode
            pass
        elif (config_dnd["dnd_input_mode"] and not allow_continue_without_user_msg):
            return False # Don't send anything to dnd if no chat msg and input mode is enabled
        
    if is_game_won_or_lost and custom_action_test is None:
        # Prepare the game won or lost in it's own convo msg
        if current_story.get("game_over_time") is None:
            prepare_game_won_or_lost(current_story, current_story["is_game_won"], current_story["is_game_lost"])
            return True
        # If game won or lost and enough time has elapsed, create a new story
        elif is_time_up_game_won_or_lost_speak_viewers:
            create_story()
            current_story = get_current_story()

            story_first_turn(current_game, username, current_story, config, config_dnd)
            return True

    run_eval = add_music = current_turn >= 1 # Turn 0 = intro
    if add_music:
        print_log("Will add music and background this turn")

    # Add previous chat msg to system if has_sent_msg=True
    if custom_action_test is None:
        response_content, convo_obj_filepath, _ = send_message("", username, start_send_message_timestamp=time.time(), current_game=current_game, state_switch=prev_messages_to_send, add_music=add_music, extra_info=specific_extra_info)
        # If moderation flag or no response
        if response_content == -1 or response_content is None: 
            return -1
    else:
        response_content = convo_obj_filepath = None

    current_story = get_current_story() 
    is_game_won_or_lost = current_story["is_game_lost"] or current_story["is_game_won"] #  Change music if game over

    if (run_eval and not is_game_won_or_lost) and (custom_action_test is None or custom_action_test == "run_eval_convo"):
        print_log("Starting eval:")
        
        custom_actions = ["is_quest_given", "update_inventory", "update_important_characters", "update_rest", "update_location", "is_main_quest_completed"] 

        if len(current_story["quests"]) > 0:
            custom_actions.insert(1, "is_quest_completed")

        # Reset eval global vars, just in case
        global location_eval, location_category_eval, important_characters_eval, main_quests_completed_eval, quests_completed_eval, quests_added_eval, update_rest_eval
        location_eval = location_category_eval = important_characters_eval = main_quests_completed_eval = quests_completed_eval = quests_added_eval = update_rest_eval = None # Don't reset battle_end_eval, it's set before the eval func

        # CUSTOM ACTIONS
        args = []
        battle_info = current_story.get("battle_info")

        for custom_action in custom_actions:
            extra_info = get_custom_action_extra_info(custom_action, battle_info)

            args.append({'current_game': current_game, 'custom_action': custom_action, 'filename': convo_obj_filepath, 'override_current_story': current_story, 'extra_info': extra_info})

        create_thread_send_message(username, args)

        step_2_custom_actions = []

        # LOCATION CATEGORY
        # Update location category once the above is done 
            # No easy way to do it directly after update_location while keeping everything parallel, should be fine since it's at the very end of the turn
        if location_eval is not None:
            step_2_custom_actions.append("update_location_category")

        # Do a second pass with the custom actions that need to be done after the first pass
        if (len(step_2_custom_actions) > 0): # and custom_action_test is None:            
            create_thread_send_message(username, args = [{'current_game': current_game, 'custom_action': custom_action, 'filename': convo_obj_filepath} for custom_action in step_2_custom_actions])

        create_eval_convo(setup_dnd, config_dnd)
        
    # Run tests
    elif custom_action_test is not None and not custom_action_test.startswith("run_"):
        custom_action = custom_action_test

        battle_info = current_story.get("battle_info")
        extra_info = get_custom_action_extra_info(custom_action, battle_info, specific_extra_info)

        _, _, roll_results = send_message("", username, current_game=current_game, custom_action=custom_action, override_current_story=current_story, extra_info=extra_info)

        if process_tests and roll_results is not None:
            process_test_rolls(custom_action, roll_results, current_story, setup_dnd)
        
    elif custom_action_test is not None and custom_action_test.startswith("run_"):
        current_message_history = get_messages_history(dnd_history_file)
        current_battle_info = current_story.get("battle_info")
        combatant_sheets = get_combatant_sheets()

        # Update the battle info (will assume that the ai or server detected a start battle if battle info doesnt exist)
        if custom_action_test == "run_update_battle_info":
            update_battle_info(current_story, username, current_game, current_message_history, True)
        
        elif custom_action_test == "run_eval_convo":
            create_eval_convo(setup_dnd, config_dnd)

        # Run all the opponent sheets for all the opponent groups in battle info
        elif custom_action_test == "run_create_combatant_sheets":
            if current_battle_info is not None:
                create_combatant_sheets(username, current_game, current_message_history, current_story, current_battle_info["opponents"])
            else:
                print("ERROR: No battle info found")

        # Run the process enemy turn for all the active opponents (default action only: attacking)
        elif custom_action_test == "run_process_enemy_turn":
            if current_battle_info is not None:
                active_opponents, _ = get_incapacitated_combatants(current_battle_info, True)
                opponent_containers = [{"combatant": opponent} for opponent in active_opponents]
                for container in opponent_containers:
                    container["action"] = Combatant_Action_Object("unknown", None, "attack", "sword", "slashing", False, 2, "")

                process_combatant_turn(current_story, setup_dnd, combatant_sheets, opponent_containers, True)
            else:
                print("ERROR: No battle info found")

        # Choose the actions for all the opponents or allies in the battle, then run process enemy turn
        elif custom_action_test in ["run_choose_opponents_actions", "run_choose_allies_actions"]:
            if current_battle_info is not None:
                is_opponent = custom_action_test == "run_choose_opponents_actions"
                combatant_containers = choose_combatants_actions(username, current_game, current_story, setup_dnd, combatant_sheets, current_battle_info, current_message_history, is_opponent)
                process_combatant_turn(current_story, setup_dnd, combatant_sheets, combatant_containers, is_opponent)
            else:
                print("ERROR: No battle info found")

        # Run a battle turn, starting from the last AI msg
            # Will remove it and everything after from the history
        elif custom_action_test.startswith("run_battle_turn"):
            start_battle_assistant = custom_action_test == "run_battle_turn_start_battle"

            last_ai_msg_content = None
            last_ai_msg_obj = None
            
            # Get the last AI msg, removing it and everything after it from the history
            while len(current_message_history) > 0:
                last_ai_msg_obj = current_message_history.pop()
                if last_ai_msg_obj["role"] == "assistant":
                    last_ai_msg_content = last_ai_msg_obj["content"]
                    break

            # Add back the last ai msg to the history
            if last_ai_msg_obj is not None:
                current_message_history.append(last_ai_msg_obj)
            
            if convo_obj_filepath is None:
                convo_obj_filepath, _ = get_new_convo_filename(True, False, current_story)

                convo_obj = create_convo_obj(last_ai_msg_content, None, username if username is not None else "system", current_game, generate_next_convo, \
                    current_story, convo_type="main")
                write_json(convo_obj_filepath, convo_obj)

            if last_ai_msg_content is not None:
                run_battle_turn(last_ai_msg_content, username, current_game, convo_obj_filepath, current_message_history, current_story, setup_dnd, config, config_dnd, True, False, start_battle_assistant) # "content" is the default emotion for the narrator
            else:
                print_log("No assistant msg found in the history")

    if custom_action_test is not None: # Leave if test
        return True

    current_turn += 1

    #Update current turn
    current_story = get_current_story() # Refresh current story in case it was changed elsewhere
    current_story["current_turn"] = current_turn 
    current_story["unrelated_or_refused_retries"] = 0 # Reset the retries once the turn ends

    set_current_story(current_story)
    print_log(f"Current turn = {current_turn}")

    # Save the current story state in the debug folder
    save_story_debug_folder(current_story)

    # Update the shared google doc
    if config.get("update_google_doc", False):
        start_update_char_sheet_doc_thread(current_story) 

    return True

@app.command()
def convo():
    extra_info = None
    custom_action_test = None #"get_roll_attack" 
    process_tests = True

    is_dnd_server_text = False # Whether to manually test dnd server

    config = get_ai_config()

    current_user = config.get("username", "system")
    current_game = config.get("game", "dnd")
    current_mode = config.get("ai_mode", "dnd")
    
    current_story = None
    if current_mode == "dnd":
        current_story = get_current_story()

        if current_story is None:
            create_story()
            current_story = get_current_story()
  
        # Initialize the story on the first turn
        if current_story["current_turn"] == 0:
            config_dnd = read_json(f'{ai_config_path}dnd_config.json')
            story_first_turn(current_game, current_user, current_story, config, config_dnd)
        else:
            print_story_properties(current_story)
            
            # print the previous history message
            dnd_history = get_messages_history(dnd_history_file)
            previous_msg_text = dnd_history[-1]["content"] if len(dnd_history) > 0 else ""
            previous_msg_text = remove_system_prefix(previous_msg_text)
            
            if previous_msg_text:
                print_special_text("\n#bold#Narrator:#bold#")
                print(previous_msg_text)
                
            # Create char sheet if absent
            if not os.path.exists(character_sheet_html_file):
                update_char_sheet_doc(current_story)

    first_turn_instance = True

    print("\nEnter a message")

    while(True):
        print("") #Newline before the input
        current_input = input(Fore.YELLOW + '?: ' + Style.RESET_ALL)
        username = current_user if current_user != "random" else f"user{rd.randrange(0,100)}" # random user if random

        if current_input == "":
            print("\nPlease enter a message\n")
            continue

        #print(current_input)

        if(current_input == "q"):
            break

        if(current_input == "user"):
            print("Enter a new current user")
            current_user = input()
            continue

        if(current_input == "game"):
            print("Enter the current game")
            current_game = input()
            continue
        
        if(current_input == "random"):
            current_user = "random"
            print("User is now randomized between 0 and 100")
            continue
        
        # Chat mode
        if current_game != "dnd":
            if (current_user == "system" and current_game != "dnd"): # Not considered as from system in dnd setting
                send_message(current_input, start_send_message_timestamp=time.time(), current_game=current_game, moderate_user_msg=True) #No prefix + no user
            else:
                send_message(current_input, username, start_send_message_timestamp=time.time(), current_game=current_game, moderate_user_msg=True)
        # Manually test the dnd server
        elif is_dnd_server_text:
            current_story = get_current_story()
            text = roll_text = ""
            send_text_command_dnd([text], get_dnd_memory_and_author_note_additions(current_story, (roll_text, [[],"", []], ""), is_narrator_response=False)) # Send new command to dnd server
        # Manually test a custom action
        elif custom_action_test is not None: 
            write_and_send_message_dnd(custom_action_test, allow_continue_without_user_msg=True, switched_scene=first_turn_instance, specific_extra_info=extra_info, process_tests = process_tests)
            print_log(f"\nCustom action test: {custom_action_test}") # So I know I'm currently testing a custom action
        # Dnd mode
        else:
            # Skip generate msg on turn 0, otherwise will run that msg once turn 0 is done
            current_story = get_current_story() # Update curr story, otherwise will stay on turn 0
            if current_story is None or current_story["current_turn"] != 0:
                set_next_message_direct(current_input)
                
            write_and_send_message_dnd(switched_scene=first_turn_instance)

        first_turn_instance = False

if __name__ == "__main__":
    convo()