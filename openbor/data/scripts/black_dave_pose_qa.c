/* Generated deterministic Black Dave pose request executor. */
void main()
{
    void player;
    int request;
    int animation;
    int frame;
    player = getglobalvar("bd_qa_player");
    request = getglobalvar("bd_qa_request");
    if(player == NULL()) return;
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
