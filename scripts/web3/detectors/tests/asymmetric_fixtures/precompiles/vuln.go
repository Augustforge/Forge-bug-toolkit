func (p *DistributionPrecompile) Run(evm *vm.EVM, contract *vm.Contract) ([]byte, error) {
    res := p.doStuff()
    // VULN: commit mid-precompile clears journal.dirties
    if err := evm.StateDB.Commit(false); err != nil { return nil, err }
    return res, nil
}
