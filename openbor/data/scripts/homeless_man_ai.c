// Homeless Man production enemy controller. OpenBOR 4.0 Build 7949.
// This thinkscript is the sole AI and pose-selection owner.

int hm_abs(int value)
{
    if(value < 0) return 0 - value;
    return value;
}

void hm_velocity(void self, int x, int z)
{
    changeentityproperty(self, "velocity", x, z, 0);
}

void hm_release_attack_token(void self)
{
    if(getglobalvar("fof2_enemy_attack_token") == self)
    {
        setglobalvar("fof2_enemy_attack_token", NULL());
        log("[FOF2_HM_AI] attack_token_release\n");
    }
}

void hm_log_state(int state)
{
    if(state == 0) log("[FOF2_HM_AI] state=spawn\n");
    else if(state == 1) log("[FOF2_HM_AI] state=idle\n");
    else if(state == 2) log("[FOF2_HM_AI] state=alert_aggro\n");
    else if(state == 3) log("[FOF2_HM_AI] state=walk_start\n");
    else if(state == 4) log("[FOF2_HM_AI] state=walk_loop\n");
    else if(state == 5) log("[FOF2_HM_AI] state=walk_stop\n");
    else if(state == 6) log("[FOF2_HM_AI] state=turn_pivot\n");
    else if(state == 7) log("[FOF2_HM_AI] state=unarmed_jab\n");
    else if(state == 8) log("[FOF2_HM_AI] state=two_hand_shove\n");
    else if(state == 9) log("[FOF2_HM_AI] state=heavy_overhand\n");
    else if(state == 10) log("[FOF2_HM_AI] state=taunt_hesitate\n");
    else if(state == 11) log("[FOF2_HM_AI] state=light_pain\n");
    else if(state == 12) log("[FOF2_HM_AI] state=heavy_pain\n");
    else if(state == 13) log("[FOF2_HM_AI] state=knockdown_fall\n");
    else if(state == 14) log("[FOF2_HM_AI] state=down\n");
    else if(state == 15) log("[FOF2_HM_AI] state=rise\n");
    else log("[FOF2_HM_AI] state=death\n");
}

int hm_state_duration(int state)
{
    if(state == 0) return 34;
    if(state == 1) return 96;
    if(state == 2) return 24;
    if(state == 3) return 12;
    if(state == 4) return 54;
    if(state == 5) return 12;
    if(state == 6) return 10;
    if(state == 7) return 28;
    if(state == 8) return 34;
    if(state == 9) return 48;
    if(state == 10) return 52;
    if(state == 11) return 18;
    if(state == 12) return 26;
    if(state == 13) return 38;
    if(state == 14) return 42;
    if(state == 15) return 42;
    return 60;
}

int hm_linear_pose(int tick, int count, int total)
{
    int pose;
    if(tick < 0) tick = 0;
    if(tick >= total) tick = total - 1;
    pose = (tick * count) / total;
    if(pose >= count) pose = count - 1;
    return pose;
}

int hm_attack_pose(int tick, int startup, int active, int recovery, int active_start, int active_count, int count)
{
    int recovery_start;
    int recovery_count;
    int total;
    total = startup + active + recovery;
    if(tick < 0) tick = 0;
    if(tick >= total) tick = total - 1;
    if(tick < startup) return (tick * active_start) / startup;
    if(tick < startup + active) return active_start + (((tick - startup) * active_count) / active);
    recovery_start = active_start + active_count;
    recovery_count = count - recovery_start;
    return recovery_start + (((tick - startup - active) * recovery_count) / recovery);
}

int hm_anim_for_state(int state)
{
    if(state == 0) return openborconstant("ANI_SPAWN");
    if(state == 1 || state == 2 || state == 10) return openborconstant("ANI_IDLE");
    if(state == 3 || state == 4 || state == 5) return openborconstant("ANI_WALK");
    if(state == 6) return openborconstant("ANI_TURN");
    if(state == 7) return openborconstant("ANI_ATTACK1");
    if(state == 8) return openborconstant("ANI_ATTACK2");
    if(state == 9) return openborconstant("ANI_ATTACK3");
    if(state == 11) return openborconstant("ANI_PAIN");
    if(state == 12) return openborconstant("ANI_PAIN2");
    if(state == 13 || state == 14) return openborconstant("ANI_FALL");
    if(state == 15) return openborconstant("ANI_RISE");
    return openborconstant("ANI_DIE");
}

void hm_enter(void self, int state)
{
    int old_state;
    old_state = getentityvar(self, "state");
    if(old_state == state) return;
    if(old_state == 7 || old_state == 8 || old_state == 9)
    {
        changeentityproperty(self, "aiflag", "attacking", 0);
        hm_release_attack_token(self);
    }
    if(state != 4) hm_velocity(self, 0, 0);
    changeentityproperty(self, "takeaction", NULL());
    if(state == 13) changeentityproperty(self, "aiflag", "drop", 1);
    if(state == 14)
    {
        changeentityproperty(self, "aiflag", "drop", 1);
        changeentityproperty(self, "aiflag", "falling", 0);
    }
    if(state == 15)
    {
        changeentityproperty(self, "aiflag", "drop", 0);
        changeentityproperty(self, "aiflag", "falling", 0);
        changeentityproperty(self, "aiflag", "rising", 1);
    }
    if(state == 16)
    {
        changeentityproperty(self, "aiflag", "drop", 0);
        changeentityproperty(self, "aiflag", "falling", 0);
        changeentityproperty(self, "aiflag", "rising", 0);
    }
    if(state != 13 && state != 14 && state != 15)
    {
        changeentityproperty(self, "aiflag", "drop", 0);
        changeentityproperty(self, "aiflag", "falling", 0);
        changeentityproperty(self, "aiflag", "rising", 0);
    }
    if(old_state == 15 && state != 15)
    {
        changeentityproperty(self, "aiflag", "rising", 0);
        changeentityproperty(self, "aiflag", "drop", 0);
    }
    setentityvar(self, "state", state);
    setentityvar(self, "state_tick", 0);
    setentityvar(self, "pose_tick", 0);
    setentityvar(self, "pose", 0);
    changeentityproperty(self, "animation", hm_anim_for_state(state));
    if(state == 7 || state == 8 || state == 9)
    {
        changeentityproperty(self, "aiflag", "attacking", 1);
    }
    hm_log_state(state);
}

int hm_pose(void self, int state, int tick)
{
    int travel;
    if(state == 0) return hm_linear_pose(tick, 6, 34);
    if(state == 1) return hm_linear_pose(tick % 96, 8, 96);
    if(state == 2) return 8 + hm_linear_pose(tick, 4, 24);
    if(state == 3) return hm_linear_pose(tick, 4, 12);
    if(state == 4)
    {
        if(getentityvar(self, "qa_hold") > 0) return 4 + hm_linear_pose(tick % 54, 12, 54);
        travel = getentityvar(self, "travel");
        return 4 + (((travel * 12) / 54) % 12);
    }
    if(state == 5) return 16 + hm_linear_pose(tick, 4, 12);
    if(state == 6) return hm_linear_pose(tick, 4, 10);
    if(state == 7) return hm_attack_pose(tick, 8, 4, 16, 3, 2, 8);
    if(state == 8) return hm_attack_pose(tick, 10, 6, 18, 3, 2, 8);
    if(state == 9) return hm_attack_pose(tick, 18, 6, 24, 5, 2, 10);
    if(state == 10) return 12 + hm_linear_pose(tick, 8, 52);
    if(state == 11) return hm_linear_pose(tick, 5, 18);
    if(state == 12) return hm_linear_pose(tick, 7, 26);
    if(state == 13) return hm_linear_pose(tick, 8, 38);
    if(state == 14) return 8 + hm_linear_pose(tick % 42, 6, 42);
    if(state == 15) return hm_linear_pose(tick, 8, 42);
    return hm_linear_pose(tick, 10, 60);
}

// BEGIN GENERATED HM POSE LOGGER
void hm_log_pose(int state, int pose)
{
    if(state == 0 && pose == 0) log("[FOF2_POSE] hm_spawn_entry_001\n");
    else if(state == 0 && pose == 1) log("[FOF2_POSE] hm_spawn_entry_002\n");
    else if(state == 0 && pose == 2) log("[FOF2_POSE] hm_spawn_entry_003\n");
    else if(state == 0 && pose == 3) log("[FOF2_POSE] hm_spawn_entry_004\n");
    else if(state == 0 && pose == 4) log("[FOF2_POSE] hm_spawn_entry_005\n");
    else if(state == 0 && pose == 5) log("[FOF2_POSE] hm_spawn_entry_006\n");
    else if(state == 1 && pose == 0) log("[FOF2_POSE] hm_idle_001\n");
    else if(state == 1 && pose == 1) log("[FOF2_POSE] hm_idle_002\n");
    else if(state == 1 && pose == 2) log("[FOF2_POSE] hm_idle_003\n");
    else if(state == 1 && pose == 3) log("[FOF2_POSE] hm_idle_004\n");
    else if(state == 1 && pose == 4) log("[FOF2_POSE] hm_idle_005\n");
    else if(state == 1 && pose == 5) log("[FOF2_POSE] hm_idle_006\n");
    else if(state == 1 && pose == 6) log("[FOF2_POSE] hm_idle_007\n");
    else if(state == 1 && pose == 7) log("[FOF2_POSE] hm_idle_008\n");
    else if(state == 2 && pose == 8) log("[FOF2_POSE] hm_alert_aggro_001\n");
    else if(state == 2 && pose == 9) log("[FOF2_POSE] hm_alert_aggro_002\n");
    else if(state == 2 && pose == 10) log("[FOF2_POSE] hm_alert_aggro_003\n");
    else if(state == 2 && pose == 11) log("[FOF2_POSE] hm_alert_aggro_004\n");
    else if(state == 3 && pose == 0) log("[FOF2_POSE] hm_walk_start_001\n");
    else if(state == 3 && pose == 1) log("[FOF2_POSE] hm_walk_start_002\n");
    else if(state == 3 && pose == 2) log("[FOF2_POSE] hm_walk_start_003\n");
    else if(state == 3 && pose == 3) log("[FOF2_POSE] hm_walk_start_004\n");
    else if(state == 4 && pose == 4) log("[FOF2_POSE] hm_walk_loop_001\n");
    else if(state == 4 && pose == 5) log("[FOF2_POSE] hm_walk_loop_002\n");
    else if(state == 4 && pose == 6) log("[FOF2_POSE] hm_walk_loop_003\n");
    else if(state == 4 && pose == 7) log("[FOF2_POSE] hm_walk_loop_004\n");
    else if(state == 4 && pose == 8) log("[FOF2_POSE] hm_walk_loop_005\n");
    else if(state == 4 && pose == 9) log("[FOF2_POSE] hm_walk_loop_006\n");
    else if(state == 4 && pose == 10) log("[FOF2_POSE] hm_walk_loop_007\n");
    else if(state == 4 && pose == 11) log("[FOF2_POSE] hm_walk_loop_008\n");
    else if(state == 4 && pose == 12) log("[FOF2_POSE] hm_walk_loop_009\n");
    else if(state == 4 && pose == 13) log("[FOF2_POSE] hm_walk_loop_010\n");
    else if(state == 4 && pose == 14) log("[FOF2_POSE] hm_walk_loop_011\n");
    else if(state == 4 && pose == 15) log("[FOF2_POSE] hm_walk_loop_012\n");
    else if(state == 5 && pose == 16) log("[FOF2_POSE] hm_walk_stop_001\n");
    else if(state == 5 && pose == 17) log("[FOF2_POSE] hm_walk_stop_002\n");
    else if(state == 5 && pose == 18) log("[FOF2_POSE] hm_walk_stop_003\n");
    else if(state == 5 && pose == 19) log("[FOF2_POSE] hm_walk_stop_004\n");
    else if(state == 6 && pose == 0) log("[FOF2_POSE] hm_turn_pivot_001\n");
    else if(state == 6 && pose == 1) log("[FOF2_POSE] hm_turn_pivot_002\n");
    else if(state == 6 && pose == 2) log("[FOF2_POSE] hm_turn_pivot_003\n");
    else if(state == 6 && pose == 3) log("[FOF2_POSE] hm_turn_pivot_004\n");
    else if(state == 7 && pose == 0) log("[FOF2_POSE] hm_unarmed_jab_001\n");
    else if(state == 7 && pose == 1) log("[FOF2_POSE] hm_unarmed_jab_002\n");
    else if(state == 7 && pose == 2) log("[FOF2_POSE] hm_unarmed_jab_003\n");
    else if(state == 7 && pose == 3) log("[FOF2_POSE] hm_unarmed_jab_004\n");
    else if(state == 7 && pose == 4) log("[FOF2_POSE] hm_unarmed_jab_005\n");
    else if(state == 7 && pose == 5) log("[FOF2_POSE] hm_unarmed_jab_006\n");
    else if(state == 7 && pose == 6) log("[FOF2_POSE] hm_unarmed_jab_007\n");
    else if(state == 7 && pose == 7) log("[FOF2_POSE] hm_unarmed_jab_008\n");
    else if(state == 8 && pose == 0) log("[FOF2_POSE] hm_two_hand_shove_001\n");
    else if(state == 8 && pose == 1) log("[FOF2_POSE] hm_two_hand_shove_002\n");
    else if(state == 8 && pose == 2) log("[FOF2_POSE] hm_two_hand_shove_003\n");
    else if(state == 8 && pose == 3) log("[FOF2_POSE] hm_two_hand_shove_004\n");
    else if(state == 8 && pose == 4) log("[FOF2_POSE] hm_two_hand_shove_005\n");
    else if(state == 8 && pose == 5) log("[FOF2_POSE] hm_two_hand_shove_006\n");
    else if(state == 8 && pose == 6) log("[FOF2_POSE] hm_two_hand_shove_007\n");
    else if(state == 8 && pose == 7) log("[FOF2_POSE] hm_two_hand_shove_008\n");
    else if(state == 9 && pose == 0) log("[FOF2_POSE] hm_heavy_overhand_001\n");
    else if(state == 9 && pose == 1) log("[FOF2_POSE] hm_heavy_overhand_002\n");
    else if(state == 9 && pose == 2) log("[FOF2_POSE] hm_heavy_overhand_003\n");
    else if(state == 9 && pose == 3) log("[FOF2_POSE] hm_heavy_overhand_004\n");
    else if(state == 9 && pose == 4) log("[FOF2_POSE] hm_heavy_overhand_005\n");
    else if(state == 9 && pose == 5) log("[FOF2_POSE] hm_heavy_overhand_006\n");
    else if(state == 9 && pose == 6) log("[FOF2_POSE] hm_heavy_overhand_007\n");
    else if(state == 9 && pose == 7) log("[FOF2_POSE] hm_heavy_overhand_008\n");
    else if(state == 9 && pose == 8) log("[FOF2_POSE] hm_heavy_overhand_009\n");
    else if(state == 9 && pose == 9) log("[FOF2_POSE] hm_heavy_overhand_010\n");
    else if(state == 10 && pose == 12) log("[FOF2_POSE] hm_taunt_hesitate_001\n");
    else if(state == 10 && pose == 13) log("[FOF2_POSE] hm_taunt_hesitate_002\n");
    else if(state == 10 && pose == 14) log("[FOF2_POSE] hm_taunt_hesitate_003\n");
    else if(state == 10 && pose == 15) log("[FOF2_POSE] hm_taunt_hesitate_004\n");
    else if(state == 10 && pose == 16) log("[FOF2_POSE] hm_taunt_hesitate_005\n");
    else if(state == 10 && pose == 17) log("[FOF2_POSE] hm_taunt_hesitate_006\n");
    else if(state == 10 && pose == 18) log("[FOF2_POSE] hm_taunt_hesitate_007\n");
    else if(state == 10 && pose == 19) log("[FOF2_POSE] hm_taunt_hesitate_008\n");
    else if(state == 11 && pose == 0) log("[FOF2_POSE] hm_light_pain_001\n");
    else if(state == 11 && pose == 1) log("[FOF2_POSE] hm_light_pain_002\n");
    else if(state == 11 && pose == 2) log("[FOF2_POSE] hm_light_pain_003\n");
    else if(state == 11 && pose == 3) log("[FOF2_POSE] hm_light_pain_004\n");
    else if(state == 11 && pose == 4) log("[FOF2_POSE] hm_light_pain_005\n");
    else if(state == 12 && pose == 0) log("[FOF2_POSE] hm_heavy_pain_001\n");
    else if(state == 12 && pose == 1) log("[FOF2_POSE] hm_heavy_pain_002\n");
    else if(state == 12 && pose == 2) log("[FOF2_POSE] hm_heavy_pain_003\n");
    else if(state == 12 && pose == 3) log("[FOF2_POSE] hm_heavy_pain_004\n");
    else if(state == 12 && pose == 4) log("[FOF2_POSE] hm_heavy_pain_005\n");
    else if(state == 12 && pose == 5) log("[FOF2_POSE] hm_heavy_pain_006\n");
    else if(state == 12 && pose == 6) log("[FOF2_POSE] hm_heavy_pain_007\n");
    else if(state == 13 && pose == 0) log("[FOF2_POSE] hm_knockdown_fall_001\n");
    else if(state == 13 && pose == 1) log("[FOF2_POSE] hm_knockdown_fall_002\n");
    else if(state == 13 && pose == 2) log("[FOF2_POSE] hm_knockdown_fall_003\n");
    else if(state == 13 && pose == 3) log("[FOF2_POSE] hm_knockdown_fall_004\n");
    else if(state == 13 && pose == 4) log("[FOF2_POSE] hm_knockdown_fall_005\n");
    else if(state == 13 && pose == 5) log("[FOF2_POSE] hm_knockdown_fall_006\n");
    else if(state == 13 && pose == 6) log("[FOF2_POSE] hm_knockdown_fall_007\n");
    else if(state == 13 && pose == 7) log("[FOF2_POSE] hm_knockdown_fall_008\n");
    else if(state == 14 && pose == 8) log("[FOF2_POSE] hm_down_001\n");
    else if(state == 14 && pose == 9) log("[FOF2_POSE] hm_down_002\n");
    else if(state == 14 && pose == 10) log("[FOF2_POSE] hm_down_003\n");
    else if(state == 14 && pose == 11) log("[FOF2_POSE] hm_down_004\n");
    else if(state == 14 && pose == 12) log("[FOF2_POSE] hm_down_005\n");
    else if(state == 14 && pose == 13) log("[FOF2_POSE] hm_down_006\n");
    else if(state == 15 && pose == 0) log("[FOF2_POSE] hm_rise_001\n");
    else if(state == 15 && pose == 1) log("[FOF2_POSE] hm_rise_002\n");
    else if(state == 15 && pose == 2) log("[FOF2_POSE] hm_rise_003\n");
    else if(state == 15 && pose == 3) log("[FOF2_POSE] hm_rise_004\n");
    else if(state == 15 && pose == 4) log("[FOF2_POSE] hm_rise_005\n");
    else if(state == 15 && pose == 5) log("[FOF2_POSE] hm_rise_006\n");
    else if(state == 15 && pose == 6) log("[FOF2_POSE] hm_rise_007\n");
    else if(state == 15 && pose == 7) log("[FOF2_POSE] hm_rise_008\n");
    else if(state == 16 && pose == 0) log("[FOF2_POSE] hm_death_001\n");
    else if(state == 16 && pose == 1) log("[FOF2_POSE] hm_death_002\n");
    else if(state == 16 && pose == 2) log("[FOF2_POSE] hm_death_003\n");
    else if(state == 16 && pose == 3) log("[FOF2_POSE] hm_death_004\n");
    else if(state == 16 && pose == 4) log("[FOF2_POSE] hm_death_005\n");
    else if(state == 16 && pose == 5) log("[FOF2_POSE] hm_death_006\n");
    else if(state == 16 && pose == 6) log("[FOF2_POSE] hm_death_007\n");
    else if(state == 16 && pose == 7) log("[FOF2_POSE] hm_death_008\n");
    else if(state == 16 && pose == 8) log("[FOF2_POSE] hm_death_009\n");
    else if(state == 16 && pose == 9) log("[FOF2_POSE] hm_death_010\n");
}
// END GENERATED HM POSE LOGGER

// BEGIN GENERATED HM SHOWCASE MAPPING
int hm_showcase_map(void self, int request)
{
    if(request == 0)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_SPAWN"));
        setentityvar(self, "showcase_state", 0);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 0);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(0, 0);
        return 1;
    }
    else if(request == 1)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_SPAWN"));
        setentityvar(self, "showcase_state", 0);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 0);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(0, 1);
        return 1;
    }
    else if(request == 2)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_SPAWN"));
        setentityvar(self, "showcase_state", 0);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 0);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(0, 2);
        return 1;
    }
    else if(request == 3)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_SPAWN"));
        setentityvar(self, "showcase_state", 0);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 0);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(0, 3);
        return 1;
    }
    else if(request == 4)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_SPAWN"));
        setentityvar(self, "showcase_state", 0);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 0);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(0, 4);
        return 1;
    }
    else if(request == 5)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_SPAWN"));
        setentityvar(self, "showcase_state", 0);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 0);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(0, 5);
        return 1;
    }
    else if(request == 6)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 1);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 1);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(1, 0);
        return 1;
    }
    else if(request == 7)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 1);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 1);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(1, 1);
        return 1;
    }
    else if(request == 8)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 1);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 1);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(1, 2);
        return 1;
    }
    else if(request == 9)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 1);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 1);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(1, 3);
        return 1;
    }
    else if(request == 10)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 1);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 1);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(1, 4);
        return 1;
    }
    else if(request == 11)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 1);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 1);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(1, 5);
        return 1;
    }
    else if(request == 12)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 1);
        setentityvar(self, "showcase_frame", 6);
        updateframe(self, 6);
        setentityvar(self, "logged_state", 1);
        setentityvar(self, "logged_pose", 6);
        hm_log_pose(1, 6);
        return 1;
    }
    else if(request == 13)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 1);
        setentityvar(self, "showcase_frame", 7);
        updateframe(self, 7);
        setentityvar(self, "logged_state", 1);
        setentityvar(self, "logged_pose", 7);
        hm_log_pose(1, 7);
        return 1;
    }
    else if(request == 14)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 2);
        setentityvar(self, "showcase_frame", 8);
        updateframe(self, 8);
        setentityvar(self, "logged_state", 2);
        setentityvar(self, "logged_pose", 8);
        hm_log_pose(2, 8);
        return 1;
    }
    else if(request == 15)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 2);
        setentityvar(self, "showcase_frame", 9);
        updateframe(self, 9);
        setentityvar(self, "logged_state", 2);
        setentityvar(self, "logged_pose", 9);
        hm_log_pose(2, 9);
        return 1;
    }
    else if(request == 16)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 2);
        setentityvar(self, "showcase_frame", 10);
        updateframe(self, 10);
        setentityvar(self, "logged_state", 2);
        setentityvar(self, "logged_pose", 10);
        hm_log_pose(2, 10);
        return 1;
    }
    else if(request == 17)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 2);
        setentityvar(self, "showcase_frame", 11);
        updateframe(self, 11);
        setentityvar(self, "logged_state", 2);
        setentityvar(self, "logged_pose", 11);
        hm_log_pose(2, 11);
        return 1;
    }
    else if(request == 18)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 3);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 3);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(3, 0);
        return 1;
    }
    else if(request == 19)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 3);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 3);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(3, 1);
        return 1;
    }
    else if(request == 20)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 3);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 3);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(3, 2);
        return 1;
    }
    else if(request == 21)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 3);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 3);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(3, 3);
        return 1;
    }
    else if(request == 22)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(4, 4);
        return 1;
    }
    else if(request == 23)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(4, 5);
        return 1;
    }
    else if(request == 24)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 6);
        updateframe(self, 6);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 6);
        hm_log_pose(4, 6);
        return 1;
    }
    else if(request == 25)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 7);
        updateframe(self, 7);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 7);
        hm_log_pose(4, 7);
        return 1;
    }
    else if(request == 26)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 8);
        updateframe(self, 8);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 8);
        hm_log_pose(4, 8);
        return 1;
    }
    else if(request == 27)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 9);
        updateframe(self, 9);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 9);
        hm_log_pose(4, 9);
        return 1;
    }
    else if(request == 28)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 10);
        updateframe(self, 10);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 10);
        hm_log_pose(4, 10);
        return 1;
    }
    else if(request == 29)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 11);
        updateframe(self, 11);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 11);
        hm_log_pose(4, 11);
        return 1;
    }
    else if(request == 30)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 12);
        updateframe(self, 12);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 12);
        hm_log_pose(4, 12);
        return 1;
    }
    else if(request == 31)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 13);
        updateframe(self, 13);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 13);
        hm_log_pose(4, 13);
        return 1;
    }
    else if(request == 32)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 14);
        updateframe(self, 14);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 14);
        hm_log_pose(4, 14);
        return 1;
    }
    else if(request == 33)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 4);
        setentityvar(self, "showcase_frame", 15);
        updateframe(self, 15);
        setentityvar(self, "logged_state", 4);
        setentityvar(self, "logged_pose", 15);
        hm_log_pose(4, 15);
        return 1;
    }
    else if(request == 34)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 5);
        setentityvar(self, "showcase_frame", 16);
        updateframe(self, 16);
        setentityvar(self, "logged_state", 5);
        setentityvar(self, "logged_pose", 16);
        hm_log_pose(5, 16);
        return 1;
    }
    else if(request == 35)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 5);
        setentityvar(self, "showcase_frame", 17);
        updateframe(self, 17);
        setentityvar(self, "logged_state", 5);
        setentityvar(self, "logged_pose", 17);
        hm_log_pose(5, 17);
        return 1;
    }
    else if(request == 36)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 5);
        setentityvar(self, "showcase_frame", 18);
        updateframe(self, 18);
        setentityvar(self, "logged_state", 5);
        setentityvar(self, "logged_pose", 18);
        hm_log_pose(5, 18);
        return 1;
    }
    else if(request == 37)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_WALK"));
        setentityvar(self, "showcase_state", 5);
        setentityvar(self, "showcase_frame", 19);
        updateframe(self, 19);
        setentityvar(self, "logged_state", 5);
        setentityvar(self, "logged_pose", 19);
        hm_log_pose(5, 19);
        return 1;
    }
    else if(request == 38)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_TURN"));
        setentityvar(self, "showcase_state", 6);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 6);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(6, 0);
        return 1;
    }
    else if(request == 39)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_TURN"));
        setentityvar(self, "showcase_state", 6);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 6);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(6, 1);
        return 1;
    }
    else if(request == 40)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_TURN"));
        setentityvar(self, "showcase_state", 6);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 6);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(6, 2);
        return 1;
    }
    else if(request == 41)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_TURN"));
        setentityvar(self, "showcase_state", 6);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 6);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(6, 3);
        return 1;
    }
    else if(request == 42)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK1"));
        setentityvar(self, "showcase_state", 7);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 7);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(7, 0);
        return 1;
    }
    else if(request == 43)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK1"));
        setentityvar(self, "showcase_state", 7);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 7);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(7, 1);
        return 1;
    }
    else if(request == 44)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK1"));
        setentityvar(self, "showcase_state", 7);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 7);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(7, 2);
        return 1;
    }
    else if(request == 45)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK1"));
        setentityvar(self, "showcase_state", 7);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 7);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(7, 3);
        return 1;
    }
    else if(request == 46)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK1"));
        setentityvar(self, "showcase_state", 7);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 7);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(7, 4);
        return 1;
    }
    else if(request == 47)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK1"));
        setentityvar(self, "showcase_state", 7);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 7);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(7, 5);
        return 1;
    }
    else if(request == 48)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK1"));
        setentityvar(self, "showcase_state", 7);
        setentityvar(self, "showcase_frame", 6);
        updateframe(self, 6);
        setentityvar(self, "logged_state", 7);
        setentityvar(self, "logged_pose", 6);
        hm_log_pose(7, 6);
        return 1;
    }
    else if(request == 49)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK1"));
        setentityvar(self, "showcase_state", 7);
        setentityvar(self, "showcase_frame", 7);
        updateframe(self, 7);
        setentityvar(self, "logged_state", 7);
        setentityvar(self, "logged_pose", 7);
        hm_log_pose(7, 7);
        return 1;
    }
    else if(request == 50)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK2"));
        setentityvar(self, "showcase_state", 8);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 8);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(8, 0);
        return 1;
    }
    else if(request == 51)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK2"));
        setentityvar(self, "showcase_state", 8);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 8);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(8, 1);
        return 1;
    }
    else if(request == 52)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK2"));
        setentityvar(self, "showcase_state", 8);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 8);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(8, 2);
        return 1;
    }
    else if(request == 53)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK2"));
        setentityvar(self, "showcase_state", 8);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 8);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(8, 3);
        return 1;
    }
    else if(request == 54)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK2"));
        setentityvar(self, "showcase_state", 8);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 8);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(8, 4);
        return 1;
    }
    else if(request == 55)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK2"));
        setentityvar(self, "showcase_state", 8);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 8);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(8, 5);
        return 1;
    }
    else if(request == 56)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK2"));
        setentityvar(self, "showcase_state", 8);
        setentityvar(self, "showcase_frame", 6);
        updateframe(self, 6);
        setentityvar(self, "logged_state", 8);
        setentityvar(self, "logged_pose", 6);
        hm_log_pose(8, 6);
        return 1;
    }
    else if(request == 57)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK2"));
        setentityvar(self, "showcase_state", 8);
        setentityvar(self, "showcase_frame", 7);
        updateframe(self, 7);
        setentityvar(self, "logged_state", 8);
        setentityvar(self, "logged_pose", 7);
        hm_log_pose(8, 7);
        return 1;
    }
    else if(request == 58)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(9, 0);
        return 1;
    }
    else if(request == 59)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(9, 1);
        return 1;
    }
    else if(request == 60)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(9, 2);
        return 1;
    }
    else if(request == 61)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(9, 3);
        return 1;
    }
    else if(request == 62)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(9, 4);
        return 1;
    }
    else if(request == 63)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(9, 5);
        return 1;
    }
    else if(request == 64)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 6);
        updateframe(self, 6);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 6);
        hm_log_pose(9, 6);
        return 1;
    }
    else if(request == 65)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 7);
        updateframe(self, 7);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 7);
        hm_log_pose(9, 7);
        return 1;
    }
    else if(request == 66)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 8);
        updateframe(self, 8);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 8);
        hm_log_pose(9, 8);
        return 1;
    }
    else if(request == 67)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_ATTACK3"));
        setentityvar(self, "showcase_state", 9);
        setentityvar(self, "showcase_frame", 9);
        updateframe(self, 9);
        setentityvar(self, "logged_state", 9);
        setentityvar(self, "logged_pose", 9);
        hm_log_pose(9, 9);
        return 1;
    }
    else if(request == 68)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 10);
        setentityvar(self, "showcase_frame", 12);
        updateframe(self, 12);
        setentityvar(self, "logged_state", 10);
        setentityvar(self, "logged_pose", 12);
        hm_log_pose(10, 12);
        return 1;
    }
    else if(request == 69)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 10);
        setentityvar(self, "showcase_frame", 13);
        updateframe(self, 13);
        setentityvar(self, "logged_state", 10);
        setentityvar(self, "logged_pose", 13);
        hm_log_pose(10, 13);
        return 1;
    }
    else if(request == 70)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 10);
        setentityvar(self, "showcase_frame", 14);
        updateframe(self, 14);
        setentityvar(self, "logged_state", 10);
        setentityvar(self, "logged_pose", 14);
        hm_log_pose(10, 14);
        return 1;
    }
    else if(request == 71)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 10);
        setentityvar(self, "showcase_frame", 15);
        updateframe(self, 15);
        setentityvar(self, "logged_state", 10);
        setentityvar(self, "logged_pose", 15);
        hm_log_pose(10, 15);
        return 1;
    }
    else if(request == 72)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 10);
        setentityvar(self, "showcase_frame", 16);
        updateframe(self, 16);
        setentityvar(self, "logged_state", 10);
        setentityvar(self, "logged_pose", 16);
        hm_log_pose(10, 16);
        return 1;
    }
    else if(request == 73)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 10);
        setentityvar(self, "showcase_frame", 17);
        updateframe(self, 17);
        setentityvar(self, "logged_state", 10);
        setentityvar(self, "logged_pose", 17);
        hm_log_pose(10, 17);
        return 1;
    }
    else if(request == 74)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 10);
        setentityvar(self, "showcase_frame", 18);
        updateframe(self, 18);
        setentityvar(self, "logged_state", 10);
        setentityvar(self, "logged_pose", 18);
        hm_log_pose(10, 18);
        return 1;
    }
    else if(request == 75)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_IDLE"));
        setentityvar(self, "showcase_state", 10);
        setentityvar(self, "showcase_frame", 19);
        updateframe(self, 19);
        setentityvar(self, "logged_state", 10);
        setentityvar(self, "logged_pose", 19);
        hm_log_pose(10, 19);
        return 1;
    }
    else if(request == 76)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN"));
        setentityvar(self, "showcase_state", 11);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 11);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(11, 0);
        return 1;
    }
    else if(request == 77)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN"));
        setentityvar(self, "showcase_state", 11);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 11);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(11, 1);
        return 1;
    }
    else if(request == 78)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN"));
        setentityvar(self, "showcase_state", 11);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 11);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(11, 2);
        return 1;
    }
    else if(request == 79)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN"));
        setentityvar(self, "showcase_state", 11);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 11);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(11, 3);
        return 1;
    }
    else if(request == 80)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN"));
        setentityvar(self, "showcase_state", 11);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 11);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(11, 4);
        return 1;
    }
    else if(request == 81)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN2"));
        setentityvar(self, "showcase_state", 12);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 12);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(12, 0);
        return 1;
    }
    else if(request == 82)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN2"));
        setentityvar(self, "showcase_state", 12);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 12);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(12, 1);
        return 1;
    }
    else if(request == 83)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN2"));
        setentityvar(self, "showcase_state", 12);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 12);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(12, 2);
        return 1;
    }
    else if(request == 84)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN2"));
        setentityvar(self, "showcase_state", 12);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 12);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(12, 3);
        return 1;
    }
    else if(request == 85)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN2"));
        setentityvar(self, "showcase_state", 12);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 12);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(12, 4);
        return 1;
    }
    else if(request == 86)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN2"));
        setentityvar(self, "showcase_state", 12);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 12);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(12, 5);
        return 1;
    }
    else if(request == 87)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_PAIN2"));
        setentityvar(self, "showcase_state", 12);
        setentityvar(self, "showcase_frame", 6);
        updateframe(self, 6);
        setentityvar(self, "logged_state", 12);
        setentityvar(self, "logged_pose", 6);
        hm_log_pose(12, 6);
        return 1;
    }
    else if(request == 88)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 13);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 13);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(13, 0);
        return 1;
    }
    else if(request == 89)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 13);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 13);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(13, 1);
        return 1;
    }
    else if(request == 90)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 13);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 13);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(13, 2);
        return 1;
    }
    else if(request == 91)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 13);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 13);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(13, 3);
        return 1;
    }
    else if(request == 92)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 13);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 13);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(13, 4);
        return 1;
    }
    else if(request == 93)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 13);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 13);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(13, 5);
        return 1;
    }
    else if(request == 94)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 13);
        setentityvar(self, "showcase_frame", 6);
        updateframe(self, 6);
        setentityvar(self, "logged_state", 13);
        setentityvar(self, "logged_pose", 6);
        hm_log_pose(13, 6);
        return 1;
    }
    else if(request == 95)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 13);
        setentityvar(self, "showcase_frame", 7);
        updateframe(self, 7);
        setentityvar(self, "logged_state", 13);
        setentityvar(self, "logged_pose", 7);
        hm_log_pose(13, 7);
        return 1;
    }
    else if(request == 96)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 14);
        setentityvar(self, "showcase_frame", 8);
        updateframe(self, 8);
        setentityvar(self, "logged_state", 14);
        setentityvar(self, "logged_pose", 8);
        hm_log_pose(14, 8);
        return 1;
    }
    else if(request == 97)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 14);
        setentityvar(self, "showcase_frame", 9);
        updateframe(self, 9);
        setentityvar(self, "logged_state", 14);
        setentityvar(self, "logged_pose", 9);
        hm_log_pose(14, 9);
        return 1;
    }
    else if(request == 98)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 14);
        setentityvar(self, "showcase_frame", 10);
        updateframe(self, 10);
        setentityvar(self, "logged_state", 14);
        setentityvar(self, "logged_pose", 10);
        hm_log_pose(14, 10);
        return 1;
    }
    else if(request == 99)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 14);
        setentityvar(self, "showcase_frame", 11);
        updateframe(self, 11);
        setentityvar(self, "logged_state", 14);
        setentityvar(self, "logged_pose", 11);
        hm_log_pose(14, 11);
        return 1;
    }
    else if(request == 100)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 14);
        setentityvar(self, "showcase_frame", 12);
        updateframe(self, 12);
        setentityvar(self, "logged_state", 14);
        setentityvar(self, "logged_pose", 12);
        hm_log_pose(14, 12);
        return 1;
    }
    else if(request == 101)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_FALL"));
        setentityvar(self, "showcase_state", 14);
        setentityvar(self, "showcase_frame", 13);
        updateframe(self, 13);
        setentityvar(self, "logged_state", 14);
        setentityvar(self, "logged_pose", 13);
        hm_log_pose(14, 13);
        return 1;
    }
    else if(request == 102)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_RISE"));
        setentityvar(self, "showcase_state", 15);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 15);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(15, 0);
        return 1;
    }
    else if(request == 103)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_RISE"));
        setentityvar(self, "showcase_state", 15);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 15);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(15, 1);
        return 1;
    }
    else if(request == 104)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_RISE"));
        setentityvar(self, "showcase_state", 15);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 15);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(15, 2);
        return 1;
    }
    else if(request == 105)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_RISE"));
        setentityvar(self, "showcase_state", 15);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 15);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(15, 3);
        return 1;
    }
    else if(request == 106)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_RISE"));
        setentityvar(self, "showcase_state", 15);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 15);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(15, 4);
        return 1;
    }
    else if(request == 107)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_RISE"));
        setentityvar(self, "showcase_state", 15);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 15);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(15, 5);
        return 1;
    }
    else if(request == 108)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_RISE"));
        setentityvar(self, "showcase_state", 15);
        setentityvar(self, "showcase_frame", 6);
        updateframe(self, 6);
        setentityvar(self, "logged_state", 15);
        setentityvar(self, "logged_pose", 6);
        hm_log_pose(15, 6);
        return 1;
    }
    else if(request == 109)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_RISE"));
        setentityvar(self, "showcase_state", 15);
        setentityvar(self, "showcase_frame", 7);
        updateframe(self, 7);
        setentityvar(self, "logged_state", 15);
        setentityvar(self, "logged_pose", 7);
        hm_log_pose(15, 7);
        return 1;
    }
    else if(request == 110)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 0);
        updateframe(self, 0);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 0);
        hm_log_pose(16, 0);
        return 1;
    }
    else if(request == 111)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 1);
        updateframe(self, 1);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 1);
        hm_log_pose(16, 1);
        return 1;
    }
    else if(request == 112)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 2);
        updateframe(self, 2);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 2);
        hm_log_pose(16, 2);
        return 1;
    }
    else if(request == 113)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 3);
        updateframe(self, 3);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 3);
        hm_log_pose(16, 3);
        return 1;
    }
    else if(request == 114)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 4);
        updateframe(self, 4);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 4);
        hm_log_pose(16, 4);
        return 1;
    }
    else if(request == 115)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 5);
        updateframe(self, 5);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 5);
        hm_log_pose(16, 5);
        return 1;
    }
    else if(request == 116)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 6);
        updateframe(self, 6);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 6);
        hm_log_pose(16, 6);
        return 1;
    }
    else if(request == 117)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 7);
        updateframe(self, 7);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 7);
        hm_log_pose(16, 7);
        return 1;
    }
    else if(request == 118)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 8);
        updateframe(self, 8);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 8);
        hm_log_pose(16, 8);
        return 1;
    }
    else if(request == 119)
    {
        changeentityproperty(self, "animation", openborconstant("ANI_DIE"));
        setentityvar(self, "showcase_state", 16);
        setentityvar(self, "showcase_frame", 9);
        updateframe(self, 9);
        setentityvar(self, "logged_state", 16);
        setentityvar(self, "logged_pose", 9);
        hm_log_pose(16, 9);
        return 1;
    }
    return 0;
}
// END GENERATED HM SHOWCASE MAPPING

int hm_showcase(void self, int request)
{
    int frame;
    if(request >= 0 && request <= 119)
    {
        hm_velocity(self, 0, 0);
        changeentityproperty(self, "takeaction", NULL());
        changeentityproperty(self, "aiflag", "attacking", 0);
        changeentityproperty(self, "aiflag", "drop", 0);
        changeentityproperty(self, "aiflag", "falling", 0);
        changeentityproperty(self, "aiflag", "rising", 0);
        hm_release_attack_token(self);
        if(getentityvar(self, "showcase_active") != 1 || request != getentityvar(self, "showcase_pose"))
        {
            if(hm_showcase_map(self, request) != 1) return 0;
            setentityvar(self, "showcase_active", 1);
            setentityvar(self, "showcase_pose", request);
        }
        frame = getentityvar(self, "showcase_frame");
        updateframe(self, frame);
        return 1;
    }
    if(getentityvar(self, "showcase_active") == 1)
    {
        setentityvar(self, "showcase_active", 0);
        setentityvar(self, "showcase_pose", -1);
        setentityvar(self, "qa_mode", 0);
        setentityvar(self, "qa_hold", 0);
        setentityvar(self, "last_request", 0);
        setentityvar(self, "logged_state", -1);
        setentityvar(self, "logged_pose", -1);
        setentityvar(self, "state", -1);
        changeentityproperty(self, "aiflag", "attacking", 0);
        changeentityproperty(self, "aiflag", "drop", 0);
        changeentityproperty(self, "aiflag", "falling", 0);
        changeentityproperty(self, "aiflag", "rising", 0);
        hm_velocity(self, 0, 0);
        changeentityproperty(self, "takeaction", NULL());
        hm_enter(self, 1);
        log("[FOF2_HM_SHOWCASE] mode=off ai=active\n");
    }
    return 0;
}

void hm_present(void self)
{
    int state;
    int tick;
    int pose;
    state = getentityvar(self, "state");
    tick = getentityvar(self, "state_tick");
    pose = hm_pose(self, state, tick);
    if(state == 0 && pose > 5) pose = 5;
    if((state == 2 || state == 3 || state == 5) && pose > 19) pose = 19;
    if(state == 6 && pose > 3) pose = 3;
    if((state == 7 || state == 8) && pose > 7) pose = 7;
    if(state == 9 && pose > 9) pose = 9;
    if(state == 10 && pose > 19) pose = 19;
    if(state == 11 && pose > 4) pose = 4;
    if(state == 12 && pose > 6) pose = 6;
    if(state == 13 && pose > 7) pose = 7;
    if(state == 15 && pose > 7) pose = 7;
    if(state == 16 && pose > 9) pose = 9;
    setentityvar(self, "pose", pose);
    updateframe(self, pose);
    if(getentityvar(self, "logged_state") != state || getentityvar(self, "logged_pose") != pose)
    {
        setentityvar(self, "logged_state", state);
        setentityvar(self, "logged_pose", pose);
        hm_log_pose(state, pose);
    }
}

void hm_request_state(void self, int request)
{
    int state;
    if(request < 1 || request > 17) return;
    state = request - 1;
    if(getentityvar(self, "state") == state) setentityvar(self, "state", -1);
    if(state == 13) setentityvar(self, "fall_real", 0);
    if(state == 16) setentityvar(self, "death_real", 0);
    hm_enter(self, state);
    setentityvar(self, "qa_hold", hm_state_duration(state));
}

void hm_fixed_step(void self)
{
    void target;
    void token;
    int initialized;
    int tick;
    int state;
    int request;
    int health;
    int previous_health;
    int x;
    int z;
    int tx;
    int tz;
    int dx;
    int dz;
    int distance;
    int direction;
    int old_x;
    int old_z;
    int choice;
    int native_drop;
    int native_falling;
    int qa_hold;
    int pose_request;

    if(self == NULL()) return;
    if(getglobalvar("fof2_combat_evidence_mode") == 1)
    {
        setglobalvar("fof2_hm_state", getentityvar(self, "state"));
        setglobalvar("fof2_hm_state_tick", getentityvar(self, "state_tick"));
        setglobalvar("fof2_hm_clock_steps", getglobalvar("fof2_hm_clock_steps") + 1);
    }
    setglobalvar("fof2_qa_hm_entity", self);
    initialized = getentityvar(self, "initialized");
    if(initialized != 1)
    {
        changeentityproperty(self, "noaicontrol", 1);
        setentityvar(self, "initialized", 1);
        setentityvar(self, "state", -1);
        setentityvar(self, "travel", 0);
        setentityvar(self, "attack_cooldown", 0);
        setentityvar(self, "last_request", 0);
        setentityvar(self, "qa_hold", 0);
        setentityvar(self, "qa_mode", 0);
        setentityvar(self, "logged_state", -1);
        setentityvar(self, "logged_pose", -1);
        setentityvar(self, "fall_real", 0);
        setentityvar(self, "death_real", 0);
        setentityvar(self, "showcase_active", 0);
        setentityvar(self, "showcase_pose", -1);
        setentityvar(self, "showcase_frame", 0);
        setentityvar(self, "showcase_state", 0);
        setentityvar(self, "clock_valid", 0);
        setentityvar(self, "clock_time", openborvariant("elapsed_time"));
        setentityvar(self, "clock_accumulator", 0);
        setentityvar(self, "last_health", getentityproperty(self, "health"));
        setentityvar(self, "old_x", getentityproperty(self, "x"));
        setentityvar(self, "old_z", getentityproperty(self, "z"));
        hm_enter(self, 0);
        log("[FOF2_HM_AI] initialized root=96,156 owner=thinkscript\n");
        return;
    }

    pose_request = getglobalvar("fof2_qa_hm_pose");
    if(typeof(pose_request) != openborconstant("VT_INTEGER")) pose_request = -1;
    if(hm_showcase(self, pose_request) == 1) return;

    tick = getentityvar(self, "state_tick") + 1;
    setentityvar(self, "state_tick", tick);
    state = getentityvar(self, "state");
    health = getentityproperty(self, "health");
    previous_health = getentityvar(self, "last_health");
    native_drop = getentityproperty(self, "aiflag", "drop");
    native_falling = getentityproperty(self, "aiflag", "falling");
    if(health <= 0)
    {
        if(getentityvar(self, "death_real") != 1)
        {
            setentityvar(self, "death_real", 1);
            setentityvar(self, "qa_hold", 0);
            setentityvar(self, "qa_mode", 0);
            if(state == 16) setentityvar(self, "state", -1);
            hm_enter(self, 16);
            log("[FOF2_HM_AI] death=health_zero\n");
        }
    }
    else if(state != 13 && state != 14 && state != 15 && state != 16 && (native_drop || native_falling))
    {
        setentityvar(self, "fall_real", 1);
        setentityvar(self, "qa_hold", 0);
        hm_enter(self, 13);
        log("[FOF2_HM_AI] knockdown=native_drop\n");
    }
    else if(health < previous_health && state != 13 && state != 14 && state != 15 && state != 16)
    {
        if(previous_health - health >= 12) hm_enter(self, 12);
        else hm_enter(self, 11);
    }
    setentityvar(self, "last_health", health);

    request = getglobalvar("fof2_qa_hm_request");
    if(request == 0)
    {
        setentityvar(self, "last_request", 0);
        if(getentityvar(self, "qa_mode") == 1)
        {
            setentityvar(self, "qa_mode", 0);
            setentityvar(self, "qa_hold", 0);
            setentityvar(self, "state", -1);
            hm_enter(self, 1);
            log("[FOF2_HM_QA] mode=off ai=active\n");
        }
    }
    if(health > 0 && request >= 1 && request <= 17 && request != getentityvar(self, "last_request"))
    {
        setentityvar(self, "last_request", request);
        setentityvar(self, "qa_mode", 1);
        hm_request_state(self, request);
        log("[FOF2_HM_QA] mode=on request=applied\n");
    }

    qa_hold = getentityvar(self, "qa_hold");
    if(getentityvar(self, "qa_mode") == 1)
    {
        if(qa_hold > 0) setentityvar(self, "qa_hold", qa_hold - 1);
        hm_present(self);
        return;
    }

    state = getentityvar(self, "state");
    tick = getentityvar(self, "state_tick");
    if(state == 16)
    {
        hm_present(self);
        if(tick >= 60)
        {
            if(getentityvar(self, "death_real") == 1)
            {
                log("[FOF2_HM_AI] death=finished_remove\n");
                killentity(self);
            }
            else hm_enter(self, 1);
        }
        return;
    }
    if(state == 0 && tick >= 34) hm_enter(self, 1);
    else if(state == 2 && tick >= 24) hm_enter(self, 3);
    else if(state == 3 && tick >= 12) hm_enter(self, 4);
    else if(state == 5 && tick >= 12)
    {
        token = getglobalvar("fof2_enemy_attack_token");
        if(token == NULL() || token == self)
        {
            setglobalvar("fof2_enemy_attack_token", self);
            choice = (openborvariant("elapsed_time") / 120) % 3;
            if(typeof(getglobalvar("fof2_test_hm_choice")) == openborconstant("VT_INTEGER"))
            {
                if(getglobalvar("fof2_test_hm_choice") >= 0 && getglobalvar("fof2_test_hm_choice") <= 2)
                {
                    choice = getglobalvar("fof2_test_hm_choice");
                    log("[FOF2_HM_AI] attack_choice=test_override\n");
                }
            }
            setentityvar(self, "last_attack_choice", choice);
            log("[FOF2_HM_AI] attack_token_grant\n");
            hm_enter(self, 7 + choice);
        }
        else hm_enter(self, 1);
    }
    else if(state == 6 && tick >= 10) hm_enter(self, 4);
    else if(state == 7 && tick >= 28) hm_enter(self, 1);
    else if(state == 8 && tick >= 34) hm_enter(self, 1);
    else if(state == 9 && tick >= 48) hm_enter(self, 1);
    else if(state == 10 && tick >= 52) hm_enter(self, 3);
    else if(state == 11 && tick >= 18) hm_enter(self, 1);
    else if(state == 12 && tick >= 26) hm_enter(self, 1);
    else if(state == 13 && tick >= 38 && (getentityvar(self, "fall_real") != 1 || native_falling == 0)) hm_enter(self, 14);
    else if(state == 14 && tick >= 42) hm_enter(self, 15);
    else if(state == 15 && tick >= 42)
    {
        setentityvar(self, "fall_real", 0);
        hm_enter(self, 1);
    }

    state = getentityvar(self, "state");
    if(state == 0 || state == 2 || state == 3 || state == 5 || state == 6 || state >= 7)
    {
        hm_present(self);
        return;
    }

    target = findtarget(self);
    if(target == NULL())
    {
        if(state != 1) hm_enter(self, 1);
        hm_present(self);
        return;
    }
    x = getentityproperty(self, "x");
    z = getentityproperty(self, "z");
    tx = getentityproperty(target, "x");
    tz = getentityproperty(target, "z");
    dx = tx - x;
    dz = tz - z;
    distance = hm_abs(dx) + hm_abs(dz);
    direction = getentityproperty(self, "direction");
    if((dx < 0 && direction != 0) || (dx > 0 && direction != 1))
    {
        changeentityproperty(self, "direction", dx > 0);
        log("[FOF2_HM_AI] turn_token\n");
        hm_enter(self, 6);
    }
    else if(state == 1 && distance < 260)
    {
        log("[FOF2_HM_AI] aggro_token\n");
        hm_enter(self, 2);
    }
    else if(state == 4)
    {
        if(distance <= 68)
        {
            log("[FOF2_HM_AI] chase_token_release\n");
            hm_enter(self, 5);
        }
        else
        {
            if(dx < -6) hm_velocity(self, -1, 0);
            else if(dx > 6) hm_velocity(self, 1, 0);
            else if(dz < -4) hm_velocity(self, 0, -1);
            else if(dz > 4) hm_velocity(self, 0, 1);
            old_x = getentityvar(self, "old_x");
            old_z = getentityvar(self, "old_z");
            if(x != old_x || z != old_z) setentityvar(self, "travel", getentityvar(self, "travel") + 1);
            setentityvar(self, "old_x", x);
            setentityvar(self, "old_z", z);
        }
    }
    hm_present(self);
}

void main()
{
    void self;
    int now;
    int last;
    int delta;
    int accumulator;
    int pose_request;
    int was_showcase;
    self = getlocalvar("self");
    if(self == NULL()) return;
    setglobalvar("fof2_qa_hm_entity", self);
    if(getentityvar(self, "initialized") != 1)
    {
        hm_fixed_step(self);
        return;
    }
    pose_request = getglobalvar("fof2_qa_hm_pose");
    if(typeof(pose_request) != openborconstant("VT_INTEGER")) pose_request = -1;
    was_showcase = getentityvar(self, "showcase_active");
    if(hm_showcase(self, pose_request) == 1)
    {
        setentityvar(self, "clock_valid", 0);
        setentityvar(self, "clock_accumulator", 0);
        return;
    }
    if(was_showcase == 1)
    {
        setentityvar(self, "clock_valid", 0);
        setentityvar(self, "clock_accumulator", 0);
        return;
    }
    now = openborvariant("elapsed_time");
    if(getentityvar(self, "clock_valid") != 1)
    {
        setentityvar(self, "clock_valid", 1);
        setentityvar(self, "clock_time", now);
        setentityvar(self, "clock_accumulator", 0);
        return;
    }
    last = getentityvar(self, "clock_time");
    delta = now - last;
    setentityvar(self, "clock_time", now);
    if(delta < 0 || delta > openborconstant("THINK_SPEED"))
    {
        setentityvar(self, "clock_accumulator", 0);
        return;
    }
    accumulator = getentityvar(self, "clock_accumulator") + delta * 60;
    while(accumulator >= 200)
    {
        accumulator = accumulator - 200;
        hm_fixed_step(self);
    }
    setentityvar(self, "clock_accumulator", accumulator);
}
