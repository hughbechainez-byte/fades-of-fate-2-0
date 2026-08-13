/* Build 7949 didblockscript: latch a resolved scripted block for Dave's
 * authoritative blockpain presentation on the next fixed simulation step. */
void main()
{
    void self;
    int seq;
    self = getlocalvar("self");
    if(self == NULL()) return;
    if(getentityproperty(self, "name") != "BlackDave") return;
    seq = getglobalvar("fof2_dave_block_seq");
    if(typeof(seq) != openborconstant("VT_INTEGER")) seq = 0;
    setglobalvar("fof2_dave_block_seq", seq + 1);
    setglobalvar("bd_block_contact", 1);
}
