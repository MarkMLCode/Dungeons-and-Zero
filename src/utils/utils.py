import json
import requests
import os
import time
from difflib import SequenceMatcher
import wave
import re
import random as rd
from datetime import datetime, date, timedelta
import inflect
import pyphen
import uuid
import glob
import threading
import csv
import tiktoken
import math
import inflect
from typing import Dict, Tuple, Any, Optional
import numpy as np
import logging
from colorama import Fore, Style

from utils.alarm import ring_alarm

inflect_engine = inflect.engine()

react_path = "../../"
root_path = "../"

show_text_next_msg_file_path = f"{react_path}react_projects/showtext-next-msg-react/src/showtext.js"

skip_log_print = False
skip_warnings = False

def update_print_log_settings(config_dict):
    global skip_log_print, skip_warnings
    skip_log_print = config_dict.get("skip_log_print", False)
    skip_warnings = config_dict.get("skip_warnings", False)

def print_log(text, is_warning = False):
    if not skip_log_print or (is_warning and not skip_warnings):
        print(text)
    elif is_warning:
        logging.warning(text)
    else:
        logging.info(text)

write_lock = threading.Lock()

def write_json(filename, content):
    # In case you try to write to the same file at the same time in diff threads (don't work for diff processes tho)
        # Will wait until the lock is released before writing
    with write_lock: 
        with open(filename, 'w', encoding="utf-8") as file:
            json.dump(content, file, indent=4)

def read_json(filename):
    nb_retry = 0
    exception = None

    # Retry a few times if json is empty, happens sometimes if accessing it while it's being written
    while nb_retry < 5:
        try:
            with open(filename, 'r', encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError as e:
            print(f"ERROR: Error decoding JSON from '{filename}'. File might be empty or corrupted. Exception: {e}")
            exception = e
        
        time.sleep(0.1)
        nb_retry += 1

    raise exception

def get_inventory_text(current_story, add_dot = False, reverse_list = False, skip_description = False):
    inventory_items = []

    # Format the inventory items
    for item in current_story["inventory"]:
        if not isinstance(item, dict):
            inventory_items.append(item)
            break
        
        # Create the text for the item
        name = item.get("name", "")
        number = item.get("quantity", 1)
        number_text = f"{number} " if number > 1 else ""

        is_equipped = item.get("is_equipped", False)
        magic_weapon_bonus = item.get("magic_weapon_bonus", 0)
        magic_armor_bonus = item.get("magic_armor_bonus", 0)
        magic_focus_bonus = item.get("magic_focus_bonus", 0)
        
        magic_item_bonus = magic_weapon_bonus if magic_weapon_bonus > 0 else (magic_armor_bonus if magic_armor_bonus > 0 else magic_focus_bonus)
        magic_item_bonus_text = f"+{magic_item_bonus}" if magic_item_bonus > 0 else ""

        text = f"{number_text}{name}{magic_item_bonus_text}"

        # Add properties
        properties = []
        if is_equipped :
            properties.append("Equipped")
        elif not skip_description and item.get("description", "") != "":
            properties.append(item["description"])

        text += f" ({', '.join(properties)})" if properties else ""

        inventory_items.append(text)

    if reverse_list:
        inventory_items = inventory_items[::-1] # Reverse the list

    dot_text = "." if add_dot else ""
    inventory_text = ", ".join(inventory_items) + dot_text if len(inventory_items) > 0 else ""

    return inventory_text

def get_formatted_currency(current_story):
    currency_obj = current_story['currency']
    coins = []
    
    if currency_obj.get('pp', 0) > 0:
        coins.append(f"{currency_obj['pp']} pp")
    if currency_obj.get('gp', 0) > 0:
        coins.append(f"{currency_obj['gp']} gp")
    if currency_obj.get('sp', 0) > 0:
        coins.append(f"{currency_obj['sp']} sp")
    if currency_obj.get('cp', 0) > 0:
        coins.append(f"{currency_obj['cp']} cp")
        
    return ', '.join(coins)

# Join all but the last with ", ", and then add " and " + the last element
def combine_array_as_sentence(arr):
    if len(arr) == 0:
        return ""
    elif len(arr) == 1:
        return arr[0][0].upper() + arr[0][1:]
    else:
        sentence = ", ".join(arr[:-1]) + " and " + arr[-1]
        return sentence[0].upper() + sentence[1:]

def get_available_spell_slots(current_story):
    spells_per_day = current_story.get("spells_per_day", [])
    all_spell_slots = current_story.get("spell_slots", [])
    
    current_spell_slots = []
    current_spells_per_day = []

    for x, nb_spell_level_per_day in enumerate(spells_per_day):
        # Only include spells slots with > 0 spells per day
        if nb_spell_level_per_day > 0:
            spell_slot_nb = all_spell_slots[x]
            current_spell_slots.append(spell_slot_nb)
            current_spells_per_day.append(nb_spell_level_per_day)

    return current_spell_slots, current_spells_per_day

def get_limited_resources_triples(current_story):
    # Limited resources
    rage_amount = current_story.get("daily_max_rage_amount", 0)
    can_rage = has_talent("rage", current_story) 
    max_ki_points = current_story.get("max_ki_points", 0)
    max_lay_on_hands_hp = current_story.get("max_lay_on_hands_hp", 0)
    max_sorcery_points = current_story.get("max_sorcery_points", 0)
    max_bardic_inspiration = current_story.get("max_bardic_inspiration", 0)
    max_arcane_ward_hp = current_story.get("max_arcane_ward_hp", 0)
    max_action_surge = 1 if has_talent("action surge", current_story) else 0
    max_second_wind = 1 if has_talent("second wind", current_story) else 0

    limited_resources = []

    # Rage
    if rage_amount > 0:
        rage_remaining = current_story.get('rage_remaining', 0)
        limited_resources.append(("Rage", rage_remaining, rage_amount))
    if can_rage:
        rage_status = "Not raging"
        rage_color = "white"

        if current_story.get('is_frenzied', False):
            rage_status = "Frenzied"
            rage_color = "red"
        elif current_story.get('is_raging', False):
            rage_status = "Raging"
            rage_color = "red"
        elif current_story.get('frenzy_used', False):
            rage_status = "Exhausted"
            
        limited_resources.append(("Status", rage_status, rage_color))
    if max_ki_points > 0:
        ki_points = current_story.get("ki_points", 0)
        limited_resources.append(("Ki Points", ki_points, max_ki_points))
    if max_lay_on_hands_hp > 0:
        lay_on_hands_hp = current_story.get("lay_on_hands_hp", 0)
        limited_resources.append(("Lay on Hands Pool", lay_on_hands_hp, max_lay_on_hands_hp))
    if max_sorcery_points > 0:
        sorcery_points = current_story.get("sorcery_points", 0)
        limited_resources.append(("Sorcery Points", sorcery_points, max_sorcery_points))
    if max_bardic_inspiration > 0:
        bardic_inspiration = current_story.get("bardic_inspiration", 0)
        limited_resources.append(("Bardic Inspiration", bardic_inspiration, max_bardic_inspiration))
    if max_arcane_ward_hp > 0:
        arcane_ward_hp = current_story.get("arcane_ward_hp", 0)
        limited_resources.append(("Arcane Ward HP", arcane_ward_hp, max_arcane_ward_hp))
    if max_action_surge > 0:
        action_surge_remaining = 0 if current_story.get("action_surge_used", False) else 1
        limited_resources.append(("Action Surge", action_surge_remaining, max_action_surge))
    if max_second_wind > 0:
        second_wind_remaining = 0 if current_story.get("second_wind_used", False) else 1
        limited_resources.append(("Second Wind", second_wind_remaining, max_second_wind))
    
    return limited_resources

def get_combatants_info(combatants, combatants_before):
    # Get a list of triples (entry_name, hp, max_hp)
    combatants_info = []
    for x, combatant in enumerate(combatants):
        entry_name = combatant.get("entry_name", "")
        if entry_name:
            entry_name = entry_name.lower().replace(" ", "_")
        else:
            entry_name = ""

        hp = combatant["hp"]
        max_hp = combatant["max_hp"]
        is_named_npc = combatant.get("is_named_npc", False)

        # combatant's hp before the assistant took her turn (equal to hp if in narrator turn instead)
        if combatants_before is not None and len(combatants) == len(combatants_before):
            initial_hp = combatants_before[x]["hp"]
        else:
            initial_hp = hp

        #combatants_info.append((entry_name, initial_hp, hp, max_hp))
        combatants_info.append((entry_name, initial_hp, max_hp, is_named_npc))

    return combatants_info

# Add battle info to convo obj
def add_battle_info_to_convo_obj(convo_obj, current_story, opponents_before = None, allies_before = None):
    battle_info = current_story.get("battle_info", None)
    if battle_info is not None:
        opponents = battle_info.get("opponents", []) 
        allies = battle_info.get("allies", []) 

        if len(opponents) > 0:
            convo_obj["opponents_info"] = get_combatants_info(opponents, opponents_before)
        
        if len(allies) > 0:
            convo_obj["allies_info"] = get_combatants_info(allies, allies_before)

        convo_obj["battle_id"] = battle_info.get("id")

    return convo_obj

def get_current_quest_text(current_story):
    current_quest = current_story["quests"][-1] if len(current_story["quests"]) > 0 else "" # Add latest quest to info
    current_quest = current_quest.get("description", "") if isinstance(current_quest, dict) else current_quest # Get description if quest is a dict (won't be if it comes from story config)
    return current_quest

def get_complete_inventory_text(current_story):
    inventory_text = get_formatted_currency(current_story)

    if len(current_story["inventory"]) > 0:
        inventory_text += ", " if inventory_text != "" else "" # Add comma if coins were added at the start of the inventory
        inventory_text += get_inventory_text(current_story, reverse_list=True, skip_description=True)

    return inventory_text

def create_convo_obj(ai_response, user_msg = "", username = "", game = None, generate_next_convo=True, current_story = None, \
                     win_count = 0, lose_count = 0, music_theme = "", display_sections = "", \
                     is_dnd_chat = False, main_quests_text = "", show_info_game_won_or_lost = False, command = "", convo_type = None):
    # Don't just set to None since that would block the tts
        # Don't set as function argument, since that can cause reference issues)
    if display_sections == "":
        display_sections = []

    convo_obj = {
        "ai_response" : ai_response,
        "user_msg" : user_msg,
        "convo_type": convo_type,
        "username" : username,
        "game" : game,
        "generate_next_convo": generate_next_convo,
        "is_dnd_chat": is_dnd_chat,
        "char_name" : "",
        "char_summary" : "",
        "current_turn" : "",
        "win_count" : win_count,
        "lose_count" : lose_count,
        "music_theme" : music_theme,
        "current_quest" : "", 
        "inventory": "",
        "location": "",
        "location_category": "", # Updated later if eval launched (same as music)
        "location_category_is_interior": False,
        "command": command,
        "hp": None,
        "narrator_hp": None,
        "max_hp": None,
        "assistant_segments": create_text_segment_objs(ai_response),
        "narrator_segments": create_text_segment_objs(user_msg),
        "display_sections": display_sections
    }

    if current_story is None:
        return convo_obj

    convo_obj["char_name"] = current_story["char_name"]
    convo_obj["hair_preset"] = current_story.get("hair_preset", "default")
    convo_obj["char_summary"] = current_story["char_summary"] + "\n\u2014 " + current_story["title"] + " \u2014"
    convo_obj["current_turn"] = current_story["current_turn"]
    
    current_quest = get_current_quest_text(current_story)
    current_quest += ("; " if current_quest != "" else "") + main_quests_text # Add main quests to info

    convo_obj["current_quest"] = current_quest
    convo_obj["hp"] = current_story['hp']
    convo_obj["max_hp"] = current_story['max_hp']

    # Show currency
    convo_obj["inventory"] = get_complete_inventory_text(current_story)

    main_location = current_story.get("main_location", "")
    sub_location = current_story.get("sub_location", "")

    convo_obj["location"] = main_location if main_location != "" else (sub_location if sub_location != "" else "Unknown")
    convo_obj["location_category"] = current_story.get("location_category", "")
    convo_obj["location_category_is_interior"] = current_story.get("location_category_is_interior", "")

    if current_story.get("spell_slots") is not None:
        spell_slots, _ = get_available_spell_slots(current_story)
        convo_obj["spell_slots"] = spell_slots

    limited_resources = get_limited_resources_triples(current_story)
    if len(limited_resources) > 0:
        convo_obj["limited_resources"] = limited_resources

    convo_obj = add_battle_info_to_convo_obj(convo_obj, current_story)
    convo_obj["combatants_present_at_start"] = current_story.get("battle_info", None) is not None

    # Only add to convo if true
    if show_info_game_won_or_lost:
        convo_obj["is_game_won"] = current_story["is_game_won"]
        convo_obj["is_game_lost"] = current_story["is_game_lost"]

    # Move the display sections to the end of the convo obj
    if "display_sections" in convo_obj:
        del convo_obj["display_sections"]
        convo_obj["display_sections"] = display_sections

    return convo_obj

def add_narrator_fields_to_convo(convo_obj, current_story, initial_hp):
    if current_story.get("spell_slots") is not None:
        spell_slots, _ = get_available_spell_slots(current_story)
        convo_obj["narrator_spell_slots"] = spell_slots

    limited_resources = get_limited_resources_triples(current_story)
    if len(limited_resources) > 0:
        convo_obj["narrator_limited_resources"] = limited_resources

    # Update the hp in the convo obj so it matches the most up to date hp at the end of the roll (including stuff like second wind)
    if current_story["hp"] != initial_hp:
        convo_obj["narrator_hp"] = current_story["hp"]

def check_profane(input):
    blacklist_path = f'{root_path}blacklist/profanity_blacklist.txt'
    # skip if file doesn't exist
    if not os.path.exists(blacklist_path):
        return False

    with open(blacklist_path, 'r', encoding="utf-8") as file:
         formatted_input = input.lower()
         for _, word in enumerate(file):
             if word.lower() in formatted_input:
                 return True
    return False

def is_moderation_flagged(inputs, username, source, is_game, from_utils = False, is_chat_dnd = False, custom_action = None):
    moderation_time = time.time()
    for input in inputs:
        if check_profane(input):
            print_log(f'Check_Profane : Moderation time: {(time.time() - moderation_time)} s, Flagged=True')
            return True

    is_flagged = False

    # OpenAI moderation

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer {}".format(os.getenv("OPENAI_API_KEY")),
    }
    data = {
        "input": inputs
    }

    formatted_data = json.dumps(data, ensure_ascii=False)
    encoded_data = formatted_data.encode('utf-8')

    nb_retry = 0
    timeout_length = 10
    results = []

    while nb_retry < 3:
        try:
            response = requests.post('https://api.openai.com/v1/moderations', headers=headers, data=encoded_data, timeout=timeout_length)

            json_response = response.json() if response else None
            results = json_response.get("results") if json_response else None

            if results is not None:
                break
            else:
                print(f'\nINVALID : OpenAI Moderation call to api is invalid, no results returned. Retry {nb_retry + 1}. Data: {formatted_data}\n')
                nb_retry += 1

        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as e:
            print(f'\nTIMEOUT : OpenAI Moderation call to api timeout. Retry {nb_retry + 1}. Exception: {e}\n')
            nb_retry += 1
            timeout_length += 3

    if results is None:
        print(f'\nERROR : OpenAI Moderation call to api failed. No results returned. Considered as flagged.\n')
        return True

    allowed_categories = ["violence", "harassment", 'self-harm', 'self-harm/intent', 'self-harm/instructions'] # Note : Self harm detected as false positive if asking to cut yourself out of something
 
    # Add other allowed categories if set
    if is_game:
        allowed_categories += ["violence/graphic", "harassment/threatening", 'self-harm', 'self-harm/intent', 'self-harm/instructions']

    flagged_categories = []
    flagged_scores = []
    moderation_messages = []
    x = 0

    # Go through the moderation result is see if any category was flagged (unless specifically allowed)
    for result in results:
        message = inputs[x]
        message_flagged_categories = []
        message_flagged_scores = []

        for key, category_is_flagged in result["categories"].items():
            if category_is_flagged and key not in allowed_categories:
                score = result['category_scores'][key]

                # Do not flag if score is too low (hate_threatening seems to have false positives with low scores (0.12))
                if score < 0.15:
                    print_log(f"Moderation flagged with low score. Category: {key}, score: {score}", True)
                    continue

                is_flagged = True
                message_flagged_categories.append(key)
                message_flagged_scores.append(score)

        moderation_messages.append({"message": message, "flagged_categories": message_flagged_categories, "flagged_scores": message_flagged_scores})
        flagged_categories += message_flagged_categories
        flagged_scores += message_flagged_scores
        
        x += 1

    moderation_dir = f'{root_path}moderation'

    suffix = ""
    if is_game or is_chat_dnd or custom_action is not None:
        suffix = suffix if not is_game else suffix + "game_"
        suffix = suffix if not is_chat_dnd else suffix + "chat_"
        suffix = suffix if custom_action is None else suffix + custom_action + "_"

    if not os.path.exists(moderation_dir):
        # Create the directory
        os.makedirs(moderation_dir)

    # Save the moderation messages to a file (keep last 2 char of float for centiseconds)
    moderation_file = f'{datetime.now().strftime("%Y%m%d%H%M%S%f")[:-4]}_{source}_{suffix}{username}.json'
    
    if is_flagged:
        print(f'MODERATION FLAG : OAI Moderation time: {(time.time() - moderation_time)} s, Flagged={is_flagged}, Flagged categories={flagged_categories}, Flagged scores={flagged_scores}')

        quarantine_dir = f'{moderation_dir}/quarantine'
        if not os.path.exists(quarantine_dir):
            # Create the directory
            os.makedirs(quarantine_dir)

        write_json(f'{quarantine_dir}/{moderation_file}', moderation_messages)
        ring_alarm(is_new_message=False)
    else:
        # Save all moderation messages, even if not flagged
        write_json(f'{moderation_dir}/{moderation_file}', moderation_messages) 

    return is_flagged

def match_onomatopoeia(words):
    # Define the onomatopoeia
    onomatopoeia_list = ["ha", "he", "hi", "ho", "oh", "Fuhu", "Nyeh", "pfft"]
    # Placeholder for the matched words
    matched_words = []
    # Iterate through each word
    for word in words:
        # Iterate through each onomatopoeia
        for ono in onomatopoeia_list:
            # Check if word starts with onomatopoeia
            if word.lower().startswith(ono):
                # Check if rest of letters in word are in onomatopoeia
                # If not, break the loop
                for letter in word[len(ono):]:
                    if letter not in ono:
                        break
                else:
                    matched_words.append(word)
                    
    return matched_words

def remove_punctuation(input_string):
    # Custom punctuation string without single quote
    punctuation = '!"#$%()*+,-./:;<=>?@[\\]^_`{|}~' 
    translator = str.maketrans('', '', punctuation)
    return input_string.translate(translator)

# Replace all numbers with words in a text
def number_to_words(text):
    p = inflect.engine()
    
    def replace_with_words(match) -> str:
        number = match.group()
        result = p.number_to_words(number)
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        else:
            return str(result)
    
    # This regular expression will match both integers and floating point numbers.
    pattern = r'\b\d+(\.\d+)?\b'
    text_with_words = re.sub(pattern, replace_with_words, text)
    return text_with_words

# Ex : bad-looking == bad looking
def replace_hyphen(input_string):
    return input_string.replace("-", " ").replace("_", " ").replace("~", " ")

def process_text_for_diff(text):
    text = number_to_words(text)
    text = replace_hyphen(text).lower()
    text = remove_punctuation(text)
    text_split = text.split()
    return text, text_split

def get_ratio_orig(text_A_split, text_B_split, sound_mode):
    sequence_matcher = SequenceMatcher(None, text_A_split, text_B_split)
    
    different_parts = []
    for tag, i1, i2, j1, j2 in sequence_matcher.get_opcodes():
        if tag == 'replace' or tag == 'delete':
            different_part = text_A_split[i1:i2]
            if len(different_part) >= 1:
                different_parts.append((i1, i2-1, ' '.join(different_part)))

    #ratio of differences over total
    total_span = 0
    for start, end, _ in different_parts:
        total_span += end + 1 - start

    # When in sound mode, remove all onomatopeas from the total_span at the end
    if sound_mode:
        matches = match_onomatopoeia(text_A_split)
        onomatopea_nb = len(matches)
        print_log(onomatopea_nb)

        total_span -= onomatopea_nb
        total_span = total_span if total_span >= 0 else 0

    ratio_orig = total_span / len(text_A_split) if len(text_A_split) > 0 else 0 # No hallucinations when textA empty (sound bites)
    return ratio_orig, different_parts

def manual_word_fixes(word):
    if word.startswith("counter-attack"): # Correct version is without hyphen, not with space
        return word.replace("-", "")
    else:
        return word

# Returns the parts in text_A that are different from text_B (including their positions).
# Also return the lenght of the different part and the ratio of differences over total
def detect_differences(words_text_A, text_B, words_sepp_tresh, sound_mode = False):

    # Take note of where we replace characters to make sure the plagiarized indexes matches those in whisper.
    current_index = 0
    replaced_words = []
    total_count_split_words = 0
    total_count_removed_words = 0

    for word in words_text_A:
        # Count removed words (comprised only of punctuation)
            # Needs to be added to the count or otherwise there will be a lenght mismatch
        if remove_punctuation(word) == "":
            total_count_removed_words += 1
        # Count words that will be split due to containing a hyphen, underscore or tilde
        elif not (word.endswith('-') or word.endswith('_') or word.endswith('~')):  # Only process the word if it doesn't end with '-'
            new_word = manual_word_fixes(word)
            new_word = replace_hyphen(word)
            count_replaced_char =  word.count('-') + word.count('_') + word.count('~')
            if count_replaced_char >= 1:
                replaced_words.append((current_index, count_replaced_char, word, new_word))
                current_index += count_replaced_char # Also add 1 to the current index for each replacement that occurs, since 1 word becomes more words
                total_count_split_words += count_replaced_char
            current_index += 1

    # Init
    text_A = " ".join(words_text_A).strip()
    text_A, text_A_split = process_text_for_diff(text_A)
    text_B, text_B_split = process_text_for_diff(text_B)

    # Determine the max ratio between both way of comparisons
    ratio_orig_A, different_parts_A = get_ratio_orig(text_A_split, text_B_split, sound_mode)
    ratio_orig_B, different_parts_B = get_ratio_orig(text_B_split, text_A_split, sound_mode)
    
    if ratio_orig_A > ratio_orig_B:
        ratio_orig = ratio_orig_A
        different_parts = different_parts_A
    else:
        ratio_orig = ratio_orig_B
        different_parts = different_parts_B

    different_parts = different_parts_A # Only thing that matters right now is the hallucination ratiom so just keep the rest the same.

    #Merge adjacent parts
    if len(different_parts) > 0:
        different_parts = sorted(different_parts, key=lambda x: x[0])
        merged_parts = []
        current_part = different_parts[0]

        for next_part in different_parts[1:]:
            if next_part[0] - current_part[1] <= words_sepp_tresh:  # 2 words apart or less
                current_part = (current_part[0], next_part[1], ' '.join(text_A_split[current_part[0]:next_part[1]+1]))
            else:
                merged_parts.append(current_part)
                current_part = next_part
        merged_parts.append(current_part)

        # Remove parts that don't start at the beginning or end at the end
        merged_parts = [part for part in merged_parts if part[0] == 0 or part[1] == len(text_A_split)-1]

        different_parts = merged_parts

    # Go through all the different parts and fix the indexes so that they match the ones in the original words_text_A array, even after replacing (-,_,etc.)
    new_different_parts = []
    for part in different_parts:
        new_start_index = part[0]
        new_end_index = part[1]
        new_part_text = part[2]

        # Go 
        for replaced_word_tuple in replaced_words:
            index = replaced_word_tuple[0]
            count_replaced_index = replaced_word_tuple[1]
            
            if part[0] == index:
                new_end_index -= count_replaced_index
            elif part[0] > index:
                new_start_index -= count_replaced_index
                new_end_index -= count_replaced_index
            elif part[1] >= index:
                new_end_index -= count_replaced_index

            old_word = replaced_word_tuple[2]
            new_word = replaced_word_tuple[3]
            new_part_text = new_part_text.replace(new_word.lower(), old_word.lower())

        new_different_parts.append((new_start_index, new_end_index, new_part_text))

    # Calculate the total span of the different parts
    total_differences = sum(new_end_index - new_start_index + 1 for new_start_index, new_end_index, _ in new_different_parts)

    len_text_A_split = len(text_A_split) - total_count_split_words + total_count_removed_words # Remove the count of replaced characters from the total length of the text
    ratio = total_differences / len_text_A_split if len_text_A_split > 0 else 0 # No hallucinations when textA empty (sound bites)
    max_ratio = max(ratio, ratio_orig)

    return new_different_parts, len_text_A_split, max_ratio, text_A

# Cut out from the filename sound file the parts defined in the times variable (containing an array of tuples of start and end time), save the result as output_filename
def cut_wav_file(filename, times, output_filename):
    # Open the file.
    with wave.open(filename, 'rb') as wf:
        # Calculate frame rate.
        frame_rate = wf.getframerate()
        # Read in all frames.
        frames = wf.readframes(wf.getnframes())
        # Initialize the new frames.
        new_frames = b''
        previous_end = 0

        # For each start and end time,
        for start, end in times:
            # Convert times to sample indices.
            start_index = int(start * frame_rate)
            end_index = int(end * frame_rate)

            # Cut the frames.
            before_cut = frames[previous_end:start_index * wf.getsampwidth()]
            #after_cut = frames[end_index * wf.getsampwidth():]
            new_frames += before_cut

            # Update the previous_end to current end_index
            previous_end = end_index * wf.getsampwidth()

        # Add the remaining frames after the last cut
        new_frames += frames[previous_end:]
        
        # Open a new file.
        with wave.open(output_filename, 'wb') as wf_out:
            wf_out.setparams(wf.getparams())
            wf_out.writeframes(new_frames)

def remove_elements_from_array(index_tuples, data_array):
    # Sort the index tuples in reverse order (this is to ensure that removing elements doesn't affect the indexes of elements yet to be removed)
    index_tuples.sort(key=lambda x: x[0], reverse=True)
    
    # Loop over the index_tuples
    for start, end in index_tuples:
        # Python's del function is used to remove elements from the list
        # Note: The range is adjusted by +1 since the end index is not included in slicing
        del data_array[start:end+1]
        
    return data_array

# Return true if segment starts and end with starts (or *.) + there are no other stars in the middle
#   (in case the segment contains subsegments within stars at start and end, but not in the middle)
def segment_completely_within_asterisks(segment):
    return segment.startswith('*') and ( \
        (segment.endswith('*') and "*" not in segment[1:-1]) or (segment.endswith('*.') and "*" not in segment[1:-2]))

# Segment the text into sentences of max char_limit characters. 
     # If there are sentences longer than char_limit, segment using the previous coma when the limit reached
     # If there are still sentences longer than the char_limit, segment at the previous word instead.
     # If there are still sentences longer than the char_limit, segment at char_limit exactly.
def segment_text(text_arg, separate_sentences=False, char_limit=165, separate_sentences_min_char=40):
    text = text_arg.replace("\n\n", "#doublenewline#").replace("\n", "#newline#").strip() #Replace newlines with spaces
    text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'").replace("\u2013", "-") # Replace unicode characters with their ascii equivalents

    # Allow the sentence to be correctly split at the end of a quote
    text = text.replace(".'", "'.").replace('."', '".') 
    text = text.replace("!'", "'!").replace('!"', '"!') 
    text = text.replace("?'", "'?").replace('?"', '"?') 

    # Split on sentence ending punctuation and sentences in quotes
    sentences = re.split(r'(?<=#newline#)|(?<=#doublenewline#)|(?<=[.!?])\s+?|(?<=\))\s+|(?<=\))$', text)

    segmented_text = []

    for sentence in sentences:
        sentence = sentence.strip()  # trim leading/trailing whitespace
        while len(sentence) > char_limit:
            # Check for splitting points
            split_points = [sentence.rfind(char, 0, char_limit) for char in [', ', ' - ', '—', '; ', '"']]
            split_point = max([pt for pt in split_points if pt != -1], default=-1)

            if split_point == -1:  # No valid split point found
                split_point = sentence.rfind(' ', 0, char_limit)  # Try splitting at last space
            if split_point == -1:  # Still no valid split point found
                split_point = char_limit  # Split at the character limit

            segmented_text.append(sentence[:split_point+1].rstrip())
            sentence = sentence[split_point:].lstrip(' ,;-—"') # Trim leading spaces and punctuation
        segmented_text.append(sentence)

    # If a segment is less than 15 characters, append it to the previous or next segment as appropriate.
    adjusted_text = []
    prev_segment = ''
    for current_segment in segmented_text:
        if prev_segment and len(prev_segment) < 15:
            #if not prev_segment.endswith('.'): # If condition is false, everything to the right will be ignored (will be stuck on that condition until the end of the sentence, see power... example in test)
            prev_segment += " " + current_segment
            continue
        elif len(current_segment) < 15:
            if prev_segment.endswith('.'):
                adjusted_text.append(prev_segment)
                prev_segment = current_segment
                continue
            else:
                prev_segment += " " + current_segment if prev_segment else current_segment
                continue
        else:
            adjusted_text.append(prev_segment)
            prev_segment = current_segment
    adjusted_text.append(prev_segment)

    # Combine asterisked sections and sentences as long as under the char limit
    grouped_text = []
    temp_segment = adjusted_text[0]

    for sentence in adjusted_text[1:]:
        # Combine segments that have asterisked sections split across them or 
        # combine sentences as long as under the char limit if separate_sentences = False, 
        # otherwise keep them separate unless < separate_sentences_min_char
        if (temp_segment.count('*') % 2 == 1) or \
        (not separate_sentences or len(temp_segment) < separate_sentences_min_char or len(sentence) < separate_sentences_min_char) and \
        len(temp_segment + " " + sentence) <= char_limit:
            temp_segment += " " + sentence
        else:
            grouped_text.append(temp_segment)
            temp_segment = sentence

    grouped_text.append(temp_segment)

    # Combine segments with ONLY asterisks or asterisks with a dot at the end with the previous or following segment
    final_text = []
    temp_segment = grouped_text[0]

    x = 0
    for sentence in grouped_text[1:]:
        # Combine the current sentence with temp_segment(previous segment) if the temp_segment is asterisked or the sentence starts with asterisk
            # Special case: If first sentence is within asterisks, prepend it to the current sentece
        if segment_completely_within_asterisks(sentence)  or \
            (x == 0 and segment_completely_within_asterisks(temp_segment)):
            temp_segment += " " + sentence
        else:
            final_text.append(temp_segment)
            temp_segment = sentence
        x += 1
            
    final_text.append(temp_segment)

    return [seg.strip().replace("#newline#", "\n").replace("#doublenewline#", "\n\n") for seg in final_text if seg]

def enumerate_folders(src_path, join_folders=False):
    all_folders = []
    # Iterate over all items in source directory
    for item in os.listdir(src_path):
        full_path = os.path.join(src_path, item)  # Construct full path
        # Check if the item is a directory and not a file
        if os.path.isdir(full_path):
            all_folders.append(item.lower())  # Add folder to the list

    # Return a joined string if join_folders is True, else return the list
    return ", ".join(all_folders) if join_folders else all_folders

# Fetch a random file in the given folder
def choose_random_file_from_path(folder_path):
    if not os.path.isdir(folder_path):
        # print_log(f"{type} folder {folder_name} not found in root_path")
        return None
    
    # Get all files in the folder, filtering out subdirectories
    files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    if not files:
        return None

    index = rd.randrange(0, len(files))

    return folder_path + "/" + files[index]

# Compare the first X words to see if they are the same
def check_first_words(text1, text2, how_many_words = 4):
    # Split the texts into words
    words1 = text1.split()
    words2 = text2.split()

    # Ensure both texts have at least X words
    if len(words1) < how_many_words or len(words2) < how_many_words:
        return False

    # Get the first X words, ignoring case
    first_words1 = [word.lower() for word in words1[:how_many_words]]
    first_words2 = [word.lower() for word in words2[:how_many_words]]

    # Compare the first X words
    return first_words1 == first_words2

def remove_all_asterisks(text_arg):
    text = re.sub(r'\s?\*.*?\*', '', text_arg) #Remove asterisks
    text = re.sub(r'(?<!\.)\.\.(?!\.)', '.', text) # Remove '..' alone, happens sometimes after removing asterisks (make sure not to remove ...)
    text = text.replace(".,", ".").replace(",.", ".") # Replace ., if the asterisks were used as the start of a sentence
    text = text.lstrip("., ") # remove dots, comas or space alone at the start
    return text

def get_random_choice(choices):
    choices_list = list(choices)
    weights = list(map(lambda choice:choice["weight"], choices_list))
    random_choice = rd.choices(choices_list, weights)
    return random_choice[0]

def get_all_files(folder_path):
    """Get all files in the directory"""
    return [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]

picked_files = [] # Previously picked files stays for the whole session.

def random_file_picker(folder_path):
    global picked_files
    all_files = get_all_files(folder_path)
    # Remove picked files from all files
    remaining_files = [f for f in all_files if f not in picked_files]
    # If all files are picked once, clear the picked_files list and start over
    if len(remaining_files) == 0:
        picked_files.clear()
        remaining_files = all_files
    # Select a file randomly from the remaining files
    selected_file = rd.choice(remaining_files)
    picked_files.append(selected_file)
    return os.path.join(folder_path, selected_file)

def check_folder_has_files(folder_path):
    return any(os.path.isfile(os.path.join(folder_path, i)) for i in os.listdir(folder_path))

def fix_dots(s):
    # Replaces any dots separated by space by 1 dot
    s = re.sub(r'\.\s+\.', '.', s)

    # Replace any instances of more than 3 dots by 3 dots
    s = re.sub(r'\.{4,}', '...', s)

    # Add back a missing space if there is a dot followed by an alphanumeric character
    s = re.sub(r'\.(?=\w)', '. ', s)
    return s

username_regex = r'^([A-Za-z0-9_\-\.\s]+):\s*'

def remove_username_prefix(text):
    modified_text = re.sub(username_regex, '', text)
    return modified_text

def extract_username_from_prefix(text):
    match = re.match(username_regex, text)
    return match.group(1) if match is not None else None

def remove_username_inside_text(text, username):
    # Replace username if it's the first word of the sentence and capitalize the next word
    text = re.sub(rf'^{username}, (\w)', lambda m: m.group(1).upper(), text, flags=re.IGNORECASE)

    # Replace username if it's the last word of a sentence and remove the comma before it
    text = re.sub(rf', {username}\b', '', text, flags=re.IGNORECASE)

    # If username is still present, just replace it
    text = re.sub(rf' \b{username}\b', '', text, flags=re.IGNORECASE)

    return text

def process_user_msg_emotion(text_arg):
    text = text_arg.strip()
    pattern = r"^#(.*?)#\s?" # Regex to match text pattern '#...#\n...' at the start of string
    match = re.match(pattern, text)

    if match:
        inside_hashtag = match.group(1)
        text = re.sub(pattern, '', text, count=1) # Remove the matched pattern from the text
    else:
        inside_hashtag = None

    return inside_hashtag, text

def process_unrelated(text_arg):
    inside_tags, text = case_insensitive_replace(text_arg, "$unrelated$", "")
    return inside_tags, text.strip() # remove empty space before $unrelated$

def process_refused(text_arg):
    inside_tags, text = case_insensitive_replace(text_arg, "$refused$", "")
    return inside_tags, text.strip() # remove empty space before $refused$

# Split the prompt into words, including the punctuation in the word
def split_words_prompt(prompt):
    # Split the prompt into words and punctuation
    split_prompt = re.findall(r"[\w:'.,!?;\"()&\n]+|[.,!?;]", prompt)

    # Remove any empty strings and return
    return list(filter(None, split_prompt))

# Force the corrected array to be == to the prompt, until the end, where everything that remains is added to the last word
def force_transcription(word_array_arg, prompt):
    prompt_words = split_words_prompt(prompt)
    corrected_array = word_array_arg.copy() 
    has_correction = len(corrected_array) != len(prompt_words)

    # Correct each words
    for i in range(len(corrected_array)):

        # Decide the prompt word to which to compare the word in the array
        if i >= len(prompt_words):
            current_prompt_word = "" # Add empty string if there are no more words in the prompt
        elif i < len(corrected_array) - 1:
            current_prompt_word = prompt_words[i] # Add the array word at the same index in the prompt
        else:
            current_prompt_word =  " ".join(prompt_words[i:]) # Add all the remaining words in the prompt into the last array word

        # Force the word in the original prompt in place of the word found in whisper
        if corrected_array[i] != current_prompt_word:
            has_correction = True
            corrected_array[i] = current_prompt_word

    return corrected_array, has_correction

# Return None when an error occured
def validate_if_oai_chunk_error(chunk):
    if chunk is not None:
        error = chunk.get("error")

        if error is not None:
            print(f"ERROR: Error received from OAI: {error}")
            return error
        
    return None

def oai_call_stream(model, messages, max_response_length, timeout, temperature, top_p, frequency_penalty, presence_penalty, json_mode = False):
    start_time = time.time()

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer {}".format(os.getenv("OPENAI_API_KEY")),
    }

    params = {
        "model": model,
        "messages": messages,
        "max_tokens": max_response_length, #Max nb of tokens in th response
        "stream": True 
    }

    if json_mode:
        params["response_format"] = {"type": "json_object"}

    # Only add the parameters if they are not None
    if temperature is not None:
        params["temperature"] = temperature
    if top_p is not None:
        params["top_p"] = top_p
    if frequency_penalty is not None:
        params["frequency_penalty"] = frequency_penalty
    if presence_penalty is not None:
        params["presence_penalty"] = presence_penalty

    formatted_params = json.dumps(params, ensure_ascii=False)
    encoded_params = formatted_params.encode('utf-8')

    response = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, data=encoded_params, timeout=timeout, stream=True)

    if response.status_code != 200:
        raise Exception(f"Error in OAI call: {response.status_code} - {response.text}")

    # Dictionary to hold the log data
    oai_call_log = {
        "id": "",
        "object": "",
        "created": "",
        "model": model,
        "temperature": temperature,
        "top_p": top_p,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
        "max_tokens": max_response_length,
        "timeout": timeout,
        "longest_time_between_chunks_id": 0,
        "longest_time_between_chunks": 0,
        "total_time_taken": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "response_message": "",
        "messages": messages,
        "chunks": []
    }

    role = None

    # Variable to keep track of the longest time between chunks
    longest_time_between_chunks = 0.0
    longest_time_between_chunks_id = 0
    last_chunk_time = time.time()

    chunk = None
    x = 0

    # create variables to collect the stream of chunks
    collected_chunks = []
    collected_messages = []

    # create a byte buffer to collect incoming data
    byte_buffer = b""

    is_first_byte = True
    is_first_chunk = True

    # iterate through the incoming bytes
    for byte_data in response.iter_content():
        if is_first_byte:
            is_first_byte = False
            print_log(f"First byte received at time: {time.time() - start_time}")

        byte_buffer += byte_data

        # Check for the end of a completed chunk
        while b'}\n\n' in byte_buffer:
            chunk_time = (time.time() - last_chunk_time)
            total_time = time.time() - start_time  # calculate the time delay of the chunk
            last_chunk_time = time.time()

            if chunk_time > longest_time_between_chunks:
                longest_time_between_chunks = chunk_time
                longest_time_between_chunks_id = x

            # Extract the next full completed chunk from the byte buffer
            chunk_end_idx = byte_buffer.index(b'}\n\n') + 3  # +3 to include "}\n\n"
            completed_chunk = byte_buffer[:chunk_end_idx].decode('utf-8')

            # Remove "data: " prefix and decode the JSON
            json_str = completed_chunk.replace("data: ", "", 1)
            chunk = json.loads(json_str)
            byte_buffer = byte_buffer[chunk_end_idx:]

            # Validate if chunk error
            chunk_error = validate_if_oai_chunk_error(chunk)
            if chunk_error:
                raise Exception(f"Error received from OAI: {chunk_error}")

            # Extract the message
            collected_chunks.append(chunk)  # save the event response
            chunk_message = chunk['choices'][0]['delta']  # extract the message
            collected_messages.append(chunk_message.get("content", ""))  # save the message
            #print_log(f"Message received {total_time:.2f} sec after request, {chunk_time:.4f} sec after last chunk: {chunk_message}")  # 

            if is_first_chunk:
                role = chunk_message.get("role", None)
                is_first_chunk = False
                print_log(f"First chunk received at time: {time.time() - start_time}")

            # Add the chunk data to the log
            oai_call_log["chunks"].append({
                "chunk_nb": x,
                "chunk_time": round(chunk_time, 4),
                "content": chunk_message.get("content", "")
            })
            x += 1

            # Check for the [DONE] marker
            if b"data: [DONE]\n\n" in byte_buffer:
                byte_buffer = b""
                break

    if chunk is None:
        raise Exception("No chunk received from OAI")
    
    if role is None:
        raise Exception("No role received from OAI")

    response_msg = "".join(collected_messages)
    response_msg_oai = format_msg_oai(role, response_msg)

    # Create the log file
    oai_call_log["id"] = chunk.get("id", "")
    oai_call_log["object"] = chunk.get("object", "")
    oai_call_log["created"] = chunk.get("created", "")
    oai_call_log["model"] = chunk.get("model", "")

    oai_call_log["longest_time_between_chunks_id"] = longest_time_between_chunks_id
    oai_call_log["longest_time_between_chunks"] = round(longest_time_between_chunks, 4)
    
    oai_call_log["total_time_taken"] = round(total_time, 4)
    oai_call_log["response_message"] = response_msg

    oai_call_log["prompt_tokens"] = count_tokens(messages)
    oai_call_log["completion_tokens"] = count_tokens([response_msg_oai]) 
    oai_call_log["total_tokens"] = oai_call_log["prompt_tokens"] + oai_call_log["completion_tokens"]

    print_log(f"Response received from OAI in {time.time() - start_time}s, model used: {model}")

    return oai_call_log, response_msg_oai


# Send msg to openai
def send_open_ai_gpt_message(max_response_length, messages_arg, model, backup_model, timeout = 8, no_gen = None, temperature = None, top_p = None, presence_penalty = None, frequency_penalty = None, from_dnd_server=False, custom_action = "", json_mode = False, is_chat_dnd = False, current_turn = None):
    # # Remove all messages with unsupported roles
    messages = [msg for msg in messages_arg if msg["role"] in ["system", "user", "assistant"] or print_log(f"WARNING: Removed message with invalid role", True)]

    # Json mode require to have json present somewhere in the prompt, definitely a bug
    if json_mode and len(messages) > 0 and "json" not in messages[-1]["content"].lower():
        raise Exception("ERROR : Json mode require to have json present somewhere in the prompt. Prompt: " + messages[-1]["content"])

    response_message = None
    max_immeditate_retry = 3 # +1 for initial try
    wait_time_until_no_response_retry = 60 # Wait 60 secs before retrying if no response received
    start_time_call_oai = time.time()

    # Loop until we get a response
    while (response_message is None):

        used_backup = False
        nb_retry = 0

        while(response_message is None and nb_retry <= max_immeditate_retry):
            try:
                oai_call_log, response_message = oai_call_stream(model, messages, max_response_length, timeout, temperature, top_p, frequency_penalty, presence_penalty, json_mode)

                # In json mode, validate if the response contains a json object
                    # Retry otherwise
                if json_mode:
                    name = custom_action if custom_action else "default"
                    json_obj = extract_json_from_response(name, response_message['content'])

                    if json_obj is None:
                        print_log("\nWARNING: No json object found in response, retrying...\n", True)
                        response_message = None
                        nb_retry += 1
                        continue

            except requests.exceptions.Timeout as e:
                print(f"Took longer than {timeout} sec, retrying... Exception: {e}")
                timeout += 3
                nb_retry += 1
            except Exception as e:
                print(f"Connexion crashed: {e}")
                timeout += 2
                nb_retry += 1

        # User backup model if still hasn't got a response
            # Note : Disable retry for json mode, backup model doesn't support it (as of dec 27 2023 anyways)
        if response_message is None and not json_mode and backup_model is not None:
            print("Max retry reached, trying backup model.")
            used_backup = True

            try:
                oai_call_log, response_message = oai_call_stream(backup_model, messages, max_response_length, timeout, temperature, top_p, frequency_penalty, presence_penalty, json_mode)
            except Exception as e:
                print(f"Backup model failed too, returning empty response : {e}")
                return None
            
        # Never return None, just wait until eventually get a response
        if (response_message is None):
            print(f"Max immediate retry reached, trying again in {wait_time_until_no_response_retry} secs.")
            time.sleep(wait_time_until_no_response_retry)

    print_log(f"Response received from OAI in {time.time() - start_time_call_oai}s, model used: {model if not used_backup else backup_model}")

    # Debug calls
    suffix = f"_{no_gen}" if no_gen is not None else ""

    if custom_action:
        suffix += f"_{custom_action}"

    if from_dnd_server:
        suffix += "_server"
    elif is_chat_dnd:
        suffix += "_chat"

    if current_turn is not None:
        suffix += f"_{current_turn}"

    filename = f'{datetime.now().strftime("%Y%m%d%H%M%S%f")[:-4]}{suffix}' # Filename including the nb of ms (otherwise filename might be overwritten)
    with open(f'{root_path}current_convo_debug/{filename}.json', 'w', encoding="utf-8") as f:
        formatted_data = json.dumps(oai_call_log, ensure_ascii=False, indent=4)
        f.write(formatted_data)

    return response_message

def format_msg_oai(msg_type, content):
    return {"role": msg_type, "content": content}

encoding_gpt = None

def count_tokens(messages):
    global encoding_gpt
    if encoding_gpt is None:
        encoding_gpt = tiktoken.encoding_for_model("gpt-4")

    num_tokens = 0
    for message in messages:
        for key, value in message.items():
            num_tokens+=len(encoding_gpt.encode(value))
        num_tokens += 4 

    num_tokens += 3
    return num_tokens


# This function takes a string of text as input and returns the text with any incomplete sentence at the end removed. 
# A sentence is considered complete if it ends with a period, question mark, or exclamation mark. 
# This function handles multi-line text correctly, treating the whole text as one continuous string of sentences rather than treating each line as a separate string.
def remove_end_partial_sentence(text):
    result = re.search(r'((?:.|\s)*[\.\?!])[^\.?!)]*$', text)
    return result.group(1) if result else text

#Matches and replaces the given prefix in the text with asterisks around it.
def match_and_replace(text, pattern, replacement):
    # Modified regex pattern to account for an optional opening quote (single or double) at the beginning
    match = re.match(r'^(["\']?)(' + pattern + ')', text, flags=re.IGNORECASE)
    if not match:
        return text

    quote, matched_text = match.groups()  # Extract any matched quote and the matched text
    text = text[len(matched_text) + len(quote):].lstrip(' .,!?')
    text = text[0].upper() + text[1:]
    text = f'{quote}*{replacement.capitalize()}*' + text

    return text

#Replaces prefixes like 'hmm', 'mmm', 'phew', 'whew', or 'ugh' with asterisks around them in the given text.
def replace_prefix_sound(text_arg):
    text = text_arg.lstrip(' .,')

    patterns = [
        (r'h{1}m+', 'hmm'),
        (r'mmm+', 'mmm'),
        (r'[pw]hew', 'whew'),
        (r'ugh+', 'ugh')
    ]

    for pattern, replacement in patterns:
        replaced_text = match_and_replace(text, pattern, replacement)
        if replaced_text != text:
            return replaced_text

    return text

def estimate_word_timing(text, audio_duration_arg):
    audio_duration = audio_duration_arg - 0.5 # Generate text a bit faster than the audio duration (calculate some empty space at the end)

    # Initialize a Pyphen instance
    dic = pyphen.Pyphen(lang='en')

    # Split words
    words = text.split()

    # Calculate the number of syllables for each word
    syllables_count = sum(len(dic.inserted(word).split('-')) for word in words)

    # Define durations for spaces based on the number of syllables
    space_duration = audio_duration / (4 * syllables_count)
    punctuation_extra_duration = 1.5 * space_duration

    # Count words ending with punctuation
    punctuation_words_count = sum(1 for word in words if word[-1] in ".!?,;:")

    # Calculate total estimated duration of the text, subtracting spaces and added punctuation durations
    total_word_duration = audio_duration - (space_duration * (len(words) - 1)) - (punctuation_extra_duration * punctuation_words_count)

    # Calculate how much time each syllable takes
    syllable_duration = total_word_duration / syllables_count

    word_timings = []
    time_elapsed = 0.1

    for word in words:
        # Check if the word ends with punctuation
        has_punctuation = word[-1] in ".!?,;:"
        
        # Calculate the word's syllables and its duration
        word_syllables = dic.inserted(word).split('-')
        word_duration = len(word_syllables) * syllable_duration

        # If it ends with punctuation, add extra duration
        if has_punctuation:
            word_duration += punctuation_extra_duration
        
        # Create word object
        word_obj = {
            "word": word,
            "start": time_elapsed,
            "end": time_elapsed + word_duration,
            "score": 0
        }

        word_timings.append(word_obj)

        # Update the time_elapsed
        time_elapsed += word_duration + space_duration

    return word_timings

# Also remove empty space before the parenthesis, or a dot after the parenthesis.
    # Also remove square brackets
def remove_parentheses(input_str):
    if input_str is None:
        return None

    return re.sub(r'\s?\([^)]*\)|\s?\[[^\]]*\]', '', input_str)

# Generate a message, as if it came from youtube
def generate_message(author, channel_id, message, messages_path, msg_type="textMessage", donation_amount=""):
    # Generate a random UUID for the "id" field
    random_id = str(uuid.uuid4())

    # Generate a timestamp for the "timestamp" field
    timestamp = time.time()

    # Create the dictionary with the desired format
    msg = {
        "id": random_id,
        "type": msg_type,
        "timestamp": timestamp,
        "author": author,
        "channel_id": channel_id,
        "donation_amount": donation_amount,
        "message": message
    }

    filename = f'{timestamp}-{msg["author"]}.json'
    filepath = messages_path + filename
    write_json(filepath, msg)

    print_log(f"JSON file '{filename}' has been created.")

# Return last json object contained in the response_content
def extract_json_from_response(func_name, response_content):
    try:
        # Use regular expression to find potential JSON objects
            # The regex also captures JSON content that might not have a closing brace.
        matches = re.findall(r'\{.*\}|\{.*$', response_content, re.MULTILINE | re.DOTALL) # Just need to detect everything in {} as a json object, json_mode should only output valid json (I think)
        
        if matches:
            modified_response = matches[0] # First match should be the JSON object

            # Calculate number of missing closing braces and append them
            missing_closing_braces = modified_response.count('{') - modified_response.count('}')
            if missing_closing_braces > 0:
                modified_response += '}' * missing_closing_braces

            # Replace "true/false" with "false", in case the JSON object contains "true/false" as a string (error when created it)
            modified_response = re.sub(r'(?i)["\']true/false["\']', 'false', modified_response) 

            # Convert all instances of "True" and "False" (case insensitive) to True and False
            modified_response = re.sub(r'(?i)["\']true["\']', 'true', re.sub(r'(?i)["\']false["\']', 'false', modified_response))
            
            # Replace N/A with "N/A" if it appears after a colon and optional whitespaces, case-insensitive
            modified_response = re.sub(r'(?i)(:\s*)N/A', r'\1"N/A"', modified_response)

            # Remove trailing commas right before ] or }
            modified_response = re.sub(r',\s*([}\]])', r'\1', modified_response)

            json_obj = json.loads(modified_response)

            if not isinstance(json_obj, dict):
                print(f'Error in {func_name}: The text does not contain an object (no dict). {response_content}')
                return None
            
            return json_obj
        else:
            print(f'Error in {func_name}: No potential JSON object found in the text. {response_content}')
            return None
    except json.JSONDecodeError as e:
        print(f'Error in {func_name}: The text does not contain a valid JSON object. {response_content}. Error : {str(e)}')
        return None

# Make sure you always return a bool, false otherwise
def validate_bool(value):
    return value == True 

# Validate if the given text is unspecified (Don't use with bools or numbers, will convert to string!)
def validate_unspecified(text, is_list = False):
    # If text is None or empty string or empty list, return None
    if not text:
        return None
    
    if isinstance(text, dict):
        print_log("Warning: validate_unspecified() doesn't support dictionaries.", True)
        return None
    
    # If text is a list, return it if is_list = True, else return the first element if it's not empty
    if isinstance(text, list):
        if is_list:
            return text
        elif len(text) > 0:
            return text[0]
        else:
            return None

    if isinstance(text, bool) or isinstance(text, int) or isinstance(text, float):
        return str(text)
    
    # List of unspecified text values
    unspecified_values = ["", "-", "none", "unknown", "unspecified", "n/a", "empty"]

    # Convert text to lowercase and check against unspecified values
    if text.lower() in unspecified_values:
        return None

    return text

# Extract a number from a string, always return an int, averaging it if there are multiple numbers
def extract_int(text):
    if text is None:
        return None
    
    if isinstance(text, int):
        return text
    
    # Check if the input is already a float
    try:
        number = float(text)
        return int(math.floor(number))
    except ValueError:
        pass

    # This pattern matches integers as well as fractions and decimal numbers
    matches = re.findall(r'\d+/\d+|\d+\.\d+|\d+', text)

    if len(matches) == 0:
        return None

    # Convert matches to floats
    float_matches = [float(eval(match)) for match in matches]

    # Calculate and return the average if there are multiple numbers
    if len(float_matches) > 1:
        average = sum(float_matches) / len(float_matches)
        return int(math.floor(average))
    elif float_matches:  # if there's only one number
        return int(float_matches[0])  # convert to int directly since it'll do flooring for float values
    else:  # if no numbers found
        return None

# Extract a number from a string, always return a float, averaging it if there are multiple numbers
def extract_float(text):
    if text is None:
        return None
    
    if isinstance(text, (int, float)):
        return float(text)
    
    # This pattern matches integers as well as fractions and decimal numbers
    matches = re.findall(r'\d+/\d+|\d+\.\d+|\d+', text)

    if len(matches) == 0:
        return None

    # Convert matches to floats
    float_matches = [float(eval(match)) for match in matches]

    # Calculate and return the average if there are multiple numbers
    if len(float_matches) > 1:
        average = sum(float_matches) / len(float_matches)
        return average
    elif float_matches:  # if there's only one number
        return float_matches[0]
    else:  # if no numbers found
        return None

# Can process any mix of positive and negative dice, and static modifiers
def process_dice(dice_expression):
    # Add a + at the start if it's not a dice and doesn't start with a + or - (ex : 70, otherwise, will just return 0)
    if "d" not in dice_expression and not dice_expression.startswith(("+", "-")):
        dice_expression = "+" + dice_expression

    # Regex to find all dice components including negative values
    dice_parts = re.findall(r'([+-]?)(\d+)[dD](\d+)', dice_expression)
    # Regex to find all modifiers including negative values
    static_adds = re.findall(r'([+-]\d+)(?![dD])', dice_expression)

    dice = []
    modifier = 0

    # Calculate the totals for each dice part
    for sign, count, sides in dice_parts:
        multiplier = -1 if sign == '-' else 1
        count = int(count) * multiplier
        sides = int(sides)
        dice.append((count, sides))

    # Include static modifiers in the totals
    for add in static_adds:
        modifier += int(add)

    return dice, modifier

# Roll the dice and return the rolls and the total
    # Allows for negative dice (will be substracted from the total, minus 0)
def get_rolls(dice, modifier, is_minimized = False, is_maximized = False, reroll_1_and_2 = False):
    dice_text = ""

    # Create the roll text
    x = 0 
    for count, side in dice:
        if x == 0:
            sign = "" if count >= 0 else "-"
        else:
            sign = " - " if count < 0 else " + "
        dice_text += f"{sign}{abs(count)}d{side}"
        x += 1

    modifier_text = ""
    if modifier != 0:
        sign = " - " if modifier < 0 else " + "
        sign = "" if dice_text == "" and modifier >= 0 else sign

        modifier_text = f"{sign}{abs(modifier)}"
        dice_text += modifier_text

    # rolls = array of array, with rolls for each dice in a diff array
    rolls = []

    # Roll the dice and place the roll results in an array
        # the number of rolls should be = sum of the count of each dice
    if is_minimized:
        for count, _ in dice:
            sign = -1 if count < 0 else 1
            rolls.append([1*sign for _ in range(abs(count))])

    elif is_maximized:
        for count, side in dice:
            sign = -1 if count < 0 else 1
            rolls.append([side*sign for _ in range(abs(count))])
    else:
        for count, side in dice:
            sign = -1 if count < 0 else 1
            rolls.append([rd.randint(1, side)*sign for _ in range(abs(count))])

    # Reroll 1s and 2s
    if reroll_1_and_2:
        for i in range(len(rolls)):
            for j in range(len(rolls[i])):
                if rolls[i][j] in [1, 2]:
                    rolls[i][j] = rd.randint(1, dice[i][1])

    # add all the arrays together
    combined_rolls = [roll for dice_rolls in rolls for roll in dice_rolls]

    # Calc the roll text (add all the rolls together)
    roll_text = ""
    if len(combined_rolls) > 0:
        roll_text += "["
        for i, roll in enumerate(combined_rolls):
            if i == 0 and roll < 0:
                roll_text += "-"
            elif i > 0:
                roll_text += " + " if roll >= 0 else " - "
            roll_text += str(abs(roll))
        roll_text += "]"

    roll_text += modifier_text

    # Calculate the total including the modifier
    total = sum(combined_rolls) + modifier
    if total < 0:
        total = 0

    return dice_text, roll_text, total

# Escape characters so that they can be added to a js script directly
def escape_js_str(s):
    s = s.replace("\\", "\\\\")
    s = s.replace("\'", "\\\'")
    return s

def unlock_next_msg():
    # if file doesn't exist, return false
    if not os.path.exists(show_text_next_msg_file_path):
        return False
    
    with open(show_text_next_msg_file_path, 'r', encoding="utf-8") as file:
        lines = file.readlines()
    
    with open(show_text_next_msg_file_path, 'w', encoding="utf-8") as file:
        for line in lines:
            if line.strip() == 'export const is_locked = true;':
                file.write('export const is_locked = false;\n')
            else:
                file.write(line)

def is_next_msg_locked():
    # if file doesn't exist, return false
    if not os.path.exists(show_text_next_msg_file_path):
        return False

    with open(show_text_next_msg_file_path, 'r', encoding="utf-8") as file:
        contents = file.read()
        if 'export const is_locked = true' in contents:
            return True
    return False

# Write to one of the console apps
def write_to_show_text(data, json_obj="", is_narrator=False, is_game=False, is_dnd_chat=False, is_info=False, is_next_msg=False, lock=False, unlock=False, from_utils=False, is_text_only = False):
    # if file doesn't exist, skip
    if not os.path.exists(show_text_next_msg_file_path):
        return
    
    show_text_file_path = f"{react_path}/react_projects/showtext-react/src/showtext.js"
    show_text_user_file_path = f"{react_path}/react_projects/showtext-user-react/src/showtext.js"
    show_text_dnd_file_path = f"{react_path}/react_projects/showtext-dnd-react/src/showtext.js"
    show_text_info_file_path = f"{react_path}/react_projects/showtext-info-react/src/showtext.js"

    if is_info:
        file_path = show_text_info_file_path
    elif is_next_msg:
        file_path = show_text_next_msg_file_path
    elif is_game or is_dnd_chat:
        file_path = show_text_dnd_file_path
    else:
        file_path = show_text_file_path if not is_narrator else show_text_user_file_path

    # Return from function if the file is locked and unlock is False, only possible for is_next_msg
    if is_next_msg and is_next_msg_locked() and not unlock:
        return

    prefix_json = "export const json_str = "
    prefix_data = "export const data = "

    formatted_json = escape_js_str(json_obj)
    data_str = ""

    if is_text_only:
        data_str = data
        data_str = escape_js_str(data_str) # Otherwise will crash if contains any '
    elif data != "" and len(data) > 0:
        data = [list(item) for item in data]
        data_str = json.dumps(data) # Already escapes ", don't need to escape I think

    with open(file_path, 'w', encoding="utf-8") as file:
        # Write text
        file.write(prefix_data)
        if is_text_only:
            file.write(f"'{data_str}'" if data_str != "" else "") 
        else:
            file.write(f"{data_str}" if data_str != "" else 'null')
        file.write("\n")

        # Write json obj
        file.write(prefix_json)
        file.write(f"'{formatted_json}'" if json_obj != "" else 'null')
        file.write("\n")

        # Add 'export const is_locked = true' if lock = true
        if is_next_msg:
            file.write(f"export const is_locked = {'true' if lock else 'false'}")

def get_files_sorted_creation(rootDir, reverse = False):
    # Get a list of all .json files in the directory
    files = glob.glob(os.path.join(rootDir, '*.json'))

    # Sort the files by modification time, oldest first
    files.sort(key=lambda f: datetime.fromtimestamp(os.path.getctime(f)), reverse=reverse)
    
    return files

def case_insensitive_replace(source, old, new) -> Tuple[Any, Any]:
    # Check if there's a match first using re.search
    if re.search(re.escape(old), source, flags=re.IGNORECASE):
        # If there's a match, perform the replacement
        replaced_text = re.sub(re.escape(old), new, source, flags=re.IGNORECASE)
        return True, replaced_text
    else:
        # If no match is found, return False and the original source text
        return False, source
    
def capitalize_first_letter(text):
    return text[0].upper() + text[1:]  if len(text) > 0 else text 

def read_csv(filename, key_field):
    with open(filename, 'r') as file:
        reader = csv.DictReader(file)
        rows = {row[key_field].lower(): row for row in reader}
    return rows

def remove_system_prefix(text):
    pattern = r"\*?(system:)\*?\s?"

    # Replace the pattern with an empty string
    new_text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    return new_text.strip()

def replace_emotion_format_errors(text):
    # This function replaces ':' or ';' with ',' inside each match (which is content inside parentheses).
    def replacer(match):
        return match.group(0).replace(':', ',').replace(';', ',')

    # Use re.sub with the replacer function, capturing everything inside parentheses
    result = re.sub(r'\([^)]*\)', replacer, text)

    if result != text:
        print_log(f"WARNING: Emotion format error detected and replaced : Original : {text}", True)
    
    return result

def convert_text_segments_to_objs(msg_segments):
    return [{"segment_id": x, "text": segment_text} for x, segment_text in enumerate(msg_segments)]

def create_text_segment_objs(text):
    if not text:
        return None

    segmented_text = segment_text(remove_system_prefix(text))
    return convert_text_segments_to_objs(segmented_text)

def create_expression_obj(character, position, expression):
    return {"character": character, "position": position, "expression": expression}

def get_talent(talent_name, current_story, partial_match = False):
    talent_name_lower = talent_name.lower()

    for talent in current_story.get("talents", []):
        talent_lower = talent.lower()
        if talent_lower == talent_name_lower or (partial_match and (talent_name_lower in talent_lower or talent_lower in talent_name_lower)):
            return talent
    return None

def has_talent(talent_name, current_story, partial_match = False):
    return get_talent(talent_name, current_story, partial_match) is not None

# Extract the text in parenthesis, using regex
def extract_text_in_parenthesis(text):
    if text is None:
        return None

    match = re.search(r"\((.*?)\)", text)
    return match.group(1).lower() if match is not None else None

def get_order_text(order):
    if order == 1:
        return "1st"
    elif order == 2:
        return "2nd"
    elif order == 3:
        return "3rd"
    else:
        return str(order) + "th"
    
singular_words = read_csv(f'utils/singular_words.csv', 'word')

def singularize_name(name):
    if not name:
        return ""

    split_sentence = name.split(" ")

    # Remove 'the' at the start (aleady included in the text when using it)
    if split_sentence[0].lower() == "the":
        split_sentence = split_sentence[1:]

        # If was just 'the'
        if len(split_sentence) == 0:
            return name

    last_word = split_sentence[-1]

    # Check if the last word is in the singular words list, or if it ends with 'ss' (already singular)
    if last_word.lower().endswith('ss') or last_word.lower() in singular_words :
        return name

    singular_last_word = inflect_engine.singular_noun(last_word)

    # Will return false when not a plural noun
    if not singular_last_word:
        return name

    singularized_sentence = " ".join(split_sentence[:-1] + [singular_last_word])

    # print_log(f"Singularized name: {singularized_sentence}")

    return singularized_sentence

def join_with_and(list_of_items, join_word = "and"):
    if len(list_of_items) == 0:
        return ""
    elif len(list_of_items) == 1:
        return list_of_items[0]
    elif len(list_of_items) >= 2:
        return ", ".join(list_of_items[:-1]) + f" {join_word} " + list_of_items[-1]
    
def array_depth(arr):
    if isinstance(arr, list):
        if not arr:
            return 1
        return 1 + max(array_depth(item) for item in arr)
    return 0

# Same distribution as x number of random true false
def get_binomial_dist_result(x):
    number_of_heads = np.random.binomial(n=x, p=0.5)
    return number_of_heads

# Recursively go through all the fields in the dict and concatenate the values of the array in the given field, if it's a list
def find_all_occurences_field_in_dict(dict_obj, field_name):
    results = []

    if not isinstance(dict_obj, dict):
        return results
    
    # Loop through all fields
    for key, value in dict_obj.items():
        # if the key is found, add the value to the results
        if key == field_name:
            results += value if isinstance(value, list) else [value]
        # Recursively go through child dictionaries
        elif isinstance(value, dict):
            results += find_all_occurences_field_in_dict(value, field_name)
        # Recursively go through child lists
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    results += find_all_occurences_field_in_dict(item, field_name)
    return results

def print_special_text(text: str):
    # Regex pattern to match text inside #red# or #green# tags
    pattern = r'#(red|green|bold)#(.*?)#\1#'

    # Define a function that replaces the matched text with colorama properties
    def replace_color(match):
        color = match.group(1)
        colored_text = match.group(2)
        if color == 'red':
            return f"{Fore.RED}{Style.BRIGHT}{colored_text}{Style.RESET_ALL}"
        elif color == 'green':
            return f"{Fore.GREEN}{Style.BRIGHT}{colored_text}{Style.RESET_ALL}"
        elif color == 'bold':
            return f"{Style.BRIGHT}{colored_text}{Style.RESET_ALL}"
        return colored_text  # Default return if no color matches

    # Substitute the pattern with the corresponding colored text
    result_text = re.sub(pattern, replace_color, text)

    # Print the final colored text
    print(result_text)

def merge_config(config1, config2):
    # Start by copying config1 into merged_config
    merged_config = config1.copy()
    
    # Replace values of matching keys from config2
    for key, value in config2.items():
        merged_config[key] = value
    
    return merged_config

def create_folders(folders):
    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)