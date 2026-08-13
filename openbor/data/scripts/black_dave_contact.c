void main()
{
    void self;
    int which;
    int attack_id;
    int previous_id;

    self = getlocalvar("self");
    which = getlocalvar("which");
    if(self == NULL() || which != openborconstant("EXCHANGE_CONFERRER"))
    {
        return;
    }
    if(getentityproperty(self, "name") != "BlackDave")
    {
        return;
    }

    attack_id = getlocalvar("attackid");
    previous_id = getglobalvar("fades_bd_last_confirmed_attack_id");
    if(attack_id == previous_id)
    {
        return;
    }
    setglobalvar("fades_bd_last_confirmed_attack_id", attack_id);
    setglobalvar("fades_bd_confirmed_contact", 1);
    setglobalvar("fades_bd_confirmed_contact_route", getglobalvar("fades_bd_route"));
    setglobalvar("fades_bd_confirmed_contact_step", getglobalvar("fades_bd_step"));
}
