void main()
{
    int health;
    void player;

    log("[FOF2_DAVE] contract_start\n");
    setspawnentry("name", "BlackDave");
    setspawnentry("coords", 320, 280, 0);
    player = spawn();
    if(player == NULL())
    {
        log("[FOF2_DAVE] spawn_failed\n");
        shutdown();
        return;
    }

    health = getentityproperty(player, "health");
    changeentityproperty(player, "playerindex", 0);
    changeplayerproperty(0, "name", "BlackDave");
    changeplayerproperty(0, "ent", player);
    changeplayerproperty(0, "lives", 3);
    changeplayerproperty(0, "hasplayed", 1);
    changeplayerproperty(0, "spawnhealth", health);
    log("[FOF2_DAVE] spawn_bound\n");
}
