// Mimics the real Orchard vuln: halo2_gadgets/src/ecc/chip/mul/incomplete.rs
pub fn add_incomplete(&self, region: &mut Region, offset: usize) -> Result<(), Error> {
    // VULNERABLE: base witness assigned without a constraint binding it to the real base.
    region.assign_advice(|| "x_p", self.double_and_add.x_p, row + offset, || x_p)?;
    region.assign_advice(|| "y_p", self.y_p, row + offset, || y_p)?;
    Ok(())
}
