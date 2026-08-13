// Runs only after Build 7949 confirms a blocked hit.
void main()
{
    void self;
    int seq;
    self = getlocalvar("self");
    if(self == NULL()) return;
    seq = getglobalvar("fof2_po_block_seq");
    if(typeof(seq) != openborconstant("VT_INTEGER")) seq = 0;
    setglobalvar("fof2_po_block_seq", seq + 1);
    setentityvar(self, "blocked_hit", 1);
    setentityvar(self, "block_damage", getlocalvar("damage"));
    log("[FOF2_PO_BLOCK] confirmed\n");
}
