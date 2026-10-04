// Benign: a plain config flag assigned, unrelated to curve arithmetic.
pub fn load_flag(&self, region: &mut Region) -> Result<(), Error> {
    region.assign_advice(|| "enabled_flag", self.cfg, 0, || flag)?;
    Ok(())
}
