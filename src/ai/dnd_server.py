import tiktoken
import sys
import random as rd
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # Add the parent directory to sys.path

from utils.utils import read_json, format_msg_oai, send_open_ai_gpt_message, count_tokens, is_moderation_flagged, extract_json_from_response, remove_parentheses, read_csv, get_rolls, has_talent, validate_bool, extract_int, validate_unspecified, find_all_occurences_field_in_dict, print_log
import re
import pandas as pd
from collections import Counter
import copy

from typing import Tuple, Any

encoding_gpt3 = tiktoken.encoding_for_model("gpt-3.5-turbo")
no_gen = 0

ai_path = "ai/"
ai_config_path = f"{ai_path}_config/"

config_file_path = f"{ai_config_path}dnd_server_config.json"
setup_file_path = f"{ai_config_path}dnd_server_setup.json"
dnd_setup_file_path = f"{ai_config_path}dnd_setup.json"
history_file_path = f"{ai_path}current_story/messages_history_dnd.json"

spells_per_day_full = read_csv(f'{ai_path}spells/spells_per_day_full.csv', 'level')
spells_per_day_half = read_csv(f'{ai_path}spells/spells_per_day_half.csv', 'level')

# csv
monsters_nb_by_cr_easy = pd.read_csv(f'{ai_path}tables/monsters_nb_by_cr_easy.csv')
monsters_nb_by_cr_medium = pd.read_csv(f'{ai_path}tables/monsters_nb_by_cr_medium.csv')
monsters_nb_by_cr_hard = pd.read_csv(f'{ai_path}tables/monsters_nb_by_cr_hard.csv')
monsters_nb_by_cr_deadly = pd.read_csv(f'{ai_path}tables/monsters_nb_by_cr_deadly.csv')
monsters_info_by_cr = pd.read_csv(f'{ai_path}tables/monsters_info_by_cr.csv')
damage_dice_chart = pd.read_csv(f'{ai_path}tables/damage_dice_chart.csv')

def get_full_casters():
    return ['wizard', 'druid', 'cleric', 'sorcerer', 'bard']

def get_half_casters():
    return  ['paladin', 'ranger', 'artificer']

# Spells info
full_casters = get_full_casters()
half_casters = get_half_casters()

def stat_to_modifier(stat):
    return (stat - 10) // 2

def get_size_bonus(size):
    sizes = ["tiny", "small", "medium", "large", "huge", "gargantuan"]

    # get index position of size
    if size.lower() not in sizes:
        print_log(f"Size {size} not found in sizes.")
        return 0
    
    size_index = sizes.index(size.lower())

    return size_index - 2

# Get the hit points for a monster of a given CR
def get_monsters_hp(cr, sheet):
    rows = monsters_info_by_cr[monsters_info_by_cr['CR'] == cr]

    if len(rows) == 0:
        print_log(f"CR ({cr} not found in monsters_info_by_cr")
        return 1
    
    row = rows.iloc[0]

    # Recalibrate based on the average expected con bonus for that cr
        # This way, creatures with a higher con mod than the average can have more hp and vice versa
    avg_con_mod = float(row["avg_con_mod"])
    nb_hit_dice = int(row["nb_hit_dice"])
    avg_hp_diff = avg_con_mod * nb_hit_dice

    hp_values = str(row["hp_range"]).split("-")
    hp_value = hp_values[0]

    # Pick randomly between 2 nb
    if len(hp_values) >= 2:
        # Lower the avg by avg_hp_diff to be able to add the con bonus while keeping the same average. Remove 2 times the avg_hp_diff from the upper bound to get a narrower range of value while keeping the decreased average.
            # Calculation: Lower each bound by avg_hp_diff, then add avg_hp_diff from the lower bound and remove avg_hp_diff from the upper bound, resulting in a change of 0 for the lower bound and 2 * avg_hp_diff for the upper bound.
        value_1 = max(int(hp_values[0]), 1)
        value_2 = max(int(hp_values[1]) - (avg_hp_diff * 2), 1)

        # make sure value_1 is lower than value_2
        if value_1 > value_2:
            value_1, value_2 = value_2, value_1

        hp_value = rd.randint(int(value_1), int(value_2))

    # Get he bonus being applied to the hp
    con_ability = sheet["con"]
    con_mod = stat_to_modifier(con_ability)
    size_bonus = get_size_bonus(sheet.get("size", "medium"))
    hp_bonus = (con_mod + size_bonus) * nb_hit_dice

    # Calc random hp for cr + bonus, min hp = 1
    final_hp = int(max(hp_value + hp_bonus, 1))

    # Check if the final hp is within the min/max bounds of hp for that cr
    if len(hp_values) >= 2:
        min_value = max(int(hp_values[0]), 1)
        if final_hp < min_value:
            final_hp = min_value

        max_value = max(int(hp_values[1]), 1)
        if final_hp > max_value:
            final_hp = max_value

    return final_hp

def get_monsters_values(cr, col_name):
    if not isinstance(cr, str):
        print_log("Warning: CR is not a string.", True)
        cr = str(cr) # Convert to string, in case I didn't use the right type

    row = monsters_info_by_cr[monsters_info_by_cr['CR'] == cr]
    values = str(row.iloc[0][col_name]).split("-")
    return values

def get_monsters_single_value(cr, col_name):
    values = get_monsters_values(cr, col_name)

    if len(values) < 1:
        print(f"ERROR: Value for col {col_name} not found for CR {cr}.")
        return None

    return values[0]

def get_monsters_attribute_text(cr, col_name):
    values = get_monsters_values(cr, col_name)
    
    # Convert stat mod to attribute value
    if col_name == "main_stat_mod_range":
        values = [10 + int(value) * 2 for value in values]

    if len(values) == 1:
        return f"{values[0]}" #, False
    else:
        return f"between {values[0]} and {values[1]}" #, True

# Read damage_dice_chart csv, get a list of the closest dice to the avg
    # If there are multiple dice with the same avg, pick one randomly
def get_closest_dice_to_avg(avg):
    damage_dice_chart['difference'] = abs(damage_dice_chart['avg'] - avg)
    min_difference = damage_dice_chart['difference'].min()
    
    # Filter rows where the difference is the minimum found
    closest_dice = damage_dice_chart[damage_dice_chart['difference'] == min_difference]
    
    # If there are multiple dice with the same minimum difference, randomly pick one
    if len(closest_dice) > 1:
        closest_dice = closest_dice.sample(n=1)
    
    return closest_dice['damage_dice'].values[0]

def get_damage_roll_by_cr(cr, main_stat, nb_of_attacks):
    values = get_monsters_values(cr, "avg_damage")

    if len(values) < 1:
        print_log("CR not found in monsters_info_by_cr")
        return "1d4"
    
    avg = float(values[0])
    stat_mod = stat_to_modifier(main_stat)

    # increase or decrease target avg by up to 25%
    random_scale = rd.uniform(0.75, 1.25)
    modified_avg = avg * random_scale

    # Remove the stat mod from the equation
    modified_avg = max(1, modified_avg - stat_mod)
    
    # Divide by nb of multiattacks
    modified_avg = modified_avg / nb_of_attacks

    # Get the closest dice to the modified avg
    dice = get_closest_dice_to_avg(modified_avg)

    return dice

def get_monsters_file_by_difficulty(difficulty_level):
    if difficulty_level == "easy":
        return monsters_nb_by_cr_easy
    elif difficulty_level == "medium":
        return monsters_nb_by_cr_medium
    elif difficulty_level == "deadly":
        return monsters_nb_by_cr_deadly
    
    return monsters_nb_by_cr_hard # Default = hard

def get_combatants_cr(level, difficulty_level, max_combatants = None):
    data = get_monsters_file_by_difficulty(difficulty_level)
    level_data = data[data['level'] == level]

    # combatant cr obj
    cr_obj = {}

    # Format the values
    formatted_values = []
    cr_list = []
    cr_max_combatants = []

    for cr, value in level_data.iloc[0].items():
        # Skip empty values and the first row
        if not pd.notna(value) or cr == 'level':
            continue
        
        cr_list.append(cr)
        cr_values = str(value).split("-")

        if len(cr_values) > 0 and max_combatants is not None and float(cr_values[0]) >= max_combatants:
            cr_max_combatants.append(cr)
            cr_obj[cr] = max_combatants
            continue

        formatted_value = ""

        # Format the value
        if len(cr_values) == 1:
            formatted_value = f"{int(float(cr_values[0]))}"
            cr_obj[cr] = int(float(cr_values[0]))
        else:
            to_value = max_combatants if max_combatants is not None and float(cr_values[1]) > max_combatants else int(float(cr_values[1]))
            formatted_value = f"{int(float(cr_values[0]))} to {to_value}" # Remove the decimal part
            cr_obj[cr] = to_value

        formatted_values.append((formatted_value, cr))
        
    cr_texts = []

    # If reached the max limit of combatants, specify can be of a lower cr too
    if len(cr_max_combatants) > 0:
        cr_texts.append(f"{max_combatants} combatants of CR {cr_max_combatants[-1]} or below")

    # list comprehension containing f"{formatted_value} combatants of CR {cr}" for each formatted_value
    cr_texts += [f"{formatted_value} combatants of CR {cr}" for formatted_value, cr in formatted_values]

    combined_text = ", ".join(cr_texts)

    return combined_text, cr_obj

def lower_cr_by_one(cr):
    if cr == "1":
        return "1/2"
    elif cr == "1/2":
        return "1/4"
    elif cr == "1/4":
        return "1/8"
    elif cr == "1/8" or cr == "0": # Can't lower more than 0
        return "0"
    
    cr_int = get_cr_int(cr)
    if cr_int > 1:
        return str(cr_int - 1)
    
    return cr

def raise_cr_by_one(cr):
    if cr == "0":
        return "1/8"
    elif cr == "1/8":
        return "1/4"
    elif cr == "1/4":
        return "1/2"
    elif cr == "1/2":
        return "1"
    
    cr_int = get_cr_int(cr)
    if cr_int >= 1:
        return str(cr_int + 1)
    
    return cr

def get_cr_normalized_value(cr):
    if cr == "0":
        return 0
    elif cr == "1/8":
        return 1
    elif cr == "1/4":
        return 2
    elif cr == "1/2":
        return 3
    else:
        extracted_cr = extract_int(cr)
        if extracted_cr is not None:
            return extracted_cr + 3 
        
    print(f"ERROR: Invalid cr value {cr}")
    return 0

def get_cr_difference(cr1, cr2):
    normalized_cr1 = get_cr_normalized_value(cr1)
    normalized_cr2 = get_cr_normalized_value(cr2)

    return normalized_cr1 - normalized_cr2

def get_max_combatants_for_cr(cr, cr_obj):
    max_combatants_nb = cr_obj.get(cr, 0)

    # If 0, then either can't have any combatants of that cr if higher than max (empty cases on the right), or same number of combatants as first value if lower than min (empty cases on the right)
    if max_combatants_nb == 0:
        first_cr = list(cr_obj.keys())[0] # First non zero cr for the level
        diff = get_cr_difference(first_cr, cr)

        # If empty case in the table + on the left of first value, then same number of combatants as first value (ex : 20)
            # If empty case in the table + on the right of first value, then can't have any combatants of that cr (max_combatants_nb == 0)
        if diff > 0:
            max_combatants_nb = cr_obj.get(first_cr, 0)

    return max_combatants_nb

def get_normalized_nb_combatant(current_cr, cr_obj, cr_counter):

    max_combatant_for_current_cr = get_max_combatants_for_cr(current_cr, cr_obj) # If not in the object, then can't have any combatants of that cr

    # When the max_combatant_for_current_cr is 0, then can't have any combatants of that cr, no need to calculate the normalized value
    if max_combatant_for_current_cr == 0:
        return 0
    
    available_cr = list(cr_counter.keys())

    total_combatants = 0

    for cr_level in available_cr:
        max_combatant_for_other_cr = get_max_combatants_for_cr(cr_level, cr_obj)

        # If 0, then can't have any combatants of that cr
        if max_combatant_for_other_cr == 0:
            max_combatant_for_other_cr = 0.05 # Set to a small value to avoid division by 0, will cause the normalized nb of combatants to be very high

        # normalized_max_combatants_other_lvl = (max_nb_of_combatants_current_cr/max_nb_combatant_other_cr) * nb_combatant_other_cr

        normalized_nb_combatants_other_lvl = (max_combatant_for_current_cr/max_combatant_for_other_cr) * cr_counter[cr_level]
        total_combatants += normalized_nb_combatants_other_lvl

    return total_combatants

def increment_cr_counter(cr_counter, old_cr, new_cr):
    cr_counter[old_cr] = cr_counter.get(old_cr, 0) - 1
    if cr_counter[old_cr] == 0:
        del cr_counter[old_cr]

    cr_counter[new_cr] = cr_counter.get(new_cr, 0) + 1

def get_cr_int(cr_text):
    cr_int = extract_int(cr_text)

    if cr_int is None:
        cr_int = 0   
    
    return cr_int

# Return the max number of additional opponents, considering the diff level and the opponents already in battle
def get_max_cr_additional_opponents(char_lvl, difficulty_level, existing_opponents, max_additional_opponents):
    current_cr_counter = Counter([opponent.get("cr", "1") for opponent in existing_opponents if opponent.get("hp", 0) > 0]) 

    _, cr_obj = get_combatants_cr(char_lvl, difficulty_level)

    normalized_max_cr_obj = {}

    # Loop through each cr in cr_obj
    for cr in reversed(list(cr_obj.keys())):
        max_nb_opponent = get_max_combatants_for_cr(cr, cr_obj)
        normalized_nb_opponent = get_normalized_nb_combatant(cr, cr_obj, current_cr_counter)
        normalized_max_nb_opponent = max_nb_opponent - normalized_nb_opponent

        normalized_max_nb_opponent_int = int(normalized_max_nb_opponent) # Remove the decimal part

        normalized_max_cr_obj[cr] = normalized_max_nb_opponent_int if normalized_max_nb_opponent_int < max_additional_opponents else max_additional_opponents

        # Keep only the highest cr that has nb of opponents = max_additional_opponents
        if normalized_max_nb_opponent_int >= max_additional_opponents:
            break

    return normalized_max_cr_obj

def get_increased_difficulty_level(difficulty_level):
    if difficulty_level == "easy":
        return "medium"
    elif difficulty_level == "medium":
        return "hard"
    else:
        return "deadly"

def get_max_cr_current_level(current_story, how_many_opponents, max_opponents, game_difficulty_level):
    char_level = current_story.get("level", 1)
    increased_difficulty_level = get_increased_difficulty_level(game_difficulty_level) # increase by 1 level

    _, cr_obj = get_combatants_cr(char_level, increased_difficulty_level, max_opponents)

    # Get the highest cr that has nb of opponents >= how_many_opponents (so, the first valid one)
    max_cr = None
    for cr in reversed(list(cr_obj.keys())):
        if cr_obj[cr] >= how_many_opponents:
            max_cr = cr
            break

    return max_cr

# Raise or lower cr based on max lvl of opponents for that cr (max 1 in either direction for now)
def fix_group_cr_by_difficulty_level(groups, difficulty_level, current_story, current_cr_counter, skip_cr_increase, is_allied_characters):
    # Count number of opponents per cr, taking into account group["how_many"]
    cr_counter = Counter([group["cr"] for group in groups for x in range(group["how_many"])])

    # if current_cr_counter is not None, combine with cr_counter
    if current_cr_counter is not None:
        cr_counter = cr_counter + current_cr_counter

    char_lvl = current_story.get("level", 1)

    # Lower the level for allied characters (except for animal companions, ex: Zephyr, bards, which can inspire others)
    if is_allied_characters and not (has_talent("animal companion", current_story) or has_talent("bardic inspiration", current_story) or has_talent("blue blood", current_story)):
        char_lvl = int(char_lvl / 2) 

    _, cr_obj = get_combatants_cr(char_lvl, difficulty_level)

    # Lower the cr of groups that have too many opponents for their cr
        # Reverse order to lower the non named npcs first (usually towards the back of the list)
    for group in reversed(groups):
        max_opponent_for_current_cr = get_max_combatants_for_cr(group["cr"], cr_obj)
        nb_opponent_for_cr = get_normalized_nb_combatant(group["cr"], cr_obj, cr_counter)

        if max_opponent_for_current_cr == 0 or nb_opponent_for_cr > max_opponent_for_current_cr:
            print_log(f"WARNING: Too many opponents for {group['name']} (cr {group['cr']}), lowering cr by one", True)

            # Change the cr and update the count (-1 for initial cr, +1 for lowered cr lvl)
            lowered_cr = lower_cr_by_one(group["cr"])
            increment_cr_counter(cr_counter, group["cr"], lowered_cr)
            group["cr"] = lowered_cr

    # Skip the increase of cr for named NPCs (ex: don't increase for allied characters)
    if skip_cr_increase:
        return groups

    # get all the named npc groups
    named_npc_groups = [group for group in groups if group.get("is_named_npc", False)]

    # Raise the cr of named npc groups that can have their CR increased
    for group in named_npc_groups:
        # Get the next cr level, changing the counter obj to reflect this new potential state
        next_cr_level = raise_cr_by_one(group["cr"])
        cloned_cr_counter = copy.deepcopy(cr_counter)
        increment_cr_counter(cloned_cr_counter, group["cr"], next_cr_level)

        nb_opponents_next_cr_level = get_normalized_nb_combatant(next_cr_level, cr_obj, cloned_cr_counter)
        max_opponent_next_cr_level = get_max_combatants_for_cr(next_cr_level, cr_obj)

        if max_opponent_next_cr_level != 0 and nb_opponents_next_cr_level <= max_opponent_next_cr_level:
            print_log(f"WARNING: Potential to raise cr lvl while being within limit of max opponents for that {group['name']} (cr {group['cr']})", True)

            # Change the cr and update the count (-1 for initial cr, +1 for raised cr lvl)
            increment_cr_counter(cr_counter, group["cr"], next_cr_level)
            group["cr"] = next_cr_level

    return groups

def get_mc_health_status(hp, max_hp, is_healing = False):
    health_ratio = hp / max_hp

    suffix = "healing" if is_healing else "health"

    if health_ratio == 1:
        health_text = "maximum_" + suffix
    elif health_ratio >= 0.67:
        health_text = "good_" + suffix
    elif health_ratio >= 0.34:
        health_text = "medium_" + suffix
    else:
        health_text = "bad_" + suffix

    return health_text

def get_opponent_health_status(hp, max_hp, is_healing = False):
    health_ratio = hp / max_hp

    if health_ratio == 1:
        health_text = "perfect_health" if not is_healing else "perfect_health_healing"
    elif health_ratio >= 0.75:
        health_text = "great_health"
    elif health_ratio >= 0.50:
        health_text = "good_health"
    elif health_ratio >= 0.25:
        health_text = "medium_health"
    elif health_ratio > 0:
        health_text = "bad_health"
    else:
        health_text = "dead"

    health_text = "opponent_" + health_text

    return health_text

def use_hit_die(current_story) -> Tuple[Any, Any, Any]:
    current_hp = current_story["hp"]
    max_hp = current_story["max_hp"]
    remaining_hit_die = current_story["remaining_hit_die"]
    hit_die = current_story["hit_die"]
    con_mod = stat_to_modifier(current_story["stats"]["con"])

    total_healed = 0
    nb_rolls = 0

    rolls_text = []
    
    while current_hp < max_hp and remaining_hit_die > 0:
        dice_text, roll_text, total = get_rolls([(1, hit_die)], con_mod)

        total = total if total >= 1 else 1 # Min heal per hit die = 1
        
        # Update HP, ensuring not to exceed max HP
        current_hp = min(current_hp + total, max_hp)
        
        # Decrement the remaining hit dice
        remaining_hit_die -= 1
        total_healed += total
        
        # Check if it's possible to heal to full with a minimum roll
        hp_diff = max_hp - current_hp
        if current_hp < max_hp and hp_diff <= (1 + con_mod):
            roll_text += f" + {hp_diff} (Bonus)"
            total_healed += hp_diff
            current_hp = max_hp

        rolls_text.append(roll_text)
        
        nb_rolls += 1

    combined_rolls_text = " + ".join(rolls_text)

    dice_full_text = f"{dice_text} (rolled {nb_rolls} times)"
    rolls_full_text = f"({dice_full_text}) : {combined_rolls_text} = {total_healed} hp healed"

    return current_hp, remaining_hit_die, rolls_full_text

def get_roll_action_result_one_reversed(d20_roll, final_roll_result, roll_dc, has_imp_crit = False) -> Tuple[Any, Any]:
    action_result_reversed, _ = get_roll_action_result(d20_roll, final_roll_result, roll_dc, True, has_imp_crit=has_imp_crit) 
    _, action_result_text = get_roll_action_result(d20_roll, final_roll_result, roll_dc, has_imp_crit=has_imp_crit)
    return action_result_reversed, action_result_text

def get_roll_action_result(d20_roll, final_roll_result, roll_dc, is_reversed = False, has_imp_crit = False) -> Tuple[Any, Any]:
    is_crit_success = d20_roll == 20 or (has_imp_crit and d20_roll == 19)
    is_crit_failure = d20_roll == 1
    
    # Action result
    if (not is_reversed and is_crit_success) or (is_reversed and is_crit_failure):
        action_result = "critical_success"
    elif (not is_reversed and is_crit_failure) or (is_reversed and is_crit_success):
        action_result = "critical_failure"
    elif (not is_reversed and final_roll_result >= int(roll_dc)) or (is_reversed and final_roll_result < int(roll_dc)):
        action_result = "success"
    else:
        action_result = "failure"
    
    action_result_text = action_result.capitalize().replace("_", " ") # fix text format
    return action_result, action_result_text

def get_bardic_inspiration_dice(current_story):
    bardic_inspiration_dice = 6
    if current_story["level"] >= 5:
        bardic_inspiration_dice = 8
    if current_story["level"] >= 10:
        bardic_inspiration_dice = 10
    if current_story["level"] >= 15:
        bardic_inspiration_dice = 12

    return bardic_inspiration_dice

def get_incapacitated_status(is_first_enemy_turn = False):
    incapacitated_status = ["incapacitated", "stunned", "unconscious"]

    if is_first_enemy_turn:
        incapacitated_status += ["surprised", "disoriented", "unaware"]

    return incapacitated_status

# Opponents are surprised if it's the first enemy turn and either all of them are incapacitated, or the enemy was already considered surrpised.
def are_opponents_surprised(battle_info):
    if battle_info is None:
        return False

    opponents_are_incapacitated = len([opponent for opponent in battle_info["opponents"] if opponent["status_effects"] not in get_incapacitated_status(True)]) == 0

    return battle_info["enemy_turn"] == 0 and (battle_info.get("enemy_is_surprised", False) or opponents_are_incapacitated)

def get_incapacitated_combatants(battle_info, is_opponent, surprised_combatants_are_incapacitated = False) -> Tuple[Any, Any]:
    if battle_info is None:
        print("ERROR: battle_info is None. Can't call get_incapacitated_combatants.")
        return [], []
    
    combatants = battle_info["opponents"] if is_opponent else battle_info["allies"]
    
    # if any combatants has an hp of None, return an empty list
    if any(combatant["hp"] is None for combatant in combatants):
        print("\nERROR: One or more combatants have an hp of None (Most likely haven't been updated after sheet creation)\n")
        return [], []

    # combatants still in battle
    combatants = [combatant for combatant in combatants if combatant["hp"] > 0]
    combatants_are_surprised = are_opponents_surprised(battle_info) and surprised_combatants_are_incapacitated if is_opponent else False

    if combatants_are_surprised:
        incapacitated_combatants = combatants
        active_combatants = []
    else:
        incapacitated_status = get_incapacitated_status()

        incapacitated_combatants = [combatant for combatant in combatants if combatant["status_effects"] is not None and combatant["status_effects"] in incapacitated_status]
        active_combatants = [combatant for combatant in combatants if combatant not in incapacitated_combatants]

    return active_combatants, incapacitated_combatants

def has_any_given_classes(current_story, class_names):
    char_classes = get_char_classes(current_story)
    
    for class_name in class_names:
        if class_name in char_classes:
            return True
        
    return False

# Check if can start frenzying, or stop frenzying
def update_frenzy_status(current_story, fight_started = False, fight_stopped = False) -> Tuple[Any, Any]:
    can_frenzy = has_talent("frenzy", current_story)
    frenzy_msg = frenzy_text = None
    char_name = current_story.get("char_name", False)

    # Can't frenzy again until short or long rest if already frenzied
    if can_frenzy and fight_started and not current_story.get("frenzy_used", False) and not current_story.get("is_frenzied", False):
        char_proficiency = get_proficiency_bonus(current_story['level']) if "wis" in current_story["saving_throws"] else 0
        stat_mod = get_stat_mod(current_story, "wis")
        frenzy_resisted_counter = current_story.get("frenzy_resisted_counter", 0)

        d20_roll = rd.randint(1, 20)
        final_roll_result = d20_roll + char_proficiency + stat_mod
        roll_dc = 8 + frenzy_resisted_counter
        
         # Action result 
        action_result, action_result_text = get_roll_action_result(d20_roll, final_roll_result, roll_dc)
        text_color = "green" if "success" in action_result else "red"

        frenzy_msg = f"Saving throw (Frostblade's influence): {d20_roll} + {stat_mod + char_proficiency} = {final_roll_result} vs DC {roll_dc}. Result: #{text_color}#{action_result_text}#{text_color}#."

        if "success" in action_result:
            current_story["frenzy_resisted_counter"] = frenzy_resisted_counter + 1
            frenzy_msg += "\nYou resisted the frostblade's influence."
            frenzy_text = f"{char_name} resisted the frostblade's influence."
        else:
            current_story["frenzy_resisted_counter"] = 0   
            current_story["is_frenzied"] = True
            frenzy_msg += "\nYou failed to resist the frostblade's influence. You went into a frenzy!"
            frenzy_text = f"{char_name} failed to resist the frostblade's influence, she went into a frenzy!"

    elif can_frenzy and fight_stopped and current_story.get("is_frenzied", False):
        current_story["is_frenzied"] = False
        current_story["frenzy_used"] = True
        frenzy_msg = "Your frenzied rage has stopped. You feel exhausted."
        frenzy_text = f"{char_name} stopped her frenzied rage and now feel exhausted."

    return frenzy_msg, frenzy_text

def get_daily_sorcery_points(current_story):
    sorcery_points = current_story["level"]
    if has_talent("metamagic adept", current_story):
        sorcery_points += 3 # +1 over RAW because I didn't add extra metamagic options

    return sorcery_points

def get_daily_ki_points(current_story):
    ki_points = current_story["level"]
    if has_talent("ki adept", current_story):
        ki_points += 2 

    return ki_points

# Recover 1 spell from every level 1 to 8 inclusively, but only if the nb of spell per day for that level > 0
def recover_spell_slots_by_1_level(spell_slots, spells_per_day):
    return [min(count + 1, spells_per_day[i - 1]) if 1 <= i <= 8 and spells_per_day[i - 1] > 0 else count for i, count in enumerate(spell_slots, 1)]

# Recover a a max number of spell slots = wizard level, minimum being wizard level / 2, starting from level 8 to 1
def recover_spell_slots_arcane_recovery(spell_slots, spells_per_day, wizard_level) -> Tuple[Any, Any]:
    total_value_recovered = 0 
    recovered_slots_per_level = [0] * 8 

    # Level 8 to 1
    for level in range(8, 0, -1):
        # Loop while there's still slots that can be recoved at this level
        while total_value_recovered + level <= wizard_level and spell_slots[level - 1] < spells_per_day[level - 1]:
            spell_slots[level - 1] += 1  # Recover one slot
            recovered_slots_per_level[level - 1] += 1  # Record the recovery
            total_value_recovered += level  # Update the total value of recovered slots

            # Break out of the loop if adding another slot of this level would exceed the wizard's level
            if total_value_recovered + level > wizard_level:
                break

    # Check if we managed to recover enough slots
    if total_value_recovered < wizard_level // 2:
        return None, None
    
    # Loop through the recovered spell slots and write a text for each level
    recovery_phrases = []
    for level, count in enumerate(recovered_slots_per_level[::-1], 1):
        if count > 0:  #
            recovery_phrases.append(f"{count} level {9 - level}")

    recovery_text = "Recovered the following spell slots using arcane recovery: " + ", ".join(recovery_phrases) + "."
    return spell_slots, recovery_text 

# Add +1 to every spell from 1 to 8 inclusively, but only if the nb of spell for that level > 0
def increase_spells_per_day_by_1_level(spell_slots):
    return [count + 1 if 1 <= i <= 8 and count > 0 else count for i, count in enumerate(spell_slots, 1)]

def extract_autocast_lvl(text):
    pattern = r"autocast lvl (\d+)"
    match = re.search(pattern, text)

    if match:
        number = match.group(1)
        return int(number)
    else:
        return 0

def get_autocast_levels(talents):
    autocast_levels = []
    for talent in talents:
        level = extract_autocast_lvl(talent)
        if level != 0:
            autocast_levels.append(level)
    return autocast_levels

def get_char_classes(current_story):
    return [remove_parentheses(class_name) for class_name in current_story["class"].lower().split("/")]

def spells_per_day(char_classes, char_level, talents):
    is_full_caster = any(char_class in full_casters for char_class in char_classes)

    # multiclass malus
    char_level = char_level if len(char_classes) == 1 else char_level - 1

    spells_per_day_levels = spells_per_day_full if is_full_caster else spells_per_day_half
    
    # Limit the char level between 1 an 20
    char_level = char_level if char_level <= 20 else 20
    char_level = char_level if char_level >= 1 else 1

    spells_per_day_level = spells_per_day_levels[f"{char_level}"] # Spells per day for the char level
    spells_per_day_1_to_9 = [int(spells_per_day_level[str(i)]) for i in range(1, len(spells_per_day_level))] # An array of 9 elements, one for each spell level

    autocast_levels = get_autocast_levels(talents)

    # Remove 1 spell slot for each autocast level (min 0)
    for level in autocast_levels:
        if level > 0 and level <= len(spells_per_day_1_to_9) - 1 and spells_per_day_1_to_9[level - 1] > 0:
            spells_per_day_1_to_9[level - 1] -= 1
            
    return spells_per_day_1_to_9

def get_max_spell_level(current_story):
    spells_per_day = current_story.get("spells_per_day")
    if spells_per_day is None:
        print("ERROR: Spells per day is None, can't get max spell level. Returning 0.")
        return 0

    # Keep going until we find a level with 0 spells per day (then, the max spell level is the previous one (i + 1 - 1 = spell lvl))
        # Important : Return i not i + 1 (since the index of the first spell level with 0 spells per day = max spell level)
    for i in range(len(spells_per_day)):
        if spells_per_day[i] == 0:
            return i
    return 9

def get_opponent_max_spell_level(cl):
    if cl is None:
        print("ERROR: CL is None, can't get max spell level. Returning 0.")
        return 0

    return min(9, (cl + 1) // 2)

def find_lowest_no_upcast_slot(spell_slots):
    for i in range(len(spell_slots)):
        if spell_slots[i] == 0:
            no_higher_slots = True
            for j in range(i + 1, len(spell_slots)):
                if spell_slots[j] > 0:
                    no_higher_slots = False
                    break
            if no_higher_slots:
                return i + 1
    return None

def remove_system_prefix(text):
    pattern = r"\*?(system:|System:)\*?\s?"

    # Replace the pattern with an empty string
    new_text = re.sub(pattern, '', text)

    return new_text.strip()

def get_current_message_text_dnd():
    messages_history = read_json(history_file_path)
    return remove_system_prefix(messages_history[-1]["content"])

def get_stat_mod(current_story, relevant_stat_short):
    relevant_stat_val = current_story["stats"].get(relevant_stat_short)
    return stat_to_modifier(relevant_stat_val) if relevant_stat_val is not None else 0

def extract_cr(text):
    if validate_unspecified(text) is None:
        return None
    
    if isinstance(text, int):
        return str(text)
    
    if isinstance(text, float):
        if text >= 1 or text == 0:
            return str(int(text))
        
        denominator = 1 / text
        # return the cr in fraction corresponding to the float
        return f"1/{int(denominator)}"
    
    # This pattern matches integers as well as fractions 
    matches = re.findall(r'\d+/\d+|\d+', text)

    if len(matches) == 0:
        return None

    return matches[0]

def get_proficiency_bonus(level_arg):
    level = level_arg if level_arg <= 30 else 30

    # Level 0 = prof 1
    if level <= 0:
        return 1
    
    return (level - 1) // 4 + 2

def get_long_stat_name(short_stat):
    stats = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
    stat_mapping = {stat[:3]: stat for stat in stats}
    return stat_mapping.get(short_stat[:3].lower())

def alignment_to_words(abbreviation):
    alignment_dict = {
        "LG": "Lawful Good",
        "NG": "Neutral Good",
        "CG": "Chaotic Good",
        "LN": "Lawful Neutral",
        "TN": "True Neutral",
        "CN": "Chaotic Neutral",
        "LE": "Lawful Evil",
        "NE": "Neutral Evil",
        "CE": "Chaotic Evil"
    }
    
    return alignment_dict.get(abbreviation.upper(), "Unknown Alignment")

# Inverts the roles of 'user' and 'assistant' in the message history.
def get_dnd_message_history():
    messages_history = read_json(history_file_path)

    for message in messages_history:
        if message['role'] == 'user':
            message['role'] = 'assistant'
        elif message['role'] == 'assistant':
            message['role'] = 'user'

    return messages_history

def get_roll_result_text(roll_info, is_assistant_roll, roll_action):
    roll_result_text = roll_info[1].lower()
    is_critical = "critical failure" in roll_result_text or "critical success" in roll_result_text

    # The main character doing a saving throw counts as them doing the roll, even if it's during narrator turn (narrator_roll)
    mc_is_doing_the_roll = is_assistant_roll or roll_action == "saving_throw_required"

    # Use the color to take into account the switch for saving throw (a failed enemy saving throw is a success for the player, and vice versa)
    is_success = (roll_result_text.startswith("#green#") and mc_is_doing_the_roll) or (roll_result_text.startswith("#red#") and not mc_is_doing_the_roll)

    if not is_success and is_critical:
        return "critical failure"
    elif is_success and is_critical:
        return "critical success"
    elif not is_success:
        return "failure"
    elif is_success:
        return "success"
    else:
        # No roll result (ex: magic at environment)
        return None

def send_text_command_dnd(new_user_messages, current_session, nb_retry = 0) -> Tuple[str, bool, bool]: #, is_narrator_msg = False):
    global no_gen

     # CURRENT SESSION VARIABLES
    is_game_lost = current_session.get("is_game_lost", False)
    is_narrator_response = current_session.get("is_narrator_response", False)
    roll_text, sections, roll_action = current_session.get("roll")
    battle_info_text = current_session.get("battle_info_text")

    current_story = current_session.get("current_story")
    current_turn = current_story.get("current_turn")
    genre = current_story.get("genre", "fantasy")
    
    battle_info = current_story.get("battle_info")
    opponents = battle_info.get("opponents", []) if battle_info is not None else []
    allies = battle_info.get("allies", []) if battle_info is not None else []

    nb_opponents = len(opponents)
    is_in_battle = nb_opponents > 0
    
    # Can only start a battle if not currently in battle and not currently in the opponents turn (don't even use that value in that case atm)
    allow_battle_start = not is_in_battle and not is_narrator_response
    
    prompt_intro_name = ""

    if type(new_user_messages) is str:
        print_log("The new user message is a string, converting to array")
        new_user_messages = [new_user_messages]

    config = read_json(config_file_path)
    setup = read_json(setup_file_path)
    system_msg = setup["system_msg"].replace("#genre#", genre)

    # Prompt intro
    if not is_narrator_response and roll_text is None:
        prompt_intro_name = "prompt_intro_assistant"
    elif not is_narrator_response and roll_text is not None:
        prompt_intro_name = "prompt_intro_assistant_roll"
    else:
        prompt_intro_name = "prompt_intro_narrator_roll"

    is_assistant_roll = prompt_intro_name == "prompt_intro_assistant_roll"
    is_narrator_roll = prompt_intro_name == "prompt_intro_narrator_roll"

    prompt = setup[prompt_intro_name]

    # Don't describe the opponent's previous actions if it's the assistant's roll (those were already described in their own turn)
    if is_assistant_roll and battle_info is not None:
        prompt += setup["dont_describe_opponents_actions"]

    # Specific to normal prompt or game over prompt
    prompt += " " + (setup["prompt"] if not is_game_lost else setup["prompt_game_lost"])

    #current_session = read_json(current_session_file_path)
    messages_history = get_dnd_message_history()
    
    messages = []
    # system msg at the start
    messages.insert(0, format_msg_oai("system", system_msg))

    # Memory right after system message, at the top
        # Don't add the memory if it's already fully contained at the top of the history.
    if current_session["memory"] != "" and (len(messages_history) == 0 or current_session["memory"] not in messages_history[0]["content"]):
        messages.append(format_msg_oai("assistant", "system: " + current_session["memory"]))

    # Get the author note additions
    author_note_msg = None 
    if current_session["author_note_additions"] != "":
        author_note_msg = format_msg_oai("assistant", "[" + current_session["author_note_additions"] + "]")

    # Insert the message history right after the memory
    start_msg_index = len(messages)

    # Replace the placeholder for the opponents in the prompt's intro
    opponent_word = only_their_opponents_text = ""
    if is_in_battle:
        opponent_word = " opponent"
        opponent_word += "s" if nb_opponents > 1 else ""
        only_their_opponents_text = setup["only_their_opponents_text"]
        
    prompt = prompt.replace("#opponent_word#", opponent_word).replace("#only_their_opponents_text#", only_their_opponents_text)

    no_additional_opponents_text = ""

    # Specify not to add additional opponents when currently in battle, unless absolutely necessary
    if battle_info is not None:
        no_additional_opponents_text = setup["no_additional_opponents_text"]
    
    prompt = prompt.replace("#no_additional_opponents_text#", no_additional_opponents_text)

    # Whether the roll word is plural in the prompt
    if sections is None or len(sections) == 0:
        total_nb_rolls = 0
    else:
        # Concatenate all rolls in sections
        all_rolls = [find_all_occurences_field_in_dict(section, field_name) for section in sections for field_name in ["rolls", "combatant_rolls"]]

        total_nb_rolls = len(all_rolls)
        
    roll_word_with_plural = "rolls" if total_nb_rolls > 1 else "roll"

    # Add or remove the json for the intend to start battle (only when not already in battle)
    battle_text = setup["intend_to_start_battle_text"] if allow_battle_start else setup["dont_intend_to_start_battle_text"]
    battle_json = setup["intend_to_start_battle_json"] if allow_battle_start else setup["introduce_additional_opponents_json"]
    prompt = prompt.replace("#battle_text#", battle_text).replace("#battle_json#", battle_json)

    # Specify that the previous roll determined the result of the action (only if there is one)
    previous_roll_determine_text = ""
    if roll_text is not None and (is_assistant_roll or is_narrator_roll):
        during_battle_text = setup["during_battle_text"] if is_in_battle else setup["not_during_battle_text"]
        player_or_opponent_action = setup["player_action"] if is_assistant_roll else setup["opponent_action"]
        player_or_opponent_action += "s" if total_nb_rolls > 1 else ""

        previous_roll_determine_text = setup["previous_roll_determine_result_text"].replace("#during_battle_text#", during_battle_text).replace("#player_or_opponent_action#", player_or_opponent_action)
    
    prompt = prompt.replace("#previous_roll_determine_result_text#", previous_roll_determine_text)
    
    # Replace with correct roll word from anywhere in the main prompt (even repetition text)
    prompt = prompt.replace("#roll_word#", roll_word_with_plural)

    # Add the new messages
    for x, new_user_msg in enumerate(new_user_messages):
        # First message is always user, the next one is assistant (if there is one, only happens after narrator roll)
        msg_type = "user" if x == 0 else "assistant"
        messages.append(format_msg_oai(msg_type, new_user_msg)) # user msg and prompt are sepparated

    # Note : The roll text is added to the prompt, so it's not needed here
        # Also, can sometimes be very long now, so it's better to keep it in the prompt
    if roll_text is not None and (is_assistant_roll or is_narrator_roll):
        roll_description = setup["previous_roll_description"].replace("#roll_word#", roll_word_with_plural)

        if is_assistant_roll:
            roll_source = setup["previous_roll_assistant"]
            if not is_narrator_response and len(allies) > 0:
                roll_source += " " + setup["previous_roll_assistant_allies"]
        elif is_in_battle:
            opponent_word_with_plural = "opponents" if nb_opponents > 1 else "opponent"
            roll_source = setup["previous_roll_narrator_battle"].replace("#opponent_word#", opponent_word_with_plural)
        else:
            roll_source = setup["previous_roll_narrator"]

        roll_description = roll_description.replace("#roll_source#", roll_source)

        messages.append(format_msg_oai("user", f"{roll_description}: {roll_text} {battle_info_text}"))
    elif battle_info_text:
        messages.append(format_msg_oai("user", battle_info_text))

    messages.append(format_msg_oai("user", prompt))

    author_note_tokens = 0

    max_dnd_response_length = config["max_dnd_response_length"]
    total_length = count_tokens(messages) + author_note_tokens + max_dnd_response_length # Total current length of messages + max possible length of the response
    
    remaining_messages_history = messages_history[:] # Copy the array so we can remove a message one by one

    while len(remaining_messages_history) > 0:
        last_msg = remaining_messages_history.pop()

        # Never send messages to oai if the role is not user, system or assistant
        if last_msg["role"] != "system" and last_msg["role"] != "user" and last_msg["role"] != "assistant":
            continue

        new_total_length = total_length + count_tokens([last_msg])
        
        if new_total_length >= config["max_dnd_messages_length"]:
            break
        else:
            messages.insert(start_msg_index, last_msg) # Always insert right after the system (since we start by the last msg and work our way backwards)
            total_length = new_total_length

    # Insert the author notes 3 messages before the end, unless there are not enough messages, then insert it at the start
    if author_note_msg is not None:
        # Note : Don't lower it too much, caused issues in the past with the wrong number of enemies being detected as being defeated (this message probably confuses the ai if too clause the end of the messages)
        author_note_insert_idx = len(messages) - 12 

        # Find the last assistant message
        while author_note_insert_idx >= start_msg_index and messages[author_note_insert_idx]["role"] != "user":
            author_note_insert_idx -= 1

        if author_note_insert_idx < start_msg_index:
            author_note_insert_idx = start_msg_index
        
        messages.insert(author_note_insert_idx, author_note_msg)

    is_json_mode = not is_game_lost

    response_message = send_open_ai_gpt_message(max_dnd_response_length, messages, config["dnd_model"], config["dnd_backup_model"], config["oai_call_timeout"], no_gen, config["temperature"], config["top_p"], config["presence_penalty"], config["frequency_penalty"], True, json_mode=is_json_mode, current_turn=current_turn)
    
    start_battle_narrator = False
    add_additional_opponents_narrator = False

    if not is_game_lost:
        response_content_obj = extract_json_from_response("Server response", response_message['content'])
        print_log(f"Dnd Server original response: {response_content_obj}")

        # Field will be missing when already in battle
        start_battle_narrator = validate_bool(response_content_obj.get("attempt_to_start_battle", False)) 
        add_additional_opponents_narrator = validate_bool(response_content_obj.get("additional_opponents_were_introduced", False))

        response_message['content'] = response_content_obj['response_text'].strip("\n ") # Remove all newlines and spaces at the start and end of the messages
    else:
        print_log(f"Dnd Server original response: {response_message['content']}")
        
    is_flagged = is_moderation_flagged([response_message['content']], "system", "dnd_server", True)
    if is_flagged:
        print("Message flagged for moderation")

        if nb_retry < 3:
            response_message['content'], start_battle_narrator, add_additional_opponents_narrator = send_text_command_dnd(new_user_messages, current_session, nb_retry + 1)
        else:
            raise Exception(f"ERROR: Moderation thrown {nb_retry} times in a row, aborting.")

    response_message['content'] = "system: " + remove_parentheses(remove_system_prefix(response_message['content'])) # Make sure there is always only one system prefix

    # Remove the extra text remaining after the punctuation
    response_message["content"] = response_message['content'].strip("\n ")

    no_gen += 1

    return response_message["content"], start_battle_narrator, add_additional_opponents_narrator