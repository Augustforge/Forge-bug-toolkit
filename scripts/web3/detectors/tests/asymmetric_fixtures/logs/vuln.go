func (l *Listener) handleLog(log types.Log) error {
    var ev StakeUpdate
    // VULN: decode a raw log without checking the event signature hash first
    if err := l.contract.UnpackLog(&ev, "StakeUpdate", log); err != nil { return err }
    applyStake(ev.NewAmount)
    return nil
}
