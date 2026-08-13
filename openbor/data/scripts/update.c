void oncreate()
{
    setglobalvar("fades_bd_state", 1);
    setglobalvar("fades_bd_state_tick", 0);
    setglobalvar("fades_bd_pose_tick", 0);
    setglobalvar("fades_bd_pose_index", 0);
    setglobalvar("fades_bd_state_phase", 0);
    setglobalvar("fades_bd_route", 0);
    setglobalvar("fades_bd_step", 0);
    setglobalvar("fades_bd_face", 1);
    setglobalvar("fades_bd_last_face", 1);
    setglobalvar("fades_bd_root_x_prev", 0);
    setglobalvar("fades_bd_root_z_prev", 0);
    setglobalvar("fades_bd_last_health", 0);
    setglobalvar("fades_bd_last_event", 0);
    setglobalvar("fades_bd_last_event_arg1", 0);
    setglobalvar("fades_bd_last_event_arg2", 0);
    setglobalvar("fades_bd_last_event_tick", 0);
    setglobalvar("fades_bd_event_category", 0);
    setglobalvar("fades_bd_event_combat", 0);
    setglobalvar("fades_bd_event_anim", 0);
    setglobalvar("fades_bd_event_vfx", 0);
    setglobalvar("fades_bd_event_audio", 0);
    setglobalvar("fades_bd_event_rumble", 0);
    setglobalvar("fades_bd_event_camera", 0);
    setglobalvar("fades_bd_event_payload", 0);
    setglobalvar("fades_bd_event_ready", 0);
    setglobalvar("fades_bd_event_ready_arg1", 0);
    setglobalvar("fades_bd_event_ready_arg2", 0);
    setglobalvar("fades_bd_buffer_route", 0);
    setglobalvar("fades_bd_buffer_ttl", 0);
    setglobalvar("fades_bd_buffer_latched_tick", 0);
    setglobalvar("fades_bd_startup_ticks", 0);
    setglobalvar("fades_bd_active_ticks", 0);
    setglobalvar("fades_bd_recovery_ticks", 0);
    setglobalvar("fades_bd_cancel_ticks", 0);
    setglobalvar("fades_bd_air_attack_used", 0);
    setglobalvar("fades_bd_hitstop", 0);
    setglobalvar("fades_bd_confirmed_contact", 0);
    setglobalvar("fades_bd_confirmed_contact_route", 0);
    setglobalvar("fades_bd_confirmed_contact_step", 0);
    setglobalvar("fades_bd_lockout", 0);
    setglobalvar("fades_bd_jump_from_ground_z", 0);
    setglobalvar("fades_bd_tick", 0);
    setglobalvar("fades_bd_snapshot_state", 1);
    setglobalvar("fades_bd_snapshot_clip", openborconstant("ANI_IDLE"));
    setglobalvar("fades_bd_snapshot_pose", 0);
    setglobalvar("fades_bd_snapshot_phase", 0);
    setglobalvar("fades_bd_snapshot_state_tick", 0);
    setglobalvar("fades_bd_snapshot_pose_tick", 0);
    setglobalvar("fades_bd_snapshot_root_x", 0);
    setglobalvar("fades_bd_snapshot_root_z", 0);
    setglobalvar("fades_bd_snapshot_face", 1);
    setglobalvar("fades_bd_snapshot_anchor_rear_x", 0);
    setglobalvar("fades_bd_snapshot_anchor_rear_z", 0);
    setglobalvar("fades_bd_snapshot_anchor_front_x", 0);
    setglobalvar("fades_bd_snapshot_anchor_front_z", 0);
    setglobalvar("fades_bd_snapshot_bounds_x", 24);
    setglobalvar("fades_bd_snapshot_bounds_y", 18);
    setglobalvar("fades_bd_snapshot_bounds_w", 144);
    setglobalvar("fades_bd_snapshot_bounds_h", 138);
    setglobalvar("fades_bd_snapshot_bounds_off", 18);
    setglobalvar("fades_bd_snapshot_event_category", 0);
    setglobalvar("fades_bd_snapshot_event_combat", 0);
    setglobalvar("fades_bd_snapshot_event_anim", 0);
    setglobalvar("fades_bd_snapshot_event_vfx", 0);
    setglobalvar("fades_bd_snapshot_event_audio", 0);
    setglobalvar("fades_bd_snapshot_event_rumble", 0);
    setglobalvar("fades_bd_snapshot_event_camera", 0);
    setglobalvar("fades_bd_snapshot_event_payload", 0);
    log("[FADES_SM] authoritative state machine initialized\n");
}

int route_for_input(int attack_edge, int special_edge, int jump_edge, int down_held, int up_held)
{
    if(attack_edge == 0)
    {
        return 0;
    }
    if(special_edge == 1)
    {
        return 3;
    }
    if(down_held == 1)
    {
        return 2;
    }
    if(jump_edge == 1 && down_held == 0)
    {
        return 0;
    }
    return 1;
}

int state_duration(int state)
{
    if(state == 12) return 12;
    if(state == 13) return 11;
    if(state == 14) return 24;
    if(state == 15) return 16;
    if(state == 16) return 20;
    if(state == 17) return 36;
    if(state == 18) return 30;
    if(state == 19 || state == 20) return 18;
    return 0;
}

int pose_hold_ticks(int state, int pose, int phase)
{
    // At 60 simulation ticks per second these authored holds present on a
    // stable 30 Hz grid. Anticipation and recovery deliberately breathe while
    // travel/contact drawings pass quickly.
    if(state == 21)
    {
        if(pose == 0) return 4;
        if(pose == 1) return 2;
        if(pose == 2) return 2;
        if(pose == 3) return 2;
        return phase == 2 ? 4 : 2;
    }
    if(state == 1 || state == 2) return 6;
    if(state == 3 || state == 5 || state == 6 || state == 11 || state == 15) return 2;
    if(state == 4) return 2;
    if(state == 7 || state == 9 || state == 12 || state == 13 || state == 14) return 3;
    return 2;
}

int clamp_route_anim(int route, int step)
{
    if(step == 1) return openborconstant("ANI_FREESPECIAL1");
    if(step == 2) return openborconstant("ANI_FREESPECIAL2");
    if(step == 3) return openborconstant("ANI_FREESPECIAL3");
    if(step == 4) return openborconstant("ANI_FREESPECIAL4");
    if(step == 5) return openborconstant("ANI_FREESPECIAL5");
    if(step == 6) return openborconstant("ANI_FREESPECIAL6");
    if(step == 7) return openborconstant("ANI_FREESPECIAL7");
    return openborconstant("ANI_ATTACK1");
}

void emit_event(int event_id, int arg1, int arg2, int tick)
{
    int category;
    int combat_event;
    int anim_event;
    int vfx_event;
    int audio_event;
    int rumble_event;
    int camera_event;

    category = 0;
    combat_event = 0;
    anim_event = 0;
    vfx_event = 0;
    audio_event = 0;
    rumble_event = 0;
    camera_event = 0;

    if((event_id >= 1101 && event_id <= 1115))
    {
        combat_event = event_id;
        category = category | 1;
        if(event_id == 1111 || event_id == 1112 || event_id == 1113 || event_id == 1114)
        {
            audio_event = event_id;
            category = category | 4;
            rumble_event = event_id;
            category = category | 8;
        }
        if(event_id == 1110)
        {
            audio_event = event_id;
            category = category | 4;
        }
    }
    if((event_id >= 1201 && event_id <= 1206) || (event_id >= 1301 && event_id <= 1306))
    {
        anim_event = event_id;
        category = category | 2;
    }
    if((event_id >= 1301 && event_id <= 1305))
    {
        camera_event = event_id;
        category = category | 16;
    }
    if(event_id >= 1210 && event_id <= 1211)
    {
        vfx_event = event_id;
        anim_event = event_id;
        category = category | 2 | 32;
    }
    if(event_id >= 1310 && event_id <= 1313)
    {
        vfx_event = event_id;
        category = category | 32;
    }
    if(event_id >= 900 && event_id <= 920)
    {
        anim_event = event_id;
        category = category | 2;
    }
    if(event_id == 1306)
    {
        combat_event = event_id;
        category = category | 1;
    }

    setglobalvar("fades_bd_event_category", category);
    setglobalvar("fades_bd_event_combat", combat_event);
    setglobalvar("fades_bd_event_anim", anim_event);
    setglobalvar("fades_bd_event_vfx", vfx_event);
    setglobalvar("fades_bd_event_audio", audio_event);
    setglobalvar("fades_bd_event_rumble", rumble_event);
    setglobalvar("fades_bd_event_camera", camera_event);
    setglobalvar("fades_bd_event_ready", event_id);
    setglobalvar("fades_bd_event_ready_arg1", arg1);
    setglobalvar("fades_bd_event_ready_arg2", arg2);
    if((getglobalvar("fades_bd_last_event") != event_id)
        || (getglobalvar("fades_bd_last_event_tick") != tick))
    {
        setglobalvar("fades_bd_last_event", event_id);
        setglobalvar("fades_bd_last_event_arg1", arg1);
        setglobalvar("fades_bd_last_event_arg2", arg2);
        setglobalvar("fades_bd_last_event_tick", tick);
    }
}

void clear_buffer()
{
    setglobalvar("fades_bd_buffer_route", 0);
    setglobalvar("fades_bd_buffer_ttl", 0);
    setglobalvar("fades_bd_buffer_latched_tick", 0);
}

void schedule_buffer(int route, int tick, int ttl)
{
    if(route == 0)
    {
        return;
    }
    if(ttl <= 0)
    {
        return;
    }
    setglobalvar("fades_bd_buffer_route", route);
    setglobalvar("fades_bd_buffer_ttl", ttl);
    setglobalvar("fades_bd_buffer_latched_tick", tick);
}

int route_startup(int route, int step)
{
    if(step < 1 || step > 7)
    {
        return 0;
    }
    if(route == 1)
    {
        if(step == 1) return 5;
        if(step == 2) return 4;
        if(step == 3) return 7;
        if(step == 4) return 5;
        if(step == 5) return 10;
        if(step == 6) return 8;
        if(step == 7) return 6;
        return 6;
    }
    if(route == 2)
    {
        if(step == 1) return 4;
        if(step == 2) return 5;
        if(step == 3) return 5;
        if(step == 4) return 8;
        if(step == 5) return 7;
        if(step == 6) return 10;
        if(step == 7) return 6;
        return 6;
    }
    if(route == 3)
    {
        if(step == 1) return 11;
        if(step == 2) return 11;
        if(step == 3) return 13;
        if(step == 4) return 14;
        if(step == 5) return 10;
        if(step == 6) return 11;
        if(step == 7) return 12;
        return 12;
    }
    return 6;
}

int route_active(int route, int step)
{
    if(step < 1 || step > 7)
    {
        return 0;
    }
    if(route == 1)
    {
        if(step == 1) return 4;
        if(step == 2) return 4;
        if(step == 3) return 6;
        if(step == 4) return 5;
        if(step == 5) return 6;
        if(step == 6) return 6;
        if(step == 7) return 5;
        return 5;
    }
    if(route == 2)
    {
        if(step == 1) return 4;
        if(step == 2) return 4;
        if(step == 3) return 5;
        if(step == 4) return 6;
        if(step == 5) return 6;
        if(step == 6) return 6;
        if(step == 7) return 5;
        return 5;
    }
    if(route == 3)
    {
        if(step == 1) return 5;
        if(step == 2) return 5;
        if(step == 3) return 6;
        if(step == 4) return 7;
        if(step == 5) return 6;
        if(step == 6) return 7;
        if(step == 7) return 8;
        return 8;
    }
    return 6;
}

int route_recovery(int route, int step)
{
    if(step < 1 || step > 7)
    {
        return 0;
    }
    if(route == 1)
    {
        if(step == 1) return 8;
        if(step == 2) return 7;
        if(step == 3) return 14;
        if(step == 4) return 10;
        if(step == 5) return 18;
        if(step == 6) return 17;
        if(step == 7) return 10;
        return 10;
    }
    if(route == 2)
    {
        if(step == 1) return 7;
        if(step == 2) return 8;
        if(step == 3) return 10;
        if(step == 4) return 17;
        if(step == 5) return 14;
        if(step == 6) return 18;
        if(step == 7) return 10;
        return 10;
    }
    if(route == 3)
    {
        if(step == 1) return 13;
        if(step == 2) return 14;
        if(step == 3) return 17;
        if(step == 4) return 20;
        if(step == 5) return 14;
        if(step == 6) return 16;
        if(step == 7) return 19;
        return 19;
    }
    return 10;
}

int route_cancel(int route, int step)
{
    if(step < 1 || step > 7)
    {
        return 0;
    }
    if(route == 1)
    {
        if(step == 1) return 12;
        if(step == 2) return 11;
        if(step == 3) return 27;
        if(step == 4) return 14;
        if(step == 5) return 30;
        if(step == 6) return 29;
        if(step == 7) return 11;
        return 11;
    }
    if(route == 2)
    {
        if(step == 1) return 11;
        if(step == 2) return 11;
        if(step == 3) return 14;
        if(step == 4) return 29;
        if(step == 5) return 27;
        if(step == 6) return 30;
        if(step == 7) return 11;
        return 11;
    }
    if(route == 3)
    {
        if(step == 1) return 18;
        if(step == 2) return 20;
        if(step == 3) return 23;
        if(step == 4) return 25;
        if(step == 5) return 17;
        if(step == 6) return 19;
        if(step == 7) return 20;
        return 20;
    }
    return 14;
}

int route_buffer_window(int route, int step)
{
    if(step < 1 || step > 7)
    {
        return 12;
    }
    if(route == 1)
    {
        if(step == 1) return 14;
        if(step == 2) return 13;
        if(step == 3) return 14;
        if(step == 4) return 14;
        if(step == 5) return 17;
        if(step == 6) return 16;
        if(step == 7) return 14;
        return 12;
    }
    if(route == 2)
    {
        if(step == 1) return 13;
        if(step == 2) return 14;
        if(step == 3) return 14;
        if(step == 4) return 16;
        if(step == 5) return 14;
        if(step == 6) return 17;
        if(step == 7) return 14;
        return 12;
    }
    if(route == 3)
    {
        if(step == 1) return 13;
        if(step == 2) return 14;
        if(step == 3) return 16;
        if(step == 4) return 17;
        if(step == 5) return 17;
        if(step == 6) return 18;
        if(step == 7) return 19;
        return 12;
    }
    return 12;
}

int route_allows_cancel(int from_route, int from_step, int to_route)
{
    if(from_step < 1 || from_step > 7)
    {
        return 0;
    }
    if(from_route == 1)
    {
        if(to_route == 1)
        {
            return from_step != 7;
        }
        if(to_route == 2)
        {
            return from_step != 7;
        }
        if(to_route == 3)
        {
            return from_step != 7;
        }
        return 0;
    }
    if(from_route == 2)
    {
        if(to_route == 1)
        {
            return from_step != 7;
        }
        if(to_route == 2)
        {
            return from_step != 7;
        }
        if(to_route == 3)
        {
            return (from_step == 1) || (from_step == 2) || (from_step == 3);
        }
        return 0;
    }
    if(from_route == 3)
    {
        return (to_route == 3) && (from_step != 7);
    }
    return 0;
}

int route_anim_event_mask(int route, int step)
{
    if(route == 1)
    {
        if(step == 1) return 3;
        if(step == 2) return 3;
        if(step == 3) return 6;
        if(step == 4) return 3;
        if(step == 5) return 3;
        if(step == 6) return 3;
        if(step == 7) return 10;
        return 3;
    }
    if(route == 2)
    {
        if(step == 1) return 3;
        if(step == 2) return 3;
        if(step == 3) return 3;
        if(step == 4) return 3;
        if(step == 5) return 6;
        if(step == 6) return 3;
        if(step == 7) return 10;
        return 3;
    }
    if(route == 3)
    {
        if(step == 1) return 3;
        if(step == 2) return 3;
        if(step == 3) return 6;
        if(step == 4) return 6;
        if(step == 5) return 18;
        if(step == 6) return 20;
        if(step == 7) return 24;
        return 3;
    }
    return 3;
}

int route_vfx_event_mask(int route, int step)
{
    if(route == 1)
    {
        if(step == 1) return 3;
        if(step == 2) return 3;
        if(step == 3) return 3;
        if(step == 4) return 3;
        if(step == 5) return 3;
        if(step == 6) return 3;
        if(step == 7) return 18;
        return 3;
    }
    if(route == 2)
    {
        if(step == 1) return 3;
        if(step == 2) return 3;
        if(step == 3) return 3;
        if(step == 4) return 3;
        if(step == 5) return 3;
        if(step == 6) return 3;
        if(step == 7) return 18;
        return 3;
    }
    if(route == 3)
    {
        if(step == 1) return 3;
        if(step == 2) return 3;
        if(step == 3) return 3;
        if(step == 4) return 3;
        if(step == 5) return 24;
        if(step == 6) return 24;
        if(step == 7) return 24;
        return 3;
    }
    return 3;
}

void emit_route_events(int route, int step, int state_t, int startup, int active, int cancel_allowed, int tick)
{
    int anim_flags;
    int vfx_flags;
    int has_contact;
    int has_launch;
    int has_shockwave;
    int has_finish;
    int has_windup;

    anim_flags = route_anim_event_mask(route, step);
    vfx_flags = route_vfx_event_mask(route, step);
    has_windup = 0;
    has_contact = 0;
    has_launch = 0;
    has_shockwave = 0;
    has_finish = 0;
    if((anim_flags & 1) != 0)
    {
        has_windup = 1;
    }
    if((anim_flags & 2) != 0)
    {
        has_contact = 1;
    }
    if((anim_flags & 4) != 0)
    {
        has_launch = 1;
    }
    if((anim_flags & 8) != 0)
    {
        has_finish = 1;
    }
    if((anim_flags & 16) != 0)
    {
        has_shockwave = 1;
    }

    if(state_t == 1)
    {
        if(has_windup == 1)
        {
            emit_event(1110, route, step, tick);
        }
        if((vfx_flags & 1) != 0)
        {
            emit_event(1210, route, step, tick);
        }
    }
    if(state_t == startup + 1)
    {
        if(has_contact == 1)
        {
            emit_event(1111, route, step, tick);
        }
        if(has_launch == 1)
        {
            emit_event(1112, route, step, tick);
        }
        if(has_shockwave == 1)
        {
            emit_event(1113, route, step, tick);
        }
        if((vfx_flags & 1) != 0)
        {
            emit_event(1310, route, step, tick);
        }
        if((vfx_flags & 2) != 0)
        {
            emit_event(1311, route, step, tick);
        }
        if((vfx_flags & 8) != 0)
        {
            emit_event(1312, route, step, tick);
        }
        if((vfx_flags & 16) != 0)
        {
            emit_event(1313, route, step, tick);
        }
    }
    if(state_t == startup + active + 1)
    {
        if(has_finish == 1)
        {
            emit_event(1114, route, step, tick);
        }
        if((vfx_flags & 1) != 0)
        {
            emit_event(1211, route, step, tick);
        }
    }
    if(cancel_allowed > 0 && state_t == cancel_allowed)
    {
        emit_event(1115, route, step, tick);
    }
}

void set_state(int state, int tick)
{
    setglobalvar("fades_bd_state", state);
    setglobalvar("fades_bd_state_tick", 0);
    setglobalvar("fades_bd_pose_tick", 0);
    setglobalvar("fades_bd_pose_index", 0);
    setglobalvar("fades_bd_state_phase", 0);
    emit_event(900 + state, state, tick, tick);
}

void apply_animation_for_state(void player, int state, int route, int step)
{
    int anim_id;

    if(state == 1)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_IDLE"));
    }
    else if(state == 2)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL1"));
    }
    else if(state == 3)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL2"));
    }
    else if(state == 4)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_WALK"));
    }
    else if(state == 5)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL4"));
    }
    else if(state == 6)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL3"));
    }
    else if(state == 7)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL5"));
    }
    else if(state == 8)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL6"));
    }
    else if(state == 9)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL7"));
    }
    else if(state == 10)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL1"));
    }
    else if(state == 11)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL2"));
    }
    else if(state == 12)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL3"));
    }
    else if(state == 13)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_PAIN"));
    }
    else if(state == 14)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FALL"));
    }
    else if(state == 15)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_RISE"));
    }
    else if(state == 16)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL4"));
    }
    else if(state == 17)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL5"));
    }
    else if(state == 18)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL6"));
    }
    else if(state == 19)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL7"));
    }
    else if(state == 20)
    {
        changeentityproperty(player, "animation", openborconstant("ANI_FREESPECIAL1"));
    }
    else
    {
        anim_id = clamp_route_anim(route, step);
        if(anim_id == 0)
        {
            anim_id = openborconstant("ANI_ATTACK1");
        }
        changeentityproperty(player, "animation", anim_id);
    }
}

void snapshot_pose_and_state(int state, int route, int step, int tick, void player, int phase)
{
    int pose;
    int pose_tick;

    pose = getglobalvar("fades_bd_pose_index");
    pose_tick = getglobalvar("fades_bd_pose_tick");

    setglobalvar("fades_bd_snapshot_state", state);
    setglobalvar("fades_bd_snapshot_state_tick", getglobalvar("fades_bd_state_tick"));
    setglobalvar("fades_bd_snapshot_pose", pose);
    setglobalvar("fades_bd_snapshot_pose_tick", pose_tick);
    setglobalvar("fades_bd_snapshot_phase", phase);
    setglobalvar("fades_bd_snapshot_route", route);
    setglobalvar("fades_bd_snapshot_step", step);
    setglobalvar("fades_bd_snapshot_tick", tick);
    setglobalvar("fades_bd_snapshot_face", getglobalvar("fades_bd_face"));
    setglobalvar("fades_bd_snapshot_clip", getentityproperty(player, "animationid"));
    setglobalvar("fades_bd_snapshot_root_x", getentityproperty(player, "x"));
    setglobalvar("fades_bd_snapshot_root_z", getentityproperty(player, "z"));
    setglobalvar("fades_bd_snapshot_anchor_rear_x", getentityproperty(player, "x") - 16);
    setglobalvar("fades_bd_snapshot_anchor_rear_z", getentityproperty(player, "z") );
    setglobalvar("fades_bd_snapshot_anchor_front_x", getentityproperty(player, "x") + 16);
    setglobalvar("fades_bd_snapshot_anchor_front_z", getentityproperty(player, "z") );
    setglobalvar("fades_bd_snapshot_bounds_x", 24);
    setglobalvar("fades_bd_snapshot_bounds_y", 18);
    setglobalvar("fades_bd_snapshot_bounds_w", 144);
    setglobalvar("fades_bd_snapshot_bounds_h", 138);
    setglobalvar("fades_bd_snapshot_bounds_off", 18);
    setglobalvar("fades_bd_snapshot_event", getglobalvar("fades_bd_last_event"));
    setglobalvar("fades_bd_snapshot_event_category", getglobalvar("fades_bd_event_category"));
    setglobalvar("fades_bd_snapshot_event_combat", getglobalvar("fades_bd_event_combat"));
    setglobalvar("fades_bd_snapshot_event_anim", getglobalvar("fades_bd_event_anim"));
    setglobalvar("fades_bd_snapshot_event_vfx", getglobalvar("fades_bd_event_vfx"));
    setglobalvar("fades_bd_snapshot_event_audio", getglobalvar("fades_bd_event_audio"));
    setglobalvar("fades_bd_snapshot_event_rumble", getglobalvar("fades_bd_event_rumble"));
    setglobalvar("fades_bd_snapshot_event_camera", getglobalvar("fades_bd_event_camera"));
    setglobalvar("fades_bd_snapshot_event_payload", getglobalvar("fades_bd_event_payload"));

    setglobalvar("fades_bd_snapshot_clip_phase", phase);
    setglobalvar("fades_bd_snapshot_event_arg1", getglobalvar("fades_bd_last_event_arg1"));
    setglobalvar("fades_bd_snapshot_event_arg2", getglobalvar("fades_bd_last_event_arg2"));
}

void advance_pose_timing()
{
    int pstate;
    int phase;
    int pose;
    int pose_tick;

    pstate = getglobalvar("fades_bd_state");
    pose = getglobalvar("fades_bd_pose_index");
    pose_tick = getglobalvar("fades_bd_pose_tick");
    phase = getglobalvar("fades_bd_state_phase");

    pose_tick = pose_tick + 1;
    if(pose_tick >= pose_hold_ticks(pstate, pose, phase))
    {
        pose_tick = 0;
        pose = pose + 1;
    }
    if(pose > 4 && (pstate == 1 || pstate == 2 || pstate == 4))
    {
        pose = 0;
    }
    else if(pose > 4)
    {
        pose = 4;
    }

    setglobalvar("fades_bd_pose_tick", pose_tick);
    setglobalvar("fades_bd_pose_index", pose);
}

void clear_combat_target_handoff()
{
    setglobalvar("fades_bd_event_payload", 0);
}

void consume_confirmed_contact(int tick)
{
    int route;
    int step;
    int freeze_ticks;

    if(getglobalvar("fades_bd_confirmed_contact") != 1)
    {
        return;
    }
    route = getglobalvar("fades_bd_confirmed_contact_route");
    step = getglobalvar("fades_bd_confirmed_contact_step");
    freeze_ticks = 4;
    if(route == 3) freeze_ticks = 7;
    if(step == 7) freeze_ticks = freeze_ticks + 2;
    setglobalvar("fades_bd_hitstop", freeze_ticks);
    setglobalvar("fades_bd_confirmed_contact", 0);
    emit_event(1111, route, step, tick);
}

void apply_authoritative_pose(void player)
{
    int pose;
    int route;
    int step;
    pose = getglobalvar("fades_bd_pose_index");
    if(pose < 0) pose = 0;
    if(pose > 4) pose = 4;
    route = getglobalvar("fades_bd_route");
    step = getglobalvar("fades_bd_step");
    if(getglobalvar("fades_bd_state") == 21 && route >= 1 && route <= 3 && step >= 1 && step <= 7)
    {
        pose = ((route - 1) * 5) + pose;
    }
    else if(getglobalvar("fades_bd_state") == 2) pose = 15 + pose;
    else if(getglobalvar("fades_bd_state") == 3) pose = 15 + pose;
    else if(getglobalvar("fades_bd_state") == 5) pose = 15 + pose;
    else if(getglobalvar("fades_bd_state") == 6) pose = 15 + pose;
    else if(getglobalvar("fades_bd_state") >= 7 && getglobalvar("fades_bd_state") <= 9) pose = 15 + pose;
    else if(getglobalvar("fades_bd_state") >= 10 && getglobalvar("fades_bd_state") <= 12) pose = 20 + pose;
    else if(getglobalvar("fades_bd_state") >= 16 && getglobalvar("fades_bd_state") <= 20)
    {
        pose = (20 + ((getglobalvar("fades_bd_state") - 16) / 7) * 5) + pose;
        if(getglobalvar("fades_bd_state") == 20) pose = 25 + getglobalvar("fades_bd_pose_index");
    }
    updateframe(player, pose);
}

void start_attack_sequence(void player, int route, int step, int from_air, int tick)
{
    int startup;
    int active;
    int recovery;
    int cancel;

    setglobalvar("fades_bd_state", 21);
    setglobalvar("fades_bd_route", route);
    setglobalvar("fades_bd_step", step);
    setglobalvar("fades_bd_state_tick", 0);
    setglobalvar("fades_bd_pose_tick", 0);
    setglobalvar("fades_bd_pose_index", 0);
    setglobalvar("fades_bd_state_phase", 0);
    setglobalvar("fades_bd_air_attack_used", from_air);

    startup = route_startup(route, step);
    active = route_active(route, step);
    recovery = route_recovery(route, step);
    cancel = route_cancel(route, step);

    setglobalvar("fades_bd_startup_ticks", startup);
    setglobalvar("fades_bd_active_ticks", active);
    setglobalvar("fades_bd_recovery_ticks", recovery);
    setglobalvar("fades_bd_cancel_ticks", cancel);

    apply_animation_for_state(player, 21, route, step);
    emit_event(1100, route, step, tick);
}

void progress_attack_sequence(void player, int tick)
{
    int route;
    int step;
    int state_t;
    int startup;
    int active;
    int recovery;
    int total;
    int cancel_allowed;
    int buffer_route;
    int clip;

    route = getglobalvar("fades_bd_route");
    step = getglobalvar("fades_bd_step");
    state_t = getglobalvar("fades_bd_state_tick");
    startup = getglobalvar("fades_bd_startup_ticks");
    active = getglobalvar("fades_bd_active_ticks");
    recovery = getglobalvar("fades_bd_recovery_ticks");
    cancel_allowed = getglobalvar("fades_bd_cancel_ticks");
    buffer_route = getglobalvar("fades_bd_buffer_route");
    total = startup + active + recovery;
    emit_route_events(route, step, state_t, startup, active, cancel_allowed, tick);

    if(state_t == 1)
    {
        emit_event(1101, route, step, tick);
        setglobalvar("fades_bd_state_phase", 0);
    }
    if(state_t == startup + 1)
    {
        emit_event(1102, route, step, tick);
        setglobalvar("fades_bd_state_phase", 1);
        clip = clamp_route_anim(route, step);
        performattack(player, clip, 1);
        setglobalvar("fades_bd_event_payload", 1);
    }
    if(state_t == startup + active + 1)
    {
        emit_event(1103, route, step, tick);
        setglobalvar("fades_bd_state_phase", 2);
    }

    // A buffered legal route transition executes as soon as its cancel gate
    // opens. Waiting for total recovery made the declared cancel timing inert.
    if(step < 7 && cancel_allowed > 0 && state_t >= cancel_allowed
        && buffer_route != 0 && route_allows_cancel(route, step, buffer_route))
    {
        start_attack_sequence(player, buffer_route, step + 1, getglobalvar("fades_bd_air_attack_used"), tick);
        clear_buffer();
        emit_event(1104, buffer_route, step + 1, tick);
        return;
    }

    if(state_t >= total)
    {
        clear_buffer();
        if(getglobalvar("fades_bd_air_attack_used") == 1)
        {
            set_state(8, tick);
            apply_animation_for_state(player, 8, 0, 0);
        }
        else
        {
            set_state(1, tick);
            apply_animation_for_state(player, 1, 0, 0);
        }
    }
}

void progress_walk_loop(void player, int travel_axis, int walked, int tick)
{
    int state;
    int state_t;
    state = getglobalvar("fades_bd_state");
    state_t = getglobalvar("fades_bd_state_tick");

    if(travel_axis == 0)
    {
        set_state(6, tick);
        apply_animation_for_state(player, 6, 0, 0);
        emit_event(1201, 0, 0, tick);
        return;
    }

    if(state == 3 && state_t >= 1)
    {
        if(walked == 1)
        {
            set_state(4, tick);
            emit_event(1202, travel_axis, 0, tick);
            apply_animation_for_state(player, 4, 0, 0);
        }
        else
        {
            set_state(6, tick);
            emit_event(1201, 0, 0, tick);
            apply_animation_for_state(player, 6, 0, 0);
        }
        return;
    }
    if(state == 4)
    {
        if(walked == 0)
        {
            set_state(6, tick);
            emit_event(1201, travel_axis, 0, tick);
            apply_animation_for_state(player, 6, 0, 0);
            return;
        }
        if(getglobalvar("fades_bd_last_face") != travel_axis)
        {
            set_state(5, tick);
            emit_event(1203, travel_axis, getglobalvar("fades_bd_last_face"), tick);
            apply_animation_for_state(player, 5, 0, 0);
            return;
        }
    }
    if(state == 5 && state_t >= 6)
    {
        if(walked == 1)
        {
            set_state(4, tick);
            apply_animation_for_state(player, 4, 0, 0);
        }
        else
        {
            set_state(6, tick);
            emit_event(1201, travel_axis, 0, tick);
            apply_animation_for_state(player, 6, 0, 0);
        }
        return;
    }
    if(state == 6)
    {
        if(walked == 1)
        {
            set_state(3, tick);
            emit_event(1202, travel_axis, 0, tick);
            apply_animation_for_state(player, 3, 0, 0);
            return;
        }
    }

}

void progress_jump_loop(void player, int tick, int air_attack, int travel_axis, int route_buffer, int route_buffered_from_jump)
{
    int state;
    int state_t;
    int next_state;
    int air_route;
    state = getglobalvar("fades_bd_state");
    state_t = getglobalvar("fades_bd_state_tick");

    next_state = state;
    if(state == 7 && state_t > 4)
    {
        next_state = 8;
        emit_event(1301, 0, 0, tick);
    }
    else if(state == 8 && state_t > 8)
    {
        next_state = 9;
        emit_event(1302, 0, 0, tick);
    }
    else if(state == 9 && state_t > 4)
    {
        next_state = 10;
        emit_event(1303, 0, 0, tick);
    }
    else if(state == 10 && state_t > 8)
    {
        next_state = 11;
        emit_event(1304, 0, 0, tick);
    }
    else if(state == 11 && state_t > 6)
    {
        next_state = 1;
        emit_event(1305, 0, 0, tick);
    }

    if(next_state != state)
    {
        set_state(next_state, tick);
        apply_animation_for_state(player, next_state, 0, 0);
        return;
    }

    if(air_attack != 0 && getglobalvar("fades_bd_air_attack_used") == 0)
    {
        if(route_buffer == 1 || route_buffer == 2)
        {
            air_route = route_buffer;
        }
        else
        {
            air_route = route_buffered_from_jump;
        }
        if(air_route == 0)
        {
            air_route = 1;
        }
        setglobalvar("fades_bd_air_attack_used", 1);
        if(air_route == 1 || travel_axis == 0)
        {
            start_attack_sequence(player, air_route, 1, 1, tick);
            emit_event(1306, air_route, 0, tick);
        }
        else
        {
            start_attack_sequence(player, 2, 1, 1, tick);
            emit_event(1306, 2, 0, tick);
        }
    }
}

void apply_guard_lock(void player, int tick, int guard_held)
{
    if(guard_held == 1)
    {
        set_state(2, tick);
        apply_animation_for_state(player, 2, 0, 0);
    }
    else if(getglobalvar("fades_bd_state") == 2)
    {
        set_state(1, tick);
        apply_animation_for_state(player, 1, 0, 0);
    }
}

void main()
{
    void player;
    int state;
    int state_t;
    int route_input;
    int route_buffer;
    int route_ttl;
    int route_buffer_ttl;
    int walked_this_tick;
    float x;
    float x_prev;
    float z;
    float z_prev;
    int travel_axis;
    int left_held;
    int right_held;
    int up_held;
    int down_held;
    int attack_edge;
    int jump_attack_input;
    int jump_edge;
    int defend_edge;
    int defend_pressed;
    int ranged_edge;
    int pet_edge;
    int special_edge;
    int health;
    int last_health;
    int tick;
    int event_route;

    if(openborvariant("in_level") != 1)
    {
        return;
    }

    if(openborvariant("game_speed") != 60)
    {
        emit_event(1401, 0, openborvariant("game_speed"), 0);
    }

    player = getplayerproperty(0, "entity");
    if(player == NULL())
    {
        return;
    }

    tick = getglobalvar("fades_bd_tick") + 1;
    setglobalvar("fades_bd_tick", tick);

    x = getentityproperty(player, "x");
    z = getentityproperty(player, "z");
    x_prev = getglobalvar("fades_bd_root_x_prev");
    z_prev = getglobalvar("fades_bd_root_z_prev");
    setglobalvar("fades_bd_root_x_prev", x);
    setglobalvar("fades_bd_root_z_prev", z);
    walked_this_tick = 0;

    if(x_prev == 0)
    {
        x_prev = x;
        setglobalvar("fades_bd_root_x_prev", x_prev);
    }
    if((x > x_prev + 0.001) || (x < x_prev - 0.001))
    {
        walked_this_tick = 1;
    }

    state = getglobalvar("fades_bd_state");
    state_t = getglobalvar("fades_bd_state_tick") + 1;
    setglobalvar("fades_bd_state_tick", state_t);

    health = getentityproperty(player, "health");
    last_health = getglobalvar("fades_bd_last_health");
    if(last_health == 0)
    {
        setglobalvar("fades_bd_last_health", health);
        last_health = health;
    }

    left_held = playerkeys(0, 0, "moveleft") != 0;
    right_held = playerkeys(0, 0, "moveright") != 0;
    up_held = playerkeys(0, 0, "moveup") != 0;
    down_held = playerkeys(0, 0, "movedown") != 0;
    attack_edge = playerkeys(0, 1, "attack") != 0;
    jump_attack_input = attack_edge;
    jump_edge = playerkeys(0, 1, "jump") != 0;
    defend_edge = playerkeys(0, 0, "attack2") != 0;
    defend_pressed = playerkeys(0, 1, "attack2") != 0;
    ranged_edge = playerkeys(0, 1, "attack3") != 0;
    pet_edge = playerkeys(0, 1, "attack4") != 0;
    special_edge = playerkeys(0, 1, "special") != 0;

    if(left_held == 1)
    {
        travel_axis = -1;
    }
    else if(right_held == 1)
    {
        travel_axis = 1;
    }
    else
    {
        travel_axis = 0;
    }

    route_input = route_for_input(attack_edge, special_edge, jump_edge, down_held, up_held);
    if(ranged_edge == 1) route_input = 4;
    if(pet_edge == 1) route_input = 5;
    if(route_input != 0)
    {
        route_buffer_ttl = 12;
        if(state == 21)
        {
            route_buffer_ttl = route_buffer_window(getglobalvar("fades_bd_route"), getglobalvar("fades_bd_step"));
            if(route_buffer_ttl <= 0)
            {
                route_buffer_ttl = 12;
            }
        }
        schedule_buffer(route_input, tick, route_buffer_ttl);
    }

    route_buffer = getglobalvar("fades_bd_buffer_route");
    route_ttl = getglobalvar("fades_bd_buffer_ttl");
    if(route_ttl > 0)
    {
        route_ttl = route_ttl - 1;
        if(route_ttl <= 0)
        {
            clear_buffer();
        }
        else
        {
            setglobalvar("fades_bd_buffer_ttl", route_ttl);
        }
    }

    if((x > x_prev + 0.001) || (x < x_prev - 0.001))
    {
        if(x > x_prev)
        {
            setglobalvar("fades_bd_face", 1);
        }
        if(x < x_prev)
        {
            setglobalvar("fades_bd_face", 2);
        }
    }

    if(health < last_health)
    {
        set_state(13, tick);
        apply_animation_for_state(player, 13, 0, 0);
        setglobalvar("fades_bd_last_health", health);
        emit_event(1501, last_health - health, 0, tick);
        clear_buffer();
        setglobalvar("fades_bd_lockout", 1);
        setglobalvar("fades_bd_hitstop", 4);
    }

    consume_confirmed_contact(tick);

    if(getglobalvar("fades_bd_hitstop") > 0)
    {
        setglobalvar("fades_bd_hitstop", getglobalvar("fades_bd_hitstop") - 1);
        setglobalvar("fades_bd_state_tick", state_t - 1);
        emit_event(1601, getglobalvar("fades_bd_hitstop"), 0, tick);
        apply_authoritative_pose(player);
        return;
    }

    if(state == 21)
    {
        progress_attack_sequence(player, tick);
    }
    else if(state == 3 || state == 4 || state == 5 || state == 6)
    {
        progress_walk_loop(player, travel_axis, walked_this_tick, tick);
        if(route_buffer != 0 && state == 4 && state_t == 1)
        {
            start_attack_sequence(player, route_buffer, 1, 0, tick);
            clear_buffer();
        }
    }
        else if(state == 7 || state == 8 || state == 9 || state == 10 || state == 11)
    {
        if(route_buffer == 1 || route_buffer == 2)
        {
            jump_attack_input = 1;
        }
        progress_jump_loop(player, tick, jump_attack_input, travel_axis, route_buffer, route_for_input(attack_edge, special_edge, jump_edge, down_held, up_held));
        if(route_buffer != 0)
        {
            clear_buffer();
        }
    }
    else if(state == 2)
    {
        apply_guard_lock(player, tick, defend_edge);
        if(route_buffer != 0)
        {
            set_state(2, tick);
        }
    }
    else if(state == 1)
    {
        if(defend_pressed == 1 && travel_axis != 0)
        {
            set_state(12, tick);
            apply_animation_for_state(player, 12, 0, 0);
            emit_event(1703, travel_axis, 0, tick);
        }
        else if(route_buffer == 5)
        {
            set_state(18, tick);
            apply_animation_for_state(player, 18, 0, 0);
            emit_event(1704, 0, 0, tick);
        }
        else if(defend_edge == 1)
        {
            apply_guard_lock(player, tick, 1);
        }
        if(jump_edge == 1)
        {
            set_state(7, tick);
            apply_animation_for_state(player, 7, 0, 0);
            setglobalvar("fades_bd_jump_from_ground_z", z);
            emit_event(1701, 0, 0, tick);
        }
        if(route_buffer != 0)
        {
            if(route_buffer == 4)
            {
                set_state(16, tick);
                apply_animation_for_state(player, 16, 0, 0);
                emit_event(1705, 0, 0, tick);
                clear_buffer();
            }
            else if(route_buffer == 5)
            {
                set_state(18, tick);
                apply_animation_for_state(player, 18, 0, 0);
                emit_event(1704, 0, 0, tick);
                clear_buffer();
            }
            else if(route_buffer == 3)
            {
                set_state(17, tick);
                apply_animation_for_state(player, 17, 0, 0);
                emit_event(1702, 3, 0, tick);
                clear_buffer();
            }
            else if(route_buffer == 1 || route_buffer == 2)
            {
                start_attack_sequence(player, route_buffer, 1, 0, tick);
                clear_buffer();
            }
        }
        if(travel_axis != 0 && getglobalvar("fades_bd_state") == 1)
        {
            if(getglobalvar("fades_bd_face") == 0)
            {
                setglobalvar("fades_bd_face", travel_axis);
            }
            set_state(3, tick);
            apply_animation_for_state(player, 3, 0, 0);
            setglobalvar("fades_bd_last_face", getglobalvar("fades_bd_face"));
        }
    }
    else if(state == 13)
    {
        if(state_t >= state_duration(13))
        {
            set_state(1, tick);
            apply_animation_for_state(player, 1, 0, 0);
            setglobalvar("fades_bd_lockout", 0);
        }
    }
    else if(state == 12 || state == 16 || state == 17 || state == 18 || state == 19 || state == 20)
    {
        if(state_t >= state_duration(state))
        {
            set_state(1, tick);
            apply_animation_for_state(player, 1, 0, 0);
        }
    }
    else if(state == 14)
    {
        if(state_t >= state_duration(14))
        {
            set_state(15, tick);
            apply_animation_for_state(player, 15, 0, 0);
        }
    }
    else if(state == 15)
    {
        if(state_t >= state_duration(15))
        {
            set_state(1, tick);
            apply_animation_for_state(player, 1, 0, 0);
        }
    }
    else
    {
        set_state(1, tick);
        apply_animation_for_state(player, 1, 0, 0);
    }

    event_route = getglobalvar("fades_bd_event_ready");
    if(event_route != 0)
    {
        setglobalvar("fades_bd_event_payload", event_route);
        setglobalvar("fades_bd_event_ready", 0);
    }

    if(getglobalvar("fades_bd_state") == 1
        && getglobalvar("fades_bd_buffer_route") == 0
        && travel_axis != 0)
    {
        setglobalvar("fades_bd_last_face", getglobalvar("fades_bd_face"));
    }

    advance_pose_timing();
    apply_authoritative_pose(player);
    snapshot_pose_and_state(getglobalvar("fades_bd_state"), getglobalvar("fades_bd_route"), getglobalvar("fades_bd_step"), tick, player, getglobalvar("fades_bd_state_phase"));
    setglobalvar("fades_bd_last_health", health);
    setglobalvar("fades_bd_last_face", getglobalvar("fades_bd_face"));
}
