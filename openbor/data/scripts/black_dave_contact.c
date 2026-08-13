/* Build 7949 didhitscript runs after a resolved hit or block.
 * This callback latches one confirmed unblocked hit per authored attack entry. */
void main()
{
    void self;
    void target;
    void name;
    int blocked;
    int seq;
    int route;
    int step;

    self = getlocalvar("self");
    target = getlocalvar("damagetaker");
    blocked = getlocalvar("blocked");
    if(self == NULL() || target == NULL()) return;
    name = getentityproperty(self, "name");
    if(name != "BlackDave" && name != "BlackDaveFlameShot")
    {
        return;
    }
    seq = getglobalvar("fof2_contact_seq");
    if(typeof(seq) != openborconstant("VT_INTEGER")) seq = 0;
    route = getglobalvar("bd_route");
    step = getglobalvar("bd_step");
    if(name == "BlackDaveFlameShot") { route = 3; step = 8; }
    setglobalvar("fof2_contact_seq", seq + 1);
    setglobalvar("fof2_contact_attacker", self);
    setglobalvar("fof2_contact_victim", target);
    setglobalvar("fof2_contact_attacker_name", name);
    setglobalvar("fof2_contact_victim_name", getentityproperty(target, "name"));
    setglobalvar("fof2_contact_blocked", blocked);
    setglobalvar("fof2_contact_damage", getlocalvar("damage"));
    setglobalvar("fof2_contact_drop", getlocalvar("drop"));
    setglobalvar("fof2_contact_attacktype", getlocalvar("attacktype"));
    setglobalvar("fof2_contact_route", route);
    setglobalvar("fof2_contact_step", step);
    setglobalvar("fof2_contact_victim_health_at_callback", getentityproperty(target, "health"));
    setglobalvar("fof2_contact_tick", openborvariant("elapsed_time"));
    log("[FOF2_COMBAT_CONTACT] attacker=dave resolved\n");
    if(blocked != 0) return;
    if(name == "BlackDaveFlameShot")
    {
        setglobalvar("bd_confirmed_contact", 1);
        setglobalvar("bd_confirmed_route", 3);
        setglobalvar("bd_confirmed_step", 8);
        setglobalvar("bd_confirmed_x", getentityproperty(self, "x"));
        setglobalvar("bd_confirmed_z", getentityproperty(self, "z"));
        setglobalvar("bd_confirmed_y", getentityproperty(self, "y"));
        return;
    }
    if(getglobalvar("bd_attack_live") != 1 || getglobalvar("bd_contact_latched") == 1)
    {
        return;
    }
    setglobalvar("bd_contact_latched", 1);
    setglobalvar("bd_confirmed_contact", 1);
    setglobalvar("bd_confirmed_route", getglobalvar("bd_route"));
    setglobalvar("bd_confirmed_step", getglobalvar("bd_step"));
    setglobalvar("bd_confirmed_x", getentityproperty(self, "x"));
    setglobalvar("bd_confirmed_z", getentityproperty(self, "z"));
    setglobalvar("bd_confirmed_y", getentityproperty(self, "y"));
}
