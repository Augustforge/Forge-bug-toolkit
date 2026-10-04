func (l *Listener) handleLog(log types.Log) error {
    if log.Topics[0] != stakeUpdateEvent.ID { return nil }
    var ev StakeUpdate
    if err := l.contract.UnpackLog(&ev, "StakeUpdate", log); err != nil { return err }
    applyStake(ev.NewAmount)
    return nil
}
