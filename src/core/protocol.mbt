///|
/// An oracle verdict is separate from process and filesystem errors.
pub(all) enum Verdict {
  Interesting
  NotInteresting
  Unresolved
}

///|
/// Positions identify elements even when two elements have equal contents.
pub(all) struct CandidateRequest {
  id : Int32
  positions : Array[Int32]
}
