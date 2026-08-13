/* Deterministic packaged showcase followed by real combat. */
void oncreate()
{
    setglobalvar("fof2_showcase_mode", 0);
    setglobalvar("fof2_showcase_phase", 0);
    setglobalvar("fof2_showcase_start", -1);
    setglobalvar("fof2_showcase_index", 4095);
    setglobalvar("fof2_qa_dave_enabled", 0);
    setglobalvar("fof2_qa_hm_pose", -1);
    setglobalvar("fof2_qa_po_pose", -1);
    setglobalvar("fof2_qa_hm_request", 0);
    setglobalvar("fof2_qa_po_request", 0);
    setglobalvar("fof2_enemy_attack_token", NULL());
    setglobalvar("fof2_native_join_pulse", 0);
    setglobalvar("fof2_native_join_logged", 0);
    setglobalvar("fof2_combat_evidence_mode", 0);
    setglobalvar("fof2_contact_seq", 0);
    setglobalvar("fof2_dave_block_seq", 0);
    setglobalvar("fof2_po_block_seq", 0);
    setglobalvar("fof2_test_hm_choice", -1);
    setglobalvar("fof2_test_po_choice", -1);
    log("[FOF2_ENTITY_QA] initialized playable combat demo\n");
}

void demo_clear_join_input()
{
    changeplayerproperty(0, "keys", 0);
    changeplayerproperty(0, "playkeys", 0);
    changeplayerproperty(0, "newkeys", 0);
    changeplayerproperty(0, "releasekeys", 0);
}

void demo_request_native_player()
{
    int pulse;
    int startkey;
    pulse = getglobalvar("fof2_native_join_pulse");
    if(pulse == 0)
    {
        startkey = openborconstant("FLAG_START");
        changeplayerproperty(0, "credits", 1);
        changeplayerproperty(0, "keys", startkey);
        changeplayerproperty(0, "playkeys", startkey);
        changeplayerproperty(0, "newkeys", startkey);
        changeplayerproperty(0, "releasekeys", 0);
        setglobalvar("fof2_native_join_pulse", 1);
        log("[FOF2_ENTITY_QA] native_player0_join_requested\n");
        return;
    }
    demo_clear_join_input();
    if(pulse == 1)
    {
        setglobalvar("fof2_native_join_pulse", 2);
        log("[FOF2_ENTITY_QA] native_player0_join_input_cleared\n");
    }
}

void demo_place(void actor, int x, int z)
{
    if(actor == NULL()) return;
    changeentityproperty(actor, "direction", 1);
    changeentityproperty(actor, "position", x, z, 0);
}

void demo_finish_showcase(void dave, void homeless, void police)
{
    setglobalvar("fof2_showcase_mode", 0);
    setglobalvar("fof2_showcase_index", -1);
    setglobalvar("fof2_qa_dave_enabled", 0);
    setglobalvar("fof2_qa_hm_pose", -1);
    setglobalvar("fof2_qa_po_pose", -1);
    setglobalvar("fof2_qa_hm_request", 0);
    setglobalvar("fof2_qa_po_request", 0);
    setglobalvar("fof2_enemy_attack_token", NULL());
    demo_place(dave, 200, 280);
    demo_place(homeless, 400, 280);
    demo_place(police, 540, 292);
    log("[FOF2_ENTITY_QA] showcase_complete combat_live\n");
}

void main()
{
    void dave;
    void homeless;
    void police;
    int now;
    int start;
    int phase;
    int request;
    dave = getplayerproperty(0, "entity");
    now = openborvariant("elapsed_time");
    if(dave == NULL())
    {
        demo_request_native_player();
        setglobalvar("fof2_showcase_start", now);
        return;
    }
    if(getglobalvar("fof2_native_join_logged") == 0)
    {
        demo_clear_join_input();
        setglobalvar("fof2_native_join_logged", 1);
        log("[FOF2_ENTITY_QA] black_dave_player0_native_spawned\n");
    }
    homeless = getglobalvar("fof2_qa_hm_entity");
    police = getglobalvar("fof2_qa_po_entity");
    if(getglobalvar("fof2_showcase_mode") != 1)
    {
        return;
    }
    phase = getglobalvar("fof2_showcase_phase");
    start = getglobalvar("fof2_showcase_start");
    if(start < 0)
    {
        start = now;
        setglobalvar("fof2_showcase_start", start);
    }
    if(playerkeys(0, 1, "attack4") != 0)
    {
        demo_finish_showcase(dave, homeless, police);
        return;
    }
    if(phase == 0)
    {
        demo_place(dave, -500, 300);
        demo_place(homeless, -500, 300);
        demo_place(police, -500, 300);
        setglobalvar("fof2_showcase_index", 4095);
        if(now - start >= 400)
        {
            setglobalvar("fof2_showcase_phase", 1);
            setglobalvar("fof2_qa_dave_enabled", 1);
            setglobalvar("fof2_showcase_start", now);
            log("[FOF2_ENTITY_QA] phase=black_dave\n");
        }
        return;
    }
    if(phase == 1)
    {
        demo_place(dave, 320, 300);
        demo_place(homeless, -500, 300);
        demo_place(police, -500, 300);
        request = getglobalvar("bd_qa_request");
        if(request >= 0 && request < 220) setglobalvar("fof2_showcase_index", request);
        if(getglobalvar("bd_qa_tick") >= 2640)
        {
            setglobalvar("fof2_qa_dave_enabled", 0);
            setglobalvar("fof2_showcase_phase", 2);
            setglobalvar("fof2_showcase_start", now);
            setglobalvar("fof2_qa_hm_pose", 0);
            setglobalvar("fof2_showcase_index", 220);
            log("[FOF2_ENTITY_QA] phase=homeless_man\n");
        }
        return;
    }
    if(phase == 2)
    {
        demo_place(dave, -500, 300);
        demo_place(homeless, 320, 300);
        demo_place(police, -500, 300);
        request = (now - start) / 40;
        if(request < 120)
        {
            setglobalvar("fof2_qa_hm_pose", request);
            setglobalvar("fof2_showcase_index", 220 + request);
        }
        else
        {
            setglobalvar("fof2_qa_hm_pose", -1);
            setglobalvar("fof2_qa_po_pose", 0);
            setglobalvar("fof2_showcase_phase", 3);
            setglobalvar("fof2_showcase_start", now);
            setglobalvar("fof2_showcase_index", 340);
            log("[FOF2_ENTITY_QA] phase=police_officer\n");
        }
        return;
    }
    if(phase == 3)
    {
        demo_place(dave, -500, 300);
        demo_place(homeless, -500, 300);
        demo_place(police, 320, 300);
        request = (now - start) / 40;
        if(request < 120)
        {
            setglobalvar("fof2_qa_po_pose", request);
            setglobalvar("fof2_showcase_index", 340 + request);
        }
        else demo_finish_showcase(dave, homeless, police);
    }
}
