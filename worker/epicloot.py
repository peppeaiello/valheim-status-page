"""
EpicLoot enchantments for the page: every effect that can roll on magic items,
with its official English name and description and where it can appear.

Effects come from the server's EpicLoot config (baseconfig/magiceffects.json);
texts come from the English translation embedded in EpicLoot.dll.
"""

import json
import os
import re

TYPE_NAMES = {
    "OneHandedWeapon": "one-handed weapons", "TwoHandedWeapon": "two-handed weapons",
    "TwoHandedWeaponLeft": "two-handed weapons", "Bow": "bows", "Bows": "bows", "Crossbows": "crossbows",
    "Staff": "staffs", "Torch": "torches", "Tool": "tools", "Helmet": "helmets", "Chest": "chest armor",
    "Legs": "leg armor", "Shoulder": "capes", "Shield": "shields", "Utility": "belts & rings", "Trinket": "trinkets",
}
# Effects without an item type list are limited by skill, by an item property, or to specific items:
# (text shown, equivalent item types for the filters)
SKILLS = {
    "Knives": ("knives", ["one-handed weapons"]), "Spears": ("spears", ["one-handed weapons"]),
    "Clubs": ("clubs", ["one-handed weapons", "two-handed weapons"]), "Axes": ("axes", ["one-handed weapons", "two-handed weapons"]),
    "Swords": ("swords", ["one-handed weapons", "two-handed weapons"]), "Polearms": ("polearms", ["two-handed weapons"]),
    "Unarmed": ("fist weapons", ["two-handed weapons"]), "Bows": ("bows", ["bows"]), "Crossbows": ("crossbows", ["crossbows"]),
    "Blocking": ("shields", ["shields"]), "Pickaxes": ("pickaxes", ["tools"]),
    "ElementalMagic": ("elemental magic staffs", ["staffs"]), "BloodMagic": ("blood magic staffs", ["staffs"]),
}
FLAGS = {
    "ItemHasChopDamage": ("weapons and tools that chop wood", ["one-handed weapons", "two-handed weapons", "tools"]),
    "ItemUsesEitrOnAttack": ("weapons that use eitr", ["staffs"]),
    "ItemUsesHealthOnAttack": ("weapons that use health", ["staffs"]),
    "ItemUsesDrawStaminaOnAttack": ("bows and crossbows (draw stamina)", ["bows", "crossbows"]),
}
ITEMS = {
    "$item_fishingrod": ("fishing rod", ["tools"]), "$item_demister": ("Wisplight", ["belts & rings"]),
    "$item_hammer": ("hammer", ["tools"]), "$item_hoe": ("hoe", ["tools"]),
}
RARITIES = ["Magic", "Rare", "Epic", "Legendary", "Mythic", "Ancient"]


def _english(dll_path):
    """The English translation block embedded in EpicLoot.dll."""
    b = open(dll_path, "rb").read()
    anchor = b.find(b'"mod_epicloot_me_modifydamage_display": "All Damage')
    if anchor < 0:
        return {}
    st = anchor
    while True:
        st = b.rfind(b"{", 0, st)
        if st < 0:
            return {}
        if b[st + 1:st + 40].lstrip().startswith(b'"') and not 32 <= b[st - 1] < 127:
            break
    end = b.find(b"\n}", anchor) + 2
    return json.loads(b[st:end].decode("utf-8"))


def _clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"\{0(:[^}]*)?\}", "X", s)
    s = re.sub(r"\{1(:[^}]*)?\}", "Y", s)
    return re.sub(r"\s+", " ", s).strip()


def _where(req):
    types = req.get("AllowedItemTypes") or []
    if types:
        names = sorted({TYPE_NAMES.get(t, t) for t in types})
        return names, names
    parts, filt = [], []
    for sk in req.get("AllowedSkillTypes") or []:
        if sk in SKILLS:
            parts.append(SKILLS[sk][0]); filt += SKILLS[sk][1]
    for it in req.get("AllowedItemNames") or []:
        if it in ITEMS:
            parts.append(ITEMS[it][0]); filt += ITEMS[it][1]
    if not parts:
        for flag, (txt, f) in FLAGS.items():
            if req.get(flag):
                parts.append(txt); filt += f
    return (parts, sorted(set(filt))) if parts else (["all equipment"], [])


def installed(server_dir):
    return os.path.exists(os.path.join(server_dir, "BepInEx", "plugins", "EpicLoot", "EpicLoot.dll"))


def build(server_dir):
    dll = os.path.join(server_dir, "BepInEx", "plugins", "EpicLoot", "EpicLoot.dll")
    effects_file = os.path.join(server_dir, "BepInEx", "config", "EpicLoot", "baseconfig", "magiceffects.json")
    if not (os.path.exists(dll) and os.path.exists(effects_file)):
        return None
    texts = _english(dll)
    effects = json.load(open(effects_file, encoding="utf-8"))["MagicItemEffects"]
    out = []
    for e in effects:
        req = e.get("Requirements") or {}
        if req.get("NoRoll"):
            continue
        where, filt = _where(req)
        rar = req.get("AllowedRarities") or []
        out.append({
            "name": _clean(texts.get(e["DisplayText"].lstrip("$"), e["Type"])),
            "desc": _clean(texts.get((e.get("Description") or "").lstrip("$"), "")),
            "where": where,
            "types": filt,
            "rarity": [r for r in RARITIES if r in rar] if rar and len(rar) < len(RARITIES) else [],
        })
    return sorted(out, key=lambda x: x["name"].lower())
