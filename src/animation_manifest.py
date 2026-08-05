"""Authoritative runtime animation inventory for the fluid-animation floor.

Every entry describes one independently selectable multi-pose strip.  The
phase names are part of the contract: they document why each drawing exists
and keep generated strips from being padded with anonymous duplicate cells.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


# The library contains the purposeful source drawings themselves.  A previous
# pass inserted a synthetic deformation between every pair of keys and then
# advanced those cels at 60 Hz.  A 30 FPS capture necessarily discarded every
# other cel, while the generated deformation sat much closer to the upcoming
# key than the current one and produced a visible large/small motion sawtooth.
# Keeping only the authored keys makes every selectable pose intentional and
# lets the presentation clock hold them at a capture-safe cadence.
BASE_POSES_PER_CLIP = 8
BASE_EXTENDED_HERO_POSES = 12
BASE_EXPANDED_PARTY_IDLE_POSES = 16
SHELLY_PERSONALITY_POSES = 16
# Combat simulation remains fixed at 60 Hz.  Sprite selection deliberately
# quantizes time to 30 Hz so a 30 FPS recording and a 60 FPS display observe
# the same ordered pose stream instead of two different halves of it.
ANIMATION_PLAYBACK_HZ = 30.0
POSES_PER_CLIP = BASE_POSES_PER_CLIP
EXTENDED_HERO_POSES = BASE_EXTENDED_HERO_POSES
EXPANDED_LOCOMOTION_POSES = BASE_EXTENDED_HERO_POSES
EXPANDED_PARTY_IDLE_POSES = BASE_EXPANDED_PARTY_IDLE_POSES


@dataclass(frozen=True, slots=True)
class AnimationClip:
    actor: str
    state: str
    atlas: str
    row: int
    cell_width: int
    cell_height: int
    loop: bool
    hold: int
    phases: tuple[str, ...]

    @property
    def frame_count(self) -> int:
        return len(self.phases)


BASE_PHASES = {
    "idle": ("settle", "inhale", "rise", "weight_left", "exhale", "weight_right", "release", "ready"),
    "move": ("plant_left", "compress", "pass", "drive_right", "plant_right", "compress_return", "pass_return", "drive_left"),
    "attack": ("guard", "anticipate", "windup", "launch", "contact", "follow_through", "recoil", "recover"),
    "ranged": ("ready", "draw", "aim", "fire", "muzzle_recoil", "lower", "reholster", "guard"),
    "dodge": ("ready", "dip", "push_off", "low_travel", "deep_travel", "brake", "rise", "ready_return"),
    "hurt": ("braced", "contact", "recoil", "stagger", "deep_stagger", "catch", "recover", "guard"),
    "down": ("hit", "buckle", "fall_start", "fall_mid", "impact", "settle", "prone", "still"),
    "power": ("ready", "gather", "raise", "charge", "release", "peak", "aftershock", "recover"),
    "air": ("crouch", "launch", "rise", "air_ready", "strike", "descent", "land", "recover"),
    "jump": ("crouch", "launch", "rise", "apex", "fall", "brace", "land", "recover"),
    "pet": ("notice", "turn", "reach", "contact", "scratch", "praise", "withdraw", "ready"),
    "refill": ("inspect", "raise_can", "align_valve", "connect", "press_fill", "release", "remove_can", "ready"),
    "pants": ("notice", "reach_back", "grip_waist", "pull_start", "pull_high", "settle_band", "release", "ready"),
    "spawn": ("grounded", "brace", "kneel", "rise_low", "rise", "square_up", "guard", "ready"),
    "sit": ("stand", "lower", "haunches", "sit", "look_left", "look_right", "settle", "alert"),
    "command": ("listen", "locate", "coil", "launch", "sprint", "acquire", "brake", "ready"),
    "maul": (
        "approach_crouch",
        "paws_brace",
        "lunge",
        "bite_contact",
        "shake_left",
        "shake_right",
        "release",
        "alert_finish",
    ),
    "guard": ("square_up", "scan_left", "listen", "scan_right", "step_forward", "hold_ground", "check_party", "ready"),
    "laugh": ("smirk", "inhale", "grin", "laugh_open", "belly_laugh", "point", "chuckle", "ready"),
    "victory": ("approach", "embrace", "hug", "release", "treat_toss", "chief_catch", "celebrate", "hero_pose"),
    "support": ("walker_set", "lean_left", "brace", "check_road", "lean_right", "steady", "listen", "settle"),
    "talk": ("notice", "draw_breath", "mutter", "speak_low", "open_hand", "emphasize", "finish_line", "listen"),
    "point": ("notice", "free_hand", "raise_elbow", "extend_arm", "point_road", "hold_direction", "withdraw", "regrip_walker"),
    "ride": ("roll_in", "left_crank", "chief_trot", "shelly_step", "right_crank", "coast", "group_wave", "ride_horizon"),
    "hero_idle": (
        "settled",
        "inhale_start",
        "inhale_shoulders",
        "inhale_peak",
        "chest_full",
        "exhale_start",
        "exhale_shoulders",
        "weight_settle",
        "breath_low",
        "micro_shift",
        "return_center",
        "ready",
    ),
    "hero_stride": (
        "left_heel_strike",
        "left_weight_accept",
        "left_mid_stance",
        "right_leg_passing",
        "left_heel_rise",
        "left_toe_off",
        "right_heel_strike",
        "right_weight_accept",
        "right_mid_stance",
        "left_leg_passing",
        "right_heel_rise",
        "right_toe_off",
    ),
    "shelly_refill": (
        "inspect_torch",
        "retrieve_canister",
        "raise_canister",
        "rotate_torch",
        "align_bottom_valve",
        "connect_bottom_valve",
        "press_fill",
        "hold_fill",
        "release_pressure",
        "detach_canister",
        "stow_canister",
        "ready",
    ),
    "shelly_pants": (
        "notice_waistband",
        "glance_back",
        "reach_back",
        "grip_waist",
        "brace",
        "pull_start",
        "pull_high",
        "adjust_left",
        "adjust_right",
        "settle_band",
        "release",
        "ready",
    ),
    "chief_idle": (
        "settled",
        "inhale",
        "ears_forward",
        "sniff_low",
        "sniff_high",
        "look_left",
        "return_center",
        "exhale",
        "tail_left",
        "tail_center",
        "tail_right",
        "ready",
    ),
    "chief_stride": (
        "left_fore_reach",
        "left_fore_contact",
        "weight_accept",
        "hind_drive",
        "flight_extend",
        "right_fore_reach",
        "right_fore_contact",
        "weight_accept_return",
        "hind_drive_return",
        "flight_extend_return",
        "collect",
        "cycle_ready",
    ),
    "chief_sit": (
        "stand_alert",
        "lower_head",
        "bend_hind_legs",
        "lower_haunches",
        "seat_contact",
        "front_paws_set",
        "sit_tall",
        "look_left_start",
        "look_left",
        "return_center",
        "look_right_start",
        "look_right",
        "return_center_again",
        "chest_breath",
        "tail_settle",
        "party_ready",
    ),
    "enemy_idle": (
        "ready",
        "inhale",
        "prop_check",
        "weight_left",
        "scan_forward",
        "weight_center",
        "weight_right",
        "listen",
        "grip_adjust",
        "exhale",
        "feet_set",
        "ready_return",
    ),
    "enemy_stride": (
        "left_heel_strike",
        "left_weight_accept",
        "left_mid_stance",
        "right_leg_passing",
        "left_heel_rise",
        "left_toe_off",
        "right_heel_strike",
        "right_weight_accept",
        "right_mid_stance",
        "left_leg_passing",
        "right_heel_rise",
        "right_toe_off",
    ),
    "couch_idle": (
        "squat_ready",
        "inhale",
        "belly_settle",
        "shoulder_roll",
        "stick_grip",
        "look_left",
        "return_center",
        "look_right",
        "jacket_settle",
        "exhale",
        "hat_adjust",
        "squat_ready_return",
    ),
    "couch_waddle": (
        "left_foot_out",
        "left_heel_contact",
        "left_belly_shift",
        "left_weight_accept",
        "right_foot_pass",
        "left_push",
        "center_crossing",
        "right_foot_out",
        "right_heel_contact",
        "right_belly_shift",
        "right_weight_accept",
        "left_foot_pass",
        "right_push",
        "center_return",
        "squat_recover",
        "cycle_ready",
    ),
    "jerry_idle": (
        "walker_set",
        "inhale",
        "coat_settle",
        "lean_left",
        "hat_dip",
        "steady",
        "lean_right",
        "look_road",
        "exhale",
        "regrip_left",
        "regrip_right",
        "walker_ready",
    ),
    "jerry_support": (
        "walker_set",
        "lean_left",
        "brace_left",
        "check_road",
        "shift_center",
        "lean_right",
        "brace_right",
        "steady_walker",
        "listen",
        "coat_settle",
        "regrip",
        "support_ready",
    ),
    "jerry_talk": (
        "notice",
        "draw_breath",
        "mutter_start",
        "speak_low",
        "mouth_open",
        "open_hand",
        "emphasize",
        "hold_line",
        "finish_line",
        "mouth_close",
        "listen",
        "dialogue_ready",
    ),
    "jerry_point": (
        "notice",
        "free_hand",
        "raise_elbow",
        "extend_forearm",
        "point_road",
        "hold_direction_start",
        "hold_direction",
        "emphasize_direction",
        "withdraw_start",
        "lower_arm",
        "regrip_walker",
        "direction_ready",
    ),
}


# Phase names map one-to-one to independently authored source keys.  Timing
# holds belong to the clip; the atlas must never manufacture count-padding.
PHASES = {name: tuple(keyframes) for name, keyframes in BASE_PHASES.items()}

# Shelly's two idle personality beats get a denser authored cadence than the
# ordinary combat clips. The extra registered poses keep the gesture readable
# at both 30 and 60 FPS without changing any gameplay timing.
SHELLY_PERSONALITY_PHASES = {
    "refill": (
        "inspect", "raise_can", "raise_can_hold", "align_valve",
        "align_valve_hold", "connect", "press_fill_start", "press_fill",
        "press_fill_hold", "release", "remove_can_start", "remove_can",
        "lower_can", "ready_transition", "ready_hold", "ready",
    ),
    "pants": (
        "notice", "reach_back_start", "reach_back", "grip_waist",
        "grip_waist_hold", "pull_start", "pull_mid", "pull_high_start",
        "pull_high", "settle_band_start", "settle_band", "release_start",
        "release", "reset_posture", "ready_transition", "ready",
    ),
}


# KO is an authored support fighter, not a Dave alias.  These state names are
# intentionally exact because his props and costume continuity are part of the
# art contract: the skateboard belongs only to ``skate``; glove-up and coat
# beats belong to ``idle``/``prepare``; combat and super use their own cels.
KO_PHASES = {
    "idle": (
        "coat_settle",
        "left_glove_start",
        "left_glove_secure",
        "right_glove_start",
        "right_glove_secure",
        "wrist_check",
        "guard_rise",
        "ready",
    ),
    "skate": (
        "rear_foot_push",
        "rear_foot_recover",
        "both_feet_set",
        "front_truck_compress",
        "coast_low",
        "coast_rise",
        "rear_truck_compress",
        "weight_transfer",
        "carve_out",
        "carve_return",
        "coast_settle",
        "roll_ready",
    ),
    "prepare": (
        "scan_crowd",
        "select_opponent",
        "grip_coat",
        "throw_coat",
        "stance_drop",
        "guard_set",
        "lets_get_it",
        "ready",
    ),
    "punch_1": (
        "guard",
        "lead_shoulder_load",
        "lead_hand_launch",
        "jab_contact",
        "jab_extension",
        "hand_return",
        "guard_recover",
        "ready",
    ),
    "punch_2": (
        "guard",
        "rear_hip_load",
        "rear_hand_launch",
        "cross_contact",
        "cross_extension",
        "torso_unwind",
        "guard_recover",
        "ready",
    ),
    "kick": (
        "guard",
        "weight_shift",
        "knee_chamber",
        "kick_launch",
        "kick_contact",
        "leg_retract",
        "foot_set",
        "ready",
    ),
    "super": (
        "stance_flash",
        "launch_blur",
        "first_target",
        "cross_screen_one",
        "second_target",
        "cross_screen_two",
        "third_target",
        "cross_screen_three",
        "crowd_finish",
        "return_blur",
        "brake_flash",
        "ready",
    ),
}


PLAYER_STATES = (
    "idle",
    "walk",
    "attack_1",
    "attack_2",
    "attack_3",
    "attack_4",
    "heavy",
    "ranged",
    "dodge",
    "hurt",
    "down",
    "super",
    "air_attack",
    "jump",
    "pet",
    "refill",
    "pants",
)
KO_STATES = tuple(KO_PHASES)
CHIEF_STATES = ("idle", "move", "attack", "frenzy", "guard", "sit", "pet", "command", "maul")
# Maul is a wide, authored composite containing Chief and a safely stylized
# grounded foe, so it lives outside Chief's normal 128px locomotion atlas.
CHIEF_ATLAS_STATES = tuple(state for state in CHIEF_STATES if state != "maul")
ENEMY_STATES = ("idle", "spawn", "walk", "attack", "charge", "recovery", "hurt", "down")
COUCH_STATES = (
    "idle",
    "spawn",
    "walk",
    "stick_attack",
    "stick_recovery",
    "pump_attack",
    "pump_recovery",
    "hurt",
    "down",
    "laugh",
)
JERRY_STATES = ("idle", "support", "talk", "point")
ENEMY_KINDS = ("stick", "cart", "whip", "pipe")
ENEMY_VARIANT_KINDS = (
    "encampment_bottle_scarf",
    "encampment_bottle_puffer",
    "encampment_tire_slinger",
    "underpass_tire_runner",
    "cart_tent_bottle_pitcher",
    "mall_security_watch",
    "event_security_heavy",
    "night_security_patrol",
    "city_patrol_nightstick",
    "transit_patrol_nightstick",
    "riot_line_nightstick",
    "bike_patrol_taser",
    "tactical_taser_unit",
)
ENEMY_VARIANT_ANIMATION_ACTORS = {variant: variant for variant in ENEMY_VARIANT_KINDS}

# Runtime/content roles reuse authored enemy motion families.  Keep the
# mapping explicit so a new role cannot silently fall back to unrelated art,
# while presentation timing always resolves to a manifest-backed actor.
ENEMY_RUNTIME_ANIMATION_ACTORS = {
    "security": "stick",
    "security_guard": "stick",
    "guard": "stick",
    "homeless": "stick",
    "police": "stick",
    "debo": "couch",
}


def enemy_animation_actor(kind: object, variant_id: object | None = None) -> str:
    """Resolve one supported runtime enemy role to its authored motion actor."""

    normalized = str(kind or "stick").strip().lower().replace("-", "_").replace(" ", "_")
    normalized_variant = str(variant_id or "").strip().lower().replace("-", "_").replace(" ", "_")
    variant_actor = ENEMY_VARIANT_ANIMATION_ACTORS.get(normalized_variant)
    if variant_actor is not None:
        return variant_actor
    if normalized in ENEMY_VARIANT_KINDS:
        return normalized
    if normalized in ENEMY_KINDS:
        return normalized
    actor = ENEMY_RUNTIME_ANIMATION_ACTORS.get(normalized)
    if actor is None:
        raise ValueError(f"unknown enemy kind: {normalized}")
    return actor


def _player_phase(actor: str, state: str) -> str:
    if state == "idle":
        return "hero_idle"
    if state == "walk":
        return "hero_stride"
    if actor == "shelly" and state == "refill":
        return "shelly_refill"
    if actor == "shelly" and state == "pants":
        return "shelly_pants"
    if state.startswith("attack_") or state == "heavy":
        return "attack"
    if state == "ranged":
        return "ranged"
    if state == "dodge":
        return "dodge"
    if state == "hurt":
        return "hurt"
    if state == "down":
        return "down"
    if state == "super":
        return "power"
    if state == "air_attack":
        return "air"
    return state


def _chief_phase(state: str) -> str:
    if state == "idle":
        return "chief_idle"
    if state == "move":
        return "chief_stride"
    if state == "sit":
        return "chief_sit"
    if state == "maul":
        return "maul"
    return "power" if state == "frenzy" else state


def _enemy_phase(state: str) -> str:
    if state == "idle":
        return "enemy_idle"
    if state == "walk":
        return "enemy_stride"
    return "attack" if state in {"attack", "charge", "recovery"} else state


def _couch_phase(state: str) -> str:
    if state == "idle":
        return "couch_idle"
    if state == "walk":
        return "couch_waddle"
    return "attack" if state in {"stick_attack", "stick_recovery", "pump_attack", "pump_recovery"} else state


def _jerry_phase(state: str) -> str:
    return f"jerry_{state}"


def _loop_and_hold(actor: str, state: str) -> tuple[bool, int]:
    if actor == "ko":
        if state == "idle":
            return True, 5
        if state == "skate":
            return True, 2
        if state == "prepare":
            return False, 2
        return False, 1
    if actor == "chief" and state == "maul":
        return False, 2
    if state == "command":
        return True, 3
    if actor in {"black_dave", "shelly"} and state == "walk":
        # Twelve true gait keys are each held for two 30 Hz ticks. Runtime
        # locomotion maps this 24-tick timeline to applied travel distance;
        # Dave's normal stride is calibrated to a deliberate 0.96 seconds.
        return True, 2
    if actor in {"black_dave", "shelly"} and state == "idle":
        return True, 5
    if actor == "chief" and state == "move":
        return True, 2
    if actor == "chief" and state == "idle":
        return True, 5
    if actor == "chief" and state == "sit":
        return True, 6
    if actor in {*ENEMY_KINDS, *ENEMY_VARIANT_KINDS} and state == "walk":
        return True, 3
    if actor in {*ENEMY_KINDS, *ENEMY_VARIANT_KINDS} and state == "idle":
        return True, 5
    if actor == "couch" and state == "walk":
        return True, 3
    if actor == "couch" and state == "idle":
        return True, 5
    if actor == "jerry" and state in {"idle", "support"}:
        return True, 6
    if actor == "jerry" and state == "talk":
        return True, 4
    if actor == "jerry" and state == "point":
        return False, 3
    if state in {"idle", "walk", "move", "frenzy", "guard", "sit", "laugh", "support", "talk", "ride"}:
        return True, 4 if state in {"walk", "move", "frenzy"} else 6
    if state in {"refill", "pants", "pet"}:
        return False, 4
    if actor == "victory":
        return False, 1
    return False, 1


ANIMATION_CLIPS: tuple[AnimationClip, ...] = tuple(
    [
        AnimationClip(
            actor,
            state,
            f"assets/sprites/{actor}_animation_atlas.png",
            row,
            128,
            128,
            *_loop_and_hold(actor, state),
            (
                SHELLY_PERSONALITY_PHASES[state]
                if actor == "shelly" and state in SHELLY_PERSONALITY_PHASES
                else PHASES[_player_phase(actor, state)]
            ),
        )
        for actor in ("black_dave", "shelly")
        for row, state in enumerate(PLAYER_STATES)
    ]
    + [
        AnimationClip(
            "ko",
            state,
            "assets/sprites/ko_animation_atlas.png",
            row,
            304,
            128,
            *_loop_and_hold("ko", state),
            KO_PHASES[state],
        )
        for row, state in enumerate(KO_STATES)
    ]
    + [
        AnimationClip(
            "chief",
            state,
            "assets/sprites/chief_animation_atlas.png",
            row,
            128,
            88,
            *_loop_and_hold("chief", state),
            PHASES[_chief_phase(state)],
        )
        for row, state in enumerate(CHIEF_ATLAS_STATES)
    ]
    + [
        AnimationClip(
            "chief",
            "maul",
            "assets/sprites/chief_maul_animation_strip.png",
            0,
            256,
            128,
            *_loop_and_hold("chief", "maul"),
            PHASES["maul"],
        )
    ]
    + [
        AnimationClip(
            kind,
            state,
            "assets/sprites/enemies_animation_atlas.png",
            kind_index * len(ENEMY_STATES) + row,
            160,
            128,
            *_loop_and_hold(kind, state),
            PHASES[_enemy_phase(state)],
        )
        for kind_index, kind in enumerate(ENEMY_KINDS)
        for row, state in enumerate(ENEMY_STATES)
    ]
    + [
        AnimationClip(
            actor,
            state,
            f"assets/sprites/enemies/{actor}_animation_atlas.png",
            row,
            160,
            128,
            *_loop_and_hold(actor, state),
            PHASES[_enemy_phase(state)],
        )
        for actor in ENEMY_VARIANT_KINDS
        for row, state in enumerate(ENEMY_STATES)
    ]
    + [
        AnimationClip(
            "couch",
            state,
            "assets/sprites/couch_animation_atlas.png",
            row,
            128,
            128,
            *_loop_and_hold("couch", state),
            PHASES[_couch_phase(state)],
        )
        for row, state in enumerate(COUCH_STATES)
    ]
    + [
        AnimationClip(
            "jerry",
            state,
            "assets/sprites/jerry_animation_atlas.png",
            row,
            192,
            144,
            *_loop_and_hold("jerry", state),
            PHASES[_jerry_phase(state)],
        )
        for row, state in enumerate(JERRY_STATES)
    ]
    + [
        AnimationClip(
            "victory",
            "celebration",
            "assets/sprites/victory_animation_strip.png",
            0,
            256,
            144,
            False,
            1,
            PHASES["victory"],
        )
    ]
    + [
        AnimationClip(
            "sunset",
            "ride",
            "assets/sprites/sunset_bmx_animation_strip.png",
            0,
            256,
            144,
            True,
            4,
            PHASES["ride"],
        )
    ]
)


_CLIP_INDEX = {(clip.actor, clip.state): clip for clip in ANIMATION_CLIPS}


PLAYER_ALIASES = {
    "downed": "down",
    "dead": "down",
    "eliminated": "down",
    "hit": "hurt",
    "hitstun": "hurt",
    "special": "super",
    "shockwave": "super",
    "speaker": "super",
    "frenzy": "super",
    "air": "air_attack",
    "jump_attack": "air_attack",
    "throw": "heavy",
    "bb_gun": "ranged",
    "shoot": "ranged",
    "uppercut": "attack_3",
    "combo_finisher": "attack_3",
    "finisher": "attack_4",
    "light": "attack_1",
    "attack": "attack_1",
    "punch": "attack_1",
    "combo": "attack_1",
    "dash": "dodge",
    "run": "walk",
    "chase": "walk",
    "butane": "refill",
    "propane": "super",
    "flamethrower": "super",
    "flame_thrower": "super",
    "butane_refill": "refill",
    "torch_refill": "refill",
    "pants_pull": "pants",
    "waistband": "pants",
}
CHIEF_ALIASES = {
    "walk": "move",
    "run": "move",
    "charge": "move",
    "follow": "move",
    "hunt": "move",
    "protect": "move",
    "return_to_caller": "move",
    "bite": "attack",
    "super": "frenzy",
    "vicious": "frenzy",
    "mauling": "maul",
    "ground_maul": "maul",
    "neck_maul": "maul",
    "settle": "sit",
    "rest": "sit",
}
ENEMY_ALIASES = {
    "run": "walk",
    "chase": "walk",
    "swing": "attack",
    "throw": "attack",
    "heavy": "attack",
    "windup": "attack",
    "hit": "hurt",
    "hitstun": "hurt",
    "dead": "down",
}
COUCH_ALIASES = {
    "run": "walk",
    "chase": "walk",
    "attack": "stick_attack",
    "swing": "stick_attack",
    "heavy": "stick_attack",
    "stick": "stick_attack",
    "windup": "stick_attack",
    "attack_recovery": "stick_recovery",
    "recovery": "stick_recovery",
    "special": "pump_attack",
    "pump": "pump_attack",
    "charge": "pump_attack",
    "special_recovery": "pump_recovery",
    "hit": "hurt",
    "hitstun": "hurt",
    "dead": "down",
    "taunt": "laugh",
}
JERRY_ALIASES = {
    "wait": "idle",
    "walker": "support",
    "brace": "support",
    "speak": "talk",
    "dialogue": "talk",
    "warn": "talk",
    "gesture": "talk",
    "direction": "point",
    "alert": "point",
}


def clip_for(actor: str, state: str) -> AnimationClip:
    normalized_actor = str(actor).strip().lower().replace("-", "_").replace(" ", "_")
    normalized_state = str(state).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_actor in {"dave", "blackdave"}:
        normalized_actor = "black_dave"
    elif normalized_actor in {"jermaine", "white_dave"}:
        normalized_actor = "black_dave"
    elif normalized_actor == "shellie":
        normalized_actor = "shelly"
    if normalized_actor == "ko":
        if normalized_state not in KO_STATES:
            raise ValueError(f"unknown KO animation state: {normalized_state}")
        return _CLIP_INDEX[("ko", normalized_state)]
    if normalized_actor in {"black_dave", "shelly"}:
        normalized_state = PLAYER_ALIASES.get(normalized_state, normalized_state)
    elif normalized_actor == "chief":
        normalized_state = CHIEF_ALIASES.get(normalized_state, normalized_state)
    elif normalized_actor in {*ENEMY_KINDS, *ENEMY_VARIANT_KINDS}:
        normalized_state = ENEMY_ALIASES.get(normalized_state, normalized_state)
    elif normalized_actor == "debo":
        normalized_actor = "couch"
        normalized_state = COUCH_ALIASES.get(normalized_state, normalized_state)
    elif normalized_actor == "couch":
        normalized_state = COUCH_ALIASES.get(normalized_state, normalized_state)
    elif normalized_actor == "jerry":
        normalized_state = JERRY_ALIASES.get(normalized_state, normalized_state)
    elif normalized_actor == "victory":
        normalized_state = "celebration"
    elif normalized_actor == "sunset":
        normalized_state = "ride"
    default_state = {"victory": "celebration", "sunset": "ride"}.get(normalized_actor, "idle")
    return _CLIP_INDEX.get((normalized_actor, normalized_state), _CLIP_INDEX[(normalized_actor, default_state)])


_ACTION_SEGMENT_PHASES: dict[str, dict[str, tuple[str, ...]]] = {
    "attack": {
        "startup": ("guard", "anticipate", "windup", "launch"),
        "active": ("contact", "follow_through"),
        "recovery": ("recoil", "recover"),
    },
    "ranged": {
        "startup": ("ready", "draw", "aim"),
        "active": ("fire", "muzzle_recoil"),
        "recovery": ("lower", "reholster", "guard"),
    },
    "dodge": {
        "startup": ("ready", "dip", "push_off"),
        "active": ("low_travel", "deep_travel"),
        "recovery": ("brake", "rise", "ready_return"),
    },
    "power": {
        "startup": ("ready", "gather", "raise", "charge"),
        "active": ("release", "peak"),
        "recovery": ("aftershock", "recover"),
    },
    "air": {
        "startup": ("crouch", "launch", "rise", "air_ready"),
        "active": ("strike",),
        "recovery": ("descent", "land", "recover"),
    },
    "jump": {
        "startup": ("crouch", "launch", "rise"),
        "active": ("apex",),
        "recovery": ("fall", "brace", "land", "recover"),
    },
    "command": {
        "startup": ("listen", "locate", "coil"),
        "active": ("launch", "sprint", "acquire"),
        "recovery": ("brake", "ready"),
    },
    "maul": {
        "startup": ("approach_crouch", "paws_brace", "lunge"),
        "active": ("bite_contact", "shake_left", "shake_right"),
        "recovery": ("release", "alert_finish"),
    },
}
_PHASE_FAMILY_BY_SIGNATURE = {
    tuple(phases): family
    for family, phases in BASE_PHASES.items()
}


def _action_segment_indices(clip: AnimationClip, segment: str) -> tuple[int, ...]:
    """Return semantically grouped pose indices for one action segment."""

    normalized_segment = str(segment).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_segment not in {"startup", "active", "recovery"}:
        raise ValueError(f"unsupported action segment: {segment!r}")

    family = _PHASE_FAMILY_BY_SIGNATURE.get(tuple(clip.phases))
    semantic = _ACTION_SEGMENT_PHASES.get(family or "", {}).get(normalized_segment, ())
    if semantic:
        indices = tuple(index for index, phase in enumerate(clip.phases) if phase in semantic)
        if indices:
            return indices

    # Unknown/custom action families still receive a stable anticipation,
    # impact, and recovery split.  The manifest floor guarantees at least five
    # poses, so each segment retains at least one independently authored key.
    count = clip.frame_count
    startup_end = max(1, count // 2)
    recovery_start = max(startup_end + 1, count - max(2, count // 4))
    recovery_start = min(count - 1, recovery_start)
    fallback = {
        "startup": tuple(range(0, startup_end)),
        "active": tuple(range(startup_end, recovery_start)),
        "recovery": tuple(range(recovery_start, count)),
    }
    return fallback[normalized_segment]


def _nonnegative_seconds(value: float, label: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds):
        raise ValueError(f"{label} must be finite")
    return max(0.0, seconds)


def action_segment_tick(
    actor: str,
    state: str,
    segment: str,
    elapsed: float,
    duration: float,
) -> int:
    """Map local segment time to an existing authored animation pose.

    ``startup``, ``active``, and ``recovery`` select semantic phase names
    rather than dividing the full strip uniformly.  The returned value is a
    presentation tick, including the clip's configured hold, and can be passed
    directly to :func:`src.sprite_atlas.animation_frame`.
    """

    clip = clip_for(actor, state)
    indices = _action_segment_indices(clip, segment)
    local_elapsed = _nonnegative_seconds(elapsed, "elapsed")
    local_duration = _nonnegative_seconds(duration, "duration")
    if local_duration <= 0.0:
        phase_index = indices[-1]
    else:
        progress = min(1.0, local_elapsed / local_duration)
        offset = min(len(indices) - 1, int(progress * len(indices)))
        phase_index = indices[offset]
    return phase_index * max(1, clip.hold)


def timed_action_tick(
    actor: str,
    state: str,
    elapsed: float,
    startup: float,
    active: float,
    recovery: float,
) -> int:
    """Select startup, contact/follow-through, or recovery art by move time.

    The first active instant selects the first semantic contact pose.  The
    first instant after the active window selects recovery art, keeping visible
    impact synchronized with the same half-open timing used by combat queries.
    """

    action_elapsed = _nonnegative_seconds(elapsed, "elapsed")
    startup_seconds = _nonnegative_seconds(startup, "startup")
    active_seconds = _nonnegative_seconds(active, "active")
    recovery_seconds = _nonnegative_seconds(recovery, "recovery")

    if startup_seconds > 0.0 and action_elapsed < startup_seconds:
        return action_segment_tick(
            actor,
            state,
            "startup",
            action_elapsed,
            startup_seconds,
        )
    active_end = startup_seconds + active_seconds
    if active_seconds > 0.0 and action_elapsed < active_end:
        return action_segment_tick(
            actor,
            state,
            "active",
            action_elapsed - startup_seconds,
            active_seconds,
        )
    return action_segment_tick(
        actor,
        state,
        "recovery",
        action_elapsed - active_end,
        recovery_seconds,
    )


def total_authored_poses() -> int:
    return sum(clip.frame_count for clip in ANIMATION_CLIPS)


__all__ = [
    "ANIMATION_CLIPS",
    "ANIMATION_PLAYBACK_HZ",
    "AnimationClip",
    "BASE_EXPANDED_PARTY_IDLE_POSES",
    "BASE_EXTENDED_HERO_POSES",
    "BASE_PHASES",
    "BASE_POSES_PER_CLIP",
    "SHELLY_PERSONALITY_PHASES",
    "SHELLY_PERSONALITY_POSES",
    "CHIEF_ATLAS_STATES",
    "CHIEF_STATES",
    "COUCH_STATES",
    "ENEMY_KINDS",
    "ENEMY_RUNTIME_ANIMATION_ACTORS",
    "ENEMY_VARIANT_ANIMATION_ACTORS",
    "ENEMY_VARIANT_KINDS",
    "ENEMY_STATES",
    "EXPANDED_LOCOMOTION_POSES",
    "EXPANDED_PARTY_IDLE_POSES",
    "EXTENDED_HERO_POSES",
    "JERRY_STATES",
    "KO_PHASES",
    "KO_STATES",
    "PLAYER_STATES",
    "POSES_PER_CLIP",
    "action_segment_tick",
    "clip_for",
    "enemy_animation_actor",
    "timed_action_tick",
    "total_authored_poses",
]
