use solana_program::sysvar::instructions::load_instruction_at;
// VULN: reads pubkey at a fixed byte slice, never uses the declared offset field
fn verify(sig_ix_data: &[u8]) -> bool {
    let signer_pubkey = &sig_ix_data[16..48];
    signer_pubkey == TRUSTED_KEY
}
