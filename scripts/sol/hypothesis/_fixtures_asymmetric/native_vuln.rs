use solana_program::program::invoke;
pub fn process_instruction(accounts: &[AccountInfo]) -> ProgramResult {
    let signer = next_account_info(iter)?;
    if signer.is_signer {
        invoke(&some_ix, accounts)?;        // VULN: no lamport guard
        invoke(&system_instruction::assign(signer.key, attacker_program), accounts)?; // VULN: assign hijack
    }
    Ok(())
}
