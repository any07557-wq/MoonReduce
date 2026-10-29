///|
priv enum Step {
  Initial
  Empty
  Subsets
  Complements
  Singles
}

///|
/// A serial request/feedback ddmin session over original element positions.
/// Requests and snapshots are immutable; at most one request is outstanding.
pub struct Reducer {
  priv original : ReadOnlyArray[Int32]
  priv mut best : ReadOnlyArray[Int32]?
  priv mut initial : Verdict?
  priv mut pending : CandidateRequest?
  priv mut next_id : Int64
  priv mut step : Step
  priv mut partitions : Int32
  priv mut chunk : Int32
  priv mut checked : Int32
  priv mut round_unresolved : Bool
  priv mut minimality : Minimality
  priv mut terminal : StopReason?
  priv mut feedback_count : Int64
  priv mut unresolved_count : Int64
}

///|
/// Construct an unverified session. Even length zero needs initial feedback.
pub fn Reducer::new(length : Int32) -> Reducer raise CoreError {
  guard length >= 0 else { raise InvalidLength(length) }
  let original = ReadOnlyArray::makei(length, i => i)
  {
    original,
    best: None,
    initial: None,
    pending: Some({ id: 0, phase: Initial, positions: original, }),
    next_id: 1,
    step: Initial,
    partitions: 2,
    chunk: 0,
    checked: 0,
    round_unresolved: false,
    minimality: NotChecked,
    terminal: None,
    feedback_count: 0,
    unresolved_count: 0,
  }
}

///|
/// Return the outstanding request or None after stopping. Repeated reads return
/// the same request; they neither execute nor cache an oracle call.
pub fn Reducer::next(self : Reducer) -> CandidateRequest? {
  self.pending
}

///|
/// True means a known Interesting best was first established or improved.
/// Wrong, duplicate and late IDs raise without mutation.
pub fn Reducer::submit(
  self : Reducer,
  id : Int64,
  verdict : Verdict,
) -> Bool raise CoreError {
  let request = match self.pending {
    Some(request) if request.id == id => request
    _ =>
      raise UnexpectedFeedback(
        expected=self.pending.map(request => request.id),
        received=id,
      )
  }
  self.pending = None
  self.feedback_count += 1
  if verdict is Unresolved {
    self.unresolved_count += 1
  }
  let improved = verdict is Interesting
  match self.step {
    Initial => {
      self.initial = Some(verdict)
      match verdict {
        Interesting => {
          self.best = Some(request.positions)
          if request.positions.length() <= 1 {
            self.begin_singles()
          } else {
            self.step = Empty
          }
        }
        NotInteresting => self.terminal = Some(InitialNotInteresting)
        Unresolved => self.terminal = Some(InitialUnresolved)
      }
    }
    Empty =>
      if improved {
        self.best = Some(request.positions)
        self.begin_singles()
      } else {
        self.step = Subsets
      }
    Subsets | Complements =>
      if improved {
        self.best = Some(request.positions)
        self.partitions = if self.step is Complements {
          Int32::max(2, self.partitions - 1)
        } else {
          2
        }
        self.partitions = Int32::min(
          self.partitions,
          request.positions.length(),
        )
        self.chunk = 0
        if request.positions.length() < 2 {
          self.begin_singles()
        } else {
          self.step = Subsets
        }
      } else {
        self.chunk += 1
      }
    Singles =>
      if improved {
        self.best = Some(request.positions)
        // Old progress and Unresolved witnesses belong to the old best.
        self.begin_singles()
      } else {
        self.checked += 1
        if verdict is Unresolved {
          self.round_unresolved = true
        }
      }
  }
  self.advance()
  improved
}

///|
/// Discard pending work, preserving the last known best. Finished sessions stay
/// unchanged, including when a budget ends exactly after a completed proof.
pub fn Reducer::stop(self : Reducer, cause : StopCause) -> Unit {
  if self.terminal is None {
    self.pending = None
    self.terminal = Some(Stopped(cause))
  }
}

///|
pub fn Reducer::snapshot(self : Reducer) -> Snapshot {
  {
    original_positions: self.original,
    best_positions: self.best,
    initial_verdict: self.initial,
    stop_reason: self.terminal,
    minimality: self.minimality,
    minimality_checked: self.checked,
    minimality_required: self.best
    .map(positions => positions.length())
    .unwrap_or(0),
    feedback_count: self.feedback_count,
    unresolved_count: self.unresolved_count,
  }
}

///|
fn Reducer::begin_singles(self : Reducer) -> Unit {
  self.step = Singles
  self.checked = 0
  self.round_unresolved = false
  self.minimality = Incomplete
}

///|
fn Reducer::issue(
  self : Reducer,
  phase : RequestPhase,
  positions : ReadOnlyArray[Int32],
) -> Unit {
  self.pending = Some({ id: self.next_id, phase, positions, })
  self.next_id += 1
}

///|
/// Bookkeeping runs eagerly after feedback without executing an oracle.
fn Reducer::advance(self : Reducer) -> Unit {
  if self.terminal is Some(_) {
    return
  }
  let best = self.best.unwrap()
  let length = best.length()
  while self.pending is None && self.terminal is None {
    match self.step {
      Initial => abort("initial request is created by Reducer::new")
      Empty => self.issue(Search, [])
      Subsets | Complements =>
        if self.chunk == self.partitions {
          if self.step is Subsets {
            self.step = Complements
            self.chunk = 0
          } else if self.partitions == length {
            self.begin_singles()
          } else {
            // Cap before multiplication to avoid overflowing large lengths.
            self.partitions = if self.partitions > length / 2 {
              length
            } else {
              self.partitions * 2
            }
            self.chunk = 0
            self.step = Subsets
          }
        } else {
          let size = length / self.partitions
          let remainder = length % self.partitions
          let start = self.chunk * size + Int32::min(self.chunk, remainder)
          let end = start + size + (if self.chunk < remainder { 1 } else { 0 })
          let positions = if self.step is Subsets {
            ReadOnlyArray::from_array(best[start:end])
          } else {
            without_range(best, start, end)
          }
          self.issue(Search, positions)
        }
      Singles =>
        if self.checked == length {
          if self.round_unresolved {
            self.minimality = BlockedByUnresolved
            self.terminal = Some(Unresolved)
          } else {
            self.minimality = Verified
            self.terminal = Some(Completed)
          }
        } else {
          self.issue(
            MinimalityCheck,
            without_range(best, self.checked, self.checked + 1),
          )
        }
    }
  }
}

///|
fn without_range(
  positions : ReadOnlyArray[Int32],
  start : Int32,
  end : Int32,
) -> ReadOnlyArray[Int32] {
  let kept = []
  for i, position in positions {
    if i < start || i >= end {
      kept.push(position)
    }
  }
  ReadOnlyArray::from_array(kept)
}
