use anchor_lang::prelude::*;
pub fn deposit(ctx: Context<Deposit>) -> Result<()> {
    token::transfer(ctx.accounts.cpi_ctx(), 100)?;
    ctx.accounts.vault.reload()?;
    let bal = ctx.accounts.vault.amount;
    credit(bal);
    Ok(())
}
