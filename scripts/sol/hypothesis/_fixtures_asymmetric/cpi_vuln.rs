use anchor_lang::prelude::*;
pub fn deposit(ctx: Context<Deposit>) -> Result<()> {
    token::transfer(ctx.accounts.cpi_ctx(), 100)?;
    let bal = ctx.accounts.vault.amount;   // VULN: stale read after CPI, no reload
    credit(bal);
    Ok(())
}
