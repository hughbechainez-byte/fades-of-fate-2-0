// Resolved combat-contact latch shared by both production enemies.
void main()
{
    void self;
    void target;
    int blocked;
    int seq;
    int choice;
    int route;
    self = getlocalvar("self");
    target = getlocalvar("damagetaker");
    blocked = getlocalvar("blocked");
    if(self == NULL() || target == NULL()) return;
    seq = getglobalvar("fof2_contact_seq");
    if(typeof(seq) != openborconstant("VT_INTEGER")) seq = 0;
    choice = getentityvar(self, "last_attack_choice");
    if(typeof(choice) != openborconstant("VT_INTEGER")) choice = 0;
    route = 4;
    if(getentityproperty(self, "name") == "PoliceOfficer") route = 5;
    setglobalvar("fof2_contact_seq", seq + 1);
    setglobalvar("fof2_contact_attacker", self);
    setglobalvar("fof2_contact_victim", target);
    setglobalvar("fof2_contact_attacker_name", getentityproperty(self, "name"));
    setglobalvar("fof2_contact_victim_name", getentityproperty(target, "name"));
    setglobalvar("fof2_contact_blocked", blocked);
    setglobalvar("fof2_contact_damage", getlocalvar("damage"));
    setglobalvar("fof2_contact_drop", getlocalvar("drop"));
    setglobalvar("fof2_contact_attacktype", getlocalvar("attacktype"));
    setglobalvar("fof2_contact_route", route);
    setglobalvar("fof2_contact_step", choice + 1);
    setglobalvar("fof2_contact_victim_health_at_callback", getentityproperty(target, "health"));
    setglobalvar("fof2_contact_tick", openborvariant("elapsed_time"));
    setentityvar(self, "confirmed_contact", 1);
    setentityvar(self, "contact_blocked", blocked);
    setentityvar(self, "contact_damage", getlocalvar("damage"));
    log("[FOF2_COMBAT_CONTACT] attacker=enemy resolved\n");
}
