/* Black Dave production controller for OpenBOR 4.0 Build 7949.
 * Engine elapsed_time is 200 Hz; an integer accumulator emits fixed 60 Hz
 * simulation steps.  updateframe() is the sole pose owner during Dave-owned
 * states.  Native control is restored only for zero-health life removal. */

void oncreate()
{
    void qa_script;
    setglobalvar("bd_state", 0);
    setglobalvar("bd_state_tick", 0);
    setglobalvar("bd_pose_start", 0);
    setglobalvar("bd_pose_count", 1);
    setglobalvar("bd_pose_total", 2);
    setglobalvar("bd_pose_loop", 0);
    setglobalvar("bd_pose_hold", 2);
    setglobalvar("bd_route", 0);
    setglobalvar("bd_step", 0);
    setglobalvar("bd_attack_live", 0);
    setglobalvar("bd_contact_latched", 0);
    setglobalvar("bd_confirmed_contact", 0);
    setglobalvar("bd_contact_pause", 0);
    setglobalvar("bd_walk_distance", 0);
    setglobalvar("bd_previous_x", 0);
    setglobalvar("bd_previous_z", 0);
    setglobalvar("bd_player", NULL());
    setglobalvar("bd_initialized", 0);
    setglobalvar("bd_owned", 0);
    setglobalvar("bd_dodge_invul", 0);
    setglobalvar("bd_attack_flag", 0);
    setglobalvar("bd_projectile_fired", 0);
    setglobalvar("bd_block_contact", 0);
    setglobalvar("bd_pending_direction", -1);
    setglobalvar("bd_jump_phase", 0);
    setglobalvar("bd_jump_phase_tick", 0);
    setglobalvar("bd_death_handoff", 0);
    setglobalvar("bd_buffered_route", 0);
    setglobalvar("bd_pending_attack", 0);
    setglobalvar("bd_pending_kick", 0);
    setglobalvar("bd_pending_power", 0);
    setglobalvar("bd_pending_ranged", 0);
    setglobalvar("bd_pending_jump", 0);
    setglobalvar("bd_clock_valid", 0);
    setglobalvar("bd_clock_time", 0);
    setglobalvar("bd_clock_accumulator", 0);
    setglobalvar("bd_qa_tick", 0);
    setglobalvar("bd_qa_request", -1);
    setglobalvar("bd_qa_player", NULL());
    qa_script = allocscript("black_dave_pose_qa", "packaged deterministic pose manifest");
    loadscript(qa_script, "data/scripts/black_dave_pose_qa.c");
    compilescript(qa_script);
    setglobalvar("bd_qa_script", qa_script);
    log("[FOF2_DAVE] production controller initialized\n");
}

int bd_abs(int value)
{
    if(value < 0) return -value;
    return value;
}

/* BEGIN GENERATED BLACK DAVE QA POSE ROUTER */
void bd_apply_qa_pose(void player, int request)
{
    int animation;
    int frame;
    animation = -1;
    frame = 0;
    if(request == 0)
    {
        animation = openborconstant("ANI_SPAWN");
        frame = 0;
        log("[FOF2_POSE] bd_entry_respawn_001\n");
    }
    if(request == 1)
    {
        animation = openborconstant("ANI_SPAWN");
        frame = 1;
        log("[FOF2_POSE] bd_entry_respawn_002\n");
    }
    if(request == 2)
    {
        animation = openborconstant("ANI_SPAWN");
        frame = 2;
        log("[FOF2_POSE] bd_entry_respawn_003\n");
    }
    if(request == 3)
    {
        animation = openborconstant("ANI_SPAWN");
        frame = 3;
        log("[FOF2_POSE] bd_entry_respawn_004\n");
    }
    if(request == 4)
    {
        animation = openborconstant("ANI_SPAWN");
        frame = 4;
        log("[FOF2_POSE] bd_entry_respawn_005\n");
    }
    if(request == 5)
    {
        animation = openborconstant("ANI_SPAWN");
        frame = 5;
        log("[FOF2_POSE] bd_entry_respawn_006\n");
    }
    if(request == 6)
    {
        animation = openborconstant("ANI_IDLE");
        frame = 0;
        log("[FOF2_POSE] bd_idle_001\n");
    }
    if(request == 7)
    {
        animation = openborconstant("ANI_IDLE");
        frame = 1;
        log("[FOF2_POSE] bd_idle_002\n");
    }
    if(request == 8)
    {
        animation = openborconstant("ANI_IDLE");
        frame = 2;
        log("[FOF2_POSE] bd_idle_003\n");
    }
    if(request == 9)
    {
        animation = openborconstant("ANI_IDLE");
        frame = 3;
        log("[FOF2_POSE] bd_idle_004\n");
    }
    if(request == 10)
    {
        animation = openborconstant("ANI_IDLE");
        frame = 4;
        log("[FOF2_POSE] bd_idle_005\n");
    }
    if(request == 11)
    {
        animation = openborconstant("ANI_IDLE");
        frame = 5;
        log("[FOF2_POSE] bd_idle_006\n");
    }
    if(request == 12)
    {
        animation = openborconstant("ANI_IDLE");
        frame = 6;
        log("[FOF2_POSE] bd_idle_007\n");
    }
    if(request == 13)
    {
        animation = openborconstant("ANI_IDLE");
        frame = 7;
        log("[FOF2_POSE] bd_idle_008\n");
    }
    if(request == 14)
    {
        animation = openborconstant("ANI_WALK");
        frame = 0;
        log("[FOF2_POSE] bd_walk_start_001\n");
    }
    if(request == 15)
    {
        animation = openborconstant("ANI_WALK");
        frame = 1;
        log("[FOF2_POSE] bd_walk_start_002\n");
    }
    if(request == 16)
    {
        animation = openborconstant("ANI_WALK");
        frame = 2;
        log("[FOF2_POSE] bd_walk_start_003\n");
    }
    if(request == 17)
    {
        animation = openborconstant("ANI_WALK");
        frame = 3;
        log("[FOF2_POSE] bd_walk_start_004\n");
    }
    if(request == 18)
    {
        animation = openborconstant("ANI_WALK");
        frame = 4;
        log("[FOF2_POSE] bd_walk_loop_001\n");
    }
    if(request == 19)
    {
        animation = openborconstant("ANI_WALK");
        frame = 5;
        log("[FOF2_POSE] bd_walk_loop_002\n");
    }
    if(request == 20)
    {
        animation = openborconstant("ANI_WALK");
        frame = 6;
        log("[FOF2_POSE] bd_walk_loop_003\n");
    }
    if(request == 21)
    {
        animation = openborconstant("ANI_WALK");
        frame = 7;
        log("[FOF2_POSE] bd_walk_loop_004\n");
    }
    if(request == 22)
    {
        animation = openborconstant("ANI_WALK");
        frame = 8;
        log("[FOF2_POSE] bd_walk_loop_005\n");
    }
    if(request == 23)
    {
        animation = openborconstant("ANI_WALK");
        frame = 9;
        log("[FOF2_POSE] bd_walk_loop_006\n");
    }
    if(request == 24)
    {
        animation = openborconstant("ANI_WALK");
        frame = 10;
        log("[FOF2_POSE] bd_walk_loop_007\n");
    }
    if(request == 25)
    {
        animation = openborconstant("ANI_WALK");
        frame = 11;
        log("[FOF2_POSE] bd_walk_loop_008\n");
    }
    if(request == 26)
    {
        animation = openborconstant("ANI_WALK");
        frame = 12;
        log("[FOF2_POSE] bd_walk_loop_009\n");
    }
    if(request == 27)
    {
        animation = openborconstant("ANI_WALK");
        frame = 13;
        log("[FOF2_POSE] bd_walk_loop_010\n");
    }
    if(request == 28)
    {
        animation = openborconstant("ANI_WALK");
        frame = 14;
        log("[FOF2_POSE] bd_walk_loop_011\n");
    }
    if(request == 29)
    {
        animation = openborconstant("ANI_WALK");
        frame = 15;
        log("[FOF2_POSE] bd_walk_loop_012\n");
    }
    if(request == 30)
    {
        animation = openborconstant("ANI_WALK");
        frame = 16;
        log("[FOF2_POSE] bd_walk_stop_001\n");
    }
    if(request == 31)
    {
        animation = openborconstant("ANI_WALK");
        frame = 17;
        log("[FOF2_POSE] bd_walk_stop_002\n");
    }
    if(request == 32)
    {
        animation = openborconstant("ANI_WALK");
        frame = 18;
        log("[FOF2_POSE] bd_walk_stop_003\n");
    }
    if(request == 33)
    {
        animation = openborconstant("ANI_WALK");
        frame = 19;
        log("[FOF2_POSE] bd_walk_stop_004\n");
    }
    if(request == 34)
    {
        animation = openborconstant("ANI_TURN");
        frame = 0;
        log("[FOF2_POSE] bd_pivot_001\n");
    }
    if(request == 35)
    {
        animation = openborconstant("ANI_TURN");
        frame = 1;
        log("[FOF2_POSE] bd_pivot_002\n");
    }
    if(request == 36)
    {
        animation = openborconstant("ANI_TURN");
        frame = 2;
        log("[FOF2_POSE] bd_pivot_003\n");
    }
    if(request == 37)
    {
        animation = openborconstant("ANI_TURN");
        frame = 3;
        log("[FOF2_POSE] bd_pivot_004\n");
    }
    if(request == 38)
    {
        animation = openborconstant("ANI_JUMPDELAY");
        frame = 0;
        log("[FOF2_POSE] bd_jump_family_001\n");
    }
    if(request == 39)
    {
        animation = openborconstant("ANI_JUMPDELAY");
        frame = 1;
        log("[FOF2_POSE] bd_jump_family_002\n");
    }
    if(request == 40)
    {
        animation = openborconstant("ANI_JUMPDELAY");
        frame = 2;
        log("[FOF2_POSE] bd_jump_family_003\n");
    }
    if(request == 41)
    {
        animation = openborconstant("ANI_JUMPDELAY");
        frame = 3;
        log("[FOF2_POSE] bd_jump_family_004\n");
    }
    if(request == 42)
    {
        animation = openborconstant("ANI_JUMP");
        frame = 0;
        log("[FOF2_POSE] bd_jump_family_005\n");
    }
    if(request == 43)
    {
        animation = openborconstant("ANI_JUMP");
        frame = 1;
        log("[FOF2_POSE] bd_jump_family_006\n");
    }
    if(request == 44)
    {
        animation = openborconstant("ANI_JUMP");
        frame = 2;
        log("[FOF2_POSE] bd_jump_family_007\n");
    }
    if(request == 45)
    {
        animation = openborconstant("ANI_JUMP");
        frame = 3;
        log("[FOF2_POSE] bd_jump_family_008\n");
    }
    if(request == 46)
    {
        animation = openborconstant("ANI_JUMP");
        frame = 4;
        log("[FOF2_POSE] bd_jump_family_009\n");
    }
    if(request == 47)
    {
        animation = openborconstant("ANI_JUMP");
        frame = 5;
        log("[FOF2_POSE] bd_jump_family_010\n");
    }
    if(request == 48)
    {
        animation = openborconstant("ANI_JUMPLAND");
        frame = 0;
        log("[FOF2_POSE] bd_jump_family_011\n");
    }
    if(request == 49)
    {
        animation = openborconstant("ANI_JUMPLAND");
        frame = 1;
        log("[FOF2_POSE] bd_jump_family_012\n");
    }
    if(request == 50)
    {
        animation = openborconstant("ANI_JUMPLAND");
        frame = 2;
        log("[FOF2_POSE] bd_jump_family_013\n");
    }
    if(request == 51)
    {
        animation = openborconstant("ANI_JUMPLAND");
        frame = 3;
        log("[FOF2_POSE] bd_jump_family_014\n");
    }
    if(request == 52)
    {
        animation = openborconstant("ANI_BLOCK");
        frame = 0;
        log("[FOF2_POSE] bd_guard_001\n");
    }
    if(request == 53)
    {
        animation = openborconstant("ANI_BLOCK");
        frame = 1;
        log("[FOF2_POSE] bd_guard_002\n");
    }
    if(request == 54)
    {
        animation = openborconstant("ANI_BLOCK");
        frame = 2;
        log("[FOF2_POSE] bd_guard_003\n");
    }
    if(request == 55)
    {
        animation = openborconstant("ANI_BLOCK");
        frame = 3;
        log("[FOF2_POSE] bd_guard_004\n");
    }
    if(request == 56)
    {
        animation = openborconstant("ANI_BLOCK");
        frame = 4;
        log("[FOF2_POSE] bd_guard_005\n");
    }
    if(request == 57)
    {
        animation = openborconstant("ANI_BLOCK");
        frame = 5;
        log("[FOF2_POSE] bd_guard_006\n");
    }
    if(request == 58)
    {
        animation = openborconstant("ANI_BLOCKPAIN");
        frame = 0;
        log("[FOF2_POSE] bd_guard_007\n");
    }
    if(request == 59)
    {
        animation = openborconstant("ANI_BLOCKPAIN");
        frame = 1;
        log("[FOF2_POSE] bd_guard_008\n");
    }
    if(request == 60)
    {
        animation = openborconstant("ANI_DODGE");
        frame = 0;
        log("[FOF2_POSE] bd_dodge_001\n");
    }
    if(request == 61)
    {
        animation = openborconstant("ANI_DODGE");
        frame = 1;
        log("[FOF2_POSE] bd_dodge_002\n");
    }
    if(request == 62)
    {
        animation = openborconstant("ANI_DODGE");
        frame = 2;
        log("[FOF2_POSE] bd_dodge_003\n");
    }
    if(request == 63)
    {
        animation = openborconstant("ANI_DODGE");
        frame = 3;
        log("[FOF2_POSE] bd_dodge_004\n");
    }
    if(request == 64)
    {
        animation = openborconstant("ANI_DODGE");
        frame = 4;
        log("[FOF2_POSE] bd_dodge_005\n");
    }
    if(request == 65)
    {
        animation = openborconstant("ANI_DODGE");
        frame = 5;
        log("[FOF2_POSE] bd_dodge_006\n");
    }
    if(request == 66)
    {
        animation = openborconstant("ANI_DODGE");
        frame = 6;
        log("[FOF2_POSE] bd_dodge_007\n");
    }
    if(request == 67)
    {
        animation = openborconstant("ANI_DODGE");
        frame = 7;
        log("[FOF2_POSE] bd_dodge_008\n");
    }
    if(request == 68)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 0;
        log("[FOF2_POSE] bd_ranged_special_001\n");
    }
    if(request == 69)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 1;
        log("[FOF2_POSE] bd_ranged_special_002\n");
    }
    if(request == 70)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 2;
        log("[FOF2_POSE] bd_ranged_special_003\n");
    }
    if(request == 71)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 3;
        log("[FOF2_POSE] bd_ranged_special_004\n");
    }
    if(request == 72)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 4;
        log("[FOF2_POSE] bd_ranged_special_005\n");
    }
    if(request == 73)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 5;
        log("[FOF2_POSE] bd_ranged_special_006\n");
    }
    if(request == 74)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 6;
        log("[FOF2_POSE] bd_ranged_special_007\n");
    }
    if(request == 75)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 7;
        log("[FOF2_POSE] bd_ranged_special_008\n");
    }
    if(request == 76)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 8;
        log("[FOF2_POSE] bd_ranged_special_009\n");
    }
    if(request == 77)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 9;
        log("[FOF2_POSE] bd_ranged_special_010\n");
    }
    if(request == 78)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 10;
        log("[FOF2_POSE] bd_ranged_special_011\n");
    }
    if(request == 79)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 11;
        log("[FOF2_POSE] bd_ranged_special_012\n");
    }
    if(request == 80)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 12;
        log("[FOF2_POSE] bd_ranged_special_013\n");
    }
    if(request == 81)
    {
        animation = openborconstant("ANI_ATTACKUP");
        frame = 13;
        log("[FOF2_POSE] bd_ranged_special_014\n");
    }
    if(request == 82)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 0;
        log("[FOF2_POSE] bd_super_001\n");
    }
    if(request == 83)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 1;
        log("[FOF2_POSE] bd_super_002\n");
    }
    if(request == 84)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 2;
        log("[FOF2_POSE] bd_super_003\n");
    }
    if(request == 85)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 3;
        log("[FOF2_POSE] bd_super_004\n");
    }
    if(request == 86)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 4;
        log("[FOF2_POSE] bd_super_005\n");
    }
    if(request == 87)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 5;
        log("[FOF2_POSE] bd_super_006\n");
    }
    if(request == 88)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 6;
        log("[FOF2_POSE] bd_super_007\n");
    }
    if(request == 89)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 7;
        log("[FOF2_POSE] bd_super_008\n");
    }
    if(request == 90)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 8;
        log("[FOF2_POSE] bd_super_009\n");
    }
    if(request == 91)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 9;
        log("[FOF2_POSE] bd_super_010\n");
    }
    if(request == 92)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 10;
        log("[FOF2_POSE] bd_super_011\n");
    }
    if(request == 93)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 11;
        log("[FOF2_POSE] bd_super_012\n");
    }
    if(request == 94)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 12;
        log("[FOF2_POSE] bd_super_013\n");
    }
    if(request == 95)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 13;
        log("[FOF2_POSE] bd_super_014\n");
    }
    if(request == 96)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 14;
        log("[FOF2_POSE] bd_super_015\n");
    }
    if(request == 97)
    {
        animation = openborconstant("ANI_SPECIAL");
        frame = 15;
        log("[FOF2_POSE] bd_super_016\n");
    }
    if(request == 98)
    {
        animation = openborconstant("ANI_JUMPATTACK");
        frame = 0;
        log("[FOF2_POSE] bd_air_punch_001\n");
    }
    if(request == 99)
    {
        animation = openborconstant("ANI_JUMPATTACK");
        frame = 1;
        log("[FOF2_POSE] bd_air_punch_002\n");
    }
    if(request == 100)
    {
        animation = openborconstant("ANI_JUMPATTACK");
        frame = 2;
        log("[FOF2_POSE] bd_air_punch_003\n");
    }
    if(request == 101)
    {
        animation = openborconstant("ANI_JUMPATTACK");
        frame = 3;
        log("[FOF2_POSE] bd_air_punch_004\n");
    }
    if(request == 102)
    {
        animation = openborconstant("ANI_JUMPATTACK");
        frame = 4;
        log("[FOF2_POSE] bd_air_punch_005\n");
    }
    if(request == 103)
    {
        animation = openborconstant("ANI_JUMPATTACK");
        frame = 5;
        log("[FOF2_POSE] bd_air_punch_006\n");
    }
    if(request == 104)
    {
        animation = openborconstant("ANI_JUMPATTACK");
        frame = 6;
        log("[FOF2_POSE] bd_air_punch_007\n");
    }
    if(request == 105)
    {
        animation = openborconstant("ANI_JUMPATTACK");
        frame = 7;
        log("[FOF2_POSE] bd_air_punch_008\n");
    }
    if(request == 106)
    {
        animation = openborconstant("ANI_JUMPATTACK2");
        frame = 0;
        log("[FOF2_POSE] bd_air_kick_001\n");
    }
    if(request == 107)
    {
        animation = openborconstant("ANI_JUMPATTACK2");
        frame = 1;
        log("[FOF2_POSE] bd_air_kick_002\n");
    }
    if(request == 108)
    {
        animation = openborconstant("ANI_JUMPATTACK2");
        frame = 2;
        log("[FOF2_POSE] bd_air_kick_003\n");
    }
    if(request == 109)
    {
        animation = openborconstant("ANI_JUMPATTACK2");
        frame = 3;
        log("[FOF2_POSE] bd_air_kick_004\n");
    }
    if(request == 110)
    {
        animation = openborconstant("ANI_JUMPATTACK2");
        frame = 4;
        log("[FOF2_POSE] bd_air_kick_005\n");
    }
    if(request == 111)
    {
        animation = openborconstant("ANI_JUMPATTACK2");
        frame = 5;
        log("[FOF2_POSE] bd_air_kick_006\n");
    }
    if(request == 112)
    {
        animation = openborconstant("ANI_JUMPATTACK2");
        frame = 6;
        log("[FOF2_POSE] bd_air_kick_007\n");
    }
    if(request == 113)
    {
        animation = openborconstant("ANI_JUMPATTACK2");
        frame = 7;
        log("[FOF2_POSE] bd_air_kick_008\n");
    }
    if(request == 114)
    {
        animation = openborconstant("ANI_PAIN");
        frame = 0;
        log("[FOF2_POSE] bd_light_pain_001\n");
    }
    if(request == 115)
    {
        animation = openborconstant("ANI_PAIN");
        frame = 1;
        log("[FOF2_POSE] bd_light_pain_002\n");
    }
    if(request == 116)
    {
        animation = openborconstant("ANI_PAIN");
        frame = 2;
        log("[FOF2_POSE] bd_light_pain_003\n");
    }
    if(request == 117)
    {
        animation = openborconstant("ANI_PAIN");
        frame = 3;
        log("[FOF2_POSE] bd_light_pain_004\n");
    }
    if(request == 118)
    {
        animation = openborconstant("ANI_PAIN");
        frame = 4;
        log("[FOF2_POSE] bd_light_pain_005\n");
    }
    if(request == 119)
    {
        animation = openborconstant("ANI_FALL");
        frame = 0;
        log("[FOF2_POSE] bd_heavy_pain_fall_001\n");
    }
    if(request == 120)
    {
        animation = openborconstant("ANI_FALL");
        frame = 1;
        log("[FOF2_POSE] bd_heavy_pain_fall_002\n");
    }
    if(request == 121)
    {
        animation = openborconstant("ANI_FALL");
        frame = 2;
        log("[FOF2_POSE] bd_heavy_pain_fall_003\n");
    }
    if(request == 122)
    {
        animation = openborconstant("ANI_FALL");
        frame = 3;
        log("[FOF2_POSE] bd_heavy_pain_fall_004\n");
    }
    if(request == 123)
    {
        animation = openborconstant("ANI_FALL");
        frame = 4;
        log("[FOF2_POSE] bd_heavy_pain_fall_005\n");
    }
    if(request == 124)
    {
        animation = openborconstant("ANI_FALL");
        frame = 5;
        log("[FOF2_POSE] bd_heavy_pain_fall_006\n");
    }
    if(request == 125)
    {
        animation = openborconstant("ANI_FALL");
        frame = 6;
        log("[FOF2_POSE] bd_heavy_pain_fall_007\n");
    }
    if(request == 126)
    {
        animation = openborconstant("ANI_FALL");
        frame = 7;
        log("[FOF2_POSE] bd_heavy_pain_fall_008\n");
    }
    if(request == 127)
    {
        animation = openborconstant("ANI_FALL");
        frame = 8;
        log("[FOF2_POSE] bd_down_001\n");
    }
    if(request == 128)
    {
        animation = openborconstant("ANI_FALL");
        frame = 9;
        log("[FOF2_POSE] bd_down_002\n");
    }
    if(request == 129)
    {
        animation = openborconstant("ANI_FALL");
        frame = 10;
        log("[FOF2_POSE] bd_down_003\n");
    }
    if(request == 130)
    {
        animation = openborconstant("ANI_FALL");
        frame = 11;
        log("[FOF2_POSE] bd_down_004\n");
    }
    if(request == 131)
    {
        animation = openborconstant("ANI_FALL");
        frame = 12;
        log("[FOF2_POSE] bd_down_005\n");
    }
    if(request == 132)
    {
        animation = openborconstant("ANI_FALL");
        frame = 13;
        log("[FOF2_POSE] bd_down_006\n");
    }
    if(request == 133)
    {
        animation = openborconstant("ANI_RISE");
        frame = 0;
        log("[FOF2_POSE] bd_rise_001\n");
    }
    if(request == 134)
    {
        animation = openborconstant("ANI_RISE");
        frame = 1;
        log("[FOF2_POSE] bd_rise_002\n");
    }
    if(request == 135)
    {
        animation = openborconstant("ANI_RISE");
        frame = 2;
        log("[FOF2_POSE] bd_rise_003\n");
    }
    if(request == 136)
    {
        animation = openborconstant("ANI_RISE");
        frame = 3;
        log("[FOF2_POSE] bd_rise_004\n");
    }
    if(request == 137)
    {
        animation = openborconstant("ANI_RISE");
        frame = 4;
        log("[FOF2_POSE] bd_rise_005\n");
    }
    if(request == 138)
    {
        animation = openborconstant("ANI_RISE");
        frame = 5;
        log("[FOF2_POSE] bd_rise_006\n");
    }
    if(request == 139)
    {
        animation = openborconstant("ANI_RISE");
        frame = 6;
        log("[FOF2_POSE] bd_rise_007\n");
    }
    if(request == 140)
    {
        animation = openborconstant("ANI_RISE");
        frame = 7;
        log("[FOF2_POSE] bd_rise_008\n");
    }
    if(request == 141)
    {
        animation = openborconstant("ANI_GET");
        frame = 0;
        log("[FOF2_POSE] bd_interaction_pickup_001\n");
    }
    if(request == 142)
    {
        animation = openborconstant("ANI_GET");
        frame = 1;
        log("[FOF2_POSE] bd_interaction_pickup_002\n");
    }
    if(request == 143)
    {
        animation = openborconstant("ANI_GET");
        frame = 2;
        log("[FOF2_POSE] bd_interaction_pickup_003\n");
    }
    if(request == 144)
    {
        animation = openborconstant("ANI_GET");
        frame = 3;
        log("[FOF2_POSE] bd_interaction_pickup_004\n");
    }
    if(request == 145)
    {
        animation = openborconstant("ANI_GET");
        frame = 4;
        log("[FOF2_POSE] bd_interaction_pickup_005\n");
    }
    if(request == 146)
    {
        animation = openborconstant("ANI_GET");
        frame = 5;
        log("[FOF2_POSE] bd_interaction_pickup_006\n");
    }
    if(request == 147)
    {
        animation = openborconstant("ANI_GET");
        frame = 6;
        log("[FOF2_POSE] bd_interaction_pickup_007\n");
    }
    if(request == 148)
    {
        animation = openborconstant("ANI_GET");
        frame = 7;
        log("[FOF2_POSE] bd_interaction_pickup_008\n");
    }
    if(request == 149)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 0;
        log("[FOF2_POSE] bd_combat_shared_001\n");
    }
    if(request == 150)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 1;
        log("[FOF2_POSE] bd_combat_shared_002\n");
    }
    if(request == 151)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 2;
        log("[FOF2_POSE] bd_combat_shared_003\n");
    }
    if(request == 152)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 3;
        log("[FOF2_POSE] bd_combat_shared_004\n");
    }
    if(request == 153)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 4;
        log("[FOF2_POSE] bd_combat_shared_005\n");
    }
    if(request == 154)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 5;
        log("[FOF2_POSE] bd_regular_01_specific_001\n");
    }
    if(request == 155)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 6;
        log("[FOF2_POSE] bd_regular_01_specific_002\n");
    }
    if(request == 156)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 7;
        log("[FOF2_POSE] bd_regular_01_specific_003\n");
    }
    if(request == 157)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 13;
        log("[FOF2_POSE] bd_kick_01_specific_001\n");
    }
    if(request == 158)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 14;
        log("[FOF2_POSE] bd_kick_01_specific_002\n");
    }
    if(request == 159)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 15;
        log("[FOF2_POSE] bd_kick_01_specific_003\n");
    }
    if(request == 160)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 21;
        log("[FOF2_POSE] bd_combat_shared_006\n");
    }
    if(request == 161)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 22;
        log("[FOF2_POSE] bd_combat_shared_007\n");
    }
    if(request == 162)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 23;
        log("[FOF2_POSE] bd_combat_shared_008\n");
    }
    if(request == 163)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 24;
        log("[FOF2_POSE] bd_power_01_specific_001\n");
    }
    if(request == 164)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 25;
        log("[FOF2_POSE] bd_power_01_specific_002\n");
    }
    if(request == 165)
    {
        animation = openborconstant("ANI_FREESPECIAL1");
        frame = 26;
        log("[FOF2_POSE] bd_power_01_specific_003\n");
    }
    if(request == 166)
    {
        animation = openborconstant("ANI_FREESPECIAL2");
        frame = 5;
        log("[FOF2_POSE] bd_regular_02_specific_001\n");
    }
    if(request == 167)
    {
        animation = openborconstant("ANI_FREESPECIAL2");
        frame = 6;
        log("[FOF2_POSE] bd_regular_02_specific_002\n");
    }
    if(request == 168)
    {
        animation = openborconstant("ANI_FREESPECIAL2");
        frame = 7;
        log("[FOF2_POSE] bd_regular_02_specific_003\n");
    }
    if(request == 169)
    {
        animation = openborconstant("ANI_FREESPECIAL2");
        frame = 13;
        log("[FOF2_POSE] bd_kick_02_specific_001\n");
    }
    if(request == 170)
    {
        animation = openborconstant("ANI_FREESPECIAL2");
        frame = 14;
        log("[FOF2_POSE] bd_kick_02_specific_002\n");
    }
    if(request == 171)
    {
        animation = openborconstant("ANI_FREESPECIAL2");
        frame = 15;
        log("[FOF2_POSE] bd_kick_02_specific_003\n");
    }
    if(request == 172)
    {
        animation = openborconstant("ANI_FREESPECIAL2");
        frame = 24;
        log("[FOF2_POSE] bd_power_02_specific_001\n");
    }
    if(request == 173)
    {
        animation = openborconstant("ANI_FREESPECIAL2");
        frame = 25;
        log("[FOF2_POSE] bd_power_02_specific_002\n");
    }
    if(request == 174)
    {
        animation = openborconstant("ANI_FREESPECIAL2");
        frame = 26;
        log("[FOF2_POSE] bd_power_02_specific_003\n");
    }
    if(request == 175)
    {
        animation = openborconstant("ANI_FREESPECIAL3");
        frame = 5;
        log("[FOF2_POSE] bd_regular_03_specific_001\n");
    }
    if(request == 176)
    {
        animation = openborconstant("ANI_FREESPECIAL3");
        frame = 6;
        log("[FOF2_POSE] bd_regular_03_specific_002\n");
    }
    if(request == 177)
    {
        animation = openborconstant("ANI_FREESPECIAL3");
        frame = 7;
        log("[FOF2_POSE] bd_regular_03_specific_003\n");
    }
    if(request == 178)
    {
        animation = openborconstant("ANI_FREESPECIAL3");
        frame = 13;
        log("[FOF2_POSE] bd_kick_03_specific_001\n");
    }
    if(request == 179)
    {
        animation = openborconstant("ANI_FREESPECIAL3");
        frame = 14;
        log("[FOF2_POSE] bd_kick_03_specific_002\n");
    }
    if(request == 180)
    {
        animation = openborconstant("ANI_FREESPECIAL3");
        frame = 15;
        log("[FOF2_POSE] bd_kick_03_specific_003\n");
    }
    if(request == 181)
    {
        animation = openborconstant("ANI_FREESPECIAL3");
        frame = 24;
        log("[FOF2_POSE] bd_power_03_specific_001\n");
    }
    if(request == 182)
    {
        animation = openborconstant("ANI_FREESPECIAL3");
        frame = 25;
        log("[FOF2_POSE] bd_power_03_specific_002\n");
    }
    if(request == 183)
    {
        animation = openborconstant("ANI_FREESPECIAL3");
        frame = 26;
        log("[FOF2_POSE] bd_power_03_specific_003\n");
    }
    if(request == 184)
    {
        animation = openborconstant("ANI_FREESPECIAL4");
        frame = 5;
        log("[FOF2_POSE] bd_regular_04_specific_001\n");
    }
    if(request == 185)
    {
        animation = openborconstant("ANI_FREESPECIAL4");
        frame = 6;
        log("[FOF2_POSE] bd_regular_04_specific_002\n");
    }
    if(request == 186)
    {
        animation = openborconstant("ANI_FREESPECIAL4");
        frame = 7;
        log("[FOF2_POSE] bd_regular_04_specific_003\n");
    }
    if(request == 187)
    {
        animation = openborconstant("ANI_FREESPECIAL4");
        frame = 13;
        log("[FOF2_POSE] bd_kick_04_specific_001\n");
    }
    if(request == 188)
    {
        animation = openborconstant("ANI_FREESPECIAL4");
        frame = 14;
        log("[FOF2_POSE] bd_kick_04_specific_002\n");
    }
    if(request == 189)
    {
        animation = openborconstant("ANI_FREESPECIAL4");
        frame = 15;
        log("[FOF2_POSE] bd_kick_04_specific_003\n");
    }
    if(request == 190)
    {
        animation = openborconstant("ANI_FREESPECIAL4");
        frame = 24;
        log("[FOF2_POSE] bd_power_04_specific_001\n");
    }
    if(request == 191)
    {
        animation = openborconstant("ANI_FREESPECIAL4");
        frame = 25;
        log("[FOF2_POSE] bd_power_04_specific_002\n");
    }
    if(request == 192)
    {
        animation = openborconstant("ANI_FREESPECIAL4");
        frame = 26;
        log("[FOF2_POSE] bd_power_04_specific_003\n");
    }
    if(request == 193)
    {
        animation = openborconstant("ANI_FREESPECIAL5");
        frame = 5;
        log("[FOF2_POSE] bd_regular_05_specific_001\n");
    }
    if(request == 194)
    {
        animation = openborconstant("ANI_FREESPECIAL5");
        frame = 6;
        log("[FOF2_POSE] bd_regular_05_specific_002\n");
    }
    if(request == 195)
    {
        animation = openborconstant("ANI_FREESPECIAL5");
        frame = 7;
        log("[FOF2_POSE] bd_regular_05_specific_003\n");
    }
    if(request == 196)
    {
        animation = openborconstant("ANI_FREESPECIAL5");
        frame = 13;
        log("[FOF2_POSE] bd_kick_05_specific_001\n");
    }
    if(request == 197)
    {
        animation = openborconstant("ANI_FREESPECIAL5");
        frame = 14;
        log("[FOF2_POSE] bd_kick_05_specific_002\n");
    }
    if(request == 198)
    {
        animation = openborconstant("ANI_FREESPECIAL5");
        frame = 15;
        log("[FOF2_POSE] bd_kick_05_specific_003\n");
    }
    if(request == 199)
    {
        animation = openborconstant("ANI_FREESPECIAL5");
        frame = 24;
        log("[FOF2_POSE] bd_power_05_specific_001\n");
    }
    if(request == 200)
    {
        animation = openborconstant("ANI_FREESPECIAL5");
        frame = 25;
        log("[FOF2_POSE] bd_power_05_specific_002\n");
    }
    if(request == 201)
    {
        animation = openborconstant("ANI_FREESPECIAL5");
        frame = 26;
        log("[FOF2_POSE] bd_power_05_specific_003\n");
    }
    if(request == 202)
    {
        animation = openborconstant("ANI_FREESPECIAL6");
        frame = 5;
        log("[FOF2_POSE] bd_regular_06_specific_001\n");
    }
    if(request == 203)
    {
        animation = openborconstant("ANI_FREESPECIAL6");
        frame = 6;
        log("[FOF2_POSE] bd_regular_06_specific_002\n");
    }
    if(request == 204)
    {
        animation = openborconstant("ANI_FREESPECIAL6");
        frame = 7;
        log("[FOF2_POSE] bd_regular_06_specific_003\n");
    }
    if(request == 205)
    {
        animation = openborconstant("ANI_FREESPECIAL6");
        frame = 13;
        log("[FOF2_POSE] bd_kick_06_specific_001\n");
    }
    if(request == 206)
    {
        animation = openborconstant("ANI_FREESPECIAL6");
        frame = 14;
        log("[FOF2_POSE] bd_kick_06_specific_002\n");
    }
    if(request == 207)
    {
        animation = openborconstant("ANI_FREESPECIAL6");
        frame = 15;
        log("[FOF2_POSE] bd_kick_06_specific_003\n");
    }
    if(request == 208)
    {
        animation = openborconstant("ANI_FREESPECIAL6");
        frame = 24;
        log("[FOF2_POSE] bd_power_06_specific_001\n");
    }
    if(request == 209)
    {
        animation = openborconstant("ANI_FREESPECIAL6");
        frame = 25;
        log("[FOF2_POSE] bd_power_06_specific_002\n");
    }
    if(request == 210)
    {
        animation = openborconstant("ANI_FREESPECIAL6");
        frame = 26;
        log("[FOF2_POSE] bd_power_06_specific_003\n");
    }
    if(request == 211)
    {
        animation = openborconstant("ANI_FREESPECIAL7");
        frame = 5;
        log("[FOF2_POSE] bd_regular_07_specific_001\n");
    }
    if(request == 212)
    {
        animation = openborconstant("ANI_FREESPECIAL7");
        frame = 6;
        log("[FOF2_POSE] bd_regular_07_specific_002\n");
    }
    if(request == 213)
    {
        animation = openborconstant("ANI_FREESPECIAL7");
        frame = 7;
        log("[FOF2_POSE] bd_regular_07_specific_003\n");
    }
    if(request == 214)
    {
        animation = openborconstant("ANI_FREESPECIAL7");
        frame = 13;
        log("[FOF2_POSE] bd_kick_07_specific_001\n");
    }
    if(request == 215)
    {
        animation = openborconstant("ANI_FREESPECIAL7");
        frame = 14;
        log("[FOF2_POSE] bd_kick_07_specific_002\n");
    }
    if(request == 216)
    {
        animation = openborconstant("ANI_FREESPECIAL7");
        frame = 15;
        log("[FOF2_POSE] bd_kick_07_specific_003\n");
    }
    if(request == 217)
    {
        animation = openborconstant("ANI_FREESPECIAL7");
        frame = 24;
        log("[FOF2_POSE] bd_power_07_specific_001\n");
    }
    if(request == 218)
    {
        animation = openborconstant("ANI_FREESPECIAL7");
        frame = 25;
        log("[FOF2_POSE] bd_power_07_specific_002\n");
    }
    if(request == 219)
    {
        animation = openborconstant("ANI_FREESPECIAL7");
        frame = 26;
        log("[FOF2_POSE] bd_power_07_specific_003\n");
    }
    if(animation < 0) return;
    if(getentityproperty(player, "animationid") != animation)
    {
        changeentityproperty(player, "animation", animation);
    }
    updateframe(player, frame);
}
/* END GENERATED BLACK DAVE QA POSE ROUTER */

int bd_route_animation(int step)
{
    if(step == 1) return openborconstant("ANI_FREESPECIAL1");
    if(step == 2) return openborconstant("ANI_FREESPECIAL2");
    if(step == 3) return openborconstant("ANI_FREESPECIAL3");
    if(step == 4) return openborconstant("ANI_FREESPECIAL4");
    if(step == 5) return openborconstant("ANI_FREESPECIAL5");
    if(step == 6) return openborconstant("ANI_FREESPECIAL6");
    return openborconstant("ANI_FREESPECIAL7");
}

int bd_route_offset(int route)
{
    if(route == 2) return 8;
    if(route == 3) return 16;
    return 0;
}

int bd_route_pose_count(int route)
{
    if(route == 3) return 11;
    return 8;
}

int bd_route_startup(int route, int step)
{
    if(route == 1)
    {
        if(step == 1) return 5; if(step == 2) return 4; if(step == 3) return 7;
        if(step == 4) return 5; if(step == 5) return 10; if(step == 6) return 8; return 6;
    }
    if(route == 2)
    {
        if(step == 1) return 4; if(step == 2) return 5; if(step == 3) return 5;
        if(step == 4) return 8; if(step == 5) return 7; if(step == 6) return 10; return 6;
    }
    if(step == 1) return 11; if(step == 2) return 11; if(step == 3) return 13;
    if(step == 4) return 14; if(step == 5) return 10; if(step == 6) return 11; return 12;
}

int bd_route_active(int route, int step)
{
    if(route == 1)
    {
        if(step <= 2) return 4; if(step == 3) return 6; if(step == 4) return 5;
        if(step <= 6) return 6; return 5;
    }
    if(route == 2)
    {
        if(step <= 2) return 4; if(step == 3) return 5; if(step <= 6) return 6; return 5;
    }
    if(step <= 2) return 5; if(step == 3 || step == 5) return 6;
    if(step == 4 || step == 6) return 7; return 8;
}

int bd_route_recovery(int route, int step)
{
    if(route == 1)
    {
        if(step == 1) return 8; if(step == 2) return 7; if(step == 3) return 14;
        if(step == 4) return 10; if(step == 5) return 18; if(step == 6) return 17; return 10;
    }
    if(route == 2)
    {
        if(step == 1) return 7; if(step == 2) return 8; if(step == 3) return 10;
        if(step == 4) return 17; if(step == 5) return 14; if(step == 6) return 18; return 10;
    }
    if(step == 1) return 13; if(step == 2) return 14; if(step == 3) return 17;
    if(step == 4) return 20; if(step == 5) return 14; if(step == 6) return 16; return 19;
}

int bd_route_effective_recovery(int route, int step)
{
    int count;
    int startup_poses;
    int active_poses;
    int recovery_poses;
    int recovery;
    count = bd_route_pose_count(route);
    active_poses = bd_route_active(route, step) / 2;
    if(active_poses < 1) active_poses = 1;
    if(active_poses > 2) active_poses = 2;
    startup_poses = bd_route_startup(route, step) / 2;
    if(startup_poses < 1) startup_poses = 1;
    if(startup_poses > count - active_poses - 1) startup_poses = count - active_poses - 1;
    recovery_poses = count - startup_poses - active_poses;
    recovery = bd_route_recovery(route, step);
    if(recovery < recovery_poses * 2) recovery = recovery_poses * 2;
    return recovery;
}

int bd_route_cancel(int route, int step)
{
    if(step == 7) return 9999;
    if(route == 1)
    {
        if(step == 1) return 12; if(step == 2) return 11; if(step == 3) return 27;
        if(step == 4) return 14; if(step == 5) return 30; return 29;
    }
    if(route == 2)
    {
        if(step == 1) return 11; if(step == 2) return 12; if(step == 3) return 14;
        if(step == 4) return 29; if(step == 5) return 27; return 30;
    }
    if(step == 1) return 18; if(step == 2) return 20; if(step == 3) return 23;
    if(step == 4) return 25; if(step == 5) return 17; return 19;
}

int bd_route_buffer_ticks(int route, int step)
{
    if(route == 1)
    {
        if(step == 1) return 14; if(step == 2) return 13; if(step == 3) return 14;
        if(step == 4) return 14; if(step == 5) return 17; if(step == 6) return 16; return 14;
    }
    if(route == 2)
    {
        if(step == 1) return 13; if(step == 2) return 14; if(step == 3) return 14;
        if(step == 4) return 16; if(step == 5) return 14; if(step == 6) return 17; return 14;
    }
    if(step == 1) return 13; if(step == 2) return 14; if(step == 3) return 16;
    if(step == 4) return 17; if(step == 5) return 17; if(step == 6) return 18; return 19;
}

int bd_route_can_cancel(int route, int step, int next_route)
{
    if(step >= 7) return 0;
    if(route == 3) return next_route == 3;
    if(route == 1 && (step == 3 || step == 5 || step == 6) && next_route == 3) return 0;
    if(route == 2 && (step == 4 || step == 5 || step == 6) && next_route == 3) return 0;
    return 1;
}

void bd_clear_attack(void player)
{
    if(getglobalvar("bd_attack_flag") == 1)
    {
        changeentityproperty(player, "aiflag", "attacking", 0);
        setglobalvar("bd_attack_flag", 0);
    }
    setglobalvar("bd_attack_live", 0);
}

void bd_enter(void player, int state, int animation, int start, int count, int total, int loop, int hold, int change_animation)
{
    int oldstate;
    oldstate = getglobalvar("bd_state");
    if(oldstate == 9 && state != 9 && state != 21 && state != 24)
        changeentityproperty(player, "aiflag", "blocking", 0);
    if(oldstate == 10 && state != 10 && getglobalvar("bd_dodge_invul") == 1)
    {
        changeentityproperty(player, "aiflag", "invincible", 0);
        setglobalvar("bd_dodge_invul", 0);
    }
    if(state != 20 && state != 11 && state != 12 && state != 13 && state != 14)
        bd_clear_attack(player);
    changeentityproperty(player, "takeaction", NULL());
    setglobalvar("bd_state", state);
    setglobalvar("bd_state_tick", 0);
    setglobalvar("bd_pose_start", start);
    setglobalvar("bd_pose_count", count);
    setglobalvar("bd_pose_total", total);
    setglobalvar("bd_pose_loop", loop);
    setglobalvar("bd_pose_hold", hold);
    if(change_animation == 1) changeentityproperty(player, "animation", animation);
    updateframe(player, start);
}

void bd_enter_idle(void player)
{
    setglobalvar("bd_buffered_route", 0);
    bd_enter(player, 1, openborconstant("ANI_IDLE"), 0, 8, 96, 1, 12, 1);
}

void bd_enter_attack(void player, int route, int step)
{
    int total;
    int count;
    if(step < 1) step = 1;
    if(step > 7) step = 7;
    count = bd_route_pose_count(route);
    total = bd_route_startup(route, step) + bd_route_active(route, step) + bd_route_effective_recovery(route, step);
    setglobalvar("bd_route", route);
    setglobalvar("bd_step", step);
    setglobalvar("bd_attack_live", 1);
    setglobalvar("bd_contact_latched", 0);
    setglobalvar("bd_confirmed_contact", 0);
    setglobalvar("bd_buffered_route", 0);
    changeentityproperty(player, "aiflag", "attacking", 1);
    setglobalvar("bd_attack_flag", 1);
    changeentityproperty(player, "velocity", 0, 0);
    bd_enter(player, 20, bd_route_animation(step), bd_route_offset(route), count, total, 0, 2, 1);
}

void bd_arm_native_attack(int route, int step)
{
    setglobalvar("bd_route", route);
    setglobalvar("bd_step", step);
    setglobalvar("bd_attack_live", 1);
    setglobalvar("bd_contact_latched", 0);
    setglobalvar("bd_confirmed_contact", 0);
}

void bd_spawn_contact_effect(void player, int route, int step)
{
    int x;
    int z;
    int y;
    int direction;
    x = getentityproperty(player, "x");
    z = getentityproperty(player, "z");
    y = getentityproperty(player, "y");
    direction = getentityproperty(player, "direction");
    if(step == 8)
    {
        x = getglobalvar("bd_confirmed_x");
        z = getglobalvar("bd_confirmed_z");
        y = getglobalvar("bd_confirmed_y");
    }
    else if(direction == 0) x = x - 44; else x = x + 44;
    clearspawnentry();
    setspawnentry("name", "BlackDaveImpact");
    setspawnentry("coords", x, z, y + 64);
    spawn();
    clearspawnentry();
    setspawnentry("name", "BlackDaveFlame");
    setspawnentry("coords", x, z, y + 56);
    spawn();
    clearspawnentry();
    setglobalvar("bd_last_vfx_route", route);
    setglobalvar("bd_last_vfx_step", step);
}

void bd_consume_confirmed_contact(void player)
{
    int route;
    int step;
    int pause_ticks;
    if(getglobalvar("bd_confirmed_contact") != 1) return;
    route = getglobalvar("bd_confirmed_route");
    step = getglobalvar("bd_confirmed_step");
    pause_ticks = 4;
    if(route == 3) pause_ticks = 7;
    if(step == 7) pause_ticks = pause_ticks + 2;
    setglobalvar("bd_contact_pause", pause_ticks);
    setglobalvar("bd_confirmed_contact", 0);
    bd_spawn_contact_effect(player, route, step);
}

void bd_present_pose(void player)
{
    int tick;
    int start;
    int count;
    int total;
    int loop;
    int hold;
    int pose;
    tick = getglobalvar("bd_state_tick") - 1;
    if(tick < 0) tick = 0;
    start = getglobalvar("bd_pose_start");
    count = getglobalvar("bd_pose_count");
    total = getglobalvar("bd_pose_total");
    loop = getglobalvar("bd_pose_loop");
    hold = getglobalvar("bd_pose_hold");
    if(loop == 1) pose = start + ((tick / hold) % count);
    else
    {
        pose = start + ((tick * count) / total);
        if(pose >= start + count) pose = start + count - 1;
    }
    updateframe(player, pose);
}

void bd_present_reverse_pose(void player)
{
    int tick;
    int start;
    int count;
    int total;
    int pose;
    tick = getglobalvar("bd_state_tick") - 1;
    if(tick < 0) tick = 0;
    start = getglobalvar("bd_pose_start");
    count = getglobalvar("bd_pose_count");
    total = getglobalvar("bd_pose_total");
    pose = start + count - 1 - ((tick * count) / total);
    if(pose < start) pose = start;
    updateframe(player, pose);
}

void bd_present_phased_pose(void player, int startup, int active, int recovery)
{
    int phase_tick;
    int start;
    int count;
    int startup_poses;
    int active_poses;
    int recovery_poses;
    int pose;
    phase_tick = getglobalvar("bd_state_tick") - 1;
    if(phase_tick < 0) phase_tick = 0;
    start = getglobalvar("bd_pose_start");
    count = getglobalvar("bd_pose_count");
    active_poses = active / 2;
    if(active_poses < 1) active_poses = 1;
    if(active_poses > 2) active_poses = 2;
    startup_poses = startup / 2;
    if(startup_poses < 1) startup_poses = 1;
    if(startup_poses > count - active_poses - 1) startup_poses = count - active_poses - 1;
    recovery_poses = count - startup_poses - active_poses;
    if(recovery < recovery_poses * 2) recovery = recovery_poses * 2;
    if(phase_tick < startup)
        pose = start + ((phase_tick * startup_poses) / startup);
    else if(phase_tick < startup + active)
        pose = start + startup_poses + (((phase_tick - startup) * active_poses) / active);
    else
    {
        phase_tick = phase_tick - startup - active;
        if(phase_tick >= recovery) phase_tick = recovery - 1;
        pose = start + startup_poses + active_poses + ((phase_tick * recovery_poses) / recovery);
    }
    if(pose >= start + count) pose = start + count - 1;
    updateframe(player, pose);
}

void bd_present_route_pose(void player)
{
    int route;
    int step;
    route = getglobalvar("bd_route");
    step = getglobalvar("bd_step");
    bd_present_phased_pose(player, bd_route_startup(route, step), bd_route_active(route, step), bd_route_effective_recovery(route, step));
}

void bd_present_walk_pose(void player)
{
    int x;
    int z;
    int px;
    int pz;
    int distance;
    x = getentityproperty(player, "x");
    z = getentityproperty(player, "z");
    px = getglobalvar("bd_previous_x");
    pz = getglobalvar("bd_previous_z");
    distance = getglobalvar("bd_walk_distance") + bd_abs(x - px) + bd_abs(z - pz);
    setglobalvar("bd_walk_distance", distance);
    setglobalvar("bd_previous_x", x);
    setglobalvar("bd_previous_z", z);
    updateframe(player, 4 + ((distance / 3) % 12));
}

int bd_spend_mp(void player, int cost, int require_full)
{
    int mp;
    mp = getentityproperty(player, "mp");
    if(require_full == 1 && mp < 100) return 0;
    if(mp < cost) return 0;
    changeentityproperty(player, "mp", mp - cost);
    return 1;
}

void bd_apply_ground_motion(void player, int state, int left, int right, int up, int down)
{
    int vx;
    int vz;
    vx = 0;
    vz = 0;
    if(state == 1 || state == 2 || state == 3 || state == 4)
    {
        if(left != 0 && right == 0) vx = -3;
        if(right != 0 && left == 0) vx = 3;
        if(up != 0 && down == 0) vz = -2;
        if(down != 0 && up == 0) vz = 2;
    }
    changeentityproperty(player, "velocity", vx, vz);
    if(vx < 0) changeentityproperty(player, "direction", 0);
    if(vx > 0) changeentityproperty(player, "direction", 1);
}

void bd_begin_dodge(void player)
{
    int direction;
    direction = getentityproperty(player, "direction");
    bd_enter(player, 10, openborconstant("ANI_DODGE"), 0, 8, 24, 0, 3, 1);
    if(direction == 0) changeentityproperty(player, "velocity", -6, 0);
    else changeentityproperty(player, "velocity", 6, 0);
}

void bd_spawn_ranged_projectile(void player)
{
    void shot;
    int x;
    int z;
    int y;
    int direction;
    x = getentityproperty(player, "x");
    z = getentityproperty(player, "z");
    y = getentityproperty(player, "y");
    direction = getentityproperty(player, "direction");
    if(direction == 0) x = x - 42; else x = x + 42;
    clearspawnentry();
    setspawnentry("name", "BlackDaveFlameShot");
    setspawnentry("coords", x, z, y + 58);
    shot = spawn();
    clearspawnentry();
    if(shot == NULL()) return;
    changeentityproperty(shot, "direction", direction);
    if(direction == 0) changeentityproperty(shot, "velocity", -6, 0, 0);
    else changeentityproperty(shot, "velocity", 6, 0, 0);
}

void bd_enter_spawn_state(void player, int animation)
{
    if(animation == openborconstant("ANI_RESPAWN"))
        bd_enter(player, 23, animation, 0, 6, 42, 0, 7, 0);
    else
        bd_enter(player, 22, openborconstant("ANI_SPAWN"), 0, 6, 36, 0, 6, 1);
}

void bd_sync_reaction(void player)
{
    int animation;
    int state;
    int health;
    animation = getentityproperty(player, "animationid");
    state = getglobalvar("bd_state");
    health = getentityproperty(player, "health");
    if(getglobalvar("bd_block_contact") == 1)
    {
        setglobalvar("bd_block_contact", 0);
        bd_enter(player, 21, openborconstant("ANI_BLOCKPAIN"), 0, 2, 6, 0, 3, 1);
        return;
    }
    if(health <= 0 && state != 16 && state != 17 && state != 25)
    {
        bd_enter(player, 16, openborconstant("ANI_FALL"), 0, 8, 38, 0, 5, 1);
        return;
    }
    if(animation == openborconstant("ANI_PAIN") && state != 15)
        bd_enter(player, 15, animation, 0, 5, 18, 0, 4, 0);
    else if(animation == openborconstant("ANI_FALL") && state != 16 && state != 17 && state != 25)
        bd_enter(player, 16, animation, 0, 8, 38, 0, 5, 0);
    else if(animation == openborconstant("ANI_GET") && state != 19)
        bd_enter(player, 19, animation, 0, 8, 34, 0, 5, 0);
    else if(animation == openborconstant("ANI_SPAWN") && state != 22)
        bd_enter(player, 22, animation, 0, 6, 36, 0, 6, 0);
    else if(animation == openborconstant("ANI_RESPAWN") && state != 23)
        bd_enter(player, 23, animation, 0, 6, 42, 0, 7, 0);
}

void bd_present_jump_pose(void player)
{
    int phase;
    int phase_tick;
    int pose;
    phase = getglobalvar("bd_jump_phase");
    phase_tick = getglobalvar("bd_jump_phase_tick") - 1;
    if(phase_tick < 0) phase_tick = 0;
    if(phase == 0)
    {
        pose = phase_tick / 2;
        if(pose > 1) pose = 1;
    }
    else if(phase == 1)
    {
        pose = 2 + (phase_tick / 2);
        if(pose > 3) pose = 3;
    }
    else
    {
        pose = 4 + (phase_tick / 2);
        if(pose > 5) pose = 5;
    }
    updateframe(player, pose);
}

void bd_release_owner()
{
    void oldplayer;
    oldplayer = getglobalvar("bd_player");
    if(oldplayer != NULL() && getentityproperty(oldplayer, "name") == "BlackDave")
    {
        changeentityproperty(oldplayer, "aiflag", "blocking", 0);
        changeentityproperty(oldplayer, "aiflag", "attacking", 0);
        changeentityproperty(oldplayer, "aiflag", "invincible", 0);
        changeentityproperty(oldplayer, "noaicontrol", 0);
    }
    setglobalvar("bd_player", NULL());
    setglobalvar("bd_initialized", 0);
    setglobalvar("bd_owned", 0);
    setglobalvar("bd_clock_valid", 0);
    setglobalvar("bd_clock_accumulator", 0);
}

void bd_run_pose_qa(void player)
{
    int tick;
    int request;
    tick = getglobalvar("bd_qa_tick");
    request = tick / 12;
    changeentityproperty(player, "takeaction", NULL());
    changeentityproperty(player, "velocity", 0, 0, 0);
    if(request < 220 && request != getglobalvar("bd_qa_request"))
    {
        setglobalvar("bd_qa_request", request);
        setglobalvar("bd_qa_player", player);
        bd_apply_qa_pose(player, request);
    }
    if(request < 220) setglobalvar("bd_qa_tick", tick + 1);
}

void bd_fixed_step(void player)
{
    int state;
    int tick;
    int moving;
    int attack_edge;
    int kick_edge;
    int power_edge;
    int ranged_edge;
    int jump_edge;
    int block_held;
    int next_route;
    int current_step;
    int current_route;
    int total;
    int buffer_start;
    int direction;
    int desired_direction;
    int move_left;
    int move_right;
    int move_up;
    int move_down;
    int health;
    int grounded;
    int phase;
    int phase_tick;
    float tossv;
    float y;
    float base;

    health = getentityproperty(player, "health");
    if(getglobalvar("bd_death_handoff") == 1)
    {
        if(health <= 0) return;
        setglobalvar("bd_death_handoff", 0);
        changeentityproperty(player, "noaicontrol", 1);
        bd_enter_spawn_state(player, getentityproperty(player, "animationid"));
        return;
    }
    changeentityproperty(player, "noaicontrol", 1);
    changeentityproperty(player, "takeaction", NULL());
    if(getglobalvar("fof2_qa_dave_enabled") == 1 || getrecordingstatus() == 2)
    {
        bd_run_pose_qa(player);
        return;
    }
    if(getglobalvar("bd_qa_request") >= 0)
    {
        setglobalvar("bd_qa_tick", 0);
        setglobalvar("bd_qa_request", -1);
        bd_enter_idle(player);
    }

    move_left = playerkeys(0, 0, "moveleft") != 0;
    move_right = playerkeys(0, 0, "moveright") != 0;
    move_up = playerkeys(0, 0, "moveup") != 0;
    move_down = playerkeys(0, 0, "movedown") != 0;
    moving = move_left || move_right || move_up || move_down;
    block_held = playerkeys(0, 0, "attack4") != 0;
    attack_edge = getglobalvar("bd_pending_attack");
    kick_edge = getglobalvar("bd_pending_kick");
    power_edge = getglobalvar("bd_pending_power");
    ranged_edge = getglobalvar("bd_pending_ranged");
    jump_edge = getglobalvar("bd_pending_jump");
    setglobalvar("bd_pending_attack", 0);
    setglobalvar("bd_pending_kick", 0);
    setglobalvar("bd_pending_power", 0);
    setglobalvar("bd_pending_ranged", 0);
    setglobalvar("bd_pending_jump", 0);

    bd_sync_reaction(player);
    bd_consume_confirmed_contact(player);
    if(getglobalvar("bd_contact_pause") > 0)
    {
        setglobalvar("bd_contact_pause", getglobalvar("bd_contact_pause") - 1);
        state = getglobalvar("bd_state");
        if(state == 20) bd_present_route_pose(player);
        else if(state == 11) bd_present_phased_pose(player, 18, 6, 36);
        else if(state == 12) bd_present_phased_pose(player, 30, 12, 48);
        else if(state == 13) bd_present_phased_pose(player, 8, 6, 22);
        else if(state == 14) bd_present_phased_pose(player, 10, 7, 23);
        else bd_present_pose(player);
        return;
    }

    state = getglobalvar("bd_state");
    tick = getglobalvar("bd_state_tick") + 1;
    setglobalvar("bd_state_tick", tick);
    bd_apply_ground_motion(player, state, move_left, move_right, move_up, move_down);

    if(state == 20)
    {
        next_route = 0;
        if(attack_edge) next_route = 1;
        if(kick_edge) next_route = 2;
        if(power_edge) next_route = 3;
        current_step = getglobalvar("bd_step");
        current_route = getglobalvar("bd_route");
        total = getglobalvar("bd_pose_total");
        buffer_start = total - bd_route_buffer_ticks(current_route, current_step);
        if(next_route != 0 && tick >= buffer_start && bd_route_can_cancel(current_route, current_step, next_route))
            setglobalvar("bd_buffered_route", next_route);
        next_route = getglobalvar("bd_buffered_route");
        if(next_route != 0 && tick >= bd_route_cancel(current_route, current_step))
        {
            if(next_route != 3 || bd_spend_mp(player, 10, 0) == 1)
            {
                bd_enter_attack(player, next_route, current_step + 1);
                return;
            }
            setglobalvar("bd_buffered_route", 0);
        }
        if(tick >= total)
        {
            bd_enter_idle(player);
            return;
        }
    }
    else if(state == 1)
    {
        desired_direction = -1;
        direction = getentityproperty(player, "direction");
        if(move_left && !move_right) desired_direction = 0;
        if(move_right && !move_left) desired_direction = 1;
        if(desired_direction >= 0 && desired_direction != direction)
        {
            setglobalvar("bd_pending_direction", desired_direction);
            bd_enter(player, 5, openborconstant("ANI_TURN"), 0, 4, 10, 0, 3, 1);
            return;
        }
        if(block_held && jump_edge) { bd_begin_dodge(player); return; }
        if(block_held)
        {
            bd_enter(player, 9, openborconstant("ANI_BLOCK"), 0, 6, 12, 0, 2, 1);
            return;
        }
        if(jump_edge)
        {
            bd_enter(player, 6, openborconstant("ANI_JUMPDELAY"), 0, 4, 8, 0, 2, 1);
            return;
        }
        if(ranged_edge && power_edge)
        {
            if(bd_spend_mp(player, 100, 1) != 1) return;
            bd_arm_native_attack(3, 9);
            changeentityproperty(player, "aiflag", "attacking", 1);
            setglobalvar("bd_attack_flag", 1);
            bd_enter(player, 12, openborconstant("ANI_SPECIAL"), 0, 16, 90, 0, 2, 1);
            return;
        }
        if(ranged_edge)
        {
            if(bd_spend_mp(player, 20, 0) != 1) return;
            bd_arm_native_attack(3, 8);
            setglobalvar("bd_projectile_fired", 0);
            bd_enter(player, 11, openborconstant("ANI_ATTACKUP"), 0, 14, 60, 0, 2, 1);
            return;
        }
        if(attack_edge) { bd_enter_attack(player, 1, 1); return; }
        if(kick_edge) { bd_enter_attack(player, 2, 1); return; }
        if(power_edge && bd_spend_mp(player, 10, 0) == 1) { bd_enter_attack(player, 3, 1); return; }
        if(moving)
        {
            bd_enter(player, 2, openborconstant("ANI_WALK"), 0, 4, 12, 0, 3, 1);
            return;
        }
    }
    else if(state == 2 && tick >= 12)
    {
        if(moving) bd_enter(player, 3, openborconstant("ANI_WALK"), 4, 12, 48, 1, 4, 1);
        else bd_enter(player, 4, openborconstant("ANI_WALK"), 16, 4, 12, 0, 3, 1);
        return;
    }
    else if(state == 3)
    {
        if(!moving)
        {
            bd_enter(player, 4, openborconstant("ANI_WALK"), 16, 4, 12, 0, 3, 1);
            return;
        }
        bd_present_walk_pose(player);
        return;
    }
    else if(state == 4 && tick >= 12) { bd_enter_idle(player); return; }
    else if(state == 5 && tick >= 10)
    {
        direction = getglobalvar("bd_pending_direction");
        if(direction >= 0) changeentityproperty(player, "direction", direction);
        setglobalvar("bd_pending_direction", -1);
        if(moving) bd_enter(player, 2, openborconstant("ANI_WALK"), 0, 4, 12, 0, 3, 1);
        else bd_enter_idle(player);
        return;
    }
    else if(state == 6 && tick >= 8)
    {
        if(getentityproperty(player, "direction") == 0) tossentity(player, 4, -2, 0);
        else tossentity(player, 4, 2, 0);
        changeentityproperty(player, "aiflag", "jumping", 1);
        setglobalvar("bd_jump_phase", 0);
        setglobalvar("bd_jump_phase_tick", 0);
        bd_enter(player, 7, openborconstant("ANI_JUMP"), 0, 6, 12, 0, 2, 1);
        return;
    }
    else if(state == 7)
    {
        if(attack_edge)
        {
            bd_arm_native_attack(1, 8);
            changeentityproperty(player, "aiflag", "attacking", 1);
            setglobalvar("bd_attack_flag", 1);
            bd_enter(player, 13, openborconstant("ANI_JUMPATTACK"), 0, 8, 36, 0, 5, 1);
            return;
        }
        if(kick_edge)
        {
            bd_arm_native_attack(2, 8);
            changeentityproperty(player, "aiflag", "attacking", 1);
            setglobalvar("bd_attack_flag", 1);
            bd_enter(player, 14, openborconstant("ANI_JUMPATTACK2"), 0, 8, 40, 0, 5, 1);
            return;
        }
        tossv = getentityproperty(player, "tossv");
        y = getentityproperty(player, "y");
        base = getentityproperty(player, "base");
        phase = getglobalvar("bd_jump_phase");
        phase_tick = getglobalvar("bd_jump_phase_tick") + 1;
        if(phase == 0 && tossv <= 0)
        {
            phase = 1;
            phase_tick = 0;
        }
        else if(phase == 1 && phase_tick >= 4)
        {
            phase = 2;
            phase_tick = 0;
        }
        setglobalvar("bd_jump_phase", phase);
        setglobalvar("bd_jump_phase_tick", phase_tick);
        grounded = y <= base && tossv <= 0;
        if(grounded && phase == 2 && phase_tick >= 4)
        {
            changeentityproperty(player, "aiflag", "jumping", 0);
            bd_enter(player, 8, openborconstant("ANI_JUMPLAND"), 0, 4, 10, 0, 3, 1);
            return;
        }
        bd_present_jump_pose(player);
        return;
    }
    else if(state == 13 || state == 14)
    {
        total = 36;
        if(state == 14) total = 40;
        if(tick >= total)
        {
            bd_clear_attack(player);
            tossv = getentityproperty(player, "tossv");
            if(tossv > 0) setglobalvar("bd_jump_phase", 0);
            else setglobalvar("bd_jump_phase", 2);
            setglobalvar("bd_jump_phase_tick", 0);
            bd_enter(player, 7, openborconstant("ANI_JUMP"), 0, 6, 12, 0, 2, 1);
            return;
        }
    }
    else if(state == 8 && tick >= 10) { bd_enter_idle(player); return; }
    else if(state == 9)
    {
        if(tick >= 6) changeentityproperty(player, "aiflag", "blocking", openborconstant("BLOCK_STATE_ACTIVE"));
        if(!block_held && tick >= 6)
        {
            changeentityproperty(player, "aiflag", "blocking", 0);
            bd_enter(player, 24, openborconstant("ANI_BLOCK"), 0, 6, 8, 0, 2, 0);
            return;
        }
        if(tick > 12) setglobalvar("bd_state_tick", 10);
    }
    else if(state == 21 && tick >= 6)
    {
        if(block_held)
        {
            bd_enter(player, 9, openborconstant("ANI_BLOCK"), 0, 6, 12, 0, 2, 1);
        }
        else bd_enter_idle(player);
        return;
    }
    else if(state == 10)
    {
        if(tick <= 8)
        {
            if(getentityproperty(player, "direction") == 0) changeentityproperty(player, "velocity", -6, 0);
            else changeentityproperty(player, "velocity", 6, 0);
        }
        else changeentityproperty(player, "velocity", 0, 0);
        if(tick >= 3 && tick <= 11)
        {
            changeentityproperty(player, "invincible", openborconstant("INVINCIBLE_INTANGIBLE"));
            changeentityproperty(player, "invinctime", openborvariant("elapsed_time") + 4);
            setglobalvar("bd_dodge_invul", 1);
        }
        if(tick > 11 && getglobalvar("bd_dodge_invul") == 1)
        {
            changeentityproperty(player, "aiflag", "invincible", 0);
            setglobalvar("bd_dodge_invul", 0);
        }
        if(tick >= 24) { bd_enter_idle(player); return; }
    }
    else if(state == 11)
    {
        if(tick >= 18 && getglobalvar("bd_projectile_fired") != 1)
        {
            bd_spawn_ranged_projectile(player);
            setglobalvar("bd_projectile_fired", 1);
        }
        if(tick >= 60) { bd_enter_idle(player); return; }
        bd_present_phased_pose(player, 18, 6, 36);
        return;
    }
    else if(state == 12)
    {
        if(tick >= 90) { bd_enter_idle(player); return; }
        bd_present_phased_pose(player, 30, 12, 48);
        return;
    }
    else if(state == 15 && tick >= 18) { bd_enter_idle(player); return; }
    else if(state == 16)
    {
        y = getentityproperty(player, "y");
        base = getentityproperty(player, "base");
        tossv = getentityproperty(player, "tossv");
        grounded = y <= base && tossv <= 0;
        if(grounded && tick >= 38)
        {
            if(getentityproperty(player, "health") <= 0)
                bd_enter(player, 25, openborconstant("ANI_FALL"), 8, 2, 22, 0, 12, 0);
            else
                bd_enter(player, 17, openborconstant("ANI_FALL"), 8, 6, 36, 1, 6, 0);
            return;
        }
    }
    else if(state == 25 && tick >= 22)
    {
        changeentityproperty(player, "aiflag", "animating", 0);
        changeentityproperty(player, "noaicontrol", 0);
        changeentityproperty(player, "takeaction", "common_lie");
        setglobalvar("bd_death_handoff", 1);
        return;
    }
    else if(state == 17 && tick >= 36)
    {
        bd_enter(player, 18, openborconstant("ANI_RISE"), 0, 8, 40, 0, 5, 1);
        return;
    }
    else if(state == 18 && tick >= 40) { bd_enter_idle(player); return; }
    else if(state == 19 && tick >= 34) { bd_enter_idle(player); return; }
    else if(state == 22 && tick >= 36) { bd_enter_idle(player); return; }
    else if(state == 23 && tick >= 42) { bd_enter_idle(player); return; }
    else if(state == 24)
    {
        bd_present_reverse_pose(player);
        if(tick >= 8) { bd_enter_idle(player); return; }
        return;
    }

    if(state == 20) bd_present_route_pose(player);
    else if(state == 13) bd_present_phased_pose(player, 8, 6, 22);
    else if(state == 14) bd_present_phased_pose(player, 10, 7, 23);
    else bd_present_pose(player);
}

void main()
{
    void player;
    void player_name;
    int now;
    int last;
    int delta;
    int accumulator;
    if(openborvariant("in_level") != 1)
    {
        bd_release_owner();
        return;
    }
    if(openborvariant("game_paused") != 0)
    {
        setglobalvar("bd_clock_valid", 0);
        setglobalvar("bd_clock_accumulator", 0);
        return;
    }
    player = getplayerproperty(0, "entity");
    if(player == NULL())
    {
        bd_release_owner();
        return;
    }
    player_name = getentityproperty(player, "name");
    if(player_name != "BlackDave")
    {
        bd_release_owner();
        return;
    }
    if(getglobalvar("bd_initialized") != 1 || getglobalvar("bd_player") != player)
    {
        bd_release_owner();
        setglobalvar("bd_initialized", 1);
        setglobalvar("bd_owned", 1);
        setglobalvar("bd_player", player);
        setglobalvar("bd_previous_x", getentityproperty(player, "x"));
        setglobalvar("bd_previous_z", getentityproperty(player, "z"));
        setglobalvar("bd_death_handoff", 0);
        changeentityproperty(player, "noaicontrol", 1);
        bd_enter_spawn_state(player, getentityproperty(player, "animationid"));
    }
    if(getglobalvar("bd_death_handoff") != 1)
    {
        changeentityproperty(player, "noaicontrol", 1);
        changeentityproperty(player, "takeaction", NULL());
    }
    if(getglobalvar("fof2_qa_dave_enabled") != 1 && getrecordingstatus() != 2)
    {
        if(playerkeys(0, 1, "attack") != 0) setglobalvar("bd_pending_attack", 1);
        if(playerkeys(0, 1, "attack2") != 0) setglobalvar("bd_pending_kick", 1);
        if(playerkeys(0, 1, "special") != 0) setglobalvar("bd_pending_power", 1);
        if(playerkeys(0, 1, "attack3") != 0) setglobalvar("bd_pending_ranged", 1);
        if(playerkeys(0, 1, "jump") != 0) setglobalvar("bd_pending_jump", 1);
    }
    now = openborvariant("elapsed_time");
    if(getglobalvar("bd_clock_valid") != 1)
    {
        setglobalvar("bd_clock_valid", 1);
        setglobalvar("bd_clock_time", now);
        setglobalvar("bd_clock_accumulator", 200);
    }
    last = getglobalvar("bd_clock_time");
    delta = now - last;
    if(delta < 0) delta = 0;
    if(delta > 20) delta = 20;
    setglobalvar("bd_clock_time", now);
    accumulator = getglobalvar("bd_clock_accumulator") + delta * 60;
    while(accumulator >= 200)
    {
        accumulator = accumulator - 200;
        bd_fixed_step(player);
    }
    setglobalvar("bd_clock_accumulator", accumulator);
}
