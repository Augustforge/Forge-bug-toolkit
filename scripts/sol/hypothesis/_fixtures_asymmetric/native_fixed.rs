use solana_program::program::invoke;
pub fn process_instruction(accounts: &[AccountInfo]) -> ProgramResult {
    let signer = next_account_info(iter)?;
    require!(signer.is_signer);
    let lamports_before = signer.lamports();
    invoke(&some_ix, accounts)?;
    let lamports_after = signer.lamports();
    require!(lamports_before <= lamports_after + MAX);
    require_keys_eq!(*signer.owner, system_program::ID);
    Ok(())
}
