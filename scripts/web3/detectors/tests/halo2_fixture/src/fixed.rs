// Fixed variant: copy_advice generates a constraint tying the value to the real base.
pub fn add_incomplete_fixed(&self, region: &mut Region, offset: usize) -> Result<(), Error> {
    base.x().copy_advice(|| "x_p", region, self.double_and_add.x_p, row + offset)?;
    base.y().copy_advice(|| "y_p", region, self.y_p, row + offset)?;
    Ok(())
}
