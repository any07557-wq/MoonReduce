///|
/// An oracle verdict is separate from process and filesystem errors.
pub(all) enum Verdict {
  Interesting
  NotInteresting
  Unresolved
} derive(Eq, @debug.Debug)

///|
pub extend Verdict with Eq::{equal, not_equal}

///|
pub extend Verdict with @debug.Debug::{to_repr}

///|
/// Final output-path revalidation belongs to the driver, not this core.
pub(all) enum RequestPhase {
  Initial
  Search
  MinimalityCheck
} derive(Eq, @debug.Debug)

///|
pub extend RequestPhase with Eq::{equal, not_equal}

///|
pub extend RequestPhase with @debug.Debug::{to_repr}

///|
/// Positions identify elements even when two elements have equal contents.
pub(all) struct CandidateRequest {
  id : Int64
  phase : RequestPhase
  positions : ReadOnlyArray[Int32]
} derive(Eq, @debug.Debug)

///|
pub extend CandidateRequest with Eq::{equal, not_equal}

///|
pub extend CandidateRequest with @debug.Debug::{to_repr}

///|
pub(all) enum Minimality {
  NotChecked
  Incomplete
  BlockedByUnresolved
  Verified
} derive(Eq, @debug.Debug)

///|
pub extend Minimality with Eq::{equal, not_equal}

///|
pub extend Minimality with @debug.Debug::{to_repr}

///|
/// The driver owns actual-call budgets, execution errors and cancellation.
pub(all) enum StopCause {
  BudgetExhausted
  ExecutionError
  Interrupted
  UserStopped
} derive(Eq, @debug.Debug)

///|
pub extend StopCause with Eq::{equal, not_equal}

///|
pub extend StopCause with @debug.Debug::{to_repr}

///|
/// Completed means a core proof, not final output revalidation.
pub(all) enum StopReason {
  Completed
  Unresolved
  InitialNotInteresting
  InitialUnresolved
  Stopped(StopCause)
} derive(Eq, @debug.Debug)

///|
pub extend StopReason with Eq::{equal, not_equal}

///|
pub extend StopReason with @debug.Debug::{to_repr}

///|
/// Immutable structural snapshot. No best exists until initial Interesting.
/// Feedback counts accepted responses, not processes actually started.
pub(all) struct Snapshot {
  original_positions : ReadOnlyArray[Int32]
  best_positions : ReadOnlyArray[Int32]?
  initial_verdict : Verdict?
  stop_reason : StopReason?
  minimality : Minimality
  minimality_checked : Int32
  minimality_required : Int32
  feedback_count : Int64
  unresolved_count : Int64
} derive(Eq, @debug.Debug)

///|
pub extend Snapshot with Eq::{equal, not_equal}

///|
pub extend Snapshot with @debug.Debug::{to_repr}

///|
pub(all) suberror CoreError {
  InvalidLength(Int32)
  UnexpectedFeedback(expected~ : Int64?, received~ : Int64)
} derive(@debug.Debug)

///|
pub extend CoreError with @debug.Debug::{to_repr}

///|
/// The synchronous wrapper returns values and their original positions.
pub(all) struct ReductionResult[T] {
  snapshot : Snapshot
  best : ReadOnlyArray[T]?
}
