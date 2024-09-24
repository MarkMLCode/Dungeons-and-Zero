import math
import re
import random as rd
import os
# import Counter
from collections import Counter
from typing import Dict, List, Tuple, Any, Optional
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # Add the parent directory to sys.path

from utils.utils import extract_json_from_response, validate_unspecified, remove_parentheses, process_dice, read_csv, get_rolls, extract_int, has_talent, get_talent, extract_text_in_parenthesis, get_order_text, singularize_name, join_with_and, validate_bool, extract_float, print_log

from ai.dnd_server import get_proficiency_bonus, \
    get_long_stat_name, get_full_casters, get_half_casters, stat_to_modifier, get_opponent_health_status, get_bardic_inspiration_dice, get_stat_mod, get_roll_action_result, get_roll_action_result_one_reversed, are_opponents_surprised, extract_cr, get_damage_roll_by_cr, get_monsters_values, get_mc_health_status, get_monsters_single_value, get_monsters_hp, get_char_classes, get_max_spell_level, fix_group_cr_by_difficulty_level, get_cr_normalized_value, get_max_cr_current_level, get_cr_difference, raise_cr_by_one

is_linux = os.name == "posix"

# Spells info
full_casters = get_full_casters()
half_casters = get_half_casters()

ai_path = "ai/"
spell_path = f"{ai_path}spells"
spells_data = read_csv(f'{spell_path}/spells.csv', 'name')
domains_data = read_csv(f'{spell_path}/domain_spells.csv', 'id') # Can't use name as it's not unique
wild_magic_data = read_csv(f'{spell_path}/wild_magic.csv', 'description')
weapons_data = read_csv(f'{ai_path}tables/weapons.csv', 'name')
skills_data = read_csv(f'{ai_path}tables/skills.csv', 'name')
monsters_entry_names = read_csv(f'{ai_path}tables/monsters_entry_names.csv', 'name')
tokens_folder_path = f"../../react_projects/showtext-dnd-react/public/tokens"

def get_spell_level_from_text(text):
    if text is None:
        return None

    if isinstance(text, str) and text.lower() == "cantrip":
        return 0

    # Attempt to convert the text to a number
    level = extract_int(text)

    if level is None:
        print(f"ERROR: Invalid spell level {text}")
        return None

    # Clamp the level between 0 and 9
    if level > 9:
        return 9
    elif level < 0:
        return 0
    else:
        return level

#Checks if the text contains a saving throw and returns it.
def get_ability_name_short(text):
    if validate_unspecified(text) is None:
        return None

    saving_throws = ["str", "dex", "con", "int", "wis", "cha"]

    for throw in saving_throws:
        if throw == text[:3].lower(): # Check if the first 3 letters of the saving throw match the current saving throw
            return throw
    return None

def try_to_extract_number_from_word(original_text):
    text = original_text.lower()

    if text is None or text == "":
        return None
    elif text in ["one"]:
        return 1
    elif text in ["two", "multiple", "several", "many"]:
        return 2
    elif text in ["three", "countless"]:
        return 3
    else:
        return 1

# Decide which action has priority
def get_chosen_action(actions):
    is_casting_a_spell, is_attacking, is_using_item, is_using_skill, is_casting_spell_with_focus = actions

    # Decide priority of rolls
    if is_casting_a_spell and (is_casting_spell_with_focus or not is_using_item): # Spells have priority, unless it's an item not used as an arcane focus
        chosen_action = "spell"
    elif is_using_item:
        chosen_action = "consumable_magic_item"
    elif is_casting_a_spell:
        chosen_action = "spell"
    elif is_attacking:
        chosen_action = "attacking"
    elif is_using_skill:
        chosen_action = "skill"

    return chosen_action

def get_primary_main_action_type(text):
    if validate_unspecified(text) is None:
        return None

    primary_actions = ["skill", "attacking", "consumable_magic_item", "spell" ,"other"]

    for action in primary_actions:
        if action == text.lower(): 
            return action
        
    print_log(f"WARNING: Primary main action type not found: {text}", True)

    return None

def get_primary_situation_saving_throw(text):
    if validate_unspecified(text) is None:
        return None

    primary_situations = ["saving_throw_required", "trap_triggered", "trap_avoided", "potential_future_hazards", "other"]

    for situation in primary_situations:
        if situation == text.lower(): 
            return situation
        
    print_log(f"WARNING: Primary main situation saving throw not found: {text}", True)

    return None

def remove_duplicate_groups(combatant_groups):
    seen = set() 
    unique_groups = [] 
    removed_groups = []

    for group in combatant_groups:
        original_name = group['name'].lower()
        singular_name = singularize_name(original_name).lower()

        # Add to filtered list if neither name is seen
        if original_name not in seen and singular_name not in seen:
            unique_groups.append(group)  
            seen.add(original_name)  
            seen.add(singular_name) 
        else:
            removed_groups.append(group)

    return unique_groups, removed_groups  # Return the list of groups without duplicates

# Create an combatant (either for battle info, or for virtual combatant when casting spells)
def create_combatant(combatant_identifier, group_name, group, is_ranged = False):
    hp = 1
    status_effects = cr = ""
    is_spellcaster = is_named_npc = False
    entry_name = original_entry_name = None

    # In case the group is null (virtual combatant)
    if group is not None:
        hp = group.get("hp")
        status_effects = group.get("status_effects")
        cr = group.get("cr")
        is_spellcaster = group.get("is_spellcaster")
        entry_name = group.get("entry_name")
        original_entry_name = group.get("original_entry_name")
        is_named_npc = group.get("is_named_npc")

    combatant = {
        "identifier": combatant_identifier,
        "group_name": group_name,
        "cr": cr,
        "max_hp": hp,
        "hp": hp,
        "entry_name": entry_name, 
        "original_entry_name": original_entry_name,
        "is_named_npc": is_named_npc,
        "status_effects": status_effects,
        "is_spellcaster": is_spellcaster,
        "is_ranged": is_ranged # Usually set in post processing using the sheets
    }

    if original_entry_name is None:
        del combatant["original_entry_name"]

    if not is_named_npc:
        del combatant["is_named_npc"]

    return combatant

def get_combatant_identifier(group_name, nb, how_many):
    order_text = f"{get_order_text(nb)} " if how_many > 1 else ""
    return f"{order_text}{singularize_name(group_name)}"

def create_group(group_name, cr, hp, is_spellcaster, entry_name, is_named_npc, how_many = None, status_effects = None, original_entry_name = None):
    combatant_group = {
        "name": group_name,
        "how_many": how_many, 
        "cr": cr,
        "hp": hp, 
        "is_spellcaster": is_spellcaster,
        "entry_name": entry_name,
        "original_entry_name": original_entry_name,
        "is_named_npc": is_named_npc,
        "status_effects": status_effects
    }

    if how_many is None:
        del combatant_group["how_many"]

    if not is_named_npc:
        del combatant_group["is_named_npc"]

    if original_entry_name is None:
        del combatant_group["original_entry_name"]
    
    return combatant_group

# Create a group from the combatant obj
def get_group_from_combatant(combatant):
    group = create_group(combatant["group_name"], combatant.get("cr", "1"), combatant["max_hp"], combatant["is_spellcaster"], combatant.get("entry_name"), combatant.get("is_named_npc"), status_effects=combatant["status_effects"])
    return group

# Create groups from the combatant objs
def get_groups_from_combatants(combatants):
    groups_obj = {}

    for combatant in combatants:
        group_name = combatant["group_name"]
        if group_name not in groups_obj:
            groups_obj[group_name] = get_group_from_combatant(combatant)

    # Return all groups
    return list(groups_obj.values())

# Go through each groups, recalibrate all group to have less than max combatants (ex: 4) and create the combatants for each group
def create_group_combatants(combatant_groups, max_combatants, total_combatants_nb, difficulty_level, current_story,  existing_combatants = None, skip_cr_increase = False, is_allied_characters = False):

    # If 4 sepparate combatants or more, set how_many = 1 for all
    if len(combatant_groups) >= max_combatants:
        for group in combatant_groups:
            group["how_many"] = 1
        # Remove extra groups in reverse order if the number of groups exceeds max_combatants
        if len(combatant_groups) > max_combatants:
            combatant_groups = combatant_groups[:max_combatants]
    # Go through each combatants 1 by 1 and remove combatants until total combatants is 4, keeping the minimum to 1
    elif total_combatants_nb > max_combatants:
        while total_combatants_nb > max_combatants:
            for group in combatant_groups:
                if total_combatants_nb > max_combatants and group["how_many"] > 1:
                    group["how_many"] -= 1
                    total_combatants_nb -= 1

    combatants = []
    current_cr_counter = Counter([combatant.get("cr", "1") for combatant in existing_combatants]) if existing_combatants is not None else None

    combatant_groups = fix_group_cr_by_difficulty_level(combatant_groups, difficulty_level, current_story, current_cr_counter, skip_cr_increase, is_allied_characters)
    
    # Create combatants for each group
    for group in combatant_groups:
        how_many = group["how_many"]
        group_name = group["name"]

        for x in range(how_many):
            nb = x + 1
            
            combatant_identifier = get_combatant_identifier(group_name, nb, how_many)
            combatant = create_combatant(combatant_identifier, group_name, group)

            combatants.append(combatant)

    return combatants, combatant_groups

def get_status_effects(response_content):
    roll_name = "GetStatusEffects"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None

    print_log(f"{roll_name}: Found in prompt: {response_content}")

    opponent_groups = roll_obj.get("opponent_groups")

    if opponent_groups is None or len(opponent_groups) == 0:
        print_log(f"WARNING: No opponents found in status effects", True)
        return None

    groups_with_status_effects = []

    for opponent_group in opponent_groups:
        name = validate_unspecified(opponent_group.get("name"))
        status_effects = validate_unspecified(opponent_group.get("status_effect"))

        if name is None:
            print(f"ERROR: Group name not found, skipping")
            continue

        print_log(f"Group name: {name}, status_effects: {status_effects}")

        # status effect = None should be returned, in case a previous status needs to be overwritten
        groups_with_status_effects.append((name, status_effects))

    return groups_with_status_effects

def has_matching_token_image(identity):
    formatted_identity = identity.replace(" ", "_").lower()
    for file_name in os.listdir(tokens_folder_path):
        image_name = os.path.splitext(file_name)[0]
        if formatted_identity == image_name.lower():
            return True
    return False

def extract_race_from_text(identity):
    if identity is None:
        return None, None
    
    race = None
    identity_text = identity.lower()  # Convert to lowercase for case-insensitive matching

    # Define regex pattern for races, including both exact and partial matches
    race_patterns = {
        "dwarf": r'\b\w*dwar\w*\b|\b\w*dwarv\w*\b',   
        "elf": r'\b\w*half-elf\w*\b|\b\w*half-elv\w*\b|\b\w*elf\w*|\b\w*elv\w*\b', 
        "halfling": r'\b\w*halfling\w*\b', 
        "human": r'\b\w*human\w*\b', 
        "dragonborn": r'\b\w*dragonborn\w*\b', 
        "gnome": r'\b\w*gnome\w*\b|\b\w*gnomi\w*\b', 
        "half-orc": r'\b\w*half-orc\w*\b', 
        "tiefling": r'\b\w*tiefling\w*\b'
    }

    # Check if the identity contains a race and remove it
    for key, pattern in race_patterns.items():
        if re.search(pattern, identity_text):
            race = key
            identity_text = re.sub(pattern, '', identity_text)
            break

    # Remove extra spaces and return the cleaned identity
    cleaned_identity = ' '.join(identity_text.split())

    return race, cleaned_identity

def process_entry_name(entry_name, identity, is_named_npc, cr):
    if entry_name is None:
        return None, None, cr

    # Remove parenthesis from the entry name
    entry_name = remove_parentheses(entry_name)
    original_entry_name = matched_entry_name = None

    # If the monster is a named npc, try to see if a matching token image exists
    if is_named_npc and identity is not None and has_matching_token_image(identity):
        matched_entry_name = identity

    # If not a named npc, or if it's name didn't match any tokens, try to match it's entry_name
    if matched_entry_name is None:
        matched_entry_name = get_corresponding_entry_name(entry_name)

    race, entry_name_no_race = extract_race_from_text(entry_name) # Try to extract the race from the entry name

    # Try removing the race from the entry name if it exists to see if there's a match for that.
    if not matched_entry_name and entry_name_no_race is not None:
        matched_entry_name = get_corresponding_entry_name(entry_name_no_race)

    # Overwrite the CR with the cr of the corresponding entry if it exists (and not a named npc)
        # Match before potentially adding the race, since that is not included in the entry names table
    if not is_named_npc and matched_entry_name:
        cr = get_corresponding_entry_cr(matched_entry_name)

    # Add the race to the entry name if it exists for this token
    if matched_entry_name:
        if race is None:
            race, _ = extract_race_from_text(identity) # Try to extract the race from the identity
            
        race_entry_name = matched_entry_name + "_" + race if race is not None else None

        if race_entry_name is not None and has_matching_token_image(race_entry_name):
            matched_entry_name = race_entry_name

    # If the matched entry name is different, replace the entry name
    if matched_entry_name != "" and matched_entry_name.lower() != entry_name.lower():
        original_entry_name = entry_name
        entry_name = matched_entry_name
        print_log(f"Entry name {original_entry_name} replaced by {entry_name}")

    # if no matched entry name is found, set the entry name to empty
    elif matched_entry_name == "" and entry_name != "":
        original_entry_name = entry_name
        entry_name = None
        print_log(f"Entry name {entry_name} not found in the database")
    
    return entry_name, original_entry_name, cr

def get_battle_info(response_content, current_story, config_dnd, is_additional_opponents = False):
    roll_name = "GetBattleInfo"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None

    print_log(f"{roll_name}: Found in prompt: {response_content}")

    difficulty_level = validate_unspecified(roll_obj.get("difficulty_level"))

    if difficulty_level is None or difficulty_level.lower() not in ["easy", "medium", "hard"]:
        difficulty_level = "medium"

    opponent_group_label = "additional_opponent_groups" if is_additional_opponents else "opponent_groups"
    opponent_obj_groups = roll_obj.get(opponent_group_label)

    if opponent_obj_groups is None or len(opponent_obj_groups) == 0:
        print_log(f"WARNING: No opponents found in battle info", True)
        return None
    
    current_battle_info = current_story.get("battle_info") 
    existing_opponents = current_battle_info.get("opponents") if current_battle_info is not None else []
    max_opponents = config_dnd["max_opponents"]

    total_opponents_nb = 0
    opponent_groups = []

    for opponent_obj_group in opponent_obj_groups:
        identity = validate_unspecified(opponent_obj_group.get("identity"))
        how_many = extract_int(opponent_obj_group.get("how_many"))
        cr = extract_cr(opponent_obj_group.get("cr"))
        entry_name = validate_unspecified(opponent_obj_group.get("entry_name"))
        is_named_npc = validate_bool(opponent_obj_group.get("is_named_npc"))

        if cr is None:
            print(f"ERROR: Challenge rating not found, defaulting to 1")
            cr = 1
            continue

        entry_name, original_entry_name, cr = process_entry_name(entry_name, identity, is_named_npc, cr)
        is_spellcaster = validate_bool(opponent_obj_group.get("is_spellcaster"))

        print_log(f"identity: {identity}, how_many: {how_many}, cr: {cr}")

        if identity is None:
            print_log(f"Identity not found, skipping")
            continue

        if is_named_npc:
            # Check if the named npc already exists
            if any([opponent["group_name"].lower() == identity.lower() for opponent in existing_opponents]):
                print_log(f"Named NPC {identity} already exists, skipping")
                continue

            how_many = 1 # Named NPCs are unique
        elif how_many is None and opponent_obj_group.get("how_many") in ["multiple", "several", "many", "more"]:
            how_many = max_opponents
        elif how_many is None:
            how_many = 1 # Default to 1 if not specified
        elif how_many > max_opponents:
            print_log(f"Too many opponents ({how_many}), limiting to {max_opponents}")
            how_many = max_opponents

        # Set max cr for the current level
        max_cr = get_max_cr_current_level(current_story, how_many, max_opponents, difficulty_level)
        cr_difference = get_cr_difference(cr, max_cr) - 1 # -1 because it will be lowered by 1 automatically later on

        # If the cr is too high, limit it to the max cr
        if cr_difference > 0:
            # Loop to raise the max cr by 1 for each 4 cr difference
            while cr_difference >= 4:
                max_cr = raise_cr_by_one(max_cr)
                cr_difference -= 4

            print_log(f"CR {cr} too high for group {identity}, limiting to {max_cr}")
            cr = max_cr

        opponent_group = create_group(identity.capitalize(), cr, None, is_spellcaster, entry_name, is_named_npc, how_many, original_entry_name = original_entry_name) # Hp set later, in cpost processing
        
        total_opponents_nb += how_many
        opponent_groups.append(opponent_group)

    if len(opponent_groups) == 0:
        print_log(f"All opponents removed from battle info")
        return None

    current_replaced_opponents = current_battle_info.get("replaced_opponents", []) if current_battle_info is not None else []

    # If additional opponents, add them to the existing groups    
    opponents = []
    total_max_opponents = max_opponents if not is_additional_opponents else config_dnd["max_additional_opponents"] # Allow for 1 more when adding opponents, so at least 1 can be added.

    if not is_additional_opponents:
        # Remove duplicated groups
        opponent_groups, removed_groups = remove_duplicate_groups(opponent_groups)
        if len(removed_groups) > 0:
            print_log(f"Removed duplicated groups: {removed_groups}")

        # Reverse group order (put more important groups towards the backm to avoid replacing them when adding additional opponents)
        opponent_groups = list(reversed(opponent_groups))

        opponents, opponent_groups = create_group_combatants(opponent_groups, total_max_opponents, total_opponents_nb, difficulty_level, current_story)
    else:
        current_battle_info = current_story.get("battle_info") 

        if current_battle_info is None:
            print(f"ERROR: No current battle info found for battle_info_additional_opponents")
            return None

        # Determine how many additional opponents can be added (at most 2 can be added at once)
        max_additional_opponents_for_groups = min(total_opponents_nb, 2)
        
        additional_opponents, _ = create_group_combatants(opponent_groups, max_additional_opponents_for_groups, total_opponents_nb, difficulty_level, current_story, existing_opponents)

        # Add to existing opponents (up to the nb of additional_opponents)
        for x in range(len(additional_opponents)):
            if len(existing_opponents) >= total_max_opponents or len(additional_opponents) == 0:
                break

            additional_opponent = additional_opponents.pop(0)
            existing_opponents.append(additional_opponent)

        combined_total_opponents = total_opponents_nb + len(existing_opponents)

        # If the additional opponents > maximum, need to remove some of the existing opponents
        if combined_total_opponents >= total_max_opponents:

            # Priorise replacing opponents with 0 hp first
            #   if nb defeated opponents > nb of additional opponents, then will only replace opponents with 0 hp
            nb_defeated = sum([1 for opponent in existing_opponents if opponent["hp"] == 0])
            nb_non_defeated_can_be_replaced = max(len(additional_opponents) - nb_defeated, 0)
            
            # Sort the opponents by cr
            opponents_sorted_by_cr = sorted(existing_opponents, key=lambda x: get_cr_normalized_value(x["cr"]))

            # Remove named npcs and defeated opponents from the list of non defeated opponents that can be replaced
            replacable_opponents_sorted_by_cr = [opponent for opponent in opponents_sorted_by_cr if not opponent.get("is_named_npc", False) and opponent["hp"] != 0]

            # Non defeated opponents can be replaced (could be 0)
            replacable_non_defeated_opponents = replacable_opponents_sorted_by_cr[:nb_non_defeated_can_be_replaced]
            nb_non_defeated_replaced = 0

            # Replace existing opponents with additional opponents
            for x, opponent in enumerate(existing_opponents):
                if len(additional_opponents) == 0:
                    break

                # Replace opponents with 0 hp first
                #   if not enough opponents with 0 hp, replace the first opponents in the list (more important enemies at the back of the list)
                if opponent["hp"] == 0 or opponent in replacable_non_defeated_opponents:
                    current_replaced_opponents.append(opponent)
                    existing_opponents[x] = additional_opponents.pop(0)

                    # If we just replaced a non-defeated opponent, increment the counter
                    if opponent["hp"] != 0:
                        nb_non_defeated_replaced += 1

        # Create object counting how many opponents are in each group
        opponent_group_total_counter = Counter([opponent["group_name"] for opponent in existing_opponents])
        opponent_group_current_count = {}

        # Refresh the identifier for each opponent, taking into account the new ones.
        for opponent in existing_opponents:
            group_name = opponent["group_name"]
            how_many = opponent_group_total_counter[group_name]

            opponent_group_current_count[group_name] = opponent_group_current_count.get(group_name, 0) + 1
            opponent["identifier"] = get_combatant_identifier(group_name, opponent_group_current_count[group_name], how_many)
        
        opponents = existing_opponents

    battle_info = {
        "id": None,
        "battle_status": "ongoing", # battle_status,
        "ally_turn": 0,
        "enemy_turn": 0,
        "replaced_opponents": current_replaced_opponents,
        #"groups": opponent_groups,
        "opponents": opponents,
        "allies": []
    }

    print_log(f'battle_info: {battle_info}')

    return battle_info

def get_updated_battle_info(response_content):
    roll_name = "GetUpdatedBattleInfo"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None

    battle_status = validate_unspecified(roll_obj.get("battle_status"))
    if battle_status is None:
        battle_status = "ongoing"

    # Determine if there are additional opponents (their identity will be determine in a separate prompt)
    additional_opponents = validate_unspecified(roll_obj.get("additional_opponents"), True)

    battle_info = {
        "battle_status": battle_status
    }

    print_log(f'battle_info: {battle_info}, found in prompt: {response_content}')

    return (battle_info, additional_opponents)

def get_allied_characters(response_content, current_story, config_dnd):
    roll_name = "GetAlliedCharacters"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None

    print_log(f"{roll_name}: Found in prompt: {response_content}")

    ally_obj_groups = roll_obj.get("allied_character_groups")

    if ally_obj_groups is None or len(ally_obj_groups) == 0:
        print_log(f"No ally found in battle info")
        return None

    difficulty_level = current_story.get("difficulty_level") # Don't want all level to change from battle to battle.

    max_allies = config_dnd["max_allies"]

    total_opponents_nb = 0
    ally_groups = []

    for opponent_obj_group in ally_obj_groups:
        identity = validate_unspecified(opponent_obj_group.get("identity"))
        how_many = extract_int(opponent_obj_group.get("how_many"))
        cr = extract_cr(opponent_obj_group.get("cr"))
        entry_name = validate_unspecified(opponent_obj_group.get("entry_name"))
        is_named_npc = validate_bool(opponent_obj_group.get("is_named_npc"))

        if cr is None:
            print(f"ERROR: Challenge rating not found, defaulting to 1")
            cr = 1
            continue
        
        entry_name, original_entry_name, cr = process_entry_name(entry_name, identity, is_named_npc, cr)

        is_spellcaster = validate_bool(opponent_obj_group.get("is_spellcaster"))

        print_log(f"identity: {identity}, how_many: {how_many}, cr: {cr}")

        if identity is None:
            print_log(f"Identity not found, skipping")
            continue

        if is_named_npc:
            how_many = 1 # Named NPCs are unique
        elif how_many is None and opponent_obj_group.get("how_many") in ["multiple", "several", "many", "more"]:
            how_many = max_allies
        elif how_many is None:
            how_many = 1 # Default to 1 if not specified
        elif how_many > max_allies:
            print_log(f"Too many allies ({how_many}), limiting to {max_allies}")
            how_many = max_allies

        # Set max cr for the current level
        max_cr = get_max_cr_current_level(current_story, how_many, max_allies, difficulty_level)
        cr_difference = get_cr_difference(cr, max_cr) - 1 # -1 because it will be lowered by 1 automatically later on

        # If the cr is too high, limit it to the max cr
        if cr_difference > 0:
            # Loop to raise the max cr by 1 for each 4 cr difference
            while cr_difference >= 4:
                max_cr = raise_cr_by_one(max_cr)
                cr_difference -= 4

            print_log(f"CR {cr} too high for group {identity}, limiting to {max_cr}")
            cr = max_cr

        opponent_group = create_group(identity.capitalize(), cr, None, is_spellcaster, entry_name, is_named_npc, how_many, original_entry_name = original_entry_name) # Hp set later, in cpost processing
        
        total_opponents_nb += how_many
        ally_groups.append(opponent_group)

    if len(ally_groups) == 0:
        print_log(f"All allies removed from battle info")
        return None
    
    ally_groups, removed_groups = remove_duplicate_groups(ally_groups)
    if len(removed_groups) > 0:
        print_log(f"Removed duplicated groups: {removed_groups}")

    allied_characters, ally_groups = create_group_combatants(ally_groups, max_allies, total_opponents_nb, difficulty_level, current_story, skip_cr_increase=True, is_allied_characters=True)

    print_log(f'Allied characters: {allied_characters}')

    return allied_characters

def get_shared_class_values(roll_obj):
    # Fighter
    using_action_surge = validate_bool(roll_obj.get("uses_action_surge"))
    using_second_wind = validate_bool(roll_obj.get("uses_second_wind"))

    # Paladin
    using_smite = validate_bool(roll_obj.get("uses_smite"))
    using_lay_on_hands = validate_bool(roll_obj.get("uses_lay_on_hands"))

    # Monk
    using_flurry_of_blows = validate_bool(roll_obj.get("uses_flurry_of_blows"))
    using_patient_defense = validate_bool(roll_obj.get("uses_dodge"))

    # Sorcerer
    using_heightened_spell = validate_bool(roll_obj.get("uses_heightened_spell"))
    using_twinned_spell = validate_bool(roll_obj.get("uses_twinned_spell"))

    # Bard
    using_bardic_inspiration = validate_bool(roll_obj.get("uses_bardic_inspiration"))
    using_unsettling_words = validate_bool(roll_obj.get("uses_unsettling_words"))

    return using_action_surge, using_second_wind, using_smite, using_lay_on_hands, using_flurry_of_blows, using_patient_defense, using_heightened_spell, using_twinned_spell, using_bardic_inspiration, using_unsettling_words

def get_special_abilities_json_names(special_abilities):
    return ["main_action_is_" + special_ability.replace(" ", "_").lower() for special_ability in special_abilities]

class Viewer_Decision_Object:
    def __init__(self, action_surge, second_wind, smite, lay_on_hands, flurry_of_blows, patient_defense, switch_rage_status, reckless_attack, heightened_spell, twinned_spell, bardic_inspiration, unsettling_words):
        self.action_surge = action_surge
        self.second_wind = second_wind
        self.smite = smite
        self.lay_on_hands = lay_on_hands

        self.flurry_of_blows = flurry_of_blows
        self.patient_defense = patient_defense
        self.switch_rage_status = switch_rage_status
        self.reckless_attack = reckless_attack

        self.heightened_spell = heightened_spell
        self.twinned_spell = twinned_spell
        self.bardic_inspiration = bardic_inspiration
        self.unsettling_words = unsettling_words

    def extract(self):
        return self.action_surge, self.second_wind, self.smite, self.lay_on_hands, self.flurry_of_blows, self.patient_defense, self.switch_rage_status, self.reckless_attack, self.heightened_spell, self.twinned_spell, self.bardic_inspiration, self.unsettling_words

def get_answer_to_viewer_decisions(response_content):
    roll_name = "GetAnswerToViewerDecisions"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None
    
    # Fighter, Paladin or Monk
    using_action_surge, using_second_wind, using_smite, using_lay_on_hands, using_flurry_of_blows, using_patient_defense, using_heightened_spell, using_twinned_spell, using_bardic_inspiration, using_unsettling_words = get_shared_class_values(roll_obj)

    # Barbarian
    start_raging = validate_bool(roll_obj.get("start_raging")) # Can only be true if not already raging
    stop_raging = validate_bool(roll_obj.get("stop_raging")) # Can only be true if already raging

    switch_rage_status = start_raging or stop_raging # Can't both be true, since only one or the other is present in the json
    using_reckless_attack = validate_bool(roll_obj.get("attack_recklessly"))
    
    print_log(f"\n{roll_name}: Found in prompt: {response_content}")

    return Viewer_Decision_Object(using_action_surge, using_second_wind, using_smite, using_lay_on_hands, using_flurry_of_blows, using_patient_defense, switch_rage_status, using_reckless_attack, using_heightened_spell, using_twinned_spell, using_bardic_inspiration, using_unsettling_words)

class Roll_Object:
    def __init__(self, chosen_action, skill, smite, lay_on_hands, action_surge, second_wind, flurry_of_blows, patient_defense, special_ability, heightened_spell, twinned_spell, bardic_inspiration, unsettling_words):
        self.chosen_action = chosen_action
        self.skill = skill
        self.smite = smite
        self.lay_on_hands = lay_on_hands
        self.action_surge = action_surge
        self.second_wind = second_wind
        self.flurry_of_blows = flurry_of_blows
        self.patient_defense = patient_defense
        self.special_ability = special_ability
        self.heightened_spell = heightened_spell
        self.twinned_spell = twinned_spell
        self.bardic_inspiration = bardic_inspiration
        self.unsettling_words = unsettling_words

    def extract(self):
        return self.chosen_action, self.skill, self.smite, self.lay_on_hands, self.action_surge, self.second_wind, self.flurry_of_blows, self.patient_defense, self.special_ability, self.heightened_spell, self.twinned_spell, self.bardic_inspiration, self.unsettling_words

def get_roll(response_content, current_story, setup_aid):
    roll_name = "GetRoll"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None

    is_attacking = validate_bool(roll_obj.get("main_action_is_attacking"))
    is_casting_a_spell = validate_bool(roll_obj.get("main_action_is_casting_a_spell"))
    is_using_skill = validate_bool(roll_obj.get("main_action_is_using_one_or_more_skill"))
    is_using_an_item = validate_bool(roll_obj.get("main_action_is_using_consumable_magic_item"))

    # Counts as spell when using an arcane focus or holy symbol
    is_casting_spell_with_holy_symbol = validate_bool(roll_obj.get("is_casting_spell_with_holy_symbol")) 
    is_casting_spell_with_arcane_focus = validate_bool(roll_obj.get("is_casting_spell_with_arcane_focus")) 
    is_casting_spell_with_focus = is_casting_spell_with_holy_symbol or is_casting_spell_with_arcane_focus
    is_casting_a_spell = is_casting_a_spell or is_casting_spell_with_focus

    skill_name = validate_unspecified(roll_obj.get("skill_name")) 
    uses_animal_companion = validate_bool(roll_obj.get("uses_animal_companion")) # Not actually used for anything

    # Fighter, Paladin or Monk
    using_action_surge, using_second_wind, using_smite, using_lay_on_hands, using_flurry_of_blows, using_patient_defense, using_heightened_spell, using_twinned_spell, using_bardic_inspiration, using_unsettling_words = get_shared_class_values(roll_obj)

    is_in_battle = current_story.get("battle_info") is not None

    special_abilities = current_story.get("special_abilities", [])
    special_abilities_json_names = get_special_abilities_json_names(special_abilities)
    is_attempting_special_ability = False
    
    for special_abilitiy_json_name in special_abilities_json_names:
        special_ability_value = validate_bool(roll_obj.get(special_abilitiy_json_name))

        # If special ability used
        if special_ability_value:
            is_attempting_special_ability = True

    # The chosen action is the one with the highest priority
    primary_main_action_type = get_primary_main_action_type(roll_obj.get("primary_main_action_type"))

    # When no action chosen, but is using a 'battle' ability, set it to attacking
    if primary_main_action_type == "other" and is_in_battle and (using_action_surge or using_smite or using_flurry_of_blows or using_patient_defense):
        primary_main_action_type = "attacking"
        is_attacking = True # Needs to be set, otherwise roll will be skipped further down
    # Casting spell when using metamagic
    elif primary_main_action_type == "other" and (using_heightened_spell or using_twinned_spell):
        primary_main_action_type = "spell"
        is_casting_a_spell = True
    # When dodging in battle, and using skill acrobatics (or dodge by mistake), can be assumed want to attack too (otherwise might just dodge with nothing else).
    elif primary_main_action_type == "skill" and is_in_battle and using_patient_defense and skill_name is not None and (skill_name.lower().startswith("acrobatics") or skill_name.lower().startswith("dodge")):
        primary_main_action_type = "attacking"
        is_attacking = True

    # Determine if the main action type is special ability (don't use it in battle if oob only, unless not attacking or casting a spell)
    can_use_special_ability = not is_in_battle or primary_main_action_type not in ["attacking", "spell"] if current_story.get("special_ability_oob_only", False) else True
    is_using_special_ability = False

    # Skill tied to special ability
    if is_attempting_special_ability and can_use_special_ability:
        primary_main_action_type = "skill"
        is_using_special_ability = True
        
    # describe_main_action = validate_unspecified(roll_obj.get("describe_main_action"))  # Not used for now

    # If no roll is needed, return empty roll
        # Doesn't apply for lay on hands, replaced by spell further down
    if not is_attacking and not is_casting_a_spell and not is_using_skill and not is_using_an_item and not using_lay_on_hands and not is_using_special_ability:
        print_log(f'{roll_name} : No roll needed : {response_content}')
        # No roll needed, but still want to return whether started raging or using smite
        return Roll_Object(None, None, using_smite, using_lay_on_hands, using_action_surge, using_second_wind, using_flurry_of_blows, using_patient_defense, is_using_special_ability, using_heightened_spell, using_twinned_spell, using_bardic_inspiration, using_unsettling_words)
    
    # If the primary main action was defined by the ai, use that (unless it's "other", want to use the priority system then)
        # Otherwise, use the default priority
    if primary_main_action_type is not None and primary_main_action_type != "other":
        chosen_action = primary_main_action_type
    else:
        actions = (is_casting_a_spell, is_attacking, is_using_an_item, is_using_skill, is_casting_spell_with_focus)
        chosen_action = get_chosen_action(actions)

    print_log(f"\n{roll_name}: Chosen action: {chosen_action}, Skill check: {is_using_skill}, Attack roll: {is_attacking}, is_casting_a_spell: {is_casting_a_spell}, is_using_an_item: {is_using_an_item}, is_using_special_ability:  {is_using_special_ability}, Skill: {skill_name if skill_name != '' else 'None'}{(', uses_animal_companion: ' + str(uses_animal_companion)) if roll_obj.get('uses_animal_companion') is not None else ''}. Found in prompt: {response_content}")

    return Roll_Object(chosen_action, is_using_skill, using_smite, using_lay_on_hands, using_action_surge, using_second_wind, using_flurry_of_blows, using_patient_defense, is_using_special_ability, using_heightened_spell, using_twinned_spell, using_bardic_inspiration, using_unsettling_words)

class Roll_Attack_Object:
    def __init__(self, opponent_identity, target_number, target_approximate_location_known, weapon_used, damage_type, is_ranged_attack, roll_stat, is_hidden, is_sneak_attack, is_favored_enemy):
        self.opponent_identity = opponent_identity
        self.target_number = target_number
        self.target_approximate_location_known = target_approximate_location_known
        self.weapon_used = weapon_used
        self.damage_type = damage_type
        self.is_ranged_attack = is_ranged_attack
        self.roll_stat = roll_stat
        self.is_hidden = is_hidden
        self.is_sneak_attack = is_sneak_attack
        self.is_favored_enemy = is_favored_enemy

    def extract(self):
        return self.opponent_identity, self.target_number, self.target_approximate_location_known, self.weapon_used, self.damage_type, self.is_ranged_attack, self.roll_stat, self.is_hidden, self.is_sneak_attack, self.is_favored_enemy

def get_roll_attack(response_content, current_story):
    roll_name = "GetRollAttack"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None

    opponent_identity = validate_unspecified(roll_obj.get("target_identity"))
    target_number = extract_int(roll_obj.get("target_number"))
    target_approximate_location_known = validate_bool(roll_obj.get("target_approximate_location_known"))
    weapon_used = validate_unspecified(roll_obj.get("weapon_used"))
    # remove weapon parenthesis if there is any
    weapon_used = remove_parentheses(weapon_used)
    damage_type = validate_unspecified(roll_obj.get("damage_type"))

    is_ranged_attack = validate_bool(roll_obj.get("is_ranged_attack"))

    roll_stat = get_ability_name_short(roll_obj.get("stat"))
    is_hidden = validate_bool(roll_obj.get("is_hidden"))

    is_sneak_attack = validate_bool(roll_obj.get("is_sneak_attack"))
    is_favored_enemy = False

    favored_enemy_talent = get_talent("favored enemy", current_story, partial_match=True)
    if favored_enemy_talent is not None:
        favored_enemy_name = extract_text_in_parenthesis(favored_enemy_talent)
        is_favored_enemy = validate_bool(roll_obj.get(f"opponent_is_{favored_enemy_name}"))

    if roll_stat is None:
        print(f'ERROR : Missing roll info in {roll_name} : {response_content}')
        return None

    is_sneak_attack_text = f", sneak_attack: {is_sneak_attack}" if roll_obj.get("is_sneak_attack") is not None else ""

    print_log(f"\n{roll_name}: opponent_identity: {opponent_identity}, target_approximate_location_known: {target_approximate_location_known}, weapon_used: {weapon_used}, Stat: {roll_stat}, is_hidden: {is_hidden}{is_sneak_attack_text}. Found in prompt: {response_content}")

    return Roll_Attack_Object(opponent_identity, target_number, target_approximate_location_known, weapon_used, damage_type, is_ranged_attack, roll_stat, is_hidden, is_sneak_attack, is_favored_enemy)

class Roll_Skill_Object:
    def __init__(self, roll_skill, roll_dc, roll_stat, reason, special_ability):
        self.roll_skill = roll_skill
        self.roll_dc = roll_dc
        self.roll_stat = roll_stat
        self.reason = reason
        self.special_ability = special_ability

    def extract(self):
        return self.roll_skill, self.roll_dc, self.roll_stat, self.reason, self.special_ability

def convert_text_dc_to_int(dc_text):
    if dc_text is None:
        return None
    
    dc_text = dc_text.lower()
    dc_int = None

    if dc_text == "easy":
        dc_int = 10
    elif dc_text == "medium":
        dc_int = 15
    elif dc_text == "hard":
        dc_int = 20
    elif dc_text == "very hard":
        dc_int = 25
    elif dc_text == "nearly impossible":
        dc_int = 30

    return dc_int

def get_roll_skill(response_content):
    roll_name = "GetRollSkill"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None

    roll_skill = validate_unspecified(roll_obj.get("main_skill_used"))
    reason = roll_obj.get("why")
    roll_dc = extract_int(roll_obj.get("skill_DC"))
    roll_stat = get_ability_name_short(roll_obj.get("stat"))

    # Attempt to convert text to int if it's not already
    if roll_dc is None:
        roll_dc_text = validate_unspecified(roll_obj.get("skill_DC"))
        roll_dc = convert_text_dc_to_int(roll_dc_text)
    
    if roll_dc is None or roll_stat is None:
        print(f'ERROR : Missing roll info in {roll_name} : {response_content}')
        return None

    print_log(f"\n{roll_name}: Skill: {roll_skill if roll_skill != '' else 'None'}, DC: {roll_dc}, Stat: {roll_stat}, Reason: {reason} Found in prompt: {response_content}")

    return Roll_Skill_Object(roll_skill, roll_dc, roll_stat, reason, None)

def get_roll_skill_special_ability(response_content):
    roll_name = "GetRollSkillSpecialAbility"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None

    reason = roll_obj.get("why")
    skill = validate_unspecified(roll_obj.get("skill"))
    special_ability = validate_unspecified(roll_obj.get("special_ability"))
    roll_dc = extract_int(roll_obj.get("skill_DC"))

    # Attempt to convert text to int if it's not already
    if roll_dc is None:
        roll_dc_text = validate_unspecified(roll_obj.get("skill_DC"))
        roll_dc = convert_text_dc_to_int(roll_dc_text)
    
    # If still none
    if roll_dc is None:
        print(f'ERROR : Missing roll info in {roll_name} : {response_content}')
        return None

    print_log(f"\n{roll_name}: DC: {roll_dc}, Reason: {reason}. Found in prompt: {response_content}")

    return Roll_Skill_Object(skill, roll_dc, None, reason, special_ability)

def extract_magic_values(magic_obj, is_ranged_spell_attk = False):
    ranged_attk_text = "is_ranged_spell_attk" if is_ranged_spell_attk else "is_ranged_attk"

    target = validate_unspecified(magic_obj.get("target"))
    target_identity = validate_unspecified(magic_obj.get("target_identity"))
    saving_throw = get_ability_name_short(magic_obj.get("saving_throw"))
    target_number = extract_int(magic_obj.get("target_number"))
    is_ranged_attk = validate_bool(magic_obj.get(ranged_attk_text))

    damage_type = validate_unspecified(magic_obj.get("damage_type"))

    damage_dice = validate_unspecified(magic_obj.get("damage_dice"))
    saves_half = validate_bool(magic_obj.get("saves_half"))
    is_aoe = validate_bool(magic_obj.get("is_aoe"))

    # AOE are always considered 'ranged', but they are not ranged attacks (ranged attacks would have only 1 target)
    if is_aoe and is_ranged_attk:
        is_ranged_attk = False

    print_text = f"target: {target}, target_identity: {target_identity}, target_number: {target_number}, saving_throw: {saving_throw}, damage_type: {damage_type}, damage_dice, {damage_dice}, saves_half: {saves_half}, is_aoe: {is_aoe}, {ranged_attk_text}: {is_ranged_attk}"

    return target, target_identity, target_number, saving_throw, is_ranged_attk, damage_type, damage_dice, saves_half, is_aoe, print_text

class Cast_Spell_Object:
    def __init__(self, spell_name, spell_level, target, target_identity, target_number, saving_throw, is_spell_attk, damage_dice, saves_half, damage_type, is_aoe, is_healing, available_to_classes):
        self.spell_name = spell_name
        self.spell_level = spell_level
        self.target = target
        self.target_identity = target_identity
        self.target_number = target_number
        self.saving_throw = saving_throw
        self.is_spell_attk = is_spell_attk
        self.damage_dice = damage_dice
        self.saves_half = saves_half
        self.damage_type = damage_type
        self.is_aoe = is_aoe
        self.is_healing = is_healing
        self.available_to_classes = available_to_classes

    def extract(self):
        return self.spell_name, self.spell_level, self.target, self.target_identity, self.target_number, self.saving_throw, self.is_spell_attk, self.damage_dice, self.saves_half, self.damage_type, self.is_aoe, self.is_healing, self.available_to_classes

def cast_spell(response_content):
    roll_name = "CastSpell"
    magic_obj = extract_json_from_response(roll_name, response_content)

    if magic_obj is None:
        return None
    
    # Note : ability_score, challenge_rating, target_AC are only included when battle info is none
    target, target_identity, target_number, saving_throw, is_spell_attk, damage_type, damage_dice, saves_half, is_aoe, print_text = extract_magic_values(magic_obj, True)

    spell_name = validate_unspecified(magic_obj.get("spell_name"))
    spell_name = remove_parentheses(spell_name)
    
    spell_level = get_spell_level_from_text(magic_obj.get("spell_level"))
    is_healing = validate_bool(magic_obj.get("is_healing"))
    available_to_classes = magic_obj.get("available_to_classes")

    print_log(f"\nRoll found in {roll_name}: spell_name: {spell_name}, spell level: {spell_level}, {print_text}, damage dice: {damage_dice}, saves half: {saves_half}, damage_type: {damage_type}, is_aoe: {is_aoe}, is_healing: {is_healing}, \
          available to classes: {available_to_classes}. Found in prompt: {response_content}")

    return Cast_Spell_Object(spell_name, spell_level, target, target_identity, target_number, saving_throw, is_spell_attk, damage_dice, saves_half, damage_type, is_aoe, is_healing, available_to_classes)

class Use_Item_Object:
    def __init__(self, item_or_ability_name, target, target_identity, target_number, saving_throw, is_ranged_attk, damage_dice, saves_half, damage_type, is_aoe, is_healing, healing_dice, item_fall_into_available_category, item_used_actively, stat_required_to_use_item):
        self.item_or_ability_name = item_or_ability_name
        self.target = target
        self.target_identity = target_identity
        self.target_number = target_number
        self.saving_throw = saving_throw
        self.is_ranged_attk = is_ranged_attk

        self.damage_dice = damage_dice
        self.saves_half = saves_half
        self.damage_type = damage_type
        self.is_aoe = is_aoe
        self.is_healing = is_healing
        self.healing_dice = healing_dice
        self.item_fall_into_available_category = item_fall_into_available_category
        self.item_used_actively = item_used_actively
        self.stat_required_to_use_item = stat_required_to_use_item

    def extract(self):
        return self.item_or_ability_name, self.target, self.target_identity, self.target_number, self.saving_throw, self.is_ranged_attk, self.damage_dice, self.saves_half, self.damage_type, self.is_aoe, self.is_healing, self.healing_dice, self.item_fall_into_available_category, self.item_used_actively, self.stat_required_to_use_item

def use_item(response_content, current_story):
    roll_name = "UseItem"
    magic_obj = extract_json_from_response(roll_name, response_content)

    if magic_obj is None:
        return None
    
    # Note : ability_score, challenge_rating, target_AC are only included when battle info is none
    target, target_identity, target_number, saving_throw, is_ranged_attk, damage_type, damage_dice, saves_half, is_aoe, print_text = extract_magic_values(magic_obj)

    item_name = validate_unspecified(magic_obj.get("item_name"))
    is_healing = validate_bool(magic_obj.get("is_healing"))
    healing_dice = validate_unspecified(magic_obj.get("healing_dice"))

    item_used_actively = magic_obj.get("item_usage_type") == "used_actively"
    stat_required_to_use_item = get_ability_name_short(magic_obj.get("stat_required_to_use_item"))

    # Determine if the item falls into the available category of item they can always have
    available_misc_objects_json_name = current_story.get("available_misc_objects_json_name")
    if available_misc_objects_json_name is not None:
        item_fall_into_available_category = validate_bool(magic_obj.get(available_misc_objects_json_name, False))

        # Reverse the logic if needed (Ruby with magic items, easier than using a negative)
        if current_story.get("available_misc_objects_is_reversed", False):
            item_fall_into_available_category = not item_fall_into_available_category
    else:
        item_fall_into_available_category = False

    print_log(f"\nRoll found in {roll_name}: item_name: {item_name}, {print_text}, is_healing: {is_healing}, \
          healing_dice: {healing_dice}, item_fall_into_available_category: {item_fall_into_available_category}, item_used_actively: {item_used_actively}, stat_required_to_use_item: {stat_required_to_use_item}. Found in prompt: {response_content}")
    
    # Should return the same number of args as use special ability
    return Use_Item_Object(item_name, target, target_identity, target_number, saving_throw, is_ranged_attk, damage_dice, saves_half, damage_type, is_aoe, is_healing, healing_dice, item_fall_into_available_category, item_used_actively, stat_required_to_use_item)

# Decide if the item is within reach, to determine if it can be used even if it,s not in the inventory
def item_is_within_reach(response_content):
    roll_name = "ItemIsWithinReach"
    item_obj = extract_json_from_response(roll_name, response_content)

    if item_obj is None:
        return None
    
    item_was_mentioned = validate_bool(item_obj.get("item_was_mentioned"))
    item_guaranteed_in_current_environment = validate_bool(item_obj.get("item_guaranteed_in_current_environment"))
    item_within_reach = validate_bool(item_obj.get("item_within_reach"))
    
    # Decide if using the item should be allowed, even if it's not in the inventory
    item_allowed = (item_was_mentioned or item_guaranteed_in_current_environment) and item_within_reach

    if item_allowed:
        print_log(f"\nItem is within reach: Found in prompt: {response_content}")
    else:
        print_log(f"\nItem not considered to be within reach: Found in prompt: {response_content}")
    
    return item_allowed

def get_roll_narrator_saving_throw(response_content):
    roll_name = "GetRollSavingThrowNarrator"
    roll_obj = extract_json_from_response("GetRollNarrator", response_content)

    if roll_obj is None:
        return None

    # The chosen situation is the one with the highest priority
    primary_situation_type = get_primary_situation_saving_throw(roll_obj.get("primary_situation"))

    chosen_situation = None

    # If the primary main action was defined by the ai, use that (unless it's "other", want to use the priority system then)
        # Otherwise, use the default priority
    if primary_situation_type is not None and primary_situation_type != "other":
        # Potential hazards = no roll needed (ex : Discussing the possibility of future dangers in a dungeon)
        if primary_situation_type == "potential_future_hazards":
            print_log(f'{roll_name} : Potential hazards, no roll needed : {response_content}')
            return None
        # Trap triggered = saving throw required
        elif primary_situation_type == "trap_triggered":
            chosen_situation = "saving_throw_required"
        else:
            chosen_situation = primary_situation_type

    if chosen_situation is None:
        print_log(f'{roll_name} : No roll needed : {response_content}')
        return None

    print_log(f"\n{roll_name}: Chosen situation: {chosen_situation}, Found in prompt: {response_content}")

    return {"chosen_situation": chosen_situation}

class Combatant_Sheet_Stats_Object:
    def __init__(self, type, race, gender, size, str, dex, con, int_param, wis, cha, ac, saving_throws_proficiencies, cr):
        self.type = type
        self.race = race
        self.gender = gender
        self.size = size
        self.str = str if isinstance(str, int) and str > 0 else 10
        self.dex = dex if isinstance(dex, int) and dex > 0 else 10
        self.con = con if isinstance(con, int) and con > 0 else 10
        self.int = int_param if isinstance(int_param, int) and int_param > 0 else 10
        self.wis = wis if isinstance(wis, int) and wis > 0 else 10
        self.cha = cha if isinstance(cha, int) and cha > 0 else 10
        self.ac = ac
        self.saving_throws_proficiencies = saving_throws_proficiencies
        self.cr = cr

    # Extract as a json object (Need to be saved on file, better for readability than .pkl)
    def extract_json(self):
        return {"type": self.type, "race": self.race, "gender": self.gender, "size": self.size, "str": self.str, "dex": self.dex, "con": self.con, "int": self.int, "wis": self.wis, "cha": self.cha, "ac": self.ac, "saving_throws_proficiencies": self.saving_throws_proficiencies, "cr": self.cr}

def create_combatant_sheet_stats(response_content):
    roll_name = "CreateCombatantSheet"
    sheet_obj = extract_json_from_response(roll_name, response_content)

    if sheet_obj is None:
        return None

    name = validate_unspecified(sheet_obj.get("name"))
    cr = extract_cr(sheet_obj.get("cr"))
    type = validate_unspecified(sheet_obj.get("type"))
    race = validate_unspecified(sheet_obj.get("race"))
    gender = validate_unspecified(sheet_obj.get("gender"))
    size = validate_unspecified(sheet_obj.get("size"))
    ac = extract_int(sheet_obj.get("ac"))

    if ac is None:
        print(f"ERROR: AC not found in prompt for {roll_name}, defaulting to 10.")
        ac = 10

    ability_scores = sheet_obj.get("ability_scores") # obj
    str = dex = con = int = wis = cha = 10

    if ability_scores is not None and isinstance(ability_scores, object):
        str = extract_int(ability_scores.get("str"))
        dex = extract_int(ability_scores.get("dex"))
        con = extract_int(ability_scores.get("con"))
        int = extract_int(ability_scores.get("int"))
        wis = extract_int(ability_scores.get("wis"))
        cha = extract_int(ability_scores.get("cha"))
    else:
        print_log(f"Ability scores not found, using default values")

    saving_throws_proficiencies = sheet_obj.get("saving_throws_proficiencies", [])

    print_log(f"{roll_name}: Found in prompt: {response_content}")

    print_log(f"{roll_name}: Name: {name}, CR: {cr}, Type: {type}, AC: {ac},  Ability scores: (Str: {str}, Dex: {dex}, Con: {con}, Int: {int}, Wis: {wis}, Cha: {cha}), Saving throws proficiencies: {saving_throws_proficiencies}")

    return Combatant_Sheet_Stats_Object(type, race, gender, size, str, dex, con, int, wis, cha, ac, saving_throws_proficiencies, cr)
    
class Combatant_Sheet_Attack_Object:
    def __init__(self, weapon, how_many, damage_type, is_ranged, ability_used):
        self.weapon = weapon
        self.how_many = how_many
        self.damage_type = damage_type
        self.is_ranged = is_ranged
        self.ability_used = ability_used

    # Extract as a json object
    def extract_json(self):
        return {"weapon": self.weapon, "how_many": self.how_many, "damage_type": self.damage_type, "is_ranged": self.is_ranged, "ability_used": self.ability_used}

class Combatant_Sheet_Attacks_Object:
    def __init__(self, attacks):
        self.attacks = attacks

    # Extract as a json object (Need to be saved on file, better for readability than .pkl)
    def extract_json(self):
        return {"attacks": [attack.extract_json() for attack in self.attacks]}

def create_combatant_sheet_attacks(response_content):
    roll_name = "CreateCombatantSheet"
    sheet_obj = extract_json_from_response(roll_name, response_content)

    if sheet_obj is None:
        return None

    name = validate_unspecified(sheet_obj.get("name"))
    challenge_rating = extract_cr(sheet_obj.get("cr"))

    attacks = []
    for attack_obj in sheet_obj.get("attacks", []):
        weapon = validate_unspecified(attack_obj.get("weapon_name"))
        # remove weapon parenthesis if there is any
        weapon = remove_parentheses(weapon) 

        damage_type = validate_unspecified(attack_obj.get("damage_type"))
        is_ranged = validate_bool(attack_obj.get("is_ranged"))
        ability_used = validate_unspecified(attack_obj.get("ability_score_used"))

        how_many_text = attack_obj.get("how_many")
        how_many = extract_int(how_many_text)

        # Try to extract the number from the word if it couldn't be converted to an int
        if how_many is None and how_many is not None and isinstance(how_many_text, str):
            how_many = try_to_extract_number_from_word(how_many_text)

        if how_many is None or how_many < 1:
            print(f"ERROR: how_many not found in prompt for {roll_name}, defaulting to 1.")
            how_many = 1

        attacks.append(Combatant_Sheet_Attack_Object(weapon, how_many, damage_type, is_ranged, ability_used))

    print_log(f"{roll_name}: Found in prompt: {response_content}")
    print_log(f"{roll_name}: Name: {name}, CR: {challenge_rating}, Attacks: {attacks}")

    return Combatant_Sheet_Attacks_Object(attacks)

class Combatant_Sheet_Spell_Object:
    def __init__(self, level, name, has_missing_info, is_higher_than_max_level):
        self.level = level
        self.name = name
        self.has_missing_info = has_missing_info
        self.is_higher_than_max_level = is_higher_than_max_level

    # Extract as a json object
    def extract_json(self):
        json_obj = {"level": self.level, "name": self.name}
        if self.has_missing_info:
            json_obj["has_missing_info"] = self.has_missing_info
        if self.is_higher_than_max_level:
            json_obj["is_higher_than_max_level"] = self.is_higher_than_max_level

        return json_obj

class Combatant_Sheet_Spells_Object:
    def __init__(self, caster_type, spellcasting_ability_score, spells):
        self.caster_type = caster_type
        self.spellcasting_ability_score = spellcasting_ability_score
        self.spells = spells

    # Extract as a json object (Need to be saved on file, better for readability than .pkl)
    def extract_json(self):
        return {"caster_type": self.caster_type, "spellcasting_ability_score": self.spellcasting_ability_score, "spells": [spell.extract_json() for spell in self.spells]}

def create_combatant_sheet_spells(response_content):
    roll_name = "CreateCombatantSheetSpells"
    sheet_obj = extract_json_from_response(roll_name, response_content)

    if sheet_obj is None:
        return None

    identity = validate_unspecified(sheet_obj.get("creature_identity"))
    max_spell_level = extract_int(sheet_obj.get("max_spell_level"))
    is_spellcaster = validate_bool(sheet_obj.get("is_spellcaster"))
    caster_type = validate_unspecified(sheet_obj.get("caster_type"))
    spellcasting_ability_score = validate_unspecified(sheet_obj.get("spellcasting_ability_score"))

    if not is_spellcaster or caster_type == "none":
        print_log(f"{roll_name}: {identity} is not a spellcaster.")
        return None

    spells = []
    for x in range(1, 10):
        spells_of_level = sheet_obj.get("level_" + str(x), [])

        if len(spells_of_level) == 0:
            continue

        for spell_name in spells_of_level:
            current_spell_level = x # Can be changed if the spell level is detected

            spell_name = validate_unspecified(spell_name)
            # remove spell parenthesis if there is any
            spell_name = remove_parentheses(spell_name)

            spell_row = get_spell_row(spell_name)
            is_oob_only = spell_row["is_oob_only"] if spell_row is not None else False
            if is_oob_only:
                print_log(f"{roll_name}: Spell {spell_name} can only be used out of battle due to long casting time, skipping.")
                continue

            detected_level = find_spell_level_from_row(spell_row)

            has_missing_info = is_higher_than_max_level = False
            if detected_level is None:
                print_log(f"{roll_name}: Spell with missing info: {spell_name}")
                has_missing_info = True
                
            elif detected_level > max_spell_level:
                print_log(f"{roll_name}: Spell {spell_name} has level higher than max. Prompt level {x}, spell list level: {detected_level}, max level: {max_spell_level}")
                current_spell_level = detected_level
                is_higher_than_max_level = True

            elif detected_level != x:
                print_log(f"{roll_name}: Spell {spell_name} has level different from prompt. Prompt level {x}, spell list level: {detected_level}. Spell set to level {detected_level} since it's lower than the max level.")
                current_spell_level = detected_level
                
            spells.append(Combatant_Sheet_Spell_Object(current_spell_level, spell_name, has_missing_info, is_higher_than_max_level))

    print_log(f"{roll_name}: Found in prompt: {response_content}")

    combatant_sheet_spells_obj = Combatant_Sheet_Spells_Object(caster_type, spellcasting_ability_score, spells)
    print_log(f"{roll_name}: Identity: {identity}, {combatant_sheet_spells_obj.extract_json()}")

    return combatant_sheet_spells_obj

class Combatant_Action_Object:
    def __init__(self, target_identity, target_number, action_type, action_name, damage_type, is_ranged, how_many, description):
        self.target_identity = target_identity
        self.target_number = target_number
        self.action_type = action_type
        self.action_name = action_name
        self.damage_type = damage_type
        self.is_ranged = is_ranged
        self.how_many = how_many
        self.description = description

    # Extract as a json object
    def extract_json(self):
        return {"target_identity": self.target_identity, "target_number": self.target_number, "action_type": self.action_type, "action_name": self.action_name, "damage_type": self.damage_type, "how_many": self.how_many, "is_ranged": self.is_ranged, "description": self.description}

def choose_combatant_action(response_content):
    roll_name = "GetChooseCombatantAction"
    root_obj = extract_json_from_response(roll_name, response_content)

    if root_obj is None:
        return None
    
    print_log(f"{roll_name}: Found in prompt: {response_content}")

    identity = validate_unspecified(root_obj.get("combatant_name"))
    target_identity = validate_unspecified(root_obj.get("target_identity"))
    target_number = extract_int(root_obj.get("target_number"))
    action_type = validate_unspecified(root_obj.get("action_type"))
    action_name = validate_unspecified(root_obj.get("action_name"))
    damage_type = validate_unspecified(root_obj.get("damage_type"))
    is_ranged = validate_bool(root_obj.get("is_ranged"))
    how_many = extract_int(root_obj.get("how_many"))
    description = validate_unspecified(root_obj.get("description"))

    if how_many is None or how_many < 1:
        print(f"ERROR: how_many not found in prompt, defaulting to 1 for {roll_name}.")
        how_many = 1

    if action_type not in ["using_a_skill", "attacking", "casting_a_spell"]:
        print(f"\nERROR: {roll_name}: Incorrect action type, action_type: {action_type}\n")
        action_type = "attacking"

    action_obj = Combatant_Action_Object(target_identity, target_number, action_type, action_name, damage_type, is_ranged, how_many, description)
    print_log(f"{roll_name}: Identity: {identity}, {action_obj.extract_json()}")

    return action_obj

class Roll_Saving_Throw_Object:
    def __init__(self, cause_of_save, saving_throw, dc, damage_dice, damage_type, save_half):
        self.cause_of_save = cause_of_save
        self.saving_throw = saving_throw
        self.dc = dc
        self.damage_dice = damage_dice
        self.damage_type = damage_type
        self.save_half = save_half

    def extract(self):
        return self.cause_of_save, self.saving_throw, self.dc, self.damage_dice, self.damage_type, self.save_half

def get_roll_saving_throw(response_content):
    roll_name = "GetRollSavingThrow"
    roll_obj = extract_json_from_response(roll_name, response_content)

    if roll_obj is None:
        return None

    cause_of_save = validate_unspecified(roll_obj.get("cause"))
    saving_throw = get_ability_name_short(roll_obj.get("saving_throw"))
    dc = extract_int(roll_obj.get("DC"))
    damage_dice = validate_unspecified(roll_obj.get("damage_dice"))
    damage_type = validate_unspecified(roll_obj.get("damage_type"))

    save_half = validate_bool(roll_obj.get("saves_half"))
    is_aoe = validate_bool(roll_obj.get("is_aoe"))
    is_fall_damage = validate_bool(roll_obj.get("is_fall_damage"))

    # Attempt to convert text to int if it's not already
    if dc is None:
        dc_text = validate_unspecified(roll_obj.get("DC"))
        dc = convert_text_dc_to_int(dc_text)

    # Always saves half on aoe or fall damage
    if is_aoe or is_fall_damage:
        save_half = True

    print_log(f"{roll_name}: cause: {cause_of_save}, saving_throw: {saving_throw}, dc: {dc}, damage_dice: {damage_dice}, damage_type: {damage_type}, save_half : {save_half}. Found in prompt: {response_content}")

    return Roll_Saving_Throw_Object(cause_of_save, saving_throw, dc, damage_dice, damage_type, save_half)

# PROCESS ROLLS

def get_item_name(item):
    return item["name"] if isinstance(item, dict) else item

def get_clean_item_name(item):
    item_name = get_item_name(item)
    return item_name.lower().strip(" ,.!?")

def fix_skill_stat(skill, stat_name):
    if skill == "investigation" and stat_name == "wis":
        return "intelligence"
    
    return None

def roll_d20(reason_advantage = None, has_advantage = False, has_disadvantage = False, has_elven_accuracy = False, skip_advantage_rolls = False, skip_reason = True): # Skip reason by default, takes too much space
    advantage_text = ""

    # If both advantage and disadvantage are present, they cancel each other out
    if (has_advantage or has_disadvantage) and not (has_advantage and has_disadvantage):
        all_d20_rolls = [rd.randint(1, 20), rd.randint(1, 20)]

        if has_elven_accuracy:
            all_d20_rolls.append(rd.randint(1, 20))

        d20_roll = max(all_d20_rolls) if has_advantage else min(all_d20_rolls)

        # Reason why advantage
        reasons = []
        if has_elven_accuracy:
            reasons.append("Elven Accuracy")
        if reason_advantage:
            reasons.append(reason_advantage)

        advantage_rolls_text = f"; {', '.join(str(roll) for roll in all_d20_rolls)}" if not skip_advantage_rolls else ""

        # Advantage text
        reason_text = f": {', '.join(reasons)}" if len(reasons) > 0 and not skip_reason else ""
        advantage_text = f" ({'advantage' if has_advantage else 'disadvantage'}{reason_text}{advantage_rolls_text})"  
        
        return d20_roll, advantage_text
    else:
        return rd.randint(1, 20), advantage_text
    
def has_gotten_lucky(current_story, current_action_nb=0, total_actions=1, is_combatant_not_targeting_mc = False):
    # If the combatant is making a saving throw or an ability check, and the player need the "chronal shift" talent, or they can't get lucky
    if is_combatant_not_targeting_mc and not has_talent("chronal shift", current_story):
        return False, None
    
    talents = [('lucky spirit', 3), ('lucky', 5), ('chronal shift', 4)]
    for talent_name, base_chance in talents:
        if has_talent(talent_name, current_story):
            malus = total_actions / (current_action_nb + 1)
            chance = base_chance * malus
            if rd.randint(1, int(chance)) == 1:
                return True, talent_name
    return False, None

def get_attack_dmg_and_how_many(weapon_name, how_many, opponent_cr, sheet, attack_ability_score_nb, max_nb_multiattack, total_nb_of_attacks_of_type):
    # In case it's not specified
    if how_many is None:
        how_many = 1
    if total_nb_of_attacks_of_type is None:
        total_nb_of_attacks_of_type = 1

    # Reduce the nb of attacks until it's lower than the max nb of multiattack, or it reaches 1
    while max_nb_multiattack is not None and total_nb_of_attacks_of_type > max_nb_multiattack and how_many > 1:
        total_nb_of_attacks_of_type -= 1
        how_many -= 1

    current_weapon_row = get_weapon_row(weapon_name)

    # If weapon is in the list, and medium size humanoid, get the weapon info
    if current_weapon_row is not None and sheet.get("type", "").lower() == "humanoid" and sheet.get("size", "").lower() in ["small", "medium"]:
        target_avg_dmg = extract_float(get_monsters_single_value(opponent_cr, "avg_damage"))
        stat_mod = stat_to_modifier(attack_ability_score_nb)

        dice, avg_dmg = get_weapon_info(current_weapon_row)
        weapon_total_avg_dmg = (avg_dmg + stat_mod) * how_many

        # Try to increase the nb of multiattack as long as the nb of attacks < the maximum and total avg dmg is lower than the target avg dmg
            # Note : The last added attack could make it so the total avg dmg is higher than the target avg dmg (shouldn't matter too much)
        while max_nb_multiattack is not None and max_nb_multiattack > total_nb_of_attacks_of_type and weapon_total_avg_dmg < target_avg_dmg:
            total_nb_of_attacks_of_type += 1
            how_many += 1
            weapon_total_avg_dmg = (avg_dmg + stat_mod) * how_many

        damage_dice = dice

    # If weapon not in the list, automatically calculate the damage dice
    else:
        damage_dice = get_damage_roll_by_cr(opponent_cr, attack_ability_score_nb, total_nb_of_attacks_of_type)

    return damage_dice, how_many

def get_corresponding_entry_row(entry_name):
    if not entry_name:
        return ""
    
    # Remove any comma or period from the entry name
    entry_name = entry_name.replace(",", "").replace(".", "").lower()

    # Signularize the name, unless it's a swarm
    singularized_entry_name = singularize_name(entry_name) if not entry_name.startswith("swarm of") else entry_name
    entry_name_set = set(singularized_entry_name.split())

    for name in monsters_entry_names:
        row = monsters_entry_names[name]
        name_set = set(name.split())

        # Check if the entry name is in the name, in whatever word order
        if entry_name_set == name_set:
            return row

        # Check if the entry name is in the alt names
        alt_names = row.get("alt_names")
        if alt_names:
            alt_names_arr = alt_names.split(";")

            # Check if any of the alt names set (sepparated by spaces) match the entry name set
            for alt_name in alt_names_arr:
                alt_name_set = set(alt_name.split()) if alt_name else set()
                if alt_name_set and entry_name_set == alt_name_set:
                    return row
        
    print(f"ERROR: Corresponding entry row not found for {entry_name}")
    return ""

def get_corresponding_entry_name(entry_name):
    entry_row = get_corresponding_entry_row(entry_name)
    return entry_row.get("name") if entry_row else ""

def get_corresponding_entry_cr(entry_name):
    entry_row = get_corresponding_entry_row(entry_name)
    return entry_row.get("cr") if entry_row else None

def get_all_entry_names():
    all_entry_names = []
    base_names_dict = {}

    for name in monsters_entry_names:
        row = monsters_entry_names[name]
        all_entry_names.append(name)

        alt_names = row.get("alt_names")
        if alt_names:
            alt_names_arr = alt_names.split(";")
            all_entry_names += alt_names_arr

        base_name = row.get("base_name")
        if base_name and base_names_dict.get(base_name) is None:
            base_names_dict[base_name] = [name] 
        elif base_name:
            base_names_dict[base_name].append(name)
                
    # Remove the exceptions (ex : dragon is too generic, will often bias the results instead of helping
        # ex : ice dragon will match with only 'dragon' in the list, but might find 'white dragon' instead if no list is given)
    entry_name_exceptions = ["dragon"]
    all_entry_names = [entry_name for entry_name in all_entry_names if entry_name not in entry_name_exceptions]

    return all_entry_names, base_names_dict

def find_entry_names_in_text(text):
    all_entry_names, base_names_dict = get_all_entry_names()
    found_entry_names = []

    # First, check if any base name can be found in the text (ex : 'goblin')
    for base_entry_name in base_names_dict:
        # Regex pattern to match the entry name surrounded by spaces or punctuation, with an optional 's' or 'es' at the end (ex: bosses)
        pattern = r'\b' + re.escape(base_entry_name) + r'(es?|s?)\b'
        if re.search(pattern, text):
            # If the base name is found, add all the entity names containing the base name
            entity_names_containing_base_name = base_names_dict[base_entry_name]
            found_entry_names += entity_names_containing_base_name

    # Then, check if any specific entry name, that isn't a base name, can be found in the text 
    for entry_name in all_entry_names:
        # Skip if entity already added
        if entry_name in found_entry_names:
            continue

        # Regex pattern to match the entry name surrounded by spaces or punctuation, with an optional 's' or 'es' at the end (ex: bosses)
        pattern = r'\b' + re.escape(entry_name) + r'(es?|s?)\b'
        if re.search(pattern, text):
            found_entry_names.append(entry_name)

    return found_entry_names

def get_max_nb_multiattack(cr):
    nb_multiattack_arr = get_monsters_values(cr, "nb_multiattack")
    return extract_int(nb_multiattack_arr[-1]) if len(nb_multiattack_arr) > 0 else None

def process_combatant_sheets(group_infos: List[Tuple[Dict, Combatant_Sheet_Stats_Object, Combatant_Sheet_Attacks_Object, Combatant_Sheet_Spells_Object]]):
    combatant_sheets = []

    for group_tuple in group_infos:
        group, stat_sheet_obj, attack_sheet_obj, spell_sheet_obj = group_tuple

        stat_sheet = stat_sheet_obj.extract_json()
        # Remove cr to not overwrite the one in group (cr from sheet is used when cast spell or use item oob)
        if "cr" in stat_sheet:
            del stat_sheet["cr"]

        attack_sheet = attack_sheet_obj.extract_json()
        spell_sheet = spell_sheet_obj.extract_json() if group_tuple[3] is not None else None

        sheet = {}

        # Note : There should be no overlap in the values (ex: the name prop should be in group only)
        sheet.update(group)
        sheet["name"] = singularize_name(sheet["name"]) # Singularize the name

        sheet.update(stat_sheet)
        sheet.update(attack_sheet)

        if spell_sheet is not None:
            sheet.update(spell_sheet)

        sheet["hp"] = get_monsters_hp(sheet["cr"], sheet)
        # sheet["entry_name"] = get_corresponding_entry_name(sheet["entry_name"])

        sheet["is_ranged"] = any([attack_obj["is_ranged"] for attack_obj in sheet["attacks"]])
        sheet["is_melee"] = any([not attack_obj["is_ranged"] for attack_obj in sheet["attacks"]])

        max_nb_multiattack = get_max_nb_multiattack(sheet["cr"])

        for attack_obj in sheet["attacks"]:
            attack_ability_name = get_ability_name_short(attack_obj["ability_used"])
            spellcasting_ability_name = sheet.get("spellcasting_ability_score")
            weapon_name = attack_obj["weapon"]

            if attack_ability_name is None:
                print_log(f"Attack ability score not found for combatant {sheet['name']}, default to str")
                attack_ability_name = "str"
            
            # Mental based attack that doesn't match the spellcasting score (+con, in case mistakenly thought the saving throw was the attack ability)
            elif attack_ability_name in ["int", "wis", "cha", "con"] and spellcasting_ability_name is not None and spellcasting_ability_name != attack_ability_name:
                print_log(f"Mental based attack ability score {attack_ability_name} is different from spellcasting ability score {spellcasting_ability_name} for combatant {sheet['name']}, weapon: {weapon_name}")
                attack_ability_name = spellcasting_ability_name
            
            attack_ability_score_nb = stat_sheet.get(attack_ability_name, 10)

            # Only count the total number of attacks of the same type (ranged/melee) when calculating the dmg dice (multiattack is always only the same types of attacks)
            total_nb_of_attacks_of_type = sum([other_attack_obj["how_many"] for other_attack_obj in sheet["attacks"] if attack_obj["is_ranged"] == other_attack_obj["is_ranged"]])

            # Get the number of attacks and dmg dice for the specified weapon
            damage_dice, how_many = get_attack_dmg_and_how_many(weapon_name, attack_obj["how_many"], sheet["cr"], sheet, attack_ability_score_nb, max_nb_multiattack, total_nb_of_attacks_of_type)

            attack_obj["damage_dice"] = damage_dice
            attack_obj["how_many"] = how_many

        combatant_sheets.append(sheet)
        # combatants = []

    return combatant_sheets

def update_opponent_hp(opponent, total_dmg):
    opponent["hp"] = max(0, opponent["hp"] - total_dmg)

def process_damage_battle_info(attack_type, current_story, setup_aid, opponents, total_damage, is_spell_attk = False, spell_level = None, has_bonus_action = False, is_first_attack = False, total_spell_attk_nb = None, using_twinned_spell = False) -> Tuple[Any, Any, Any, Any, Any, Any]:
    roll_info_text_damages = []
    roll_text_damages = []

    # Get the opponents
    if opponents is None or len(opponents) == 0:
        return "", "", has_bonus_action, 0, False, ""

    # Count how many opponents are left
    total_opponents = sum([1 for opponent in opponents if opponent["hp"] > 0])

    can_use_twinned_spell = False

    # Determine if using twinned spell
    if spell_level is not None and is_spell_attk and using_twinned_spell and has_talent("twinned spell", current_story, partial_match=True) and total_opponents > 1 and (total_spell_attk_nb is None or total_spell_attk_nb == 1):
        sorcery_points = current_story.get("sorcery_points", 0)
        metamagic_cost = max(spell_level, 1) # cantrip = costs 1

        if sorcery_points >= metamagic_cost:
            current_story["sorcery_points"] -= metamagic_cost
            can_use_twinned_spell = True

        else:
            print_log("Not enough sorcery points to use twinned spell")

    # Apply the same damage on 2 melee opponets on the first attack (cleave)
        # Only on the first attack to be equivalent to 2 separate attack rolls (as if both had the same roll, either both touched or neither touched)
    can_use_horde_breaker = has_talent("horde breaker", current_story) and has_bonus_action and is_first_attack
    is_using_horde_breaker = False
    is_using_twinned_spell = False

    dual_target = None
    has_reduced_opponent_0_hp = False
    total_damage_including_extra = 0

    for opponent in opponents:
        if opponent["hp"] == 0:
            continue
        
        update_opponent_hp(opponent, total_damage)
        total_damage_including_extra += total_damage

        # opponent_health_text = get_opponent_health_status(opponent["hp"], opponent["max_hp"])
        is_ranged_opponent = opponent["is_ranged"]

        # Cleave if prev opponent died or was a crit.
        if is_using_horde_breaker and not is_ranged_opponent:
            roll_info_text_damages.append(f"Horde Breaker was used to attack two opponents at the same time.")
            roll_text_damages.append(f"{opponent['identifier']} was hit at the same time")
            is_using_horde_breaker = can_use_horde_breaker = False

            has_bonus_action = False
            dual_target = opponent
        elif is_using_twinned_spell:
            roll_info_text_damages.append(f"Twinned spell was used to attack two opponents at the same time.")
            roll_text_damages.append(f"{opponent['identifier']} was hit by the spell at the same time by using the 'Twinned Spell' metamagic")
            is_using_twinned_spell = can_use_twinned_spell = False

            has_bonus_action = False
            dual_target = opponent

        if opponent["hp"] == 0:
            roll_text_damages.append(setup_aid["combatant_dead"].replace("#combatant_identifier#", opponent["identifier"].capitalize()).replace("#attack_type#", attack_type))
            has_reduced_opponent_0_hp = True

        # Continue to the next opponent if horde breaker is used and the enemy is melee and the pc has horde_breaker 
        if can_use_horde_breaker and not is_ranged_opponent and total_damage > 0:
            is_using_horde_breaker = True
        elif can_use_twinned_spell and total_damage > 0:
            is_using_twinned_spell = True
        else:
            break

    roll_text_damage = ", ".join(roll_text_damages)
    roll_info_text_damage = "\n".join(roll_info_text_damages)

    return roll_info_text_damage, roll_text_damage, has_bonus_action, total_damage_including_extra, has_reduced_opponent_0_hp, dual_target

def get_is_all_opponents_defeated(battle_info):
    if battle_info is None:
        return False

    opponents = battle_info["opponents"]
    if len(opponents) == 0:
        return False

    # Count how many opponents are left
    total_opponents = sum([1 for opponent in opponents if opponent["hp"] > 0])

    return total_opponents == 0

def get_is_targeted_opponents_defeated(opponents):
    if opponents is None or len(opponents) == 0:
        return False

    # Count how many opponents are left
    total_opponents = sum([1 for opponent in opponents if opponent["hp"] > 0])

    return total_opponents == 0

def get_bonus_rage_damage(current_story):
    current_level = current_story["level"]
    if current_level < 9:
        return 2
    elif current_level < 16:
        return 3
    else:
        return 4

# Get the equipped weapon magic bonus
def get_magic_weapon_bonus(current_story):
    for item in current_story["inventory"]:
        if not item.get("is_equipped", False):
            continue

        magic_weapon_bonus = item.get("magic_weapon_bonus")
        if magic_weapon_bonus is not None:
            return magic_weapon_bonus
        
    return 0

# Get the equipped magic focus bonus
def get_magic_focus_bonus(current_story):
    for item in current_story["inventory"]:
        if not item.get("is_equipped", False):
            continue

        magic_focus_bonus = item.get("magic_focus_bonus")
        if magic_focus_bonus is not None:
            return magic_focus_bonus
        
    return 0

def get_tides_of_chaos_bonus(current_story) -> Tuple[Any, Any]:
    tides_of_chaos_text = ""
    tides_of_chaos_bonus = 0
    if has_talent("tides of chaos", current_story) or has_talent("tides of dreams", current_story):
        is_negative = rd.randint(1, 4) == 1 # 1/4 chance of being negative
        tides_of_chaos_bonus = -2 if is_negative else 2
        tides_of_chaos_name = "Tides of Chaos" if has_talent("tides of chaos", current_story) else "Tides of Dreams"
        tides_of_chaos_text = (" - 2" if is_negative else " + 2") + f" ({tides_of_chaos_name})"

    return tides_of_chaos_bonus, tides_of_chaos_text

def get_touch_of_magic_bonus(current_story):
    touch_of_magic_level = current_story["level"] 
    return (touch_of_magic_level - 1 if has_talent("multiclass", current_story) else touch_of_magic_level) // 2

def get_combatant_sheet(group_name, combatant_cr, combatant_sheets):
    formatted_group_name = singularize_name(group_name).lower() 

    for sheet in combatant_sheets:
        if sheet["name"].lower() == formatted_group_name and sheet["cr"] == combatant_cr:
            return sheet
        
    # Fallback if sheet with both name and cr not found
    for sheet in combatant_sheets:
        if sheet["name"].lower() == formatted_group_name:
            return sheet

    # Fallback if the formatted name is not found
    for sheet in combatant_sheets:
        if sheet["name"].lower() == group_name.lower():
            return sheet

    return None

def get_next_combatant_sheet(targeted_combatants, combatant_sheets):
    # use 'next' to get the next combatant that has > 0 hp
    next_combatant = next((combatant for combatant in targeted_combatants if combatant["hp"] > 0), None)

    if next_combatant is None:
        return None, None

    next_combatant_sheet = get_combatant_sheet(next_combatant["group_name"], next_combatant["cr"], combatant_sheets)

    return next_combatant, next_combatant_sheet

def is_combatant_targeted(combatant, target_identity_text):
    target_identities = target_identity_text.lower().split("/") # Split using /, if multiple targets
    group_name_lower = combatant["group_name"].lower() 
    identifier_lower = combatant["identifier"].lower()

    for target_identity in target_identities:
        if group_name_lower in target_identity or target_identity in group_name_lower or identifier_lower in target_identity or target_identity in identifier_lower:
            return True
        
    return False

def get_targeted_combatants(battle_info_combatants, target_identity, target_number):
    # Filter based on the group name or identifier (identifier usually singular and group name plural, so should work in all cases)
    targeted_combatants = [combatant for combatant in battle_info_combatants if is_combatant_targeted(combatant, target_identity)]

    # If target number is specified, target the combatant at the specified index
    if target_number is not None and target_number - 1 < len(targeted_combatants):
        target_combatant = targeted_combatants[target_number - 1] # Target nb starts at 1
        targeted_combatants.remove(target_combatant)
        targeted_combatants.insert(0, target_combatant)

    return targeted_combatants

def get_battle_info_combatants(current_story, target_identity, target_number, is_targeting_opponents, is_ranged_attack = True, is_empty_if_no_target_found = False) -> Tuple[Any, Any, Any, Any]:
    battle_info = current_story.get("battle_info")

    if battle_info is None:
        return [], None, False, False
    
    target_identity = target_identity if target_identity is not None else "target all" # Target all if not specific target

    battle_info_combatants = battle_info["opponents"] if is_targeting_opponents else battle_info.get("allies", [])
    mc_name = current_story["char_name"].lower()
    target_identity_lower = target_identity.lower()

    # Determine if targeting the main character
    if not is_targeting_opponents and (target_identity_lower in mc_name or mc_name in target_identity_lower):
        return [], battle_info, True, False
    
    # Determine if targeting self (for combatants only)
    if not is_targeting_opponents and target_identity_lower == "self":
        return [], battle_info, False, True
    
    # Try targeting the opposing combatants first
    targeted_combatants = get_targeted_combatants(battle_info_combatants, target_identity, target_number)
        
    # Try targeting their allies if that fails.
    if len(targeted_combatants) == 0:
        battle_info_opposite_combatants = battle_info.get("allies", []) if is_targeting_opponents else battle_info["opponents"]
        battle_info_opposite_combatants = get_targeted_combatants(battle_info_opposite_combatants, target_identity, target_number)

        if len(battle_info_opposite_combatants) > 0:
            targeted_combatants = battle_info_opposite_combatants

    # If no targets were found, return an empty list
    if len(targeted_combatants) == 0 and is_empty_if_no_target_found:
        return [], battle_info, False, False

    # Filter out combatants with 0 hp
    targeted_combatants = [combatant for combatant in targeted_combatants if combatant["hp"] > 0]

    # If no targets were found, target all combatants that are still alive by default if it's not the enemies' turn
    if len(targeted_combatants) == 0 and is_targeting_opponents:
        targeted_combatants = [combatant for combatant in battle_info_combatants if combatant["hp"] > 0]
    # If not targets were found, but it's the enemies turn, target the main character
    elif len(targeted_combatants) == 0:
        return [], battle_info, True, False

    # If not a ranged attack, target only melee combatants + 1 ranged, only 2 ranged if no melees (exception monks with more movements)
    if not is_ranged_attack:
        melee_combatants = [combatant for combatant in targeted_combatants if not combatant["is_spellcaster"] and not combatant["is_ranged"]]
        ranged_combatants = [combatant for combatant in targeted_combatants if combatant["is_ranged"] or combatant["is_spellcaster"]]
        
        # Nb of targetable ranged combatants
        nb_targetable_ranged_combatants = 2

        # Fast movers can target more ranged combatants
        if has_talent("fast movement", current_story) or has_talent("unarmored movement", current_story):
            nb_targetable_ranged_combatants += 1

        # Same as above if has mobile feat
        if has_talent("mobile", current_story):
            nb_targetable_ranged_combatants += 1

        if len(melee_combatants) > 0:
            targeted_combatants = melee_combatants + ranged_combatants[:nb_targetable_ranged_combatants - 1]
        else:
            targeted_combatants = ranged_combatants[:nb_targetable_ranged_combatants] # Usually 2, but 3 for monks

    return targeted_combatants, battle_info, False, False

def get_attack_bonus(current_story, is_ranged_attack, roll_stat_name) -> Tuple[Any, Any]:
    if roll_stat_name is None:
        roll_stat_name = "strength"

    relevant_stat_short = roll_stat_name[:3].lower()

    relevant_stat_mod = get_stat_mod(current_story, relevant_stat_short)
    relevant_stat_mod_text = f"{relevant_stat_mod} ({roll_stat_name})"

    base_proficiency_bonus = get_proficiency_bonus(current_story["level"])
    base_proficiency_bonus_text = f" + {base_proficiency_bonus} (Proficiency)"

    magic_weapon_bonus = get_magic_weapon_bonus(current_story)
    magic_weapon_bonus_text = f" + {magic_weapon_bonus} (Magic weapon bonus)" if magic_weapon_bonus > 0 else ""

    # Archery fighting style
    using_archery_fighting_style = has_talent("fighting style (archery)", current_story) and is_ranged_attack
    archery_fighting_style_bonus = 2 if using_archery_fighting_style else 0
    archery_fighting_style_text = f" + 2 (Archery)" if using_archery_fighting_style else ""

    # CQS fighting style
    using_cqs_fighting_style = has_talent("fighting style (close quarters shooter)", current_story) and is_ranged_attack
    cqs_fighting_style_bonus = 1 if using_cqs_fighting_style else 0
    cqs_fighting_style_text = f" + 1 (CQ Shooter)" if using_cqs_fighting_style else ""

    # blade mastery
    using_blade_mastery = has_talent("blade mastery", current_story)
    blade_mastery_bonus = 1 if using_blade_mastery else 0
    blade_mastery_text = f" + 1 (Blade Mastery)" if using_blade_mastery else ""

    attack_bonus = relevant_stat_mod + base_proficiency_bonus + magic_weapon_bonus + archery_fighting_style_bonus + cqs_fighting_style_bonus + blade_mastery_bonus 

    attack_text = f"{relevant_stat_mod_text}{base_proficiency_bonus_text}{magic_weapon_bonus_text}{archery_fighting_style_text}{cqs_fighting_style_text}{blade_mastery_text}"

    return attack_bonus, attack_text

def is_using_sharpshooter_or_gwm(current_story, base_attack_bonus, current_opponent_ac, using_reckless_attack):
    # Always use it in some cases
    if using_reckless_attack or has_talent("dual wield (darts)", current_story):
        return True
    else:
        # Algo : If current_opponent_ac - (base_attack_bonus - 5 (sharpshooter)) <= 11, use sharpshooter, don't otherwise
            # Need the parenthesis, otherwise it's a minus minus (ex: -11 - 6 = -17, instead of -(11-6) = -5)
        return current_opponent_ac - (base_attack_bonus - 5) <= 11

def get_damage_bonus(current_story, is_ranged_attack, roll_stat_name, skip_dmg_mod = False) -> Tuple[Any, Any, Any]:
    relevant_stat_short = roll_stat_name[:3].lower()
    relevant_stat_mod = get_stat_mod(current_story, relevant_stat_short)

    ranged_weapon_damage = current_story.get("ranged_weapon_damage")

    # 1d4 = default weapon damage
    damage_dice = ranged_weapon_damage if is_ranged_attack and ranged_weapon_damage is not None else current_story.get("base_weapon_damage", "1d4")

    # Remove stat mod if dual wielding without fighting style
    stat_mod = 0 if skip_dmg_mod else relevant_stat_mod

    # Magic weapon damage bonus
    magic_weapon_bonus = get_magic_weapon_bonus(current_story)
    magic_weapon_text = f" + {magic_weapon_bonus} (Magic weapon bonus)" if magic_weapon_bonus > 0 else ""
    
    aura_of_conquest_bonus = int(get_stat_mod(current_story, "cha") / 2) if has_talent("aura of conquest", current_story) and not is_ranged_attack else 0
    aura_of_conquest_text = f" + {aura_of_conquest_bonus} (Aura of Conquest)" if aura_of_conquest_bonus > 0 else ""

    dueling_fighting_style_bonus = 2 if has_talent("fighting style (dueling)", current_story) else 0
    dueling_fighting_style_text = f" + {dueling_fighting_style_bonus} (Dueling)" if dueling_fighting_style_bonus > 0 else ""

    poison_proficiency_bonus = 2 if has_talent("poison proficiency", current_story) else 0
    poison_proficiency_text = f" + {poison_proficiency_bonus} (Poison)" if poison_proficiency_bonus > 0 else ""

    # Touch of magic
    touch_of_magic = get_talent("touch of light", current_story)
    touch_of_magic = get_talent("touch of death", current_story) if touch_of_magic is None else touch_of_magic
    touch_of_magic_bonus = 0
    touch_of_magic_text = ""

    if touch_of_magic is not None:
        touch_of_magic_bonus = get_touch_of_magic_bonus(current_story)
        touch_of_magic_domain = "Light" if "light" in touch_of_magic.lower() else "Death"
        touch_of_magic_text = f" + {touch_of_magic_bonus} ({f'Touch of {touch_of_magic_domain}'})"

    damage_mod = stat_mod + magic_weapon_bonus + aura_of_conquest_bonus + dueling_fighting_style_bonus + poison_proficiency_bonus + touch_of_magic_bonus

    damage_mod_text = f"{stat_mod} ({roll_stat_name}){magic_weapon_text}{aura_of_conquest_text}{dueling_fighting_style_text}{poison_proficiency_text}{touch_of_magic_text}"

    if has_talent("spirit attack", current_story):
        # current_story['level'] / 2), round up
        damage_dice = get_sneak_attack_dice(current_story)
        damage_mod = stat_mod
        damage_mod_text = f"{stat_mod} ({roll_stat_name})"

    return damage_dice, damage_mod, damage_mod_text

def get_base_extra_attacks(current_story, nb_of_attacks, used_bonus_action) -> Tuple[Any, Any, Any, Any]:

    # Extra attack
    if has_talent("extra attack", current_story):
        nb_of_attacks += 1

    # Already used their bonus action, no bonus action attacks
    if used_bonus_action:
        return nb_of_attacks, used_bonus_action, False, False

    # Bonus action attacks
    has_martial_arts = has_talent("martial arts", current_story) or has_talent("pugilistic arts", current_story)
    has_polearm_master = has_talent("polearm master", current_story)
    has_crossbow_expert_bonus_attack = has_talent("crossbow expert", current_story) and has_item_in_inventory("hand crossbow", current_story, True)

    used_bonus_action = False
    is_dual_wielding_without_style = False

    if has_polearm_master or has_martial_arts or has_crossbow_expert_bonus_attack:
        nb_of_attacks += 1
        used_bonus_action = True
    # Dual wielding
    elif has_talent("dual wielder", current_story) or has_talent("dual wield", current_story, partial_match=True):
        nb_of_attacks += 1
        is_dual_wielding_without_style = not has_talent("fighting style (Two-Weapon Fighting)", current_story) and not has_talent("thrown weapon expert", current_story)
        used_bonus_action = True

    return nb_of_attacks, used_bonus_action, is_dual_wielding_without_style, has_crossbow_expert_bonus_attack

# Also works for spirit attacks
def get_sneak_attack_dice(current_story):
    has_multiclass = has_talent("multiclass", current_story)
    sneak_attack_level = current_story["level"] if not has_multiclass else current_story["level"] - 1
    sneak_attack_dice = f"{math.ceil(sneak_attack_level / 2)}d6"
    return sneak_attack_dice

def process_are_opponents_defeated(setup_aid, targeted_opponents, battle_info):
    if get_is_all_opponents_defeated(battle_info):
        # Note : battle info actually ended in update_battle_info in vtai
        battle_info["battle_status"] = "victorious"
        return setup_aid["all_opponents_defeated"]
    
    elif get_is_targeted_opponents_defeated(targeted_opponents):
        return setup_aid["all_opponents_within_range_defeated"]
    
    return None

def get_remaining_opponents_text(battle_info, setup_aid):
    # Remaining opponents texts
    remaining_opponents = [opponent for opponent in battle_info["opponents"] if opponent["hp"] > 0]
    remaining_text = ""
    
    if len(remaining_opponents) > 0:
        remaining_opponents_texts = []

        for opponent in remaining_opponents:
            opponent_health_label = get_opponent_health_status(opponent["hp"], opponent["max_hp"])
            opponent_health_status_text = setup_aid[opponent_health_label]
            remaining_opponents_texts.append(f"{opponent['identifier']} ({opponent_health_status_text})")

        remaining_text = f"{len(remaining_opponents_texts)} remaining opponents: " + ", ".join(remaining_opponents_texts) + f". {setup_aid['battle_still_ongoing']}" if len(remaining_opponents_texts) > 0 else ""

    return remaining_text

def clean_section_obj(section_obj):
    if "info" in section_obj and not section_obj["info"]:
        del section_obj["info"]

    if "start_info" in section_obj and not section_obj["start_info"]:
        del section_obj["start_info"]

def get_nb_attacks_text(nb_attacks_vs_current_opponent, weapon_used = "", has_crossbow_expert_bonus_attack = False):
    # Exception hand crossbow offhand (skip if main attack was hand crossbow, can just say attacked 2 times with it then)    
    if has_crossbow_expert_bonus_attack and weapon_used is not None and not "hand crossbow" in weapon_used:
        return f" {nb_attacks_vs_current_opponent - 1} times and with 'Hand Crossbow' once"
    else:
        return f" {nb_attacks_vs_current_opponent} times" if nb_attacks_vs_current_opponent > 1 else ""

def add_attacks_current_opponent_roll_text(current_opponent_roll_text, nb_of_attacks_text, attack_result_texts, setup_aid, total_nb_attacks_vs_current_opponent):
    current_opponent_roll_text = current_opponent_roll_text.replace("#number_of_times#", nb_of_attacks_text)

    nb_attacks = 0
    nb_successful_attacks = 0

    # Replace the attack result text with the actual result
    for x, attack_result in enumerate(attack_result_texts):
        if attack_result.startswith("#action_result#"):
            action_result = attack_result.replace("#action_result#", "")
            result_text = setup_aid[action_result + "_words"]

            # Attack result text
            if total_nb_attacks_vs_current_opponent == 1:
                attack_result_text = setup_aid[f"attack_result"].replace("#attack_result#", result_text)
            else:
                order_name = get_order_text(nb_attacks + 1)
                attack_result_text = setup_aid[f"attack_result_order"].replace("#order#", order_name).replace("#attack_result#", result_text)
            
            attack_result_texts[x] = attack_result_text

            nb_attacks += 1
            nb_successful_attacks += 1 if "success" in action_result else 0

    combined_attack_results = ", ".join(attack_result_texts)
    combined_attack_results = combined_attack_results[0].upper() + combined_attack_results[1:] if len(combined_attack_results) > 0 else ""

    current_opponent_roll_text += combined_attack_results + "."
    return current_opponent_roll_text, nb_successful_attacks

def add_explanation_last_opponent_health(last_attacked_opponents, battle_info, setup_aid):
    # Add and explanation of the current opponent's health after the last attack if any attacks were successful vs this opponent, but it was not defeated.
        # Reason: Otherwise, can get confused about whether the opponent was defeated or not.
    if battle_info is not None and last_attacked_opponents is not None and len(last_attacked_opponents) > 0:
        current_opponent = last_attacked_opponents[0]
        
        # 1st opponent
        opponent_health_label = get_opponent_health_status(current_opponent["hp"], current_opponent["max_hp"])
        opponent_health_status_text = setup_aid[opponent_health_label]
        opponent_health_explanation_text = setup_aid["last_opponent_wounded_explanation"] # Can be replaced further down
        
        # Dual target
        if len(last_attacked_opponents) > 1:
            dual_opponent = last_attacked_opponents[1]

            # Skip dual opponent text if the dual opponent was defeated
            if dual_opponent["hp"] > 0:
                dual_opponent_health_label = get_opponent_health_status(dual_opponent["hp"], dual_opponent["max_hp"])
                dual_opponent_health_status_text = setup_aid[dual_opponent_health_label]

                opponent_health_explanation_text = setup_aid["last_opponent_dual_wounded_explanation"] # Replace the explanation with one including both opponents
                opponent_health_explanation_text = opponent_health_explanation_text.replace("#opponent_2#", 
                dual_opponent["identifier"]).replace("#opponent_health_2#", dual_opponent_health_status_text)
        
        # Replace at the end, since the explanation text can be overwritten depending on the dual target
        opponent_health_explanation_text = opponent_health_explanation_text.replace("#opponent#", current_opponent["identifier"]).replace("#opponent_health#", opponent_health_status_text)
        
        return opponent_health_explanation_text

    return None

def get_combatants_health_history(combatants, current_story, include_mc_health = False):
    health_history = []

    if include_mc_health:
        health_history.append(current_story["hp"])

    for combatant in combatants:
        health_history.append(combatant['hp'])

    return health_history 

def process_roll_attack(roll_results: Roll_Attack_Object, current_story, setup_aid, opponent_sheets, using_smite = False, using_action_surge = False, using_reckless_attack = False, using_flurry_of_blows = False, using_patient_defense = False, using_bardic_inspiration = False) -> Tuple[Any, Any, Any, Any, Any]:
    if roll_results is None:
        return None, None, False, None, None

    opponent_identity, target_number, target_approximate_location_known, weapon_used, damage_type, is_ranged_attack, roll_stat, is_hidden, is_sneak_attack, is_favored_enemy = roll_results.extract()

    # Determine opponent and weapon
    opponent_identity = opponent_identity if opponent_identity is not None else "unknown opponent"

    if not target_approximate_location_known:
        print_log("WARNING: Target location not known, attack failed.", True)
        return setup_aid["attack_target_location_unknown"].replace("#attack_target#", opponent_identity), None, True, None, None

    # Get opponents currently being targeted from battle info
    targeted_opponents, battle_info, _, _ = get_battle_info_combatants(current_story, opponent_identity, target_number, True, is_ranged_attack)

    if len(targeted_opponents) == 0:
        print(f"ERROR: No opponents found in battle info for {opponent_identity}")
        return None, None, True, None, None
    
    # Always have the same format (both a short and a long, even if the one given wasn't long)
    relevant_stat_short = roll_stat[:3].lower()
    roll_stat_name = get_long_stat_name(relevant_stat_short)

    # Override attack ability if present (always dex)
    attack_ability_override = current_story.get("attack_ability")
    if attack_ability_override is not None:
        roll_stat_name = attack_ability_override
        relevant_stat_short = attack_ability_override[:3].lower()
    elif roll_stat_name is None:
        roll_stat_name = "strength"
        relevant_stat_short = "str"

    nb_of_attacks = 1

    # Has allies
    allies = battle_info.get("allies", [])
    ally_is_nearby = len([ally for ally in allies if ally["hp"] > 0]) > 0

    # Rage
    is_raging = current_story.get("is_raging", False)

    # # Sharpshooter or Great Weapon Master (Both the same bonus)
    has_talent_sharpshooter = has_talent("sharpshooter", current_story)
    has_talent_gwm = has_talent("great weapon master", current_story)
    #used_bonus_action = used_patient_defense = False

    # Ki points
    nb_of_ki_points = current_story.get("ki_points", 0)

    # Used bonus action for something else
    used_bonus_action = using_patient_defense or using_bardic_inspiration

    # Flurry of Blows
    used_flurry_of_blows = has_talent("flurry of blows", current_story) and nb_of_ki_points > 0 and using_flurry_of_blows and not used_bonus_action
    
    if used_flurry_of_blows:
        nb_of_attacks += 2
        used_bonus_action = True

    # Determine how many attacks are made
    nb_of_attacks, used_bonus_action, is_dual_wielding_without_style, has_crossbow_expert_bonus_attack = get_base_extra_attacks(current_story, nb_of_attacks, used_bonus_action)

    # roll 1d8 to determine if action surge is triggered
    has_triggered_action_surge = False
    is_using_random_action_surge = False
    
    if has_talent("action surge", current_story) and ((using_action_surge and not current_story.get("action_surge_used", False)) or rd.randint(1, 8) == 8):
        nb_of_attacks += 2
        has_triggered_action_surge = True

        if using_action_surge:
            current_story["action_surge_used"] = True
        else:
            is_using_random_action_surge = True
    
    is_in_frenzied_rage = current_story.get("is_frenzied", False)# Frenzy
    can_do_extra_attack_gwm = False

    # Frenzy
    if is_in_frenzied_rage and not used_bonus_action:
        nb_of_attacks += 1
    # Will be skipped if didn't kill enemy or crit
    elif has_talent_gwm and not used_bonus_action:
        nb_of_attacks += 1
        can_do_extra_attack_gwm = True

    base_attack_bonus, base_attack_text = get_attack_bonus(current_story, is_ranged_attack, roll_stat_name)

    # Touch of magic (light or death)
    touch_of_magic = get_talent("touch of light", current_story)
    touch_of_magic = touch_of_magic if touch_of_magic is not None else get_talent("touch of death", current_story)
    can_use_touch_of_magic = touch_of_magic is not None

    # spirit attack
    has_spirit_attack = has_talent("spirit attack", current_story)
    if has_spirit_attack:
        weapon_used = "spirit attack"

    # Tides of chaos
    tides_of_chaos_bonus, tides_of_chaos_text = get_tides_of_chaos_bonus(current_story)

    # fighting style (great weapon fighting)
    has_great_weapon_fighting = has_talent("fighting style (great weapon fighting)", current_story)
    # improved critical
    has_improved_critical = has_talent("improved critical", current_story)
    # has brutal critical
    has_brutal_critical = has_talent("brutal critical", current_story)
    # has Aura of Conquest
    has_aura_of_conquest = has_talent("aura of conquest", current_story)

    can_use_sneak_attack = has_talent("sneak attack", current_story)

    total_attacks_dmg = 0
    nb_damage_sources = 0

    roll_texts = []
    action_results = []
    
    has_bonus_action = True
    has_hidden_advantage = is_hidden

    # If enemy skipped first turn, then pc played first even if enemy turn = 1
        # If no battle_info, assume pc played first
    enemy_has_not_taken_turn = battle_info["enemy_turn"] == 0

    # Assassinate advantage if enemies haven't taken their turn yet
    has_assassinate_advantage = has_talent("assassinate", current_story) and enemy_has_not_taken_turn

    # Assassinate crit if enemies are surprised (can only happen on the first turn)
    has_assassinate_crit = has_assassinate_advantage and are_opponents_surprised(battle_info)

    has_elven_accuracy = has_talent("elven accuracy", current_story)
    has_reckless_attack_advantage = has_talent("reckless attack", current_story) and using_reckless_attack

    nb_attacks_performed = 0
    has_defeated_opponent_or_crit = False

    current_opponent = current_dual_target = None
    current_opponent_identity = ""
    current_opponent_roll_text = ""
    nb_attacks_vs_current_opponent = 0

    attack_result_texts = []
    attack_objs = []

    for x in range(nb_of_attacks):
        is_first_attack = x == 0

        current_opponent, current_opponent_sheet = get_next_combatant_sheet(targeted_opponents, opponent_sheets)
        if current_opponent is None:
            print_log(f"WARNING: No more opponents left to target", True)
            continue
        elif current_opponent_sheet is None:
            print(f"ERROR: No opponent sheet found for {opponent_identity}")
            continue
        
        # Skip extra attack GWM if didn't kill enemy or crit
        if can_do_extra_attack_gwm and x >= (nb_of_attacks - 1) and not has_defeated_opponent_or_crit:
            continue

        if current_opponent_identity != current_opponent["identifier"]:
            current_opponent_identity = current_opponent["identifier"]

            # write roll_text
            then_text = "then " if x > 0 else ""
            base_attack = setup_aid["base_attack"].replace("#then_text#", then_text) # Add 'then' for all subsequent attacks
            weapon_used_text = f" with '{weapon_used}'" if weapon_used is not None else ""
            
            base_roll_msg = base_attack.replace("#opponent_identity#", current_opponent_identity).replace("#weapon_text#", weapon_used_text)

            if current_opponent_roll_text != "":
                nb_of_attacks_text = get_nb_attacks_text(nb_attacks_vs_current_opponent, weapon_used, has_crossbow_expert_bonus_attack)

                current_opponent_roll_text, _ = add_attacks_current_opponent_roll_text(current_opponent_roll_text, nb_of_attacks_text, attack_result_texts, setup_aid, nb_attacks_vs_current_opponent)
                roll_texts.append(current_opponent_roll_text)
                
                attack_result_texts = []
                current_dual_target = None # Reset whenever we target a new opponent

            current_opponent_roll_text = base_roll_msg
            nb_attacks_vs_current_opponent = 1
        else:
            nb_attacks_vs_current_opponent += 1

        # Lucky
        has_lucky_advantage, lucky_text = has_gotten_lucky(current_story, x, nb_of_attacks)

        # Advantage on first attack when attacking from hidden
        has_advantage = has_assassinate_advantage or has_hidden_advantage or has_lucky_advantage or has_reckless_attack_advantage
        which_advantage_text = "assassinate" if has_assassinate_advantage else ("hidden" if has_hidden_advantage else (lucky_text if has_lucky_advantage else ("reckless attack" if has_reckless_attack_advantage else None)))

        # Opponent's AC
        current_opponent_ac = current_opponent_sheet["ac"]

        # Sharpshooter or GWM
        can_use_sharpshooter_or_gwm = (has_talent_sharpshooter and is_ranged_attack) or (has_talent_gwm and not is_ranged_attack)
        using_sharpshooter_or_gwm = is_using_sharpshooter_or_gwm(current_story, base_attack_bonus, current_opponent_ac, using_reckless_attack) if can_use_sharpshooter_or_gwm else False

        sharpshooter_or_gwm_bonus = -5 if using_sharpshooter_or_gwm else 0
        sharpshooter_or_gwm_name = "SharpS" if has_talent_sharpshooter else "GW Master"
        sharpshooter_or_gwm_text = f" - 5 ({sharpshooter_or_gwm_name})" if using_sharpshooter_or_gwm else ""

        d20_roll, advantage_text = roll_d20(which_advantage_text, has_advantage, has_elven_accuracy = has_elven_accuracy)
        has_hidden_advantage = is_hidden and has_talent("skulker", current_story) # Clear hidden advantage after first attack, unless skulker

        final_roll_result = d20_roll + base_attack_bonus + sharpshooter_or_gwm_bonus + tides_of_chaos_bonus

        is_critical = d20_roll == 20 or (has_improved_critical and d20_roll == 19) or has_assassinate_crit

        # Action result
        action_result, action_result_text = get_roll_action_result(d20_roll, final_roll_result, current_opponent_ac, has_imp_crit=has_improved_critical)

        # Text
        text_color = "green" if "success" in action_result else "red"
        
        # Roll info
        roll_info_base_atack_total = d20_roll + base_attack_bonus

        roll_info_base_target = f"Target => {opponent_identity}"
        roll_info_base_attack = f"[{d20_roll}] + {base_attack_bonus} = #{text_color}#{roll_info_base_atack_total}#{text_color}#" 
        roll_info_base_attack_detailed = f"[{d20_roll}] + {base_attack_text} = {roll_info_base_atack_total}"

        roll_info_optional_with_total = f"{sharpshooter_or_gwm_text}{tides_of_chaos_text} = {final_roll_result}" if using_sharpshooter_or_gwm or tides_of_chaos_bonus != 0 else ""

        roll_info_text = f"#base_attack#{roll_info_optional_with_total} vs AC {current_opponent_ac}" 

        roll_info_text += advantage_text

        # Add in the base attack (Print includes more details)
        print_log(roll_info_text.replace("#base_attack#", roll_info_base_attack_detailed))
        roll_info_text = roll_info_text.replace("#base_attack#", roll_info_base_attack)

        roll_info_text_damage = roll_text_damage = ""
        total_attack_damage_including_extra = 0
        attack_dmg = 0

        # Damages
        if "success" in action_result:
            skip_dmg_mod = x == 1 and is_dual_wielding_without_style
            damage_dice, damage_mod, _ = get_damage_bonus(current_story, is_ranged_attack, roll_stat_name, skip_dmg_mod)

            if is_raging:
                damage_mod += get_bonus_rage_damage(current_story)

            # favored enemy bonus
            if is_favored_enemy:
                damage_mod += 4

            # Fire monastery, + 2 dmg on flurry of blows attacks
            is_using_fire_fists = used_flurry_of_blows and has_talent("fire fists", current_story) and x > 1
            if is_using_fire_fists:
                damage_mod += 2

            if using_sharpshooter_or_gwm:
                damage_mod += 10

            roll_dmg_text, attack_dmg = process_damage_dice(damage_dice, is_critical, damage_mod, reroll_1_and_2=has_great_weapon_fighting, has_brutal_critical=has_brutal_critical, is_short_dmg_text=True)
            roll_info_text += f". {roll_dmg_text}"
            nb_damage_sources += 1

            damage_details = []

            if is_raging:
                damage_details.append("Rage")

            # Either GWM or Sharpshooter
            if using_sharpshooter_or_gwm:
                damage_details.append(sharpshooter_or_gwm_name)

            # Assassinate
            if has_assassinate_advantage:
                damage_details.append("Assassinate")

            if is_favored_enemy:
                damage_details.append("Favored Enemy")

            if has_aura_of_conquest:
                damage_details.append("Aura of Conquest")

            if is_using_fire_fists:
                damage_details.append("Fire Fists")

            if can_use_touch_of_magic:
                touch_of_magic_domain = "Light" if "light" in touch_of_magic else "Death"
                damage_details.append(f"Touch of {touch_of_magic_domain}")

            roll_info_text += f" ({', '.join(damage_details)})" if len(damage_details) > 0 else ""

            # SNEAK ATTACK
            sneak_attack_dmg = 0

            # Can use rakish audacity if only one opponent or less is melee
            can_use_rakish_audacity = has_talent("rakish audacity", current_story) and sum([1 for opponent in targeted_opponents if not opponent["is_ranged"]]) <= 1

            if can_use_sneak_attack and (has_advantage or is_sneak_attack or ally_is_nearby or can_use_rakish_audacity):
                sneak_attack_dice = get_sneak_attack_dice(current_story)

                sneak_attack_dmg_text, sneak_attack_dmg = process_damage_dice(sneak_attack_dice, is_critical, is_sneak_attack=True, is_short_dmg_text=True)
                
                roll_info_text += f"\n{sneak_attack_dmg_text}"
                attack_dmg += sneak_attack_dmg
                nb_damage_sources += 1
                can_use_sneak_attack = False # One sneak attack per turn

                attack_result_texts.append(setup_aid["special_text_attack"].replace("#special_text#", "Sneak Attack"))

            # DIVINE SMITE
            smite_dmg = 0
            if has_talent("divine smite", current_story) and (using_smite or is_critical):
                highest_spell_slot = 0

                if using_smite:
                    # Find the highest available spell slot (inverse order)
                    for spell_slot_index in range(len(current_story["spell_slots"]) - 1, -1, -1): # Don't use 'x' in the loop, would clash with the outer loop
                        available_spell_slot_count = current_story["spell_slots"][spell_slot_index]
                        if available_spell_slot_count > 0:
                            highest_spell_slot = spell_slot_index + 1
                            current_story["spell_slots"][spell_slot_index] -= 1
                            break
                
                # If critical, free smite even if none remain or already used this turn
                if is_critical and highest_spell_slot == 0:
                    highest_spell_slot = 1

                # Smite if a spell slot was found
                if highest_spell_slot > 0:
                    smite_dice = f"{1 + highest_spell_slot}d8"
                    smite_dmg_text, smite_dmg = process_damage_dice(smite_dice, is_critical, is_smite=True, is_short_dmg_text=True)
                    roll_info_text += f"\n{smite_dmg_text}"
                    
                    attack_dmg += smite_dmg
                    nb_damage_sources += 1
                    using_smite = False # Only one smite per turn
                else:
                    roll_info_text += f"\nDivine smite failed: No spell slot available."

                attack_result_texts.append(setup_aid["special_text_attack"].replace("#special_text#", "Divine Smite"))

            roll_info_text_damage, roll_text_damage, has_bonus_action, total_attack_damage_including_extra, has_reduced_opponent_0_hp, dual_target = process_damage_battle_info("attack", current_story, setup_aid, targeted_opponents, attack_dmg, has_bonus_action=has_bonus_action, is_first_attack = is_first_attack)

            if dual_target is not None:
                current_dual_target = dual_target

            # Used aoe attack (ex: cleave)
            if total_attack_damage_including_extra != attack_dmg:
                nb_damage_sources += 1

            # Check if opponent was defeated or if it was a crit (for GWM)
            if has_reduced_opponent_0_hp or is_critical:
                has_defeated_opponent_or_crit = True

        total_attacks_dmg += total_attack_damage_including_extra

        roll_info_text += f"\n{roll_info_text_damage}" if roll_info_text_damage != "" else ""

        action_results.append(action_result)

        attack_result_texts.append("#action_result#" + action_result)
        if roll_text_damage:
            attack_result_texts.append(roll_text_damage)

        nb_attacks_performed += 1

        attack_obj = {
            "number": x + 1,
            "rolls": [d20_roll],
            "start_info": roll_info_base_target,
            "info": roll_info_text,
            "adversaries_hp": get_combatants_health_history(battle_info["opponents"], current_story)
        }
        attack_objs.append(attack_obj)
    
    # Combine the rollinfos for all attacks
    weapon_used_for_attack = weapon_used if not has_crossbow_expert_bonus_attack else weapon_used + " / Hand Crossbow"
    nb_attacks_text = f" (x{nb_attacks_performed})" if nb_attacks_performed > 1 else ""

    roll_info_text_intro = f"{weapon_used_for_attack}{nb_attacks_text}"

    character_obj = {
        "name": "main",
        "unique_actions": [
            {
                "name": weapon_used_for_attack,
                "info": roll_info_text_intro,
                "sound": get_sound_triple(damage_type, is_ranged_attack, weapon_used),
                "actions": attack_objs 
            }
        ]
    }

    nb_of_attacks_text = get_nb_attacks_text(nb_attacks_vs_current_opponent, weapon_used, has_crossbow_expert_bonus_attack)

    # Conclude the last opponent's attacks
    current_opponent_roll_text, nb_success_last_opponent = add_attacks_current_opponent_roll_text(current_opponent_roll_text, nb_of_attacks_text, attack_result_texts, setup_aid, nb_attacks_vs_current_opponent)
    roll_texts.append(current_opponent_roll_text)

    last_attacked_opponents = []
    
    if nb_success_last_opponent > 0 and current_opponent is not None and current_opponent["hp"] > 0:
        last_attacked_opponents.append(current_opponent)

        if current_dual_target is not None:
            last_attacked_opponents.append(current_dual_target)

    roll_info_texts = []

    # Flurry of blows
    if used_flurry_of_blows and nb_attacks_performed > 3:
        current_story["ki_points"] -= 1 # Only use flurry of blows if more than 3 attacks performed

        flurry_of_blow_text = "Flurry of blows: 1 additional attack (costs 1 ki point)"
        flurry_of_blow_text += " + fire damage" if has_talent("fire fists", current_story) else ""
        roll_info_texts.append(f"{flurry_of_blow_text}.")

    # Extra ttack frenzy
    if is_in_frenzied_rage:
        roll_info_texts.append("Frenzied rage: 1 additional attack")

    # Performed 1 additional attack with GWM (doesn'T stack with frenzy)
    elif can_do_extra_attack_gwm and has_defeated_opponent_or_crit and nb_attacks_performed == nb_of_attacks:
        roll_info_texts.append("Great Weapon Master: 1 additional attack")

    is_performed_all_attacks = nb_attacks_performed >= nb_of_attacks
    is_performed_all_attacks_minus_1 = nb_attacks_performed >= nb_of_attacks - 1

    # Action surge roll info
    if has_triggered_action_surge and (is_performed_all_attacks or is_performed_all_attacks_minus_1):
        nb_additional_attacks = 2 if is_performed_all_attacks else 1
        random_action_surge_text = "Random " if is_using_random_action_surge else ""
        roll_info_texts.append(f"{random_action_surge_text}Action surge triggered: {nb_additional_attacks} additional attacks")

    # TOTAL DMG (on new line)
    if nb_damage_sources > 1:
        roll_info_texts.append(f"Total damage: #bold#{total_attacks_dmg}#bold#")

    # if any of the action_results contained success, then add rage attack
    if is_raging and any("success" in action_result for action_result in action_results):
        # Add text about the attack being stronger because of the rage (only if it hits)
        raging_text = setup_aid['rage_attack'] if nb_attacks_performed == 1 else setup_aid['rage_attack_multiple']
        roll_texts.append(raging_text)

    # Attacked from hidden
    if is_hidden:
        roll_texts.append(setup_aid["hidden_attack"])

    # Assassinate
    if has_assassinate_advantage:
        roll_texts.append(setup_aid["assassinate_attack"])

    # Flurry of blows
    if used_flurry_of_blows and nb_attacks_performed > 3:
        flurry_of_blows_text = setup_aid["flurry_of_blows_attack"]
        flurry_of_blows_text += (setup_aid["fire_fists_attack"] if has_talent("fire fists", current_story) else "") + "."
        roll_texts.append(flurry_of_blows_text)
    # If did bonus attack with fire dmg, but no flurry, then mention fire on last attack.
    elif used_flurry_of_blows and nb_attacks_performed > 2:
        roll_texts.append(setup_aid["fire_fists_last_attack"])

    if has_triggered_action_surge and (is_performed_all_attacks or is_performed_all_attacks_minus_1):
        action_surge_attacks = "two" if is_performed_all_attacks else "one"
        action_surge_text = setup_aid["action_surge_attack"].replace("#nb_attacks#", action_surge_attacks)
        roll_texts.append(action_surge_text)

    if has_spirit_attack:
        roll_texts.append(setup_aid["spirit_attack"])

    roll_text = " ".join(roll_texts) if len(roll_texts) > 0 else ""

    roll_info_text_combined = "#message_separator#".join(roll_info_texts)

    # Add currently active effects
    current_effects = []
    if has_reckless_attack_advantage:
        current_effects.append("Reckless Attack")

    roll_info_intro_text = "Effects: " + ", ".join(current_effects) if len(current_effects) > 0 else ""

    section_obj = {
        "name": "main",
        "start_info": roll_info_intro_text,
        "characters": [character_obj],
        "info": roll_info_text_combined
    }
    clean_section_obj(section_obj)

    return roll_text, section_obj, False, targeted_opponents, last_attacked_opponents

def get_skills_array(roll_skill):
    return [remove_parentheses(skill).lower() for skill in re.split(r'\/| or |, ', roll_skill)] #

def get_has_skill_expert(skill, current_story):
    return has_talent(f"skill expert ({skill})", current_story) or has_talent(f"expertise ({skill})", current_story) or has_talent(f"canny ({skill})", current_story)

def adjust_dc(base_dc):
    # Define the probabilities and the corresponding DC adjustments
    adjustments = [2, 1, 0, -1, -2]
    probabilities = [0.08, 0.12, 0.35, 0.25, 0.20]
    adjustment = rd.choices(adjustments, probabilities)[0]

    # Apply the adjustment to the base DC
    new_dc = base_dc + adjustment
    
    if new_dc != base_dc:
        print_log(f"DC adjusted from {base_dc} to {new_dc}")

    return new_dc

def process_roll_skill(roll_results: Roll_Skill_Object, current_story, setup_aid, using_special_ability) -> Tuple[Any, Any]:
    if roll_results is None:
        return None, None

    roll_skill, roll_dc, roll_stat, reason, special_ability = roll_results.extract()

    # Hardcode skill and stat when using a special ability
    if using_special_ability:
        roll_skill = current_story.get("special_ability_skill", None)
        roll_stat = get_use_special_ability_stat(current_story)

    base_proficiency_bonus = get_proficiency_bonus(current_story["level"])

    # Always have the same format (both a short and a long, even if the one given wasn't long)
    relevant_stat_short = roll_stat[:3].lower()
    roll_stat_name = get_long_stat_name(relevant_stat_short)
    
    # Split roll_skill into an array of skills
    roll_skills = get_skills_array(roll_skill)

    # Initialize variables
    has_proficiency = False
    cleaned_skill = roll_skills[0].lower() # Pick first one by default

    # Check if any skill in roll_skills is present in current_story["skills"]
    for skill in roll_skills:
        if skill in [remove_parentheses(s) for s in current_story["skills"]]:
            cleaned_skill = skill
            has_proficiency = True
            break

    # Check if has skill expert or expertise (bard) or canny (ranger)
    has_skill_expert = get_has_skill_expert(skill, current_story)

    # Fix skill stat if needed
    fixed_stat = fix_skill_stat(cleaned_skill, relevant_stat_short)
    if fixed_stat is not None:
        roll_stat_name = fixed_stat
        relevant_stat_short = roll_stat_name[:3].lower()

    special_ability_text = f": {special_ability}" if using_special_ability else ""

    roll_name = f"Skill check ({cleaned_skill}){special_ability_text}" if cleaned_skill != "" else "Ability check"

    # Get stats
    relevant_stat_mod = get_stat_mod(current_story, relevant_stat_short)

    has_lucky_advantage, lucky_text = has_gotten_lucky(current_story)
    has_rage_str_advantage = current_story.get("is_raging", False) and relevant_stat_short == "str"
    has_advantage = has_lucky_advantage or has_rage_str_advantage

    has_frenzy_disadvantage = has_talent("frenzy", current_story) and current_story.get("frenzy_used", False)
    which_advantage_text = lucky_text if has_lucky_advantage else ("rage" if has_rage_str_advantage else ("exhausted" if has_frenzy_disadvantage else None))

    has_reliable_talent = has_talent("reliable talent", current_story) and has_proficiency
    has_silver_tongue = has_talent("silver tongue", current_story) and cleaned_skill in ["persuasion", "deception"]

    d20_roll, advantage_text = roll_d20(which_advantage_text, has_advantage, has_frenzy_disadvantage)

    # Reliable talent or silver tongue
    replaced_d20_roll = None
    if (has_reliable_talent or has_silver_tongue) and d20_roll < 10:
        replaced_d20_roll = d20_roll
        d20_roll = 10

    # Half proficiency on all non-proficient skills
    if has_talent("jack of all trades", current_story) and not has_proficiency:
        has_proficiency = True
        base_proficiency_bonus = base_proficiency_bonus // 2

    final_proficiency_bonus = (base_proficiency_bonus if has_proficiency else 0) * (2 if has_skill_expert else 1)
    final_roll_result = d20_roll + relevant_stat_mod + final_proficiency_bonus

    # FLASH OF GENIUS
    flash_of_genius_text = ""
    if has_talent("flash of genius", current_story) and rd.randint(1, 4) == 4:
        int_score = get_stat_mod(current_story, "int")
        final_roll_result += int_score
        flash_of_genius_text = f" + {int_score} (Flash of genius)"

    # Stealth disadvantage
    stealth_disadvantage_text = ""
    if has_talent("stealth disadvantage", current_story) and cleaned_skill == "stealth":
        final_roll_result -= 2
        stealth_disadvantage_text = f" - {2} (heavy armor)"

    # Remarkable athlete
    remarkable_athlete_text = ""
    if has_talent("remarkable athlete", current_story) and relevant_stat_short in ["str", "dex", "con"]:
        roll_bonus = math.ceil(base_proficiency_bonus / 2)
        final_roll_result += roll_bonus
        remarkable_athlete_text = f" + {roll_bonus} (remarkable athlete)"

    # Thief bonus
    thief_text = ""
    if has_talent("fast hands", current_story) and cleaned_skill in ["sleight of hand", "thieves tools"]:
        roll_bonus = math.ceil(base_proficiency_bonus / 2)
        final_roll_result += roll_bonus
        thief_text = f" + {roll_bonus} (fast hands)"

    # Tides of chaos
    tides_of_chaos_bonus, tides_of_chaos_text = get_tides_of_chaos_bonus(current_story)
    final_roll_result += tides_of_chaos_bonus

    # Randomly change the DC a bit (more likely to go down than up)
    roll_dc = adjust_dc(roll_dc)

    # Action result
    action_result, action_result_text = get_roll_action_result(d20_roll, final_roll_result, roll_dc)

    # Text
    proficiency_expert_text = "expert proficiency" if has_skill_expert else "proficiency"
    proficiency_text = f" + {final_proficiency_bonus} ({proficiency_expert_text})" if has_proficiency else ""
    text_color = "green" if "success" in action_result else "red"

    roll_info_text = f"[{d20_roll}] + {relevant_stat_mod} ({roll_stat_name}){proficiency_text}{flash_of_genius_text}{stealth_disadvantage_text}{thief_text}{tides_of_chaos_text}{remarkable_athlete_text} = #{text_color}#{final_roll_result}#{text_color}# vs DC {roll_dc}" #: {action_result_text}"

    # Advantage text
    roll_info_text += advantage_text

    if replaced_d20_roll is not None:
        ability_name = "reliable talent" if has_reliable_talent else "silver tongue"
        roll_info_text += f"#message_separator#Used the '{ability_name}' ability to replace a roll of {replaced_d20_roll} with a 10."

    flash_of_genius_roll_text = ""
    if flash_of_genius_text != "" and "success" in action_result:
        roll_info_text += f"#message_separator#You had a flash of genius!"
        flash_of_genius_roll_text = " They had a flash of genius!"

    print_log(roll_info_text)

    # Determine the skill or ability text
    if cleaned_skill != '':
        skill_or_ability_text = setup_aid["skill_text"].replace("#skill_name#", cleaned_skill).replace("#stat_name#", roll_stat_name)
    else:
        skill_or_ability_text = setup_aid["ability_text"].replace("#stat_name#", roll_stat_name)

    # Determine why roll needed
    reason = reason if reason is not None else ""
    reason = reason + "." if not reason.endswith('.') else reason 

    # flash of genius
    
    # write roll_text
    base_roll_msg =  setup_aid["base_skill"].replace("#skill_or_ability_text#", skill_or_ability_text).replace("#reason#", reason)
    roll_text = f"{base_roll_msg}{flash_of_genius_roll_text} {setup_aid[action_result].replace('#injuries#', '')}"

    section_obj = {
        "name": "main",
        "characters": [
            {
                "name": "main",
                "unique_actions": [
                    {
                        "name": skill_or_ability_text,
                        "info": roll_name,
                        "actions": [
                            {
                                "rolls": [d20_roll],
                                "info": roll_info_text
                            }
                        ] 
                    }
                ]
            }
        ]
    }

    return roll_text, section_obj

def get_rolls_damage(damage_text, is_critical=False, damage_mod = None, is_minimized = False, is_maximized = False, reroll_1_and_2 = False, has_brutal_critical = False):
    # dice = [(count, side)]
    dice, modifier = process_dice(damage_text)

    # Only use the ability modifier if it's set (ex: weapon attacks)
    if damage_mod is not None: 
        modifier += damage_mod

    # Double the number of dice rolled if it's a critical hit
    if is_critical and len(dice) > 0:
        # multiply the number of dice by 2
        dice = [(count * 2, side) for count, side in dice]

        # Increase the count of the first dice by 1
        if has_brutal_critical:
            dice[0] = (dice[0][0] + 1, dice[0][1])

    # Roll the dice and place the roll results in an array
    dice_text, dice_roll_text, total = get_rolls(dice, modifier, is_minimized, is_maximized, reroll_1_and_2)

    return dice_text, dice_roll_text, total

def process_damage_total(dice_text, roll_text, total, is_saves_half = False, has_resistance = False, is_healing = False, is_sneak_attack = False, is_smite = False, has_heavy_armor_master = False, resistance_reason = "", saves_half_reason = "", is_short_dmg_text = False, is_uncanny_dodge = False, print_short_dmg_text = False, print_dmg_text = False):
    roll_title = "Damage " if not is_healing else "Healing "
    if is_sneak_attack:
        roll_title = "Sneak attack damage roll "

    if is_smite:
        roll_title = "Divine smite damage roll "

    # Heavy armor mastery
    heavy_armor_master_text = ""
    if has_heavy_armor_master:
        total = max(total - 3, 0) # -3 dmg, min 0
        heavy_armor_master_text = " - 3 (Heavy Armor Master)" 

    total_final = total // 2 if is_saves_half else total
    total_final = total_final // 2 if has_resistance else total_final
    total_final = total_final // 2 if is_uncanny_dodge else total_final

    # Resistance
    resistance_reason = resistance_reason if resistance_reason != "" else "resistance"
    resistance_text = f" / 2 ({resistance_reason})" if has_resistance else ""

    # Saves half
    saves_half_reason = saves_half_reason if saves_half_reason != "" else "saves half"
    saves_half_text = f" / 2 ({saves_half_reason})" if is_saves_half else ""

    # Uncanny dodge
    is_uncanny_dodge_text = f" / 2 (Uncanny Dodge)" if is_uncanny_dodge else ""

    half_damage_text = f"{resistance_text}{saves_half_text}{is_uncanny_dodge_text}"
    total_half_damage_text = f"{half_damage_text} = #bold#{total_final}#bold#" if has_resistance or is_saves_half or is_uncanny_dodge else ""

    hashtag = "#green#" if is_healing else "#bold#"

    roll_text_short = f"{roll_title}({dice_text}{heavy_armor_master_text}){half_damage_text} = {hashtag}{total_final}{hashtag}"
    roll_text_long = f"{roll_title}({dice_text}{heavy_armor_master_text}) : {roll_text} = {total}{total_half_damage_text}"

    if is_short_dmg_text:
        roll_text = roll_text_short
        if print_dmg_text:
            roll_text_print = roll_text_short if print_short_dmg_text else roll_text_long
            roll_text_print = roll_text_print.replace("#bold#", "")
            print_log(roll_text_print)
    else:
        roll_text = roll_text_long

    return roll_text, total_final

# Call this function to process the damage dice and the final total (can also call each individually (Ex: cast spell with save))
def process_damage_dice(damage_text, is_critical=False, damage_mod = None, is_saves_half = False, has_resistance = False, is_healing = False, is_sneak_attack = False, is_smite = False, is_minimized = False, is_maximized = False, reroll_1_and_2 = False, has_heavy_armor_master = False, has_brutal_critical = False, resistance_reason = "", saves_half_reason = "", is_short_dmg_text = False, is_uncanny_dodge = False):
    # Roll the dice and place the roll results in an array
    dice_text, dice_roll_text, total = get_rolls_damage(damage_text, is_critical, damage_mod, is_minimized, is_maximized, reroll_1_and_2, has_brutal_critical)
    
    dice_roll_text, total_final = process_damage_total(dice_text, dice_roll_text, total, is_saves_half, has_resistance, is_healing, is_sneak_attack, is_smite, has_heavy_armor_master, resistance_reason, saves_half_reason, is_short_dmg_text, is_uncanny_dodge, print_dmg_text=True)
    
    return dice_roll_text, total_final

def get_combatant_stats(ability_score, challenge_rating_text):
    relevant_stat_mod = stat_to_modifier(ability_score)
    challenge_rating = extract_int(challenge_rating_text)
    
    # If the CR was between 0 and 1 (extract_int between 0 and 1), but not == "0", then the CR bonus is 2
    if challenge_rating_text != "0" and challenge_rating == 0:
        cr_bonus = 2
    else:
        cr_bonus = get_proficiency_bonus(challenge_rating)

    return relevant_stat_mod, cr_bonus

def get_weapon_row(weapon_name):
    if weapon_name and weapon_name.lower() in weapons_data:
        return weapons_data[weapon_name.lower()]
    
    for row in weapons_data.values():
        alt_names_text = row["alt_names"]
        if not alt_names_text:
            continue

        alt_names = alt_names_text.split(";")
        alt_names = [alt_name.strip().lower() for alt_name in alt_names]

        if weapon_name.lower() in alt_names:
            return row
    
    return None

def get_skill_ability(skill_name, use_str_intimidation = False):
    if skill_name is None:
        return None, None
    
    # Go through all skills in skills_data, and see if any name is contained in skill_name or vice versa
    for skill in skills_data.values():
        if skill_name.lower() in skill["name"].lower() or skill["name"].lower() in skill_name.lower():
            found_skill_name = skill["name"]
            found_skill_ability = skill["ability"] 

            # Override ability for intimidation if use_str_intimidation is True
            if found_skill_name.lower() == "intimidation" and use_str_intimidation:
                found_skill_ability = "str"

            return found_skill_name, found_skill_ability

    return None, None

def get_weapon_info(weapon_row) -> Tuple[Any, Any]:
    if weapon_row is None:
        return None, None

    dice = weapon_row["dice"]
    avg_dmg = extract_float(weapon_row["avg_dmg"])

    return dice, avg_dmg

def find_spell_level_from_row(spell_row):
    if spell_row is not None:
        return int(spell_row["level"])

    return None

def find_spell_level(spell_name):
    spell_row = get_spell_row(spell_name)
    return find_spell_level_from_row(spell_row)

# Return True if the given class has the given spell, return None if the spell is not in the database
    # Also, return the min spell level for the spell (if it's in the database)
def any_class_has_spell(spell_name, classes_name) -> Tuple[Any, Any]:
    spell_name = spell_name.lower()
    spell_level = find_spell_level(spell_name)

    if spell_level is None:
        return None, None

    for class_name in classes_name:
        if spells_data[spell_name].get(class_name, 'False') == 'True':
            return True, spell_level
        
    return False, spell_level

def get_domain_name(current_story):
    domain_label = None
    if has_talent("domain", current_story, partial_match=True):
        domain_label = "domain"
    elif has_talent("oath", current_story, partial_match=True):
        domain_label = "oath"
    elif has_talent("specialty", current_story, partial_match=True):
        domain_label = "specialty"
    
    # If no domain, oath or specialty, return False
    if domain_label is None:
        return None

    spell_domain_text = get_talent(domain_label, current_story, partial_match=True)
    spell_domain = extract_text_in_parenthesis(spell_domain_text)

    return spell_domain

def spell_in_domain(spell_name, current_story) -> Tuple[Any, Any]:
    spell_domain = get_domain_name(current_story)

    if spell_domain is None:
        return False, None
    
    spell_level = None

    # Iterate through the domain_spells data to find the spell
    for domain_spell in domains_data.values():
        if domain_spell['name'].lower() == spell_name.lower() and domain_spell['domain'].lower() == spell_domain.lower():
            spell_level = int(domain_spell['level'])
            return True, spell_level

    return False, spell_level

# Return the alternate classes for the given class (only for spellcasting of unknown spells)
def get_alternate_classes(char_class):
    if char_class == "paladin":
        return ["cleric"]
    elif char_class == "ranger":
        return ["druid"]
    elif char_class == "druid":
        return ["cleric", "ranger"]
    elif char_class == "bard":
        return ["wizard", "cleric"]
    elif char_class in ["wizard", "sorcerer", "artificer"]:
        return ["wizard", "sorcerer"]
    else:
        return []

# Return True if any of the character's class (or any of his alternate spellcasting class) is in available_to_classes
    # Only for spellcasting of unknown spells 
def class_has_spell_available_classes(available_to_classes, char_classes):
    for char_class in char_classes:
        if char_class in available_to_classes:
            return True
        elif any(alternate_class in available_to_classes for alternate_class in get_alternate_classes(char_class)):
            return True

    return False

def get_healing(spell_name, spell_level, ability_mod, spell_row, upcast_level, char_level, has_touch_of_life = False) -> Tuple[Any, Any]:
    # Make spell_name case-insensitive and handle "mass" versions
    spell_name = spell_name.lower().replace('mass', '').strip()
    is_dice = True

    touch_of_life_text = " (preserve life)" if has_touch_of_life else ""

    healing_bonus = 0 if not has_touch_of_life else char_level + 2 + spell_level # preserve life + disciple of life bonuses

    # Healing dices
    if spell_row is not None:
        healing_dice = get_spell_damage_from_row(spell_row, spell_name, upcast_level, char_level, True)
        if healing_dice is None:
            healing_dice = "1d8" # If somehow None, but should never happen

        is_dice = "d" in healing_dice 

        # Add ability mod when it's a dice
        total_healing_bonus = ability_mod + healing_bonus if is_dice else healing_bonus
        healing = f"{healing_dice}+{total_healing_bonus}" if total_healing_bonus > 0 else healing_dice
    else:
        healing = f"{spell_level}d8+{ability_mod+healing_bonus}" # Any unknown healing spell == 1d8 per spell level

    healing_roll_text, total_healing = process_damage_dice(healing, is_healing=True, is_short_dmg_text=True) # Don't add ability mod, already added above

    # Remove the total from the healing text if it's just a number
    if not is_dice and "+" not in healing:
        healing_roll_text = f"Healing #green#{healing}#green#"
    
    roll_text = f"{healing_roll_text} hit points{touch_of_life_text}" # roll_text includes #green# for healing

    return roll_text, total_healing

def use_spell_slot(spell_level, current_story):
    # Will be 0 when using sorcery points
    if current_story["spell_slots"][spell_level - 1] > 0:
        current_story["spell_slots"][spell_level - 1] -= 1

# Return the used spell level and a boolean indicating if the spell can be cast
def get_spell_slot(spell_level, current_story) -> Tuple[Any, Any]:
    # Cantrip always available
    if spell_level == 0:
        return spell_level, True
    
    # Shouldn't happen, but just in case
    if len(current_story["spell_slots"]) < spell_level:
        return spell_level, False
    
    # Check if spell can be cast at the desired level
    if current_story["spell_slots"][spell_level - 1] > 0:
        return spell_level, True

    # Check if spell can be cast at a higher level
    new_spell_level = spell_level + 1

    while new_spell_level <= 9:
        if current_story["spell_slots"][new_spell_level - 1] > 0:
            return new_spell_level, True
        else:
            # Move to the next spell level.
            new_spell_level += 1

    return spell_level, False
    
def process_opponent_save(saving_throw, saving_throw_short, saving_throw_DC, opponent, opponent_sheet, current_story, setup_aid, base_msg, is_spell, has_used_bonus_action, saves_half, current_save_nb, nb_saves, using_heightened_spell, using_unsettling_words) -> Tuple[Any, Any, Any, Any, Any, Any, Any, Any]:

    # Get stats
    target_relevant_stat_mod, target_cr_bonus, _ = get_combatant_saving_throw_info(saving_throw_short, opponent, opponent_sheet)

    # Doesn't apply to luck feats (only chronal shift)
    has_lucky_advantage, lucky_text = has_gotten_lucky(current_story, current_save_nb, nb_saves, is_combatant_not_targeting_mc=True)

    # Roll
    d20_roll, advantage_text = roll_d20(lucky_text, has_lucky_advantage)

    final_roll_bonus = target_relevant_stat_mod + target_cr_bonus 
    final_roll_result = d20_roll + final_roll_bonus# Recalculated if the char has the "Heightened spell" or "Unsettling words" talents, see below

    special_roll_info = special_roll_info_text = special_roll_text = ""

    # Heightened spell
    if using_heightened_spell and has_talent("heightened spell", current_story, partial_match=True) and current_story.get("sorcery_points", 0) >= 3:
        # sort rolls with disadvantage
        rolls = [d20_roll, rd.randint(1, 20)]
        rolls.sort(reverse=True)
        
        d20_roll = rolls[1] # Keep lowest score
        rolls = [str(roll) for roll in rolls]

        final_roll_result = d20_roll + final_roll_bonus
        current_story["sorcery_points"] -= 3

        # Note : More like a reroll than a disadvantage, but it's easier to understand this way
        special_roll_info = f" (Disadvantage: Heightened Spell; {', '.join(rolls)})"
        special_roll_text = f"I used the Heightened Spell metamagic to make it harder for the previous opponent to resist"
        has_used_bonus_action = True

    # Unsettling words
    if using_unsettling_words and has_talent("unsettling words", current_story) and current_story.get("bardic_inspiration", 0) >= 1:
        inspiration_dice_faces = get_bardic_inspiration_dice(current_story)
        inspiration_dice_roll = rd.randint(1, inspiration_dice_faces)
        final_roll_result -= inspiration_dice_roll
        current_story["bardic_inspiration"] -= 1

        special_roll_info = f" (Unsettling Words cost 1 bardic inspiration)"
        special_roll_info_text = f" - {inspiration_dice_roll} (Unsettling Words)"
        special_roll_text = f"I used my Unsettling Words ability to make it harder for the previous opponent to resist"
        has_used_bonus_action = True

    # Action result 
    action_result_reversed, action_result_text = get_roll_action_result_one_reversed(d20_roll, final_roll_result, saving_throw_DC) 

    is_success = "success" in action_result_reversed
    text_color = "green" if is_success else "red"

    # Saves
    roll_info_target_text = f"Target => {opponent['identifier']}"
    roll_info_text = f"[{d20_roll}] + {final_roll_bonus}{special_roll_info_text} = #{text_color}#{final_roll_result}#{text_color}# vs DC {saving_throw_DC}{special_roll_info}" 

    if text_color != "green":
        roll_info_text += f" (Avoids Half)" if saves_half else f" (Avoids All)"

    base_msg = base_msg.replace("#saving_throw_text#", setup_aid["saving_throw_text"].replace("#saving_throw#", saving_throw))

    roll_info_text += advantage_text

    return d20_roll, roll_info_target_text, roll_info_text, base_msg, action_result_reversed, special_roll_text, has_used_bonus_action, is_success

def get_magic_damage_roll(current_story, damage_dice, is_critical, char_ability_mod, spell_level, is_minimized_dmg, is_maximized_dmg):
    triggered_overchannel = False
    total = 0
    roll_info_text = roll_text = dice_text = dice_roll_text = ""
    caused_damages = True
    
    # Overchannel
    if spell_level is not None and damage_dice is not None:
        # 20% chance of dealing max damage
        triggered_overchannel = has_talent("overchannel", current_story) and spell_level <= 5 and rd.randint(1, 5) == 1
        if triggered_overchannel:
            print_log("TRIGGERED OVERCHANNEL")
            is_maximized_dmg = True

    # Apply damages
    if damage_dice is not None:
        spell_damage_mod = char_ability_mod if has_talent("empowered evocation", current_story) else None

        dice_text, dice_roll_text, total = get_rolls_damage(damage_dice, is_critical, spell_damage_mod, is_minimized_dmg, is_maximized_dmg)

        if triggered_overchannel:
            roll_info_text += f"\nOverchannel triggered: The spell deals maximum damage"
            roll_text += "You overchanneled the spell, making it as powerful as it could be."

    elif damage_dice is None:
        caused_damages = False
        print_log("No damage dice for spell, no damage dealt.")

    return roll_info_text, roll_text, dice_text, dice_roll_text, total, caused_damages

def process_magic_damage(is_spell, current_story, setup_aid, targeted_opponents, roll_info_text, is_spell_attk, saves_half, spell_level, dice_text, dice_roll_text, total, is_first_opponent, caused_damages, is_success, is_save = False, total_attk_nb = None, attack_defeated_opponent = False, using_twinned_spell = False):
    roll_info_text_damages = roll_text_damages = ""
    dual_target = None
    total_attack_damage_including_extra = 0
    show_total = False
    
    # Apply damages
    if caused_damages and (is_success or (saves_half and not is_spell_attk)):
        trigger_saves_half = not is_success and not is_spell_attk and saves_half # only half dmg when enemy succeeds their save (not is_success since it's reversed for saves)
        
        roll_dmg_text, total_attack_dmg = process_damage_total(dice_text, dice_roll_text, total, trigger_saves_half, is_short_dmg_text=True, print_short_dmg_text = not is_first_opponent, print_dmg_text = not is_save)
        
        # Dmg is shown one time at the start for saves (same dmg for all opponents)
        if not is_save:
            roll_info_text += f". {roll_dmg_text}"

        attack_type = "spell" if is_spell else "action"
        roll_info_text_damages, roll_text_damages, _, total_attack_damage_including_extra, _, dual_target = process_damage_battle_info(attack_type, current_story, setup_aid, targeted_opponents, total_attack_dmg, is_spell_attk=is_spell_attk, spell_level=spell_level, total_spell_attk_nb=total_attk_nb, using_twinned_spell=using_twinned_spell)

        roll_info_text += "\n" + roll_info_text_damages if roll_info_text_damages else ""

        # If all opponents are already defeated, just apply the dmg to the total (would be 0 otherwise since hp of all opponents are 0)
        if attack_defeated_opponent:
            total_attack_damage_including_extra = total_attack_dmg

        # If more than 1 attack done when processing the damages, show the total at the end
        if total_attack_dmg != total_attack_damage_including_extra:
            show_total = True

    else:
        print_log("Spell caused no damage")

    return roll_info_text, roll_text_damages, dual_target, total_attack_damage_including_extra, show_total

def process_magic_spell_attack(current_story, setup_aid, targeted_opponents, next_opponent, next_opponent_sheet, is_auto_hit, magic_name, char_proficiency_bonus, char_ability_mod, damage_dice, spell_level, is_minimized_dmg, is_maximized_dmg, is_spell_attk, saves_half, current_attack_index, total_attk_nb, attack_defeated_opponent, is_virtual_target, using_twinned_spell) -> Tuple[Any, Any, Any, Any, Any, Any, Any]:

    advantage_text = ""
    is_success = False
    roll_info_target_text = roll_info_text =""

    if is_auto_hit:
        d20_roll = None
        action_result = "success"
        action_result_text = action_result.capitalize()
        roll_info_target_text = f"Target => {next_opponent['identifier']}"
        roll_info_text = "#green#Automatic hit#green#"
        is_success = True
    else:
        target_AC = next_opponent_sheet["ac"]

        # Lucky
        has_lucky_advantage, lucky_text = has_gotten_lucky(current_story, current_attack_index, total_attk_nb)

        # Roll
        d20_roll, advantage_text = roll_d20(lucky_text, has_lucky_advantage)

        # Proficiency bonus
        char_proficiency_text = f" + {char_proficiency_bonus} (Proficiency)" if char_proficiency_bonus > 0 else ""

        # Tides of chaos
        tides_of_chaos_bonus, tides_of_chaos_text = get_tides_of_chaos_bonus(current_story)

        # magic focus bonus
        magic_focus_bonus = get_magic_focus_bonus(current_story)
        magic_focus_text = f" + {magic_focus_bonus} (Magic focus bonus)" if magic_focus_bonus > 0 else ""

        final_roll_bonus = char_ability_mod + char_proficiency_bonus + tides_of_chaos_bonus + magic_focus_bonus
        final_roll_result = d20_roll + final_roll_bonus

        action_result, action_result_text = get_roll_action_result(d20_roll, final_roll_result, target_AC)
        is_success = "success" in action_result
        text_color = "green" if is_success else "red"

        base_spell_text = f"{final_roll_bonus}"
        detailed_base_spell_text = f"{char_ability_mod} ({current_story.get('spellcasting_ability', '').capitalize()}){char_proficiency_text}{tides_of_chaos_text}{magic_focus_text}"

        roll_info_target_text = f"Target => {next_opponent['identifier']}"
        roll_info_text = f"[{d20_roll}] + #base_spell_text# = #{text_color}#{final_roll_result}#{text_color}# vs AC {target_AC}"

        print_log(roll_info_text.replace("#base_spell_text#", detailed_base_spell_text))

        roll_info_text = roll_info_text.replace("#base_spell_text#", base_spell_text)

    roll_info_text += advantage_text
    
    is_critical = d20_roll == 20

    roll_info_magic_dmg, special_damage_roll_text, dice_text, dice_roll_text, total, caused_damages = get_magic_damage_roll(current_story, damage_dice, is_critical, char_ability_mod, spell_level, is_minimized_dmg, is_maximized_dmg)

    # special dmg msg only if spell hits
    roll_info_text += roll_info_magic_dmg if is_success else "" 

    roll_info_text, roll_text_damages, dual_target, total_dmg, show_total = process_magic_damage(True, current_story, setup_aid, targeted_opponents, roll_info_text, is_spell_attk, saves_half, spell_level, dice_text, dice_roll_text, total, True, caused_damages, is_success, total_attk_nb=total_attk_nb, attack_defeated_opponent = attack_defeated_opponent, using_twinned_spell=using_twinned_spell)

    # Skip the dmg text if all opponents are already defeated
    roll_text_damages = f"{roll_text_damages}" if not attack_defeated_opponent else ""

    # special dmg msg only if spell hits
    special_damage_roll_text = f"{special_damage_roll_text} " if special_damage_roll_text and "success" in action_result else ""

    roll_texts = []

    if special_damage_roll_text:
        roll_texts.append(special_damage_roll_text)

    roll_texts.append("#action_result#" + action_result)

    if roll_text_damages:
        roll_texts.append(roll_text_damages)
    
    return d20_roll, roll_info_target_text, roll_info_text, roll_texts, dual_target, total_dmg, show_total

def roll_magic(is_spell, current_story, setup_aid, battle_info, opponent_sheets, targeted_opponents, specific_target, is_spell_attk, is_ranged_attk, magic_name, saving_throw, is_aoe, is_auto_hit, damage_dice, saves_half, damage_type, is_item = False, spell_level = None, is_minimized_dmg = False, is_maximized_dmg = False, orig_nb_attack_rolls = None, is_virtual_target = False, using_heightened_spell = False, using_twinned_spell = False, using_unsettling_words = False) -> Tuple[Any, Any, Any]:
    
    # Caster stats
    char_proficiency_bonus = get_proficiency_bonus(current_story["level"])

    default_ability = "int" if is_spell else "dex" # dex default for items and special abilities

    # The ability might not be set for special abilities or items
    char_ability = current_story.get("spellcasting_ability")
    char_ability = char_ability if char_ability is not None or is_spell else current_story.get("special_ability_stat")
    char_ability = char_ability if char_ability is not None else default_ability

    char_ability_mod = get_stat_mod(current_story, char_ability[:3].lower())

    attack_objs = []
    last_attacked_opponents = []

    roll_info_intro = roll_info_text_total = ""

    # Is ranged spell attack (char attacks target)
    if is_auto_hit or is_spell_attk:
        nb_attack_rolls = 1 if orig_nb_attack_rolls is None else orig_nb_attack_rolls # Default to 1 attack roll if not set

        show_total = False
        roll_texts = []
        total_attacks_dmg = 0
        nb_attacks_performed = 0

        current_opponent_identity = ""
        current_opponent_roll_text = ""
        nb_attacks_vs_current_opponent = 0
        attack_result_texts = []

        current_opponent = current_dual_target = current_opponent_sheet = None
        attack_defeated_opponent = False

        for x in range(nb_attack_rolls):
            # Next target
            potential_opponent, potential_opponent_sheet = get_next_combatant_sheet(targeted_opponents, opponent_sheets)
            # If there are no more opponents, keep attacking the last opponents (always use all the attack rolls, prolly the expected behavior)
            if potential_opponent is not None:
                current_opponent = potential_opponent
                current_opponent_sheet = potential_opponent_sheet
            else:
                attack_defeated_opponent = True # Keep attacking, even if all opponents defeated

            # Can happen when manually changes battle info in current_story (sheets won't match)
            if current_opponent_sheet is None:
                opponent_name = " (" + potential_opponent["identifier"] + ")" if potential_opponent is not None else ""
                print(f"ERROR: Opponent sheet not found for opponent{opponent_name} in roll_magic")
                return None, None, None

            if current_opponent_identity != current_opponent["identifier"]:
                current_opponent_identity = current_opponent["identifier"]

                # write roll_text
                then_text = "then " if x > 0 else ""
                base_msg = setup_aid["base_spell_attack"].replace("#then_text#", then_text) # Add 'then' for all subsequent attacks

                attack_type = "spell" if is_spell else ("item" if is_item else "ability")
                attack_used = f" with the {attack_type} '{magic_name}'"
                
                base_roll_msg = base_msg.replace("#opponent_identity#", current_opponent_identity).replace("#attack_used#", attack_used)

                if current_opponent_roll_text != "":
                    nb_of_attacks_text = get_nb_attacks_text(nb_attacks_vs_current_opponent)

                    current_opponent_roll_text, _ = add_attacks_current_opponent_roll_text(current_opponent_roll_text, nb_of_attacks_text, attack_result_texts, setup_aid, nb_attacks_vs_current_opponent)
                    roll_texts.append(current_opponent_roll_text)
                    
                    attack_result_texts = []

                current_opponent_roll_text = base_roll_msg
                nb_attacks_vs_current_opponent = 1
            else:
                nb_attacks_vs_current_opponent += 1

            d20_roll, roll_info_target_text, roll_info_text, roll_texts_spell_attack, dual_target, total_dmg, show_total_magic_attk = process_magic_spell_attack(current_story, setup_aid, targeted_opponents, current_opponent, current_opponent_sheet, is_auto_hit, magic_name, char_proficiency_bonus, char_ability_mod, damage_dice, spell_level, is_minimized_dmg, is_maximized_dmg, is_spell_attk, saves_half, x, nb_attack_rolls, attack_defeated_opponent, is_virtual_target, using_twinned_spell)

            if dual_target is not None:
                current_dual_target = dual_target

            attack_result_texts += roll_texts_spell_attack

            if show_total_magic_attk and not is_virtual_target:
                show_total = True

            total_attacks_dmg += total_dmg

            nb_attacks_performed += 1

            attack_obj = {
                "number": x + 1,
                "rolls": [d20_roll],
                "start_info": roll_info_target_text,
                "info": roll_info_text,
                "adversaries_hp": get_combatants_health_history(battle_info["opponents"], current_story) if battle_info is not None else None
            }
            attack_objs.append(attack_obj)

        # Add the intro to the rollinfo (cast spell X)
        roll_info_intro = f"Cast Spell ({magic_name}, Spell Attack):"

        # Add the attacks to the roll_info
        nb_of_attacks_text = get_nb_attacks_text(nb_attacks_vs_current_opponent)

        # Conclude the last opponent's attacks
        current_opponent_roll_text, nb_success_last_opponent = add_attacks_current_opponent_roll_text(current_opponent_roll_text, nb_of_attacks_text, attack_result_texts, setup_aid, nb_attacks_vs_current_opponent)
        roll_texts.append(current_opponent_roll_text)

        if nb_success_last_opponent > 0 and current_opponent is not None and current_opponent["hp"] > 0:
            last_attacked_opponents.append(current_opponent)

            if current_dual_target is not None:
                last_attacked_opponents.append(current_dual_target)
                
        roll_text = " ".join(roll_texts)
            
        if show_total or nb_attacks_performed > 1:
            roll_info_text_total = f"Total damage: #bold#{total_attacks_dmg}#bold#"
            print_log(roll_info_text_total.replace("#bold#", ""))
        
    # Is saving throw (target resists char's spell)
    else:
        # Saving throw (always same format)
        saving_throw_short = ""
        if saving_throw is not None:
            saving_throw_short = saving_throw[:3].lower()
            saving_throw = get_long_stat_name(saving_throw_short)

        saving_throw_DC = 8 + char_ability_mod + char_proficiency_bonus

        # Opponents that are directly attacked (everyone if aoe)
            # The original targeted_opponents is still given to the dmg, in case some dmg applies to opponents around the main target (ex : twinned spell)
        main_targeted_opponents = targeted_opponents[:1] if not is_aoe else targeted_opponents

        roll_texts = []
        show_total = False
        final_total = 0

        # Damages
        _, roll_text_special_dmg, dice_text, roll_text_magic_dmg, total, caused_damages = get_magic_damage_roll(current_story, damage_dice, False, char_ability_mod, spell_level, is_minimized_dmg, is_maximized_dmg)

        if is_spell:
            base_msg = setup_aid["base_spell"].replace("#spell_name#", magic_name)
        else:
            base_msg = setup_aid["base_use_item_or_ability"].replace("#magic_name#", magic_name)

        base_msg = base_msg.replace("#specific_target#", specific_target).replace("#saving_throw_text#", "")

        base_msg += f" {roll_text_special_dmg}" if roll_text_special_dmg else ""

        is_first_opponent = True
        has_used_bonus_action = False

        if caused_damages:
            roll_info_text_dmg, _ = process_damage_total(dice_text, roll_text_magic_dmg, total, False, is_short_dmg_text=True, print_short_dmg_text=False, print_dmg_text=True)
        else:
            roll_info_text_dmg = ""

        roll_info_saves = []

        for x, opponent in enumerate(main_targeted_opponents):
            # Only target 1 opponent at a time for saves (otherwise same opponents could be attacked multiple times)
            currently_targeted_opponents = [opponent] 
            opponent_sheet = get_combatant_sheet(opponent["group_name"], opponent["cr"], opponent_sheets)
            
            # Can happen when manually changes battle info in current_story (sheets won't match)
            if opponent_sheet is None:
                opponent_name = " (" + opponent["identifier"] + ")" if opponent is not None else ""
                print(f"ERROR: Opponent sheet not found for opponent{opponent_name} in roll_magic")
                return None, None, None

            d20_roll, roll_info_target_text, roll_info_text_save, base_msg, action_result_reversed, special_roll_text, used_bonus_action_save, is_success = process_opponent_save(saving_throw, saving_throw_short, saving_throw_DC, opponent, opponent_sheet, current_story, setup_aid, base_msg, is_spell, has_used_bonus_action, saves_half, x, len(main_targeted_opponents), using_heightened_spell, using_unsettling_words)

            using_heightened_spell = False # Only use once

            if used_bonus_action_save:
                has_used_bonus_action = True

            print_log(roll_info_text_save)

            roll_text_damages = None
            total_dmg = 0
            show_total_magic_dmg = False

            # Skip damage for virtual targets
            roll_info_text, roll_text_damages, _, total_dmg, show_total_magic_dmg = process_magic_damage(is_spell, current_story, setup_aid, currently_targeted_opponents, roll_info_text_save, is_spell_attk, saves_half, spell_level, dice_text, roll_text_magic_dmg, total, is_first_opponent, caused_damages, is_success, True)

            if show_total_magic_dmg:
                show_total = True

            target_name = opponent["identifier"].capitalize()

            # skip save half msg when opponent is defeated, even if did save half, in order to reduce confusion
            if saves_half and "failure" in action_result_reversed and opponent["hp"] <= 0:
                action_result_reversed = "success"

            # Whether to show the saves half message 
            # Note: action results are reversed for saving throws
            if saves_half and "failure" in action_result_reversed:
                # Saves half when the opponent succeeds
                magic_result_text = setup_aid["saved_half_magic"].replace("#target#", target_name)
            else:
                magic_result_text = setup_aid[action_result_reversed + "_magic"].replace("#target#", target_name)

            opponent_roll_texts = [magic_result_text]
            if roll_text_damages:
                opponent_roll_texts.append(roll_text_damages)

            if special_roll_text:
                opponent_roll_texts.append(special_roll_text)

            opponent_roll_texts_combined = ", ".join(opponent_roll_texts) + "."
            roll_texts.append(opponent_roll_texts_combined)

            roll_info_saves.append(roll_info_text)

            final_total += total_dmg
            is_first_opponent = False

            attack_obj = {
                "number": x + 1,
                "combatant_rolls": [d20_roll],
                "start_info": roll_info_target_text,
                "info": roll_info_text,
                "adversaries_hp": get_combatants_health_history(battle_info["opponents"], current_story) if battle_info is not None else None
            }
            attack_objs.append(attack_obj)

        # Saving throw = yellow (since multiple opponents can be targeted by the same effect)
        
        roll_info_text_dmg_text = f", {roll_info_text_dmg}" if roll_info_text_dmg else ""
        roll_info_intro = f"Cast Spell ({magic_name}, Saving Throw){roll_info_text_dmg_text}:"

        # Determine if all targeted opponents are defeated
        opponent_defeated_msg = process_are_opponents_defeated(setup_aid, targeted_opponents, battle_info)
        if opponent_defeated_msg:
            roll_texts.append(opponent_defeated_msg)

        if show_total or len(main_targeted_opponents) > 1:
            roll_info_text_total = f"Total damage: #bold#{final_total}#bold#"
            print_log(roll_info_text_total.replace("#bold#", ""))

        roll_text = base_msg + " " + " ".join(roll_texts)
    
    section_obj = {
        "name": "main",
        "characters": [{
            "name": "main",
            "unique_actions": [
                {
                    "name": magic_name,
                    "info": roll_info_intro,
                    "sound": get_sound_triple(damage_type, is_ranged_attk, magic_name),
                    "actions": attack_objs 
                }
            ]
        }],
        "info": roll_info_text_total
    }
    clean_section_obj(section_obj)

    return roll_text, section_obj, last_attacked_opponents

def get_specific_target(target, target_identity):
    return (target_identity if target_identity is not None else target).capitalize() if target is not None else ''

def get_wild_magic(current_story, force_roll = None) -> Tuple[Any, Any]:
    if not has_talent("wild magic", current_story):
        return None, None
    
    # 1/4 chance of triggering (usually 1/20)
    if rd.randint(1, 4) != 1 and force_roll is None:
        return None, None
    
    d100_roll = rd.randint(1, 100)

    if force_roll is not None:
        d100_roll = force_roll
    
    wild_magic_list = list(wild_magic_data.values())
    adjusted_index = (d100_roll - 1) % len(wild_magic_list) # Ensure the roll doesn't exceed the number of items in the list
    wild_magic_row = wild_magic_list[adjusted_index]
    
    return d100_roll, wild_magic_row

def apply_wild_magic(d100_roll_wild_magic, wild_magic_row, current_story, setup_aid, spell_name, target) -> Tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    is_minimized_dmg = is_maximized_dmg = is_skip_turn = is_wild_magic_replacement = False
    wild_magic_roll_info = wild_magic_roll_text = ""

    # Replace spell with wild magic effect
    if wild_magic_row["replacement_spell"]:
        is_wild_magic_replacement = True
        original_spell_name = spell_name
        spell_name = wild_magic_row["replacement_spell"].strip()

        wild_magic_partial_text = setup_aid["base_wild_magic"].replace("#spell_name#", spell_name).replace("#original_spell_name#", original_spell_name)

        wild_magic_roll_info = wild_magic_partial_text.replace("#char_pronoun#", "You")
        wild_magic_roll_text = wild_magic_partial_text.replace("#char_pronoun#", "I")

        # Extra text when roll 100
        if d100_roll_wild_magic == 100:
            wild_magic_explosion_text = " Massive explosions surrounds #you#, consuming all #your# available spell slots in the process."
            wild_magic_roll_info += wild_magic_explosion_text.replace("#you#", "you").replace("#your#", "your")
            wild_magic_roll_text += wild_magic_explosion_text.replace("#you#", "me").replace("#your#", "my")
            current_story["spell_slots"] = [0] * len(current_story["spells_per_day"])
        else:
            wild_magic_roll_text += " " # Make it diff that "" so the description roll text isn't use farther down

    elif d100_roll_wild_magic == 1:
        current_story["hp"] = 1
    elif d100_roll_wild_magic == 2:
        current_story["hp"] = current_story["max_hp"]
    elif d100_roll_wild_magic == 3:
        current_story["sorcery_points"] = current_story["level"]
    elif d100_roll_wild_magic == 4:
        current_story["spell_slots"] = current_story["spells_per_day"][:]
    elif d100_roll_wild_magic == 5:
        is_minimized_dmg = True
    elif d100_roll_wild_magic == 6:
        is_maximized_dmg = True

    # Wild magic text
    wild_magic_roll_info = f"Wild Magic Surge ({d100_roll_wild_magic}): " + (wild_magic_roll_info if wild_magic_roll_info != "" else wild_magic_row["description"])
    wild_magic_roll_text = f"I triggered a wild magic surge: " + (wild_magic_roll_text if wild_magic_roll_text != "" else wild_magic_row["description_roll_text"])

    # Skip turn
    if wild_magic_row["skip_turn"].lower() == "true":
        is_skip_turn = True 
    
    return spell_name, target, is_minimized_dmg, is_maximized_dmg, wild_magic_roll_info, wild_magic_roll_text, is_skip_turn, is_wild_magic_replacement

def get_domain_spells(domain_name):
    domain_spells = []

    for domain_spell_dict in domains_data.values():
        spell_domain_name = domain_spell_dict["domain"]
        spell_name = domain_spell_dict["name"]

        if spell_domain_name.lower() == domain_name.lower():
            domain_spells.append(spell_name) # lowercase

    return domain_spells

# List all the class spells available at the player's level, but only those from the PHB
def list_class_spells(current_story, mark_non_phb = True):
    char_name = current_story["char_name"].lower()
    char_classes = get_char_classes(current_story)
    max_spell_level = get_max_spell_level(current_story)

    domain_name = get_domain_name(current_story)
    domain_spells = get_domain_spells(domain_name) if domain_name is not None else []
    domain_spells = [spell.lower() for spell in domain_spells] # lowercase

    character_alignment = current_story.get("alignment", "").lower()
    is_character_good = character_alignment[1] == "g" if len(character_alignment) > 1 else False
    is_character_evil = character_alignment[1] == "e" if len(character_alignment) > 1 else False
    
    class_spells_dict = {}
    domains_spells_dict = {}
    
    default_spells = []
    primary_class = char_classes[0].lower()
    default_label = primary_class + "_default"

    for spell_name, spell_row in spells_data.items():
        spell_level = spell_row["level"]
        if int(spell_level) > max_spell_level:
            break

        # Add to default spells if it's a default spell
        is_default_spell = spell_row.get(default_label, 'False') == 'True'
        if is_default_spell:
            default_spells.append(spell_name)
        
        spell_is_good = spell_row["alignment"].lower() == "good"
        spell_is_evil = spell_row["alignment"].lower() == "evil"

        # Skip if the spell doesn't match the character's alignment
        if (is_character_good and spell_is_evil) or (is_character_evil and spell_is_good):
            continue

        # Find if is_class_spell in one line
        is_class_spell = any([spell_row.get(class_name, 'False') == 'True' for class_name in char_classes])
        is_phb_spell = spell_row["book"].lower() == "phb"
        is_domain_spell = spell_name.lower() in domain_spells

        is_exception = spell_row["exception"].lower() == char_name

        # Skip if not a class spell or not from the PHB, unless it's a domain spell
        if (not is_class_spell or not is_phb_spell) and not is_domain_spell and not is_exception:
            continue

        is_skipped = spell_row["is_skipped"].lower() == "true"

        # Skip the spell if specified in the list to skip it.
        if is_skipped:
            continue

        # Create the spell list for that specific level if it doesn't exist
        if spell_level not in class_spells_dict:
            class_spells_dict[spell_level] = [] 

        # Specify not from the phb (only possible for domain spells)
        if not is_phb_spell and mark_non_phb:
            spell_name = f"#NON_PHB#{spell_name}"

        class_spells_dict[spell_level].append(spell_name)

        if is_domain_spell:
            if spell_level not in domains_spells_dict:
                domains_spells_dict[spell_level] = [] 

            domains_spells_dict[spell_level].append(spell_name)

    return class_spells_dict, domains_spells_dict, default_spells

def get_spell_row(spell_name):
    if spell_name and spell_name.lower() in spells_data:
        return spells_data[spell_name.lower()]
    
    return None

def get_spell_info(spell_row, current_story) -> Tuple[Any, Any, Any, Any, Any, Any, Any, Any, Any, Any, Any, Any, Any]:
    if spell_row is None:
        return None, False, False, False, False, False, False, False, False, None, False, False, None

    effect = spell_row["effect"].lower()
    save_miss = spell_row["save_miss"].lower()
    damage_type = spell_row["type"].lower()
    is_aoe = spell_row["is_aoe"].lower() == "true"
    is_healing = spell_row["healing_dice"].lower() != ""
    is_buff = spell_row["is_buff"].lower() == "true"
    is_oob_only = spell_row["is_oob_only"].lower() == "true"
    nb_attack_rolls = extract_int(spell_row["nb_attack_rolls"])

    saving_throw = None
    is_ranged_attack = is_melee_attack = saves_half = is_auto_hit = False

    if effect in ["str", "dex", "con", "int", "wis", "cha"]:
        saving_throw = effect
    elif effect.startswith("ranged"):
        is_ranged_attack = True
    elif effect.startswith("melee"):
        is_melee_attack = True

    if save_miss == "half":
        saves_half = True
    elif save_miss == "auto":
        is_auto_hit = True

    is_spell_attk = (is_ranged_attack or is_melee_attack or is_auto_hit) and not is_healing # Both counts as spell attacks

    # Check if the character has resistance to the damage type
    has_resistance, _ = has_resistance_to_damage(damage_type, current_story)

    return saving_throw, is_ranged_attack, is_spell_attk, saves_half, is_auto_hit, is_aoe, is_healing, is_buff, is_oob_only, nb_attack_rolls, True, has_resistance, damage_type

def get_cantrip_scaling_nb(char_level):
    num_dice_level_scaling = 1 if char_level >= 5 else 0
    num_dice_level_scaling += 1 if char_level >= 11 else 0
    num_dice_level_scaling += 1 if char_level >= 17 else 0

    return num_dice_level_scaling

def get_spell_damage_from_row(spell_row, spell_name, upcast_level, char_level, is_healing = False):
    dice_label_text = "healing_dice" if is_healing else "damage_dice"

    damage_dice = spell_row[dice_label_text].strip()

    # Return none if no damage dice
    damage_dice = spell_row[dice_label_text].strip()
    if damage_dice == "":
        return None
    
    is_dice = "d" in damage_dice

    if not is_dice:
        damage_dice = f"+{damage_dice}"
    
    # Init
    num_dice_upcast = mod_upcast = num_dice_level_scaling = 0

    # Process the damage dice
    # num_dice_damage, num_faces_damage, mod_damage = process_dice(damage_dice)
    dice_damage, mod_damage = process_dice(damage_dice)

    if dice_damage is None or len(dice_damage) < 1 and is_dice:
        print(f"ERROR: Processing dice for spell {spell_name} failed")
        return None
    elif dice_damage is None or len(dice_damage) < 1:
        return f"{mod_damage}" # return text
    
    num_dice_damage = dice_damage[0][0]
    num_faces_damage = dice_damage[0][1]

    # Upcast dice
    upcast_dice_label_text = "healing_upcast_dice" if is_healing else "upcast_dice"
    upcast_dice = spell_row[upcast_dice_label_text].strip()
    if upcast_dice != "" and upcast_level is not None:
        dice_upcast, mod_upcast = process_dice(upcast_dice)

        if dice_upcast is not None and len(dice_upcast) >= 1:
            num_dice_upcast = dice_upcast[0][0]
            num_dice_upcast *= upcast_level
            mod_upcast *= upcast_level
        else:
            print(f"ERROR: Processing upcast dice for spell {spell_name} failed.")
        
    # Level scaling dice (adds an extra dice at set levels)
        # Only for cantrips
    level_scaling_dice = spell_row["level_scaling_dice"].strip()
    if level_scaling_dice != "":
        num_dice_level_scaling = get_cantrip_scaling_nb(char_level)

    # Combine the dice (number of faces always the same for all dice)
    final_damage_dice = f"{num_dice_damage + num_dice_upcast + num_dice_level_scaling}d{num_faces_damage}+{mod_damage + mod_upcast}"

    return final_damage_dice

def get_spell_damage(spell_name, upcast_level, char_level, is_healing = False):
    spell_row = spells_data[spell_name.lower()]
    return get_spell_damage_from_row(spell_row, spell_name, upcast_level, char_level, is_healing)

# Add nb of opponents targetted if AOE
def get_aoe_target(targeted_opponents, specific_target):
    nb_targets_text = f"{len(targeted_opponents)} " if len(targeted_opponents) > 0 else ""
    return f"{nb_targets_text}'{specific_target}'"

def add_wild_magic_text(wild_magic_roll_text, wild_magic_roll_info, roll_text, roll_info_text):
    if wild_magic_roll_text != "":
        roll_text = wild_magic_roll_text.strip() + (" " + roll_text if roll_text else "")
    if wild_magic_roll_info != "":
        roll_info_text = wild_magic_roll_info.strip() + ("#message_separator#" + roll_info_text if roll_info_text else "")

    return roll_text, roll_info_text

def create_virtual_opponent(target_name, ability_score, cr, ac):
    opponent = create_combatant(target_name, target_name, None)
    opponent["cr"] = cr # Cr not set above since group is None

    opponent_sheet = Combatant_Sheet_Stats_Object("", None, None, "", ability_score, ability_score, ability_score, ability_score, ability_score, ability_score, ac, [], cr).extract_json()

    opponent_sheet["name"] = target_name
    opponent_sheet["cr"] = cr

    opponent["hp"] = opponent["max_hp"] = get_monsters_hp(cr, opponent_sheet)

    return opponent, opponent_sheet

def heal_combatant_hp(combatant, total_healing):
    combatant["hp"] = min(combatant["max_hp"], combatant["hp"] + total_healing)

def heal_mc_hp(current_story, total_healing):
    current_story["hp"] = min(current_story["max_hp"], current_story["hp"] + total_healing)

def cast_healing_or_self_spell(spell_name, roll_info_text, setup_aid, specific_target, upcast_text_msg, wild_magic_roll_text, wild_magic_roll_info, healing_status_text):
    base_spell_msg = setup_aid["base_spell"].replace("#spell_name#", spell_name).replace("#specific_target#", specific_target).replace("#saving_throw_text#", "") + (" " + upcast_text_msg if upcast_text_msg != "" else "")

    # Add wild magic
    base_spell_msg, roll_info_text = add_wild_magic_text(wild_magic_roll_text, wild_magic_roll_info, base_spell_msg, roll_info_text)

    roll_text = f"{base_spell_msg} {setup_aid['success'].replace('#injuries#', '')}{healing_status_text}"

    return roll_info_text, roll_text

def get_char_obj_healing(battle_info, current_story, magic_name, is_ranged, char_name, roll_info_intro_text, roll_info_text, is_opponent = False):
    if battle_info is None:
        return None
    
    comrades_type = "opponents" if is_opponent else "allies"
    adversaries_type = "allies" if is_opponent else "opponents"

    attack_obj = {
        "number": 1,
        "info": roll_info_text,
        "comrades_hp": get_combatants_health_history(battle_info[comrades_type], current_story, not is_opponent),
        "adversaries_hp": get_combatants_health_history(battle_info[adversaries_type], current_story, is_opponent) # include adversaries hp in case they were healed (ex : mc decides to heal opponent, opponent convinced to heal mc, etc.)
    }

    character_obj = {
        "name": char_name,
        "unique_actions": [
            {
                "name": magic_name,
                "info": roll_info_intro_text,
                "sound": get_sound_triple("healing", is_ranged, magic_name),
                "actions": [attack_obj] 
            }
        ]
    }

    return character_obj

def get_combatant_healing_status(targeted_combatant, setup_aid):
    ally_status = get_opponent_health_status(targeted_combatant["hp"], targeted_combatant["max_hp"], True)
    ally_healing_status = " " + setup_aid["combatant_health_explanation"].replace("#combatant_identifier#", targeted_combatant["identifier"]).replace("#healing_status#", ally_status)

    return ally_healing_status

def get_combatants_healing_status_group(targeted_combatants, health_status, setup_aid):
    identifiers = [combatant["identifier"] for combatant in targeted_combatants]
    are_or_is = "are" if len(identifiers) > 1 else "is"
    return f"{join_with_and(identifiers)} {are_or_is} now {setup_aid[health_status]}"

def process_combatant_healing(targeted_combatants, total_healing, setup_aid):
    current_targeted_combatant = targeted_combatants[0]
    heal_combatant_hp(current_targeted_combatant, total_healing)
    healing_status = get_opponent_health_status(current_targeted_combatant["hp"], current_targeted_combatant["max_hp"], True)

    return get_combatants_healing_status_group([current_targeted_combatant], healing_status, setup_aid)

def process_aoe_heal_combatants(targeted_combatants, total_healing, setup_aid):
    status_groups = {}

    for combatant in targeted_combatants:
        heal_combatant_hp(combatant, total_healing)
        combatant_status = get_opponent_health_status(combatant["hp"], combatant["max_hp"], True)
        if combatant_status not in status_groups:
            status_groups[combatant_status] = []
        status_groups[combatant_status].append(combatant)

    # Combine together in a sentence the combatant that have the same health status.
        # Ex : 'Archer 1 and Archer 2 are now severly wounded, but archer 3 is now moderately healthy.'
    if len(status_groups) == 1:
        status = list(status_groups.keys())[0]
        return get_combatants_healing_status_group(status_groups[status], status, setup_aid) + "."
    elif len(status_groups) == 2:
        status_1 = list(status_groups.keys())[0]
        status_text_1 = get_combatants_healing_status_group(status_groups[status_1], status_1, setup_aid)
        status_2 = list(status_groups.keys())[1]
        status_text_2 = get_combatants_healing_status_group(status_groups[status_2], status_2, setup_aid)
        return f"{status_text_1}, but {status_text_2}."
    else:
        status_texts = []
        for status, names in status_groups.items():
            status_texts = get_combatants_healing_status_group(names, status, setup_aid)

        return ", ".join(status_texts) + "."

def get_targeted_opponents_mc_magic(magic_type_text, is_target_self_or_env, is_aoe, is_healing, is_buff, current_story, target_identity, target_number, specific_target, damage_dice, opponent_sheets, saving_throw, virtual_target_sheet) -> Tuple[Any, Any, Any, Any, Any, Any, Any]:
    targeted_combatants = []
    battle_info = None

    # Get targeted opponents, exit if none found and not targeting self or env (except if aoe and there is an ongoing battle)
    if is_target_self_or_env and (not is_aoe or current_story.get("battle_info") is None):
        battle_info = current_story.get("battle_info")
    else:
        is_targeting_opponents = not is_healing and not is_buff # Healing or buff spells target allies

        # Get opponents currently being targeted from battle info
        targeted_combatants, battle_info, _, _ = get_battle_info_combatants(current_story, target_identity, target_number, is_targeting_opponents, True)

        # Note : Should never happen, since the sheet should always be generated when battle info is none + cast spell
            # Don't quit on aoe, since that is managed in the is_target_self_or_env section
        if battle_info is None and virtual_target_sheet is None and not is_aoe: 
            print(f"ERROR: Trying to damage '{specific_target}' using the {magic_type_text} without battle info.")
            roll_error_text = f"Failed to find a valid target for the {magic_type_text}."
            roll_error_info_text = f"#red# {roll_error_text}#red#"
            return targeted_combatants, battle_info, specific_target, opponent_sheets, roll_error_text, roll_error_info_text, True

        # Create virtual opponent if no current battle info, but not a spell with damages (ex : charm person)
        elif virtual_target_sheet is not None:
            target_ac = virtual_target_sheet["ac"]
            target_cr = virtual_target_sheet["cr"]
            target_ability_score = 10 # Default

            if saving_throw is not None:
                saving_throw_short = saving_throw[:3].lower()
                target_ability_score = virtual_target_sheet[saving_throw_short] if saving_throw_short in virtual_target_sheet else 10

            # ability_score, challenge_rating, target_AC, 
            opponent, sheet = create_virtual_opponent(specific_target, target_ability_score, target_cr, target_ac)
            targeted_combatants.insert(0, opponent)
            opponent_sheets = [sheet]

        # If there is an ongoing battle, but no targets, exit
        elif len(targeted_combatants) == 0:
            print(f"ERROR: No opponents found in battle info for {specific_target}")
            return targeted_combatants, battle_info, specific_target, opponent_sheets, None, None, True
        else:
            specific_target = targeted_combatants[0]["identifier"]

    return targeted_combatants, battle_info, specific_target, opponent_sheets, None, None, False

def create_section_obj(start_roll_info = None, char_obj = None, end_roll_info = None, section_name = "main"):
    section_obj = {
        "name": section_name
    }

    if start_roll_info:
        section_obj["start_info"] = start_roll_info

    if char_obj is not None:
        section_obj["characters"] = [char_obj]

    if end_roll_info:
        section_obj["info"] = end_roll_info

    return section_obj

def process_cast_spell(cast_spell_results: Cast_Spell_Object, can_cast_spell, current_story, setup_aid, opponent_sheets, using_heightened_spell = False, using_twinned_spell = False, attempts_lay_on_hands = False, using_unsettling_words = False, virtual_target_sheet = None) -> Tuple[Any, Any, Any, Any]:
    # No sell casting ability
    if not can_cast_spell:
        roll_info_text = "#red# " + setup_aid["no_spellcasting_ability_info_text"] + "#red#"
        section_obj = create_section_obj(roll_info_text)
        return setup_aid["no_spellcasting_ability"], section_obj, None, None

    # No spell cast (spell cast error)
    if cast_spell_results is None:
        return None, None, None, None

    spell_name, spell_level, target, target_identity, target_number, saving_throw, is_spell_attk, damage_dice, saves_half, damage_type, is_aoe, is_healing, available_to_classes = cast_spell_results.extract()
    
    target_self_or_env = target is None or "creature" not in target.lower()

    # If using lay on hand, hardcode as spell lvl 0, will manage it specifically further down
    is_using_lay_on_hand = has_talent("lay on hands", current_story) and (attempts_lay_on_hands or (spell_name.lower() in "lay on hand" or "lay on hand" in spell_name.lower()))
    if is_using_lay_on_hand:
        spell_name = "Lay on Hands"
        spell_level = 0
        is_healing = True

    if spell_name is None or spell_level is None or (target_identity is None and not target_self_or_env):
        print("WARNING: Spell info is missing (spell_name, spell_level), spell not cast", True)
        return None, None, None, None

    nb_attack_rolls = None # Only for spell with potential multiple attack rolls (ex: scorching ray)
    is_ranged_attk = is_spell_attk # Spell attack is ranged in the prompt
    is_auto_hit = is_oob_only = is_buff = False

    spell_row = get_spell_row(spell_name)

    if spell_row is not None:
        saving_throw, is_ranged_attk, is_spell_attk, saves_half, is_auto_hit, is_aoe, is_healing, is_buff, is_oob_only, nb_attack_rolls, _, _, damage_type = get_spell_info(spell_row, current_story)
    
    # If the spell can only be used outside of battle, but currently in battle, spell fails
    if is_oob_only and current_story.get("battle_info") is not None:
        section_obj = create_section_obj(setup_aid["spell_oob_only_info_text"].replace("#spell_name#", spell_name))
        return setup_aid["spell_oob_only"].replace("#spell_name#", spell_name), section_obj, None, None

    available_to_classes = [item.lower() for item in available_to_classes] if available_to_classes is not None else [] # lowercase
    char_classes = get_char_classes(current_story)
    
    # Check if spell is available to any of the char's current classes
        # Check actual spell list first (any_class_has_spell), then check the backup (if the prompt allowed one of their classes to cast it)
    char_has_spell, min_spell_level = any_class_has_spell(spell_name, char_classes)

    # Check if the spell is in the cleric domain for that char.
    if not char_has_spell:
        char_has_domain_spell, domain_spell_lvl = spell_in_domain(spell_name, current_story)
        min_spell_level = domain_spell_lvl if min_spell_level is None else min_spell_level

        # Need to keep the original char_has_spell value, in case it was 'None' (no class has the spell)
            # If None, can then check if it could be valid as a custom spell for the char's class
        char_has_spell = True if char_has_domain_spell else char_has_spell

    # Use the min spell level if the spell level is lower than the minimum
    spell_level = max(spell_level, min_spell_level) if min_spell_level is not None else spell_level 

    # cantrips are always 0 (can't be upcasted)
    if min_spell_level is not None and min_spell_level == 0:
        spell_level = 0

    if char_has_spell == False or (char_has_spell is None and not class_has_spell_available_classes(available_to_classes, char_classes)):
        print_log(f"Spell {spell_name} not available to current class.")
        roll_info_text = "#red# " + setup_aid["spell_not_available_to_class_info_text"].replace("#spell_name#", spell_name).replace("#char_class#", current_story["class"]) + "#red#"
        section_obj = create_section_obj(roll_info_text)
    
        return setup_aid["spell_not_available_to_class"].replace("#spell_name#", spell_name).replace("#char_class#", current_story["class"]), section_obj, None, None

    # Spell level always an int between 0 and 9 (cantrip = 0)
    max_spell_level = get_max_spell_level(current_story)
    if not spell_level <= max_spell_level:
        if spell_name.lower() != "heal":
            print_log(f"Spell level {spell_level} too high for current level {current_story['level']}.")
            roll_info_text = "#red# " + setup_aid["spell_level_too_high_info_text"].replace("#spell_name#", spell_name) + "#red#"
            section_obj = create_section_obj(roll_info_text)

            return setup_aid["spell_level_too_high"].replace("#spell_name#", spell_name), section_obj, None, None
        else:
            # Heal defaults to cure wound level 1 when cant cast it.
            spell_level = 1
            spell_name = "Cure Wounds"
            spell_row = get_spell_row(spell_name)

    original_spell_level = spell_level
    spell_slot_used, can_cast_spell_at_level = get_spell_slot(spell_level, current_story)

    # Upcast forced because of a lack of spell slots
    forced_upcast_level = spell_slot_used - spell_level if spell_slot_used > spell_level else None

    # Actual upcast of the spell over it's min spell level (defines the extra dmg dice)
    upcast_level = spell_slot_used - min_spell_level if min_spell_level is not None and spell_slot_used > min_spell_level else forced_upcast_level

    spell_level = spell_slot_used

    # Can use sorcery point to cast the spell even if no spell slots left
    sorcery_points = current_story.get("sorcery_points", 0)
    nb_sorcery_points_used_for_spell_slot = 0

    if not can_cast_spell_at_level and sorcery_points >= spell_slot_used:
        can_cast_spell_at_level = True
        nb_sorcery_points_used_for_spell_slot = spell_slot_used

    # No spell slots left to cast the spell (can't upcast it either)
    if not can_cast_spell_at_level:
        print_log(f"No spell slots left to cast {spell_name}.")
        roll_info_text = "#red# " + setup_aid["no_spell_slots_info_text"].replace("#spell_name#", spell_name).replace("#spell_level#", str(spell_level)) + "#red#" # Need to convert spell level to str, or crash
        section_obj = create_section_obj(roll_info_text)
        return setup_aid["no_spell_slots"].replace("#spell_name#", spell_name), section_obj, None, None

    # WILD MAGIC
    # Can't be after the upcast, since the spell might be replaced by wild magic
    d100_roll_wild_magic, wild_magic_row = get_wild_magic(current_story)
    
    is_minimized_dmg = is_maximized_dmg = False
    wild_magic_roll_info = wild_magic_roll_text = ""

    if d100_roll_wild_magic is not None:
        print_log(f"Triggered wild magic: {d100_roll_wild_magic}")

        spell_name, target, is_minimized_dmg, is_maximized_dmg, wild_magic_roll_info, wild_magic_roll_text, is_skip_turn, is_wild_magic_replacement = apply_wild_magic(d100_roll_wild_magic, wild_magic_row, current_story, setup_aid, spell_name, target)

        if is_wild_magic_replacement:
            replaced_spell_name = spell_name if spell_name != "explosion" else "Meteor Swarm"
            upcast_level = None # Don't upcast the spell if it was replaced by wild magic

            spell_row = get_spell_row(replaced_spell_name)
            saving_throw, is_ranged_attk, is_spell_attk, saves_half, is_auto_hit, is_aoe, is_healing, is_buff, is_oob_only, nb_attack_rolls, _, _, damage_type = get_spell_info(spell_row, current_story)

        # Skip turn
        if is_skip_turn:
            print_log(f"Skipped turn due to wild magic.")
            section_obj = create_section_obj("#red#" + wild_magic_roll_info + "#red#")
            return wild_magic_roll_text, section_obj, None, None
        
        if is_wild_magic_replacement:
            upcast_text_msg = "" # Don't show the upcast text if the spell was replaced by wild magic

            # When replacing with healing, change the target to self.
            if is_healing:
                target_self_or_env = True
                target = target_identity = "self"

    # update the nb of attacks (only for spells with potential multiple attacks) 
    #  cantrips scale with level, while +1 attk by upscale lvl for the rest
    if nb_attack_rolls is not None and spell_level == 0:
        nb_attack_rolls += get_cantrip_scaling_nb(current_story["level"])
    elif nb_attack_rolls is not None and upcast_level is not None:
        nb_attack_rolls += upcast_level
    elif nb_attack_rolls is None and (is_auto_hit or is_spell_attk):
        nb_attack_rolls = 1

    upcast_text_msg = "" # Contains only info about the spell cast
    roll_info_text_spell_slot = ""

    # Update spell msg with upcast level
    if upcast_level is not None:
        upcast_text_msg = setup_aid["spell_upcasted"].replace("#upcast_level#", f"{upcast_level}") 

        # Specify if the spell was forced to be upcasted or if it was planned
        upcast_spell_msg = setup_aid["upcasted_spell_slot_used"] if forced_upcast_level is None else setup_aid["forced_upcasted_spell_slot_used"].replace("#original_spell_slot#", f"{original_spell_level}")
        roll_info_text_spell_slot += upcast_spell_msg.replace("#spell_slot#", f"{spell_slot_used}")
    elif nb_sorcery_points_used_for_spell_slot > 0:
        roll_info_text_spell_slot += setup_aid["sorcery_points_used"].replace("#spell_slot#", f"{spell_slot_used}").replace("#sorcery_points#", f"{nb_sorcery_points_used_for_spell_slot}")
    elif spell_slot_used > 0:
        roll_info_text_spell_slot += setup_aid["spell_slot_used"].replace("#spell_slot#", f"{spell_slot_used}")
    else:
        roll_info_text_spell_slot += setup_aid["no_spell_slot_used"]

    # Overwrite the damage dice with those in the spell sheet
    if min_spell_level is not None:
        damage_dice = get_spell_damage(spell_name, upcast_level, current_story["level"])

    is_spell_cast_at_self_or_env = target_self_or_env or (not is_spell_attk and saving_throw is None and not is_healing)
    specific_target = get_specific_target(target, target_identity)

    targeted_combatants, battle_info, specific_target, opponent_sheets, roll_error_text, roll_error_info_text, is_return_in_error = get_targeted_opponents_mc_magic("spell", is_spell_cast_at_self_or_env, is_aoe, is_healing, is_buff, current_story, target_identity, target_number, specific_target, damage_dice, opponent_sheets, saving_throw, virtual_target_sheet)

    if is_return_in_error:
        section_obj = create_section_obj(roll_error_info_text) if roll_error_info_text is not None else None
        return roll_error_text, section_obj, None, None

    # Use sorcery points
    if nb_sorcery_points_used_for_spell_slot > 0:
        current_story["sorcery_points"] -= nb_sorcery_points_used_for_spell_slot
    else:
        # Use the spell slot for the spell cast
        use_spell_slot(spell_level, current_story)

    # Change the target's text format depending on the type of spell
    if is_healing and (is_aoe or target_self_or_env):
        specific_target = setup_aid["myself_and_allies_text"] if is_aoe and battle_info is not None and len(battle_info.get("allies", [])) > 0 else setup_aid["myself_text"]
    elif is_aoe:
        specific_target = get_aoe_target(targeted_combatants, specific_target)
    else:
        specific_target = f"'{specific_target}'" if nb_attack_rolls is None else specific_target

    # LAY ON HANDS
    if is_using_lay_on_hand:
        if current_story.get("lay_on_hands_hp", 0) == 0:
            section_obj = create_section_obj("#red#No lay on hands left for the day.#red#")
            return setup_aid["no_lay_on_hands_left"], section_obj, None, None
        
        healing_status_text = ""
        
        if not target_self_or_env and len(targeted_combatants) > 0:
            targeted_combatant = targeted_combatants[0]
            total_healing = min(current_story["lay_on_hands_hp"], targeted_combatant["max_hp"] - targeted_combatant["hp"])
            targeted_combatant["hp"] += total_healing

            healing_status_text = get_combatant_healing_status(targeted_combatant, setup_aid)
        elif not target_self_or_env:
            total_healing = min(5, current_story["lay_on_hands_hp"]) # If can't find a target, heal 5 hp
        else:
            total_healing = min(current_story["lay_on_hands_hp"], current_story["max_hp"] - current_story["hp"])
            current_story["hp"] += total_healing
            healing_status = get_mc_health_status(current_story["hp"], current_story["max_hp"], True)
            healing_status_text = " " + setup_aid[healing_status] if healing_status is not None else ""

        current_story["lay_on_hands_hp"] -= total_healing

        # write_json("current_story.json", current_story)
        target_text = ' on ' + ('self' if target_self_or_env else target_identity)
        roll_info_intro_text = f"Used lay on hands{target_text}:"
        roll_info_text = f"Healed #green#{total_healing}#green# hit points."

        used_lay_on_hands_msg = setup_aid["used_lay_on_hands"].replace("#target_text#", target_text)
        char_obj = get_char_obj_healing(battle_info, current_story, spell_name, is_ranged_attk, roll_info_intro_text, roll_info_text, "main")

        section_obj = create_section_obj(roll_info_text, char_obj)

        return f"{used_lay_on_hands_msg} {setup_aid['success'].replace('#injuries#', '')}{healing_status_text}", section_obj, None, None

    # Caster stats
    char_spellcasting_ability = current_story["spellcasting_ability"] # Should always have it (no spellcast otherwise)
    char_spellcasting_mod = get_stat_mod(current_story, char_spellcasting_ability[:3].lower())

    if is_healing:
         # Healing
        roll_info_text, total_healing = get_healing(spell_name, spell_level, char_spellcasting_mod, spell_row, upcast_level,  current_story["level"], has_talent("preserve life", current_story))
        print_log(roll_info_text)

        healing_status_text = ""

        if is_aoe or is_spell_cast_at_self_or_env:
            heal_mc_hp(current_story, total_healing)
            healing_status = get_mc_health_status(current_story["hp"], current_story["max_hp"], True)
            healing_status_text = " " + setup_aid[healing_status] if healing_status is not None else ""

        if is_aoe:
            healing_status_text += " " + process_aoe_heal_combatants(targeted_combatants, total_healing, setup_aid)

        elif len(targeted_combatants) > 0 and not is_spell_cast_at_self_or_env:
            healing_status_text = process_combatant_healing(targeted_combatants, total_healing, setup_aid)

        roll_info_text, roll_text = cast_healing_or_self_spell(spell_name, roll_info_text, setup_aid, specific_target, upcast_text_msg, wild_magic_roll_text, wild_magic_roll_info, healing_status_text)

        target_text = f" => {specific_target}" if specific_target is not None else ":"
        roll_info_intro_text = f"Casting Spell ({spell_name}){target_text}"

        char_obj = get_char_obj_healing(battle_info, current_story, spell_name, is_ranged_attk, "main", roll_info_intro_text, roll_info_text)

        section_obj = create_section_obj(char_obj=char_obj, end_roll_info=roll_info_text_spell_slot)

        return roll_text, section_obj, None, None

    # If target self or environment, no need to do anything
        # Also, if info missing, spell assumed to succeed (happens when targetting an ally or self, for example)
        # Finally, don't auto succeed when is_aoe with battle info, since should instead just target all opponents
    elif is_spell_cast_at_self_or_env and (battle_info is None or not is_aoe):
        print_log("Spell cast at self or environment, or info missing: automatic success.")

        roll_info_text = f"Casting {spell_name}"
        if specific_target is not None:
            roll_info_text += f" on {specific_target}"
        
        roll_info_text, roll_text = cast_healing_or_self_spell(spell_name, roll_info_text, setup_aid, specific_target, upcast_text_msg, wild_magic_roll_text, wild_magic_roll_info, "")

        section_obj = create_section_obj(roll_info_text, end_roll_info=roll_info_text_spell_slot)

        return roll_text, section_obj, None, None

    # Magic roll, either attack of saving throw
    roll_text, section_obj, last_attacked_opponents = roll_magic(True, current_story, setup_aid, battle_info, opponent_sheets, targeted_combatants, specific_target, is_spell_attk, is_ranged_attk, spell_name, saving_throw, is_aoe, is_auto_hit, damage_dice, saves_half, damage_type, spell_level = spell_level, is_minimized_dmg=is_minimized_dmg, is_maximized_dmg=is_maximized_dmg, orig_nb_attack_rolls=nb_attack_rolls, is_virtual_target=virtual_target_sheet is not None, using_heightened_spell=using_heightened_spell, using_twinned_spell=using_twinned_spell, using_unsettling_words=using_unsettling_words)

    roll_text = f"{roll_text} {upcast_text_msg}" if upcast_text_msg != "" else roll_text

    # Add wild magic
    roll_text, roll_info_text = add_wild_magic_text(wild_magic_roll_text, wild_magic_roll_info, roll_text, section_obj.get("info"))

    # Add spell slots
    #roll_info_text += roll_info_text_damages
    print_log(roll_info_text_spell_slot + "\n")
    if roll_info_text is not None:
        roll_info_text += "#message_separator#" + roll_info_text_spell_slot

    section_obj["info"] = roll_info_text

    #print_log(roll_info_text)

    return roll_text, section_obj, targeted_combatants, last_attacked_opponents

def get_use_special_ability_stat(current_story):
    if current_story.get("special_ability_stat") is not None:
        return current_story["special_ability_stat"]
    
    print("ERROR: No special ability stat found.")
    return None

def has_item_in_inventory(item_name, current_story, is_equipped = None):
    lower_item_name = item_name.lower()

    # Check if item is in inventory before use, fails if not
    current_inventory = current_story["inventory"]
    cleaned_inventory = [(get_clean_item_name(item), item.get("is_equipped")) for item in current_inventory]
    item_in_inventory = False

    # Check if item is in inventory
    for cleaned_item, is_cleaned_item_equipped in cleaned_inventory:
        if (lower_item_name in cleaned_item or cleaned_item in lower_item_name) and (is_equipped is None or is_cleaned_item_equipped == is_equipped):
            item_in_inventory = True
            break

    return item_in_inventory

def use_item_or_ability_healing_or_self(item_or_ability_text, item_or_ability_name, heal_roll, setup_aid, specific_target, healing_status_text):
    roll_info_text = f"Using {item_or_ability_text} '{item_or_ability_name}'"
    if specific_target is not None:
        roll_info_text += f" on {specific_target}"

    roll_info_text += f" #green#{heal_roll}#green#" if heal_roll is not None else ""
    print_log(roll_info_text)

    base_use_item_or_ability_msg = setup_aid["base_use_item_or_ability"].replace("#magic_name#", item_or_ability_name).replace("#specific_target#", specific_target)
    use_item_or_ability_msg = base_use_item_or_ability_msg.replace("#saving_throw_text#", "")
    roll_text = f"{use_item_or_ability_msg} {setup_aid['success'].replace('#injuries#', '')} {healing_status_text}"

    return roll_info_text, roll_text

def process_use_item(roll_results: Use_Item_Object, current_story, setup_aid, opponent_sheets, allow_item_not_in_inventory = False, virtual_target_sheet = None) -> Tuple[Any, Any, Any, Any, Any]:
    if roll_results is None:
        print_log("No item/special ability use found")
        return None, None, None, None, None

    item_or_ability_name, target, target_identity, target_number, saving_throw, is_ranged_attk, damage_dice, saves_half, damage_type, is_aoe, is_healing, healing_dice, item_fall_into_available_category, item_used_actively, stat_required_to_use_item = roll_results.extract()

    item_or_ability_id = "item_name"
    item_or_ability_text = "item " 

    target_self_or_env = target is None or "creature" not in target.lower()

    if item_or_ability_name is None or (target_identity is None and not target_self_or_env):
        print_log(f"Info is missing ({item_or_ability_id} or target_identity)")
        return None, None, None, None, None
    
    # Check if char can automatically have any item (Eris)
    can_have_any_item = current_story.get("available_misc_objects") is not None and current_story.get("available_misc_objects_json_name") is None

    # Check if item is in inventory for use magic item, fails if not
        # Exception: Allowed if deemed that the item falls into the misc obj category for that character (ex: a potion for the alchemist)
    if not item_fall_into_available_category and not can_have_any_item and not allow_item_not_in_inventory:
        item_name = item_or_ability_name
        item_in_inventory = has_item_in_inventory(item_name, current_story)

        # Fail if item is not in inventory
        if not item_in_inventory:
            print_log(f"Item '{item_name}' isn't in inventory")
            roll_info_text = "#red# " + setup_aid["item_not_in_inventory_info_text"].replace("#item_name#", item_name) + "#red#"
            section_obj = create_section_obj(roll_info_text)
            return setup_aid["item_not_in_inventory"].replace("#item_name#", item_name), section_obj, item_name, None, None

    # Let the msg pass through if the item is used passively (would fail if the item wasn't in the inventory, see above)
    if not item_used_actively:
        print_log(f"Item '{item_or_ability_name}' used passively, no roll needed.")
        return None, None, None, None, None

    if stat_required_to_use_item is None and is_ranged_attk:
        print_log(f"Stat required to use item not set but ranged attack, defaulting to dex.")
        stat_required_to_use_item = "dex"
  
    is_item_target_self_or_env = target_self_or_env or (((not is_ranged_attk and saving_throw is None) or stat_required_to_use_item is None) and not is_healing)

    # Target
    specific_target = get_specific_target(target, target_identity)
    item_or_ability_text = 'item'

    # Get the targeted combatants for this item or ability
    targeted_combatants, battle_info, specific_target, opponent_sheets, roll_error_text, roll_error_info_text, is_return_error = get_targeted_opponents_mc_magic(item_or_ability_text, is_item_target_self_or_env, is_aoe, is_healing, False, current_story, target_identity, target_number, specific_target, damage_dice, opponent_sheets, saving_throw, virtual_target_sheet)

    if is_return_error:
        section_obj = create_section_obj(roll_error_info_text) if roll_error_info_text is not None else None
        return roll_error_text, section_obj, None, None, None
        
    # Add nb of opponents targetted if AOE
    if is_healing and (is_aoe or is_item_target_self_or_env):
        specific_target = setup_aid["myself_and_allies_text"] if is_aoe and battle_info is not None and len(battle_info.get("allies", [])) > 0 else setup_aid["myself_text"]
    elif is_aoe:
        specific_target = get_aoe_target(targeted_combatants, specific_target)

    if is_healing:
        healing_dice = healing_dice if healing_dice is not None else "2d4+2" # Default to healing potion
        heal_roll, total_healing = process_damage_dice(healing_dice, is_healing=True) # Don't add ability mod, already added above
        print_log(heal_roll)

        healing_status_text = ""

        if is_aoe or is_item_target_self_or_env:
            heal_mc_hp(current_story, total_healing)
            healing_status = get_mc_health_status(current_story["hp"], current_story["max_hp"], True)
            healing_status_text = " " + setup_aid[healing_status] if healing_status is not None else ""

        if is_aoe:
            healing_status_text += " " + process_aoe_heal_combatants(targeted_combatants, total_healing, setup_aid)
        elif len(targeted_combatants) > 0 and not is_item_target_self_or_env:
            healing_status_text = process_combatant_healing(targeted_combatants, total_healing, setup_aid)

        roll_info_text, roll_text = use_item_or_ability_healing_or_self(item_or_ability_text, item_or_ability_name, heal_roll, setup_aid, specific_target, healing_status_text)

        target_text = f" => {specific_target}" if specific_target is not None else ":"
        roll_info_intro_text = f"Using item ({item_or_ability_name}){target_text}"

        char_obj = get_char_obj_healing(battle_info, current_story, item_or_ability_name, is_ranged_attk, "main", roll_info_intro_text, roll_info_text)

        section_obj = create_section_obj(char_obj=char_obj)

        return roll_text, section_obj, None, None, None

    # If target self or environment, no need to do anything
        # Also, if info missing, magic item use assumed to succeed (happens when targetting an ally or self, for example)
        # Also, for item, if ability required to use item is not set, assume success
    elif is_item_target_self_or_env:
        roll_info_text, roll_text = use_item_or_ability_healing_or_self(item_or_ability_text, item_or_ability_name, None, setup_aid, specific_target, "")
        section_obj = create_section_obj(roll_info_text)

        return roll_text, section_obj, None, None, None

    # Magic roll, either attack of saving throw
    roll_text, section_obj, last_attacked_opponents = roll_magic(False, current_story, setup_aid, battle_info, opponent_sheets, targeted_combatants, specific_target, is_ranged_attk, is_ranged_attk, item_or_ability_name, saving_throw, is_aoe, False, damage_dice, saves_half, damage_type, True, is_virtual_target=virtual_target_sheet is not None)

    return roll_text, section_obj, None, targeted_combatants, last_attacked_opponents

def get_incurred_damaged_text(total_dmg, current_story, setup_aid, action_name):
    if total_dmg <= 0:
        return ""

    #current_hp = current_story["hp"] - total_dmg if current_story["hp"] - total_dmg >= 0 else 0
    current_hp_ratio = current_story["hp"] / current_story["max_hp"]
    injury_level = ""

    if current_hp_ratio >= 0.67:
        injury_level = "minor"
    elif current_hp_ratio >= 0.34:
        injury_level = "moderate"
    elif current_hp_ratio > 0:
        injury_level = "severe"
    else:
        injury_level = "fatal"
    
    incurred_dmg_text = setup_aid["incurred_damage"].replace("#injury_level#", injury_level).replace("#action_name#", 
    action_name)

    return incurred_dmg_text

def get_arcane_ward_text(current_story, total_dmg, setup_aid) -> Tuple[Any, Any]:
    arcane_ward_broke = current_story["arcane_ward_hp"] <= total_dmg

    arcane_ward_text = f"Their Arcane Ward absorbed all the damages"
    arcane_ward_info = f"Your Arcane Ward absorbed all the damages"

    if arcane_ward_broke:
        arcane_ward_text += ", but then broke in the end"
        arcane_ward_info += ", but then broke"
            
    return arcane_ward_text, arcane_ward_info

def get_damage_source_text(total_nb_of_attacks, total_nb_of_spells):
    dmg_sources = []

    if total_nb_of_attacks > 0:
        dmg_sources.append("attack" if total_nb_of_attacks == 1 else "attacks")
    if total_nb_of_spells > 0:
        dmg_sources.append("spell" if total_nb_of_spells == 1 else "spells")

    return " and ".join(dmg_sources)

# Determine if a spell can be used (max lvl spell = 1/day, other spells = 2/day)
def can_use_spell(spell, max_spell_level, used_spells):
    spell_use_nb = sum([1 for spellname in used_spells if spellname.lower() == spell["name"].lower()])

    if spell.get("level", 0) >= max_spell_level and spell_use_nb >= 1:
        return False
    elif spell.get("level", 0) < max_spell_level and spell_use_nb >= 2:
        return False
    
    return True

def get_matched_spell(spells, spell_name, opponent):
    matched_spells = [spell for spell in spells if spell["name"] == spell_name]

    if len(matched_spells) > 0:
        matched_spell = matched_spells[0]

        max_spell_level = spells[-1]["level"]
        used_spells = opponent.get("used_spells", [])
        can_cast_spell = can_use_spell(matched_spell, max_spell_level, used_spells)

        if can_cast_spell:
            return matched_spell
        else:
            print(f"ERROR: {opponent['identifier']} can't cast spell {spell_name}, expended all daily uses.")
    else:
        print(f"ERROR: Spell {spell_name} not found in opponent's spell list.")

    return None

def process_combatant_turn(current_story, setup_aid, combatant_sheets, combatant_containers, is_opponent, using_reckless_attack = False, using_patient_defense = False, using_bardic_inspiration = False) -> Tuple[Any, Any, Any, Any]:
    battle_info = current_story.get("battle_info")
    total_nb_of_attacks_vs_mc = 0
    total_nb_of_spells_vs_mc = 0

    total_dmg_vs_mc_all_combatants = 0
    total_dmg_all_combatants = 0
    has_been_hit = False
    previously_used_deflect_arrow = False # Used to track if used deflect arrow this turn
    character_objs = []
    last_successfully_attacked_adversaries = []

    for x, combatant_container in enumerate(combatant_containers):
        combatant = combatant_container["combatant"]
        sheet = get_combatant_sheet(combatant["group_name"], combatant["cr"], combatant_sheets)
        sheet_spells = sheet.get("spells", [])

        has_remaining_opponents = len([opponent for opponent in battle_info["opponents"] if opponent["hp"] > 0]) > 0

        if sheet is None:
            print_log(f"Sheet not found for combatant {combatant['group_name']}")
            continue

        # Stops whenever the AI hp drops to 0
        if current_story["hp"] == 0:
            print_log(f"Skip remaining {'opponents' if is_opponent else 'allies'} turn, Main Character is down.")
            break
        # Stops whenever all opponents are down
        elif not is_opponent and not has_remaining_opponents:
            print_log(f"Skip remaining allies turn, all opponents are down.")
            break

        combatant_action = combatant_container.get("action")
        matched_spell = None

        if combatant_action is not None and combatant_action.action_type == "casting_a_spell":
            matched_spell = get_matched_spell(sheet_spells, combatant_action.action_name, combatant)

            # IF spell not found or no more uses, will default to attack
            if matched_spell is None:
                combatant_action = Combatant_Action_Object(combatant_action.target_identity, combatant_action.target_number, "attacking", None, None, False, 1, "")

        character_obj = None

        if matched_spell is not None:
            roll_text, character_obj, total_dmg, total_dmg_vs_mc, has_been_hit, successfully_attacked_adversaries, total_nb_spells_vs_mc_combatant, _ = process_target_of_spell_turn(is_opponent, current_story, setup_aid, combatant, x, len(combatant_containers), sheet, combatant_sheets, matched_spell, has_been_hit, combatant_action, using_reckless_attack, using_patient_defense, using_bardic_inspiration)

            if successfully_attacked_adversaries is not None:
                last_successfully_attacked_adversaries = successfully_attacked_adversaries

            total_nb_of_spells_vs_mc += total_nb_spells_vs_mc_combatant

        elif combatant_action is not None and combatant_action.action_type == "using_a_skill":
            roll_text, character_obj = process_combatant_skill_turn(current_story, setup_aid, combatant, sheet, combatant_action)
            total_dmg = total_dmg_vs_mc = 0
        else:
            combatant_action = combatant_action if combatant_action is not None else Combatant_Action_Object("", None, "attacking", None, None, False, 1, "")

            # Attack = default
            roll_text, character_obj, total_dmg, total_dmg_vs_mc, total_nb_of_attacks_vs_mc_combatant, has_been_hit, previously_used_deflect_arrow, last_successfully_attacked_adversaries = process_attacked_turn(is_opponent, current_story, setup_aid, combatant, x, len(combatant_containers), sheet, combatant_sheets, has_been_hit, previously_used_deflect_arrow, combatant_action, using_reckless_attack, using_patient_defense, using_bardic_inspiration)
            
            total_nb_of_attacks_vs_mc += total_nb_of_attacks_vs_mc_combatant

        # Skip if no results
        if roll_text is None or character_obj is None:
            print_log(f"No results found for combatant {combatant['identifier']}.")
            continue

        character_objs.append(character_obj)

        total_dmg_vs_mc_all_combatants += total_dmg_vs_mc 
        total_dmg_all_combatants += total_dmg

        # Combine results with previous combatants
        if x == 0:
            final_roll_text = roll_text
        else:
            final_roll_text += f"\n{roll_text}"

    if len(character_objs) == 0:
        print_log(f"Skip {'opponents' if is_opponent else 'allies'} turn.")
        return None, None, None, None
    
    has_resistance_rage = current_story.get("is_raging", False)
    has_reckless_attack_advantage = has_talent("reckless attack", current_story) and using_reckless_attack

    # Add currently active effects
    current_effects = []
    if is_opponent and has_reckless_attack_advantage:
        current_effects.append("Reckless Attack")
    if is_opponent and has_resistance_rage:
        current_effects.append("Rage Resistance")
    if not is_opponent and using_bardic_inspiration:
        current_effects.append("Bardic Inspiration")

    roll_info_intro_text = "Effects: " + ", ".join(current_effects) if len(current_effects) > 0 else ""
    roll_info_end_texts = []
    
    # Total damage vs MC alone
    if is_opponent and total_dmg_vs_mc_all_combatants != total_dmg_all_combatants and total_dmg_vs_mc_all_combatants > 0:
        total_dmg_text = f"Total damage vs Main Character: #bold#{total_dmg_vs_mc_all_combatants}#bold#"
        print_log(total_dmg_text)
        roll_info_end_texts.append(total_dmg_text)
        
    # Total damage vs all combatants
    if total_dmg_all_combatants > 0:
        total_dmg_text = f"Total damage: #bold#{total_dmg_all_combatants}#bold#"
        print_log(total_dmg_text)
        roll_info_end_texts.append(total_dmg_text)
    
    if is_opponent and current_story.get("arcane_ward_hp", 0) > 0:
        arcane_ward_text, arcane_ward_info = get_arcane_ward_text(current_story, total_dmg_all_combatants, setup_aid)
        final_roll_text += f"\n{arcane_ward_text}."
        roll_info_end_texts.append(arcane_ward_info)

    # Get action text, including incurred damage (empty string if no damage)
    elif is_opponent and total_dmg_vs_mc_all_combatants > 0:
        dmg_source = get_damage_source_text(total_nb_of_attacks_vs_mc, total_nb_of_spells_vs_mc)
        incurred_damaged_text = get_incurred_damaged_text(total_dmg_vs_mc_all_combatants, current_story, setup_aid, dmg_source)
        final_roll_text += f"\n{incurred_damaged_text}" if incurred_damaged_text != "" else ""
    elif not is_opponent and using_bardic_inspiration:
        final_roll_text += f"\n{setup_aid['bardic_inspiration_used']}"

    print_log(final_roll_text)

    roll_info_end_text = "#message_separator#".join(roll_info_end_texts)

    section_obj = {
        "name": "Opponents" if is_opponent else "Allies",
        "start_info": roll_info_intro_text,
        "characters": character_objs,
        "info": roll_info_end_text
    }
    clean_section_obj(section_obj)

    return final_roll_text, section_obj, total_dmg_all_combatants, last_successfully_attacked_adversaries

def get_mc_skill_mod(current_story, skill_name):
    # Get what ability to use for the skill
    _, ability = get_skill_ability(skill_name)

    mc_ability_mod = get_stat_mod(current_story, ability)
    has_skill_expert = get_has_skill_expert(skill_name, current_story)
    base_proficiency_bonus = get_proficiency_bonus(current_story["level"])
    mc_has_proficiency = False

    if skill_name in [remove_parentheses(s) for s in current_story["skills"]]: # remove parentheses for some skills (ex : perform (lute))
        mc_has_proficiency = True

    mc_skill_mod = mc_ability_mod + ((base_proficiency_bonus if mc_has_proficiency else 0) * (2 if has_skill_expert else 1))

    return mc_skill_mod

def process_combatant_skill_turn(current_story, setup_aid, combatant, sheet, combatant_action: Combatant_Action_Object) -> Tuple[Any, Any]:
    # Whether to use str or cha for intimidation
    use_str_intimidation = sheet.get("str", 10) > sheet.get("cha", 10)

    # In case the skills were separated by commas or /, get the first one that matches a skill
    skills_array = get_skills_array(combatant_action.action_name)
    for action_skill_name in skills_array:
        skill_name, ability = get_skill_ability(action_skill_name, use_str_intimidation)

        if skill_name is not None:
            break

    if skill_name is None:
        print(f"\nERROR: Skill {combatant_action.action_name} not found.\n")
        return None, None
    
    # combatant stats
    combatant_ability_score = sheet[ability]
    combatant_relevant_stat_mod, combatant_cr_bonus = get_combatant_stats(combatant_ability_score, combatant["cr"])
    combatant_skill_mod = combatant_relevant_stat_mod + combatant_cr_bonus

    roll_dc = 15 # default

    skill_name_lower = skill_name.lower()
    opposed_skill = None

    if skill_name_lower in ["deception", "insight"]:
        opposed_skill = "insight" if skill_name_lower == "deception" else "deception"
    elif skill_name_lower == "intimidation":
        opposed_skill = "intimidation"
    elif skill_name_lower == "persuasion":
        opposed_skill = "persuasion"
    elif skill_name_lower in ["sleight of hand", "stealth"]:
        opposed_skill = "perception"
    elif skill_name_lower == "perception":
        opposed_skill = "stealth"

    if opposed_skill is not None:
        # mc_stats
        roll_dc = 10 + get_mc_skill_mod(current_story, opposed_skill)
    else:
        # Randomly change the DC a bit (more likely to go down than up)
        roll_dc = adjust_dc(roll_dc)

    # Doesn't apply to luck feats (only chronal shift)
    has_lucky_advantage, lucky_text = has_gotten_lucky(current_story, is_combatant_not_targeting_mc=True)

    # Roll
    d20_roll, advantage_text = roll_d20(lucky_text, has_lucky_advantage)

    final_roll_result = d20_roll + combatant_skill_mod

    # Action result
    action_result, action_result_text = get_roll_action_result(d20_roll, final_roll_result, roll_dc) #(Reversed, since the enemy makes the roll, success = our failure)

    text_color = "red" if "success" in action_result else "green"

    roll_info_intro_text = f"{skill_name}:"
    roll_info_text = f"[{d20_roll}] + {combatant_skill_mod} = #{text_color}#{final_roll_result}#{text_color}# vs DC {roll_dc}"
    
    # Advantage text
    roll_info_text += advantage_text

    print_log(roll_info_text)

    # Determine the skill or ability text
    skill_or_ability_text = f"to use '{skill_name}'"
    
    # Determine why roll needed
    reason = combatant_action.description if combatant_action.description is not None else ""
    reason = reason + "." if reason and not reason.endswith('.') else reason 
    reason_text = f"{reason} " if reason else ""

    identity_prefix = "The " if not combatant.get("is_named_npc", False) else ""
    combatant_identity = identity_prefix + combatant["identifier"]

    # write roll_text
    base_roll_msg =  setup_aid["base_skill_combatant"].replace("#skill_or_ability_text#", skill_or_ability_text).replace("#identity#", combatant_identity)
    roll_text = f"{reason_text}{base_roll_msg} {setup_aid[action_result + '_combatant_skill']}"

    character_obj = {
        "name": combatant_identity,
        "unique_actions": [
            {
                "name": skill_or_ability_text,
                "info": roll_info_intro_text,
                "actions": [
                    {
                        "combatant_rolls": [d20_roll],
                        "info": roll_info_text
                    }
                ] 
            }
        ]
    }

    return roll_text, character_obj

def get_ability_score_used_for_spell(sheet):
    ability_score_name = sheet.get("spellcasting_ability_score", "int")

    return sheet.get(ability_score_name, 10)

def get_sound_triple(damage_type, is_ranged, label):
    if damage_type and damage_type.lower() == "sonic":
        damage_type = "thunder"

    return (damage_type, is_ranged, label)

def get_action_result_reversed(action_result):
    return action_result.replace("success", "failure") if "success" in action_result else action_result.replace("failure", "success")

def get_bardic_inspiration_bonus(current_story, using_bardic_inspiration, is_opponent, is_spell_save = False):
    bardic_inspiration_bonus = 0
    bardic_inspiration_text = ""
    # Bardic inspiration during ally turn for attack rolls (physical or spell), or during opponent turn for spell saves
    if using_bardic_inspiration and ((not is_opponent and not is_spell_save) or (is_opponent and is_spell_save)):
        bardic_inspiration_bonus = rd.randint(1, get_bardic_inspiration_dice(current_story))
        bardic_inspiration_text = f" + {bardic_inspiration_bonus} (Bard. Insp.)"

    return bardic_inspiration_bonus, bardic_inspiration_text

def process_target_of_spell_turn(is_opponent, current_story, setup_aid, combatant, combatant_nb, combatants_count, sheet, combatant_sheets, spell, has_been_hit, combatant_action, using_reckless_attack, using_patient_defense, using_bardic_inspiration) -> Tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    if spell.get("has_missing_info", False) or spell.get("is_higher_than_max_level", False):
        print_log("Spell info is missing")
        return None, None, 0, 0, has_been_hit, None, 0, False
    
    combatant_identity = combatant["identifier"]
    challenge_rating = sheet.get("cr")

    spell_name = spell.get("name")
    spell_level = spell.get("level")
    
    spell_row = get_spell_row(spell_name)
    saving_throw, is_ranged_attk, is_spell_attk, saves_half, is_auto_hit, is_aoe, is_healing, is_buff, is_oob_only, nb_attack_rolls, spell_found, mc_has_resistance, damage_type = get_spell_info(spell_row, current_story)

    if not spell_found:
        print_log(f"Spell {spell_name} not found in the spell list.")
        return None, None, 0, 0, has_been_hit, None, 0, False
    
    action_target_identity = combatant_action.target_identity

    # Target comrades when healing
    is_targeting_opponents = (not is_opponent and not is_healing and not is_buff) or (is_opponent and (is_healing or is_buff))

    # Get combatants currently being targeted from battle info
    targeted_combatants, battle_info, is_targeting_mc, is_targeting_self = get_battle_info_combatants(current_story, action_target_identity, combatant_action.target_number, is_targeting_opponents, True)

    if battle_info is None:
        print(f"ERROR: No battle info found for process_attacked")
        return None, None, 0, 0, has_been_hit, None, 0, False
    
    if is_targeting_self:
        action_target_identity = "themself"

    is_targeting_mc_or_aoe = is_targeting_mc or (is_opponent and is_aoe)
    combatant_opponents = battle_info.get("allies", []) if is_opponent else battle_info["opponents"]
    combatant_opponents_alive = [opponent for opponent in combatant_opponents if opponent["hp"] > 0]
    
    damage_dice = get_spell_damage(spell_name, None, challenge_rating)
    
    identity_prefix = "The " if not combatant.get("is_named_npc", False) else ""

    # Different msg for spell attacks
    base_spell_msg = setup_aid["base_target_of_spell"] if not is_spell_attk else setup_aid["base_target_of_spell_attack"]

    base_spell_msg = base_spell_msg.replace("#spell_name#", spell_name).replace("#combatant_identity#", identity_prefix + combatant_identity)

    total_nb_spells_targeting_mc = 0

    # Auto success when spell is not an attack and has no saving throw, unless it's healing
    if ((is_targeting_self or (not is_spell_attk and saving_throw is None)) and not is_healing):
        print_log("Spell cast that isn't an attack and has no saves: automatic success.")
        roll_info = f"Casting '{spell_name}'"
        base_spell_msg = base_spell_msg.replace("#target_identity#", action_target_identity)

        total_nb_spells_targeting_mc += 1 if is_targeting_mc else 0

        char_obj = {
            "name": combatant_identity,
            "info": roll_info
        }

        return f"{base_spell_msg} {setup_aid['success'].replace('#injuries#', '')}", char_obj, 0, 0, has_been_hit, None, total_nb_spells_targeting_mc, False

    # char stats
    char_ac = current_story['AC']
    is_evading = has_shield_master = False

    # combatant stats
    ability_score = get_ability_score_used_for_spell(sheet)
    ability_score_mod, combatant_cr_bonus = get_combatant_stats(ability_score, challenge_rating)
    advantage_text = ""

    if is_healing:
         # Healing
        roll_info_text, total_healing = get_healing(spell_name, spell_level, ability_score_mod, spell_row, None,  challenge_rating)
        print_log(roll_info_text)

        healing_status_text = ""

        if (is_aoe and not is_opponent) or is_targeting_mc:
            heal_mc_hp(current_story, total_healing)
            healing_status = get_mc_health_status(current_story["hp"], current_story["max_hp"], True)
            healing_status_text = " " + setup_aid[healing_status] if healing_status is not None else ""

        if is_aoe:
            all_combatants = battle_info["opponents"] if is_opponent else battle_info.get("allies", []) # Heal everyone onm their team
            healing_status_text += " " + process_aoe_heal_combatants(all_combatants, total_healing, setup_aid)

        elif is_targeting_self:
            healing_status_text = process_combatant_healing([combatant], total_healing, setup_aid)

        elif len(targeted_combatants) > 0:
            healing_status_text = process_combatant_healing(targeted_combatants, total_healing, setup_aid)

        roll_text = base_spell_msg.replace("#target_identity#", action_target_identity) + " " + identity_prefix + healing_status_text

        roll_info_text_intro = f"{combatant_identity} ({spell_name}) => {action_target_identity if not is_targeting_self else 'self'}"

        char_obj = get_char_obj_healing(battle_info, current_story, spell_name, is_ranged_attk, combatant_identity, roll_info_text_intro, roll_info_text, is_opponent)

        return roll_text, char_obj, 0, 0, has_been_hit, None, 0, False
    
    # Advantage on roll if saving throw, disadvantage on combatant roll if spell attack
    has_lucky, lucky_text = has_gotten_lucky(current_story, combatant_nb, combatants_count, is_combatant_not_targeting_mc = not is_targeting_mc_or_aoe) 

    roll_info_text = roll_text = ""

    action_results = []
    total_dmg_all = 0
    total_dmg_vs_mc = 0
    attack_objs = []
    target_of_spell_roll_texts = []

    nb_successful_attacks_non_mc = 0
    current_targeted_combatant = None

    roll_info_intro_text = ""

    if is_spell_attk:
        nb_attack_rolls = nb_attack_rolls if nb_attack_rolls is not None else 1
        is_hit = is_critical = has_uncanny_dodge_reduction = False
        total_attk_hits = 0

        nb_attack_rolls_vs_current_target = 0

        for x in range(nb_attack_rolls):
            nb_attack_rolls_vs_current_target += 1
            has_resistance = False

            if is_targeting_mc:
                current_targeted_combatant = current_targeted_combatant_sheet = None
                target_identity = "me"
                has_resistance = mc_has_resistance
            else:
                current_targeted_combatant, current_targeted_combatant_sheet = get_next_combatant_sheet(targeted_combatants, combatant_sheets)
                if current_targeted_combatant is None and is_opponent: # If no more combatants left to target, target the main character
                    is_targeting_mc = True
                    target_identity = "me"
                elif current_targeted_combatant is None:
                    print_log(f"Warning: No more combatants left to target", True)
                    break
                else:
                    target_identity = current_targeted_combatant["identifier"]
                
            if is_auto_hit:
                d20_roll = None
                is_hit = True
                total_attk_hits += 1

                action_result = "success"
                action_results.append(action_result)
                action_result_text = action_result.capitalize()

                text_color = "red" if is_opponent else "green"
                roll_info_text = f"#green#Auto-hit#green#" 
                print_log(roll_info_text)

            # Is ranged spell attack (combatant attacks char)
            else:
                has_reckless_attack_advantage = has_talent("reckless attack", current_story) and using_reckless_attack and is_opponent and is_targeting_mc

                reason_advantage = "rage" if has_reckless_attack_advantage else ""

                has_advantage = has_reckless_attack_advantage
                has_disadvantage = False

                # Patient defense = disadvantage on opponents attack roll
                if using_patient_defense and is_opponent and is_targeting_mc:
                    has_disadvantage = True
                    reason_advantage = "patient defense"

                # Lucky = disadvantage for opponents targetting the mc, advantage for allies
                if has_lucky and is_opponent:
                    reason_advantage = reason_advantage if reason_advantage != "" else lucky_text
                    has_disadvantage = True
                    has_lucky = False
                elif has_lucky and not is_opponent:
                    reason_advantage = reason_advantage if reason_advantage != "" else lucky_text
                    has_advantage = True
                    has_lucky = False

                # Bardic inspiration
                bardic_inspiration_bonus, bardic_inspiration_text = get_bardic_inspiration_bonus(current_story, using_bardic_inspiration, is_opponent)

                # Lucky = disadvantage on combatant roll
                d20_roll, advantage_text = roll_d20(reason_advantage, has_advantage, has_disadvantage, skip_advantage_rolls=True)

                final_roll_bonus = ability_score_mod + combatant_cr_bonus # Don't include BI here, want to be shown in the roll info separately
                final_roll_result = d20_roll + final_roll_bonus + bardic_inspiration_bonus

                target_ac = char_ac if is_targeting_mc else current_targeted_combatant_sheet["ac"]

                # Add armor bonus to allies (mc is already precalculated in the char sheet AC)
                if is_opponent and not is_targeting_mc and has_talent("aura of armor", current_story):
                    target_ac += 1

                action_result, action_result_text = get_roll_action_result(d20_roll, final_roll_result, target_ac)
                is_success = "success" in action_result

                # Text color (Reversed for opponents)
                if is_opponent:
                    text_color = "red" if is_success else "green"
                else:
                    text_color = "green" if is_success else "red"

                action_results.append(action_result)

                # Roll info
                roll_info_text = f"[{d20_roll}] + {final_roll_bonus}{bardic_inspiration_text} = #{text_color}#{final_roll_result}#{text_color}#{advantage_text} vs AC {target_ac}"

                print_log(roll_info_text)

                is_hit = text_color == "red"
                total_attk_hits += 1 if is_hit else 0

                # Uncanny dodge
                if is_hit and not has_been_hit and is_targeting_mc:
                    has_been_hit = True # Only for spell attacks (magic missile is not a spell attack)
                    has_uncanny_dodge_reduction = has_talent("uncanny dodge", current_story)

                is_critical = d20_roll == 20

            if is_hit:
                roll_info_damage, total_attk_dmg = process_damage_dice(damage_dice, is_critical, has_resistance = has_resistance, is_short_dmg_text = True, is_uncanny_dodge = has_uncanny_dodge_reduction)

                has_uncanny_dodge_reduction = False

                roll_info_text += f". {roll_info_damage}" if roll_info_damage != "" else ""

                # Update the ai hp and add to history
                if is_targeting_mc:
                    update_ai_hp(current_story, total_attk_dmg)
                    total_dmg_vs_mc += total_attk_dmg
                elif not is_targeting_mc:
                    update_opponent_hp(current_targeted_combatant, total_attk_dmg)

                total_dmg_all += total_attk_dmg

                if not is_targeting_mc:
                    nb_successful_attacks_non_mc += 1
                else: 
                    total_nb_spells_targeting_mc += 1

            attack_obj = {
                "number": x + 1,
                "combatant_rolls": [d20_roll],
                "info": roll_info_text,
                "adversaries_hp": get_combatants_health_history(combatant_opponents, current_story, is_opponent)
            }
            attack_objs.append(attack_obj)

            has_deafeated_current_target = (is_targeting_mc and current_story["hp"] == 0) or (not is_targeting_mc and current_targeted_combatant["hp"] == 0)

            # Create the result text for all attacks vs the current target, stopping if the target is defeated or if it's the last attack
            if has_deafeated_current_target or x == nb_attack_rolls - 1:
                # Only specify the nb of times if > 1
                spell_msg_intro = base_spell_msg.replace("#target_identity#", target_identity).replace("#nb_times#",  f" {nb_attack_rolls_vs_current_target} times").replace("#then_text#", " then" if nb_attack_rolls_vs_current_target != nb_attack_rolls else "")

                # Get the result text for the attack, taking into account how many attacks there are and if they are all the same
                target_of_spell_roll_text = get_attack_results_texts(action_results, nb_attack_rolls_vs_current_target, setup_aid)
                target_of_spell_roll_texts.append(spell_msg_intro + target_of_spell_roll_text)

                action_results = []
                nb_attack_rolls_vs_current_target = 0

                spell_text = spell_name + (f", Spell Attack" if not is_auto_hit else "")
                attack_info_target_identity = "You" if is_targeting_mc else target_identity

                roll_info_intro_text = f"{combatant_identity} ({spell_text}) => {attack_info_target_identity}"

                if not is_targeting_mc:
                    health_text = get_combatant_health_text(current_targeted_combatant, setup_aid)
                    health_text = health_text[0].upper() + health_text[1:] if health_text is not None else None # capitalize the first letter

                    if health_text is not None:
                        target_of_spell_roll_texts.append(health_text + ".")

            # Stops whenever the AI hp drops to 0
            if current_story["hp"] == 0:
                break

    # Is saving throw (char resists combatant's spell)
    else:
        target_stat_short = saving_throw[:3].lower()
        main_targeted_combatants = []

        # Target list
        if is_aoe:
            if is_opponent:
                main_targeted_combatants.append(None) # Main character is just None at the start of the list
            main_targeted_combatants += combatant_opponents_alive # aoe targets everyone
        elif is_targeting_mc:
            main_targeted_combatants.append(None) # Main character is just None at the start of the list
        else:
            main_targeted_combatants = targeted_combatants[:1] # Target first opponent

        # Note : Shouldn't actually happen, since action should be skipped in process_combatant_turn if no combatants to target
        if len(main_targeted_combatants) == 0:
            print("ERROR: No combatants found to target")
            return None, None, 0, 0, has_been_hit, None, 0, False

        # Target text
        if is_aoe:
            target_identity = setup_aid["me_and_allies_text"] if is_opponent else "all opponents" # target everyone
        elif is_targeting_mc:
            target_identity = "me"
        else:
            target_identity = main_targeted_combatants[0]["identifier"]

        base_spell_msg = base_spell_msg.replace("#target_identity#", target_identity).replace("#nb_times#", "").replace("#then_text#", "")

        roll_texts = []

        dice_text, dice_roll_text, total = get_rolls_damage(damage_dice, False)

        # Saving throw = yellow (since multiple opponents can be targeted by the same effect)
        roll_info_intro_text = f"Cast Spell ({spell_name}, Saving Throw), {total}:"

        # Loop over all combatants for AOE (including the MC possibly, x = 0)
        for x, targeted_combatant in enumerate(main_targeted_combatants):
            is_mc_saving_throw = targeted_combatant is None and x == 0
            targeted_combatant_sheet = None
            has_resistance = has_rage_str_advantage = has_danger_sense_advantage = has_patient_defense_advantage = False
            bardic_inspiration_bonus = 0
            bardic_inspiration_text = ""

            if is_mc_saving_throw:
                target_relevant_mod, target_prof_bonus, target_prof_text, _, _, total_bonus, total_bonus_text = get_char_info_for_saving_throw(saving_throw, current_story)
                has_resistance = mc_has_resistance

                # Potential advantage on saves targetting the mc
                has_rage_str_advantage = current_story.get("is_raging", False) and target_stat_short == "str"
                has_danger_sense_advantage = has_talent("danger sense", current_story) and target_stat_short == "dex"
                has_patient_defense_advantage = using_patient_defense and target_stat_short == "dex"
                current_target_identity = "I"

            else:
                targeted_combatant_sheet = get_combatant_sheet(targeted_combatant["group_name"], targeted_combatant["cr"], combatant_sheets)
                
                # Can happen when manually changes battle info in current_story (sheets won't match)
                if targeted_combatant_sheet is None:
                    target_name = " (" + targeted_combatant["identifier"] + ")" if targeted_combatant is not None else ""
                    print(f"ERROR: Opponent sheet not found for target{target_name} in target of spell")
                    return None, None, 0, 0, None, None, 0, False

                target_relevant_mod, target_prof_bonus, target_prof_text = get_combatant_saving_throw_info(saving_throw, combatant, targeted_combatant_sheet)

                total_bonus = 0
                total_bonus_text = ""

                # Add aura of protection bonus to allies
                if is_opponent and has_talent("aura of protection", current_story):
                    aura_of_protection_bonus = get_stat_mod(current_story, "cha")
                    total_bonus += aura_of_protection_bonus
                    f" + {aura_of_protection_bonus}(aura of protection)"

                # Bardic inspiration
                bardic_inspiration_bonus, bardic_inspiration_text = get_bardic_inspiration_bonus(current_story, using_bardic_inspiration, is_opponent, True)

                current_target_identity = targeted_combatant["identifier"]

            # ADVANTAGE
            has_advantage = has_danger_sense_advantage or has_rage_str_advantage or has_patient_defense_advantage
            has_disadvantage = False

            reason_advantage = "rage" if has_rage_str_advantage else ("danger sense" if has_danger_sense_advantage else ("patient defense" if has_patient_defense_advantage else (lucky_text if has_lucky else None)))

            # Lucky = advantage on allies save, disadvantage for opponents save
            if has_lucky and is_opponent:
                reason_advantage = reason_advantage if reason_advantage != "" else lucky_text
                has_disadvantage = False
                has_lucky = False
            elif has_lucky and not is_opponent:
                reason_advantage = reason_advantage if reason_advantage != "" else lucky_text
                has_advantage = True
                has_lucky = False

            # Roll
            d20_roll, advantage_text = roll_d20(reason_advantage, has_advantage, has_disadvantage)

            saving_throw_DC = 8 + ability_score_mod + combatant_cr_bonus

            final_roll_bonus = target_relevant_mod + target_prof_bonus + total_bonus # Don't include BI here, want to be shown in the roll info separately
            final_roll_result = d20_roll + final_roll_bonus + bardic_inspiration_bonus 

            action_result, action_result_text = get_roll_action_result(d20_roll, final_roll_result, saving_throw_DC)
            is_success = "success" in action_result

            # Action result 
            if is_opponent:
                text_color = "green" if is_success else "red"
            else:
                text_color = "red" if is_success else "green"

            save_base_text = f"[{d20_roll}] + {final_roll_bonus}{bardic_inspiration_text}"
            detailed_save_base_text = f"[{d20_roll}] + {target_relevant_mod}({target_stat_short}){target_prof_text}{total_bonus_text}{bardic_inspiration_text}"

            roll_info_target_save = f"Target => {'You' if is_mc_saving_throw else current_target_identity}"
            roll_info_save = f"#save_base# = #{text_color}#{final_roll_result}#{text_color}# vs DC {saving_throw_DC}"

            roll_info_save += advantage_text

            print_log(roll_info_save.replace("#save_base#", detailed_save_base_text))
            roll_info_save = roll_info_save.replace("#save_base#", save_base_text)

            # Whether the char uses evasion to evade all
            is_evading, has_shield_master = get_is_evading(saves_half, target_stat_short, current_story) if is_mc_saving_throw else (False, False) # Only applies to the main character

            total_dmg_save, roll_info_damage, roll_text_damage = get_damage_info_save(dice_text, dice_roll_text, total, not is_success, damage_dice, saves_half, is_evading, has_shield_master, has_resistance, setup_aid, is_short_dmg_text=True)
            
            roll_info_save += roll_info_damage

            # Update the ai hp and add to history
            if is_mc_saving_throw:
                update_ai_hp(current_story, total_dmg_save)
                total_dmg_vs_mc += total_dmg_save
                total_nb_spells_targeting_mc += 1 if total_dmg_save > 0 else 0

            elif not is_mc_saving_throw:
                update_opponent_hp(targeted_combatant, total_dmg_save)

            total_dmg_all += total_dmg_save

            attack_obj = {
                "number": x + 1,
                "rolls": [d20_roll] if is_mc_saving_throw else None,
                "combatant_rolls": [d20_roll] if not is_mc_saving_throw else None,
                "start_info": roll_info_target_save,
                "info": roll_info_save,
                "adversaries_hp": get_combatants_health_history(combatant_opponents, current_story, is_opponent)
            }
            if attack_obj["rolls"] is None:
                del attack_obj["rolls"]
            if attack_obj["combatant_rolls"] is None:
                del attack_obj["combatant_rolls"]

            attack_objs.append(attack_obj)

            # skip save half msg when a combatant is defeated, even if did save half, in order to reduce confusion
            if not is_mc_saving_throw and saves_half and "success" in action_result and targeted_combatant["hp"] <= 0:
                action_result = "failure"

            # Whether to show the saves half message 
            # Note: action results are reversed for saving throws
            if saves_half and is_success:
                # Saves half when the opponent succeeds
                save_result_text = setup_aid["saved_half_magic"].replace("#target#", current_target_identity)
            else:
                action_result_reversed = get_action_result_reversed(action_result)
                save_result_text = setup_aid[action_result_reversed + "_magic"].replace("#target#", current_target_identity)

            if not is_mc_saving_throw:
                health_text = get_combatant_health_text(targeted_combatant, setup_aid)
                
                if health_text is not None:
                    save_result_text += ", " + health_text

            roll_texts.append(save_result_text)

    if is_spell_attk:
        roll_text = " ".join(target_of_spell_roll_texts)
    else:
        roll_text = base_spell_msg + " " + ". ".join(roll_texts)

    # Successfully attacked adversaries
    last_successfully_attacked_adversaries = []

    if nb_successful_attacks_non_mc > 0 and not is_targeting_mc and current_targeted_combatant is not None and current_targeted_combatant["hp"] > 0:
        last_successfully_attacked_adversaries = [current_targeted_combatant]

    # Add used spells
    combatant["used_spells"] = combatant.get("used_spells", []) + [spell_name]

    character_obj = {
        "name": combatant_identity,
        "unique_actions": [
            {
                "name": spell_name,
                "info": roll_info_intro_text,
                "sound": get_sound_triple(damage_type, is_ranged_attk, spell_name),
                "actions": attack_objs 
            }
        ]
    }

    print_log(character_obj)

    return roll_text, character_obj, total_dmg_all, total_dmg_vs_mc, has_been_hit, last_successfully_attacked_adversaries, total_nb_spells_targeting_mc, is_spell_attk

def is_normal_dmg_type(damage_type):
    damage_types = damage_type.lower().split("/") if damage_type is not None else []
    normal_dmg_types = ["bludgeoning", "piercing", "slashing"]

    return any([dmg_type in normal_dmg_types for dmg_type in damage_types])

def has_resistance_to_damage(damage_type, current_story):
    damage_types = damage_type.lower().split("/") if damage_type is not None else []

    # Has a talent giving it resistance to this damage type
    resistance_talent = get_talent("resistance", current_story, partial_match=True)
    resistance_name = extract_text_in_parenthesis(resistance_talent) if resistance_talent is not None else None
    has_resistance_talent = resistance_name is not None and resistance_name in damage_types

    # Has resistance to all normal dmg types when raging (slashing, piercing, bludgeoning)
    has_resistance_rage = current_story.get("is_raging", False)
    resistance_rage_applies = has_resistance_rage and is_normal_dmg_type(damage_type)

    has_resistance = has_resistance_talent or resistance_rage_applies

    return has_resistance, resistance_rage_applies

# Get the result text for the attack, taking into account how many attacks there are and if they are all the same
def get_attack_results_texts(action_results, how_many_attacks, setup_aid):
    final_results_text = ""
    ordered_results_obj = {}

    # Group the results by their type
    for y, result in enumerate(action_results):
        if result not in ordered_results_obj:
            ordered_results_obj[result] = []
        ordered_results_obj[result].append(get_order_text(y+1))

    is_all_same_results = len(ordered_results_obj) == 1

    # Add the results of the attack
    if how_many_attacks == 1:
        first_result = setup_aid[action_results[0] + "_words"]
        final_results_text = ", which was " + first_result + "."
        
    # If all the same results
    elif is_all_same_results:
        first_result = setup_aid[action_results[0] + "_words"]
        final_results_text = ", all of which were " + first_result + "."

    # If diff result and nb of diff results == 2
    elif len(ordered_results_obj) == 2:
        first_result = list(ordered_results_obj)[0]
        first_result_values = ordered_results_obj[first_result]
        first_were_or_was = "were" if len(first_result_values) > 1 else "was"
        first_add_s = "s" if len(first_result_values) > 1 else ""

        second_result = list(ordered_results_obj)[1]
        second_result_values = ordered_results_obj[second_result]
        second_were_or_was = "were" if len(second_result_values) > 1 else "was"
        
        # Ex : the first and third were successful, but the second was unsuccessful.
        final_results_text = f": the {join_with_and(first_result_values)} attack{first_add_s} {first_were_or_was} {setup_aid[first_result + '_words']}, but the {join_with_and(second_result_values)} attack{first_add_s} {second_were_or_was} {setup_aid[second_result + '_words']}."
        
    # If diff result and nb of diff results > 2
    elif len(ordered_results_obj) > 2:
        final_results_arr = []

        # Ex : the first and third were successful, the second unsuccessful and the fourth critically successful.
        for result, values in ordered_results_obj.items():
            result_text = setup_aid[result + "_words"]
            were_or_was = "were" if len(values) > 1 else "was"
            
            final_results_arr.append(f"the {join_with_and(values)} {were_or_was} {result_text}")

        final_results_text = ": " + join_with_and(final_results_arr) + "."

    return final_results_text

def update_ai_hp(current_story, total_dmg):
    current_story["hp"] = max(0, current_story["hp"] - total_dmg)

def get_combatant_health_text(combatant, setup_aid):
    if combatant["hp"] == 0:
        return setup_aid["combatant_dead"].replace("#attack_type#", "attack").replace("#combatant_identifier#", combatant["identifier"])
    
    return None

def process_attacked_turn(is_opponent, current_story, setup_aid, combatant, combatant_nb, combatants_count, sheet, combatant_sheets, has_been_hit, previously_used_deflect_arrow, combatant_action: Combatant_Action_Object, using_reckless_attack = False, using_patient_defense = False, using_bardic_inspiration = False) -> Tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    mc_behind_cover = False # Always false for now
    
    has_heavy_armor_master = has_talent("heavy armor master", current_story)
    has_multiattack_defense = has_talent("multiattack defense", current_story)
    has_resistance_rage = current_story.get("is_raging", False)

    identity = combatant["identifier"]
    cr = combatant.get("cr", 1)

    # char stats
    char_ac = current_story['AC']
    final_char_ac = char_ac + 2 if mc_behind_cover else char_ac
    
    # Roll
    total_dmg = 0
    total_dmg_vs_mc = 0
    roll_texts = []

    # Get combatants currently being targeted from battle info
    targeted_combatants, battle_info, is_targeting_mc, _ = get_battle_info_combatants(current_story, combatant_action.target_identity, combatant_action.target_number, not is_opponent, combatant_action.is_ranged)

    if battle_info is None:
        print(f"ERROR: No battle info found for process_attacked")
        return None, None, None, 0, 0, has_been_hit, previously_used_deflect_arrow, None

    combatant_opponents = battle_info.get("allies", []) if is_opponent else battle_info["opponents"]

    action_weapon_name = combatant_action.action_name if combatant_action is not None else None
    action_how_many = combatant_action.how_many if combatant_action is not None else 1

    #combatant_is_ranged = sheet.get("is_ranged")    
    unique_attacks = sheet.get("attacks", [])

    # if action_weapon_name contained in any of the attack's weapon name (match all of action is None (ex: tests))
    matched_action_unique_attacks = [attack for attack in unique_attacks if action_weapon_name.lower() in attack.get("weapon", "").lower() or attack.get("weapon", "").lower() in action_weapon_name.lower()] if action_weapon_name is not None else unique_attacks

    # If the weapon name is contained anywhere in the weapon's list, use that attack type's multiattack (ranged or not)
    if len(matched_action_unique_attacks) > 0:
        matched_action_attack = matched_action_unique_attacks[0]
        is_ranged_attack = matched_action_attack.get("is_ranged", False) # Whether the chosen attack is ranged or not

        # Make sure to only include attacks with the same weapon type (ranged or not)
        unique_attacks_correct_type = [attack for attack in unique_attacks if attack.get("is_ranged", False) == is_ranged_attack]

        if len(unique_attacks_correct_type) > 0 and len(unique_attacks_correct_type) < len(unique_attacks):
            unique_attacks = unique_attacks_correct_type
    else:
        # Use highest of str or dex for custom attack
        str_score = sheet.get("str", 10)
        dex_score = sheet.get("dex", 10)
        attack_ability, attack_ability_score_nb = ("str", str_score) if str_score > dex_score else ("dex", dex_score)

        max_nb_multiattack = get_max_nb_multiattack(cr)

        damage_dice, how_many = get_attack_dmg_and_how_many(action_weapon_name, action_how_many, cr, sheet, attack_ability_score_nb, max_nb_multiattack, action_how_many)

        unique_attacks = [{"weapon": action_weapon_name, "damage_type": combatant_action.damage_type, "is_ranged": combatant_action.is_ranged, "how_many": how_many, "ability_used": attack_ability, "damage_dice": damage_dice, "is_split": False}]

    target_identity = ""
    was_hit_multiattack = False
    has_uncanny_dodge_reduction = False
    total_nb_of_attacks_vs_mc = 0
    unique_attack_objs = []
    x = 0

    has_reckless_attack_advantage = has_talent("reckless attack", current_story) and using_reckless_attack and is_opponent and is_targeting_mc

    nb_successful_attacks_non_mc = 0
    current_targeted_combatant = None

    # Attack rolls
    #for x, attack in enumerate(unique_attacks):
    while x < len(unique_attacks):
        attack = unique_attacks[x]

        if is_targeting_mc:
            current_targeted_combatant = current_targeted_combatant_sheet = None
            target_identity = "me"
        else:
            current_targeted_combatant, current_targeted_combatant_sheet = get_next_combatant_sheet(targeted_combatants, combatant_sheets)
            if current_targeted_combatant is None and is_opponent: # If no more combatants left to target, target the main character
                is_targeting_mc = True
                target_identity = "me"
            elif current_targeted_combatant is None:
                print_log(f"WARNING: No more combatants left to target", True)
                break
            else:
                target_identity = current_targeted_combatant["identifier"]

        how_many_attacks = attack.get("how_many", 1)

        # Set on a per attack basis
        attack_ability_name = attack.get("ability_used", "str")
        attack_ability_score = sheet.get(attack_ability_name, 10)
        
        # Doesn't really make sense for attacker to have 0 ability score, just set to 10 as default
        attack_ability_score = attack_ability_score if attack_ability_score > 0 else 10

        # combatant stats
        combatant_relevant_stat_mod, combatant_cr_bonus = get_combatant_stats(attack_ability_score, cr)

        action_results = []
        unique_attack_results= []

        attack_objs = []

        # 1 to how_many_attacks
        for y in range(how_many_attacks):
            weapon = attack.get("weapon")
            damage_dice = attack.get("damage_dice")
            is_ranged = attack.get("is_ranged", False)
            how_many_attacks_total = len(unique_attacks) * how_many_attacks

            # Damage resistances
            damage_type = attack.get("damage_type")

            has_resistance, resistance_rage_applies = has_resistance_to_damage(damage_type, current_story) if is_targeting_mc else (False, False)

            # Patient defense = disadvantage on opponents attack roll
            has_patient_defense_disadvantage = using_patient_defense and is_opponent and is_targeting_mc

            # LUCKY
            has_lucky, lucky_text = has_gotten_lucky(current_story, (combatant_nb * how_many_attacks_total) + y, combatants_count * how_many_attacks_total, is_combatant_not_targeting_mc = not is_targeting_mc)

            has_lucky_disadvantage = has_lucky and is_opponent
            has_lucky_advantage = has_lucky and not is_opponent

            # Reason for advantage or disadvantage
            which_disadvantage_text = lucky_text if has_lucky_disadvantage else ("patient defense" if has_patient_defense_disadvantage else "")
            which_advantage_text = lucky_text if has_lucky_advantage else ("reckless attack" if has_reckless_attack_advantage else "")
            which_adv_or_dis_text = which_advantage_text if which_disadvantage_text == "" else (which_disadvantage_text if which_advantage_text == "" else "") # Empty if both advantage and disadvantage applies
            
            # Bardic inspiration
            bardic_inspiration_bonus, bardic_inspiration_text = get_bardic_inspiration_bonus(current_story, using_bardic_inspiration, is_opponent)
                        
            # Roll
            d20_roll, advantage_text = roll_d20(which_adv_or_dis_text, has_lucky_advantage or has_reckless_attack_advantage, has_lucky_disadvantage or has_patient_defense_disadvantage, skip_advantage_rolls=True)
            
            final_roll_bonus = combatant_relevant_stat_mod + combatant_cr_bonus # Don't include BI here, want to be shown in the roll info separately
            final_roll_result = d20_roll + final_roll_bonus + bardic_inspiration_bonus

            target_ac = final_char_ac if is_targeting_mc else current_targeted_combatant_sheet["ac"]

            # Add armor bonus to allies (mc is already precalculated in the char sheet AC)
            if is_opponent and not is_targeting_mc and has_talent("aura of armor", current_story):
                target_ac += 1

            action_result, action_result_text = get_roll_action_result(d20_roll, final_roll_result, target_ac)
            is_success = "success" in action_result

            if is_opponent:
                text_color = "red" if is_success else "green" # Color reversed when enemy attacks
            else:
                text_color = "green" if is_success else "red"

            # Is hit
            is_hit = is_success
            using_deflect_arrow = is_targeting_mc and has_talent("deflect missiles", current_story) and is_ranged and is_hit and not previously_used_deflect_arrow and damage_type is not None and "piercing" in damage_type.lower()
            if using_deflect_arrow:
                text_color = "green"

            cover_text = f" + 2 (cover) = {target_ac}" if is_targeting_mc and mc_behind_cover else ""
            multi_attack_defense_text = " + 4 (multiattack defense)" if has_multiattack_defense and was_hit_multiattack else ""

            roll_info_text = f"[{d20_roll}] + {final_roll_bonus}{bardic_inspiration_text} = #{text_color}#{final_roll_result}#{text_color}#{advantage_text} vs AC {target_ac}{cover_text}{multi_attack_defense_text}"

            # Need to add it before printing the info
            if using_deflect_arrow:
                roll_info_text += f" (Deflect Missiles)"

            print_log(roll_info_text)

            # Damage
            total_attack_dmg = 0

            if is_hit and damage_dice is not None and not using_deflect_arrow:
                
                has_uncanny_dodge_reduction = is_targeting_mc and has_talent("uncanny dodge", current_story) and not has_been_hit

                # Multiattack Defense (skip if last attack of multiattack)
                if is_targeting_mc and has_multiattack_defense and not was_hit_multiattack and how_many_attacks_total > 1 and not ((x + 1) == len(unique_attacks) and (y + 1) == how_many_attacks):
                    was_hit_multiattack = True
                    # roll_info_text += f" (Triggered Multiattack Defense)"
                    final_char_ac += 4

                heavy_armor_master_applies = is_targeting_mc and has_heavy_armor_master and is_normal_dmg_type(damage_type) # Applies to magical attacks too (shield maiden ability)
                half_dmg_text = ""

                damage_bonus = combatant_relevant_stat_mod
                # Add aura of conquest bonus to allies
                if not is_opponent and not is_ranged and has_talent("aura of conquest", current_story):
                    aura_of_conquest_bonus = int(get_stat_mod(current_story, "cha") / 2)
                    damage_bonus += aura_of_conquest_bonus

                # Process damages
                roll_dmg_text, total_attack_dmg = process_damage_dice(damage_dice, d20_roll == 20, damage_bonus, has_resistance=has_resistance, has_heavy_armor_master=heavy_armor_master_applies, resistance_reason=half_dmg_text, is_short_dmg_text=True, is_uncanny_dodge=has_uncanny_dodge_reduction)

                # Apply damages
                has_been_hit = True
                roll_info_text += f". {roll_dmg_text}"

                total_dmg += total_attack_dmg
                total_dmg_vs_mc += total_attack_dmg if is_targeting_mc else 0
                #total_unique_attack_damages += total_attack_dmg
                if not is_targeting_mc:
                    nb_successful_attacks_non_mc += 1

            # Add the roll info text before printing the info, above
            elif using_deflect_arrow:
                has_been_hit = True
                previously_used_deflect_arrow = True
                action_result = "failure"

            attacked_result_text = ""
            ordered_text = f" {get_order_text(y+1)}" if how_many_attacks > 1 else ""

            # Specialized roll text
            if using_deflect_arrow:
                attacked_result_text = f"I catched the{ordered_text} projectile in midair!"
            elif has_uncanny_dodge_reduction:
                attacked_result_text = f"I partially dodged the{ordered_text} attack, reducing some of the damages!"

            #roll_texts.append(attacked_result_text)
            if attacked_result_text != "":
                unique_attack_results.append(attacked_result_text)

            action_results.append(action_result)

            if is_targeting_mc:
                total_nb_of_attacks_vs_mc += 1

            # Update the AI hp after each attacks, but only if no arcane ward is active.
            if is_targeting_mc and current_story.get("arcane_ward_hp", 0) == 0:
                update_ai_hp(current_story, total_attack_dmg)
            elif not is_targeting_mc:
                update_opponent_hp(current_targeted_combatant, total_attack_dmg)

            if not is_targeting_mc:
                health_text = get_combatant_health_text(current_targeted_combatant, setup_aid)
                health_text = health_text[0].upper() + health_text[1:] if health_text is not None else None # capitalize the first letter

                if health_text is not None:
                    unique_attack_results.append(health_text + ".")

            attack_obj = {
                "number": y + 1,
                "combatant_rolls": [d20_roll],
                "info": roll_info_text,
                "adversaries_hp": get_combatants_health_history(combatant_opponents, current_story, is_opponent)
            }
            attack_objs.append(attack_obj)

            has_remaining_attacks = (y + 1) < how_many_attacks

            # If the combatant still has attacks remaining for this unique attack type, but they just defeated their target, create a clone of the unique attack and insert it right after the current attack (so a new target can be chosen)
            if (has_remaining_attacks and ((is_targeting_mc and current_story["hp"] == 0) or (not is_targeting_mc and current_targeted_combatant["hp"] == 0))):
                cloned_attack = attack.copy()
                cloned_attack["is_split"] = True

                cloned_attack["how_many"] = how_many_attacks - (y + 1)
                how_many_attacks = y + 1

                # insert cloned attack after current attack
                unique_attacks.insert(x + 1, cloned_attack)
                
                break

        weapon_text = weapon + (f"{' x' + str(how_many_attacks)}" if how_many_attacks > 1 else "")
        attack_info_target_identity = "You" if is_targeting_mc else target_identity

        roll_info_intro = f"{identity} ({weapon_text}) => {attack_info_target_identity}"

        unique_attack_obj = {
            "name": weapon,
            "info": roll_info_intro,
            "sound": get_sound_triple(damage_type, is_ranged, weapon) if damage_type is not None else [],
            "actions": attack_objs
        }
        unique_attack_objs.append(unique_attack_obj)
        base_roll_msg = setup_aid["base_attacked"]

        multiple_attacks_text = f" {how_many_attacks} times" if how_many_attacks > 1 else ""
        weapon_text = " with '" + weapon + "'" if weapon is not None else ""

        identity_prefix = "The " if not combatant.get("is_named_npc", False) else ""
        then_text = " then" if x > 0 else ""

        base_roll_msg = base_roll_msg.replace("#combatant_identity#", identity_prefix + identity + then_text) .replace("#target_identity#", target_identity)
        
        base_roll_msg += weapon_text + multiple_attacks_text

        # Get the result text for the attack, taking into account how many attacks there are and if they are all the same
        final_results_text = get_attack_results_texts(action_results, how_many_attacks, setup_aid)

        base_roll_msg += final_results_text
        base_roll_msg += f" {' '.join(unique_attack_results)}" if len(unique_attack_results) > 0 else ""

        roll_texts.append(base_roll_msg)

        x += 1

        # Stop whenever hp drops to 0 (Otherwise, might get confused as to who did the last attack)
        if current_story["hp"] == 0:
            break

    # Successfully attacked adversaries
    last_successfully_attacked_adversaries = []

    if nb_successful_attacks_non_mc > 0 and not is_targeting_mc and current_targeted_combatant is not None and current_targeted_combatant["hp"] > 0:
        last_successfully_attacked_adversaries = [current_targeted_combatant]

    character_obj = {
        "name": combatant["identifier"],
        "unique_actions": unique_attack_objs
    }

    if has_resistance_rage and total_dmg_vs_mc > 0:
        roll_texts.append(f"My rage reduced some of the received damages!")

    roll_text = " ".join(roll_texts)

    print_log(character_obj)
        
    # Don't show rolls when attacked by combatant
    return roll_text, character_obj, total_dmg, total_dmg_vs_mc, total_nb_of_attacks_vs_mc, has_been_hit, previously_used_deflect_arrow, last_successfully_attacked_adversaries

def get_char_info_for_saving_throw(saving_throw, current_story):
    # Saving throw
    char_relevant_stat_short = saving_throw[:3].lower()
    saving_throw = get_long_stat_name(char_relevant_stat_short)

    # Saving throw stats
    char_relevant_stat_mod = get_stat_mod(current_story, char_relevant_stat_short)

    # char proficiency
    has_proficiency = char_relevant_stat_short in current_story["saving_throws"]
    char_proficiency = get_proficiency_bonus(current_story['level']) if has_proficiency else 0
    char_proficiency_text = f" + {char_proficiency}(proficiency)" if has_proficiency else ""

    has_staff_of_power = has_talent("staff of power", current_story)
    staff_of_power_bonus = 0 if not has_staff_of_power else 2
    staff_of_power_text = f" + {staff_of_power_bonus}(staff of power)" if has_staff_of_power else ""

    has_cloak_of_protection = has_talent("cloak of protection", current_story)
    cloak_of_protection_bonus = 0 if not has_cloak_of_protection else 1
    cloak_of_protection_text = f" + {cloak_of_protection_bonus}(cloak of protection)" if has_cloak_of_protection else ""

    has_aura_of_protection = has_talent("aura of protection", current_story)
    aura_of_protection_bonus = 0 if not has_aura_of_protection else get_stat_mod(current_story, "cha")
    aura_of_protection_text = f" + {aura_of_protection_bonus}(aura of protection)" if has_aura_of_protection else ""
    
    has_shield_master = has_talent("shield master", current_story)
    shield_master_bonus = 0 if not has_shield_master else 3 # 2 shield + 1 bonus ac
    shield_master_text = f" + {shield_master_bonus}(shield master)" if has_shield_master else ""

    # Tides of chaos
    tides_of_chaos_bonus, tides_of_chaos_text = get_tides_of_chaos_bonus(current_story)

    total_bonus = staff_of_power_bonus + cloak_of_protection_bonus + aura_of_protection_bonus + tides_of_chaos_bonus + shield_master_bonus
    total_bonus_text = staff_of_power_text + cloak_of_protection_text + aura_of_protection_text + tides_of_chaos_text + shield_master_text

    return char_relevant_stat_mod, char_proficiency, char_proficiency_text, char_relevant_stat_short, saving_throw, total_bonus, total_bonus_text

def get_combatant_saving_throw_info(saving_throw, combatant, combatant_sheet):
    saving_throw_short = saving_throw[:3].lower()
    saving_throw = get_long_stat_name(saving_throw_short)

    ability_score = combatant_sheet[saving_throw_short]
    challenge_rating = combatant["cr"]
    target_relevant_stat_mod, target_cr_bonus = get_combatant_stats(ability_score, challenge_rating)

    proficiency_text = f" + {target_cr_bonus}(proficiency)" if target_cr_bonus != 0 else ""

    return target_relevant_stat_mod, target_cr_bonus, proficiency_text

def get_damage_info_save(dice_text, dice_roll_text, total, is_failed_save, damage_dice, saves_half, is_evading, has_shield_master, has_resistance, setup_aid, damage_postfix = "", resistance_reason = "", is_short_dmg_text = False, is_uncanny_dodge = False):
    roll_info_damage = ""
    roll_text_damage = ""

    # Damage:
    total_dmg = 0
    evasion_text = "Shield Master" if has_shield_master else "Evasion"

    if not is_failed_save and is_evading:
        roll_info_damage += f" ({evasion_text})"
        
    # Calc the damage, including half damage (half damage on failure when evasion, no damage at all on success)
        # not is_failed_save and saves_half and not is_evading = still takes half damage when not hit
    if (is_failed_save or (not is_failed_save and saves_half and not is_evading)) and damage_dice is not None:
        currently_saves_half = saves_half and (not is_failed_save or (is_evading and not has_shield_master)) # Evasion = half damage when hit, doesn't apply for shield master
        saves_half_reason = evasion_text if is_evading else ""

        roll_dmg, total_dmg = process_damage_total(dice_text, dice_roll_text, total, currently_saves_half, has_resistance, False, False, False, False, resistance_reason, saves_half_reason, is_short_dmg_text, is_uncanny_dodge, print_dmg_text=True)

        if total_dmg > 0:
            roll_info_damage += f"\n{roll_dmg}" if not is_short_dmg_text else f". {roll_dmg}"

    # Partial damage prompt
    if saves_half and not is_failed_save:
        roll_text_damage = setup_aid["partial_damage_after_success" + damage_postfix] if not is_evading else setup_aid["no_damage_evasion" + damage_postfix].replace("#evasion_text#", evasion_text)
    elif saves_half and is_failed_save and is_evading and not has_shield_master:
        roll_text_damage = setup_aid["partial_damage_after_fail" + damage_postfix]

    return total_dmg, roll_info_damage, roll_text_damage

def get_is_evading(saves_half, char_relevant_stat_short, current_story):
    has_evasion = has_talent("evasion", current_story)
    has_shield_master = has_talent("shield master", current_story)

    return saves_half and char_relevant_stat_short == "dex" and (has_evasion or has_shield_master), has_shield_master

def process_roll_saving_throw(roll_results: Roll_Saving_Throw_Object, current_story, setup_aid, opponent_sheets) -> Tuple[Any, Any, Any]:
    if roll_results is None:
        return None, None, None

    cause_of_save, saving_throw, saving_throw_DC, damage_dice, damage_type, saves_half = roll_results.extract()

    # Missing info
    if cause_of_save is None or saving_throw is None or saving_throw_DC is None:
        return None, None, None
    
    char_relevant_stat_mod, char_proficiency, char_proficiency_text, char_relevant_stat_short, saving_throw, total_bonus, total_bonus_text = get_char_info_for_saving_throw(saving_throw, current_story)

    # Advantage
    has_lucky_advantage, lucky_text = has_gotten_lucky(current_story)
    has_danger_sense_advantage = has_talent("danger sense", current_story) and char_relevant_stat_short == "dex"
    has_rage_str_advantage = current_story.get("is_raging", False) and char_relevant_stat_short == "str"

    has_advantage = has_lucky_advantage or has_danger_sense_advantage or has_rage_str_advantage
    which_advantage_text = lucky_text if has_lucky_advantage else ("danger sense" if has_danger_sense_advantage else ("rage" if has_rage_str_advantage else None))

    # Roll
    d20_roll, advantage_text = roll_d20(which_advantage_text, has_advantage, skip_advantage_rolls=True)

    final_roll_bonus = char_relevant_stat_mod + char_proficiency + total_bonus
    final_roll_result = d20_roll + final_roll_bonus

    # Action result 
    action_result, action_result_text = get_roll_action_result(d20_roll, final_roll_result, saving_throw_DC)
    text_color = "green" if "success" in action_result else "red"
    
    # roll info base
    roll_info_base = f"[{d20_roll}] + {final_roll_bonus} = #{text_color}#{final_roll_result}#{text_color}#" 
    roll_info_base_detailed = f"[{d20_roll}] + {char_relevant_stat_mod} ({saving_throw}){char_proficiency_text}{total_bonus_text} = {final_roll_result}"

    roll_info_intro_text = f"{char_relevant_stat_short.capitalize()} saving throw ({cause_of_save}):"
    roll_info_text = f"#base_save# vs DC {saving_throw_DC}" #: {action_result_text}"
    roll_info_text += advantage_text

    # Replace the base info with the detailed one for print, with total only for roll info text
    print_log(roll_info_text.replace("#base_save#", roll_info_base_detailed))
    roll_info_text = roll_info_text.replace("#base_save#", roll_info_base)

    # Whether the char uses evasion to evade all
    is_evading, has_shield_master = get_is_evading(saves_half, char_relevant_stat_short, current_story)
    is_failed_save = text_color == "red"

    has_resistance, _ = has_resistance_to_damage(damage_type, current_story)

    # Roll the dice and place the roll results in an array
    dice_text, dice_roll_text, total = get_rolls_damage(damage_dice, False)
    
    total_dmg, roll_info_damage, roll_text_damage = get_damage_info_save(dice_text, dice_roll_text, total, is_failed_save, damage_dice, saves_half, is_evading, has_shield_master, has_resistance, setup_aid, is_short_dmg_text=True)

    # Get action text, including incurred damage (empty string if no damage)
    incurred_damaged_text = get_incurred_damaged_text(total_dmg, current_story, setup_aid, "saving throw")
    saving_throw_action_text = setup_aid[action_result].replace("#injuries#", incurred_damaged_text + " " if incurred_damaged_text != "" else "")

    # roll_text
    base_spell_msg = setup_aid["base_saving_throw"].replace("#stat_name#", saving_throw).replace("#cause#", cause_of_save)
    roll_text = f"{base_spell_msg} {saving_throw_action_text}{' ' + roll_text_damage if roll_text_damage else ''}"

    # Update roll info with dmg
    roll_info_text += roll_info_damage # Empty when no damage

    # Update the ai hp
    update_ai_hp(current_story, total_dmg)

    section_obj = {
        "name": "Saving throw",
        "characters": [{
            "name": "environment",
            "unique_actions": [
                {
                    "name": cause_of_save,
                    "info": roll_info_intro_text,
                    "sound": get_sound_triple(damage_type, False, cause_of_save),
                    "actions": [
                        {
                            "number": 1,
                            "rolls": [d20_roll],
                            "info": roll_info_text,
                            "adversaries_hp": [current_story["hp"]] # Never allies for saving throws + counts as opponent turn
                        }
                    ] 
                }
            ]
        }]
    }
    
    return roll_text, section_obj, total_dmg

def get_roll_from_action(custom_action, response_content, convo_obj_filename, current_story, setup_aid, config_dnd) -> Tuple[Any, Any, Any]:
    #return response_content, convo_obj_filename, {"test": ""}
    if custom_action == "get_roll":
        return response_content, convo_obj_filename, get_roll(response_content, current_story, setup_aid)
    elif custom_action == "get_status_effects":
        return response_content, convo_obj_filename, get_status_effects(response_content)
    elif custom_action == "get_battle_info":
        return response_content, convo_obj_filename, get_battle_info(response_content, current_story, config_dnd)
    elif custom_action == "get_battle_info_additional_opponents":
        return response_content, convo_obj_filename, get_battle_info(response_content, current_story, config_dnd, True)
    elif custom_action == "get_allied_characters":
        return response_content, convo_obj_filename, get_allied_characters(response_content, current_story, config_dnd)
    elif custom_action == "get_updated_battle_info":
        return response_content, convo_obj_filename, get_updated_battle_info(response_content)
    elif custom_action == "get_roll_attack":
        return response_content, convo_obj_filename, get_roll_attack(response_content, current_story)
    elif custom_action == "get_roll_skill":
        return response_content, convo_obj_filename, get_roll_skill(response_content)
    elif custom_action == "get_roll_skill_special_ability":
        return response_content, convo_obj_filename, get_roll_skill_special_ability(response_content)
    elif custom_action == "cast_spell":
        return response_content, convo_obj_filename, cast_spell(response_content)
    elif custom_action == "use_item":
        return response_content, convo_obj_filename, use_item(response_content, current_story)
    elif custom_action == "get_roll_narrator_saving_throw":
        return response_content, convo_obj_filename, get_roll_narrator_saving_throw(response_content)
    elif custom_action == "get_roll_saving_throw":
        return response_content, convo_obj_filename, get_roll_saving_throw(response_content)
    elif custom_action == "item_is_within_reach":
        return response_content, convo_obj_filename, item_is_within_reach(response_content)
    elif custom_action == "create_combatant_sheet_stats":
        return response_content, convo_obj_filename, create_combatant_sheet_stats(response_content)
    elif custom_action == "create_combatant_sheet_attacks":
        return response_content, convo_obj_filename, create_combatant_sheet_attacks(response_content)
    elif custom_action == "create_combatant_sheet_spells":
        return response_content, convo_obj_filename, create_combatant_sheet_spells(response_content)
    elif custom_action == "choose_combatant_action":
        return response_content, convo_obj_filename, choose_combatant_action(response_content)
    elif custom_action == "get_answer_to_viewer_decisions":
        return response_content, convo_obj_filename, get_answer_to_viewer_decisions(response_content)
    
    return response_content, convo_obj_filename, None