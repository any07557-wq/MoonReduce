///|
fn main {
  let command = @argparse.Command(
    "moonreduce",
    version="0.1.0-stage0",
    about="Stage 0 bootstrap. Reduction is not implemented yet; see docs/SPEC.md.",
  )
  println(command.render_help())
}
