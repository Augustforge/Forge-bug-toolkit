use solana_program::sysvar::instructions::load_instruction_at;
struct Ed25519SignatureOffsets { public_key_offset: u16 }
fn verify(d: &[u8], offs: Ed25519SignatureOffsets) -> bool {
    let o = offs.public_key_offset as usize;
    let signer_pubkey = &d[o..o+32];
    signer_pubkey == TRUSTED_KEY
}
