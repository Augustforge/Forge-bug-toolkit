func (k Keeper) EndBlock(ctx sdk.Context) {
    k.stateDB.Commit(true)  // legitimate end-of-block commit
}
