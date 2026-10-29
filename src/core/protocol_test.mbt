///|
fn trace(
  length : Int32,
  oracle : (ReadOnlyArray[Int32]) -> @core.Verdict,
) -> (Array[@core.CandidateRequest], @core.Snapshot) raise {
  let reducer = @core.Reducer::new(length)
  let requests : Array[@core.CandidateRequest] = []
  while reducer.next() is Some(request) {
    @test.assert_eq(reducer.next(), Some(request))
    assert_true(requests.length() < 1000)
    if requests.last() is Some(previous) {
      assert_true(request.id > previous.id)
    }
    let mut previous_position = -1
    for position in request.positions {
      assert_true(position > previous_position && position < length)
      previous_position = position
    }
    let old_best = reducer.snapshot().best_positions
    requests.push(request)
    let verdict = oracle(request.positions)
    @test.assert_eq(reducer.submit(request.id, verdict), verdict == Interesting)
    let best = reducer.snapshot().best_positions
    if verdict == Interesting {
      @test.assert_eq(best, Some(request.positions))
      if old_best is Some(old) {
        assert_true(request.positions.length() < old.length())
      }
    } else {
      @test.assert_eq(best, old_best)
    }
    if best is Some(best) {
      @test.assert_eq(oracle(best), Interesting)
    }
  }
  (requests, reducer.snapshot())
}

///|
test "identical deterministic input repeats request order and result" {
  fn oracle(values : ReadOnlyArray[Int32]) -> @core.Verdict {
    if values.contains(1) && values.contains(4) {
      Interesting
    } else if values.length() == 3 {
      Unresolved
    } else {
      NotInteresting
    }
  }
  let first = trace(5, oracle)
  @test.assert_eq(first, trace(5, oracle))
}

///|
test "uneven chunks and complements are visited from left to right" {
  let (requests, _) = trace(5, values => {
    if values.length() == 5 {
      Interesting
    } else {
      NotInteresting
    }
  })
  @test.assert_eq(requests[0].phase, Initial)
  @test.assert_eq(requests[0].positions, [0, 1, 2, 3, 4])
  @test.assert_eq(requests[1].positions, [])
  @test.assert_eq(requests[2].positions, [0, 1, 2])
  @test.assert_eq(requests[3].positions, [3, 4])
  @test.assert_eq(requests[4].positions, [3, 4])
  @test.assert_eq(requests[5].positions, [0, 1, 2])
  @test.assert_eq(requests[6].positions, [0, 1])
  @test.assert_eq(requests[7].positions, [2])
  @test.assert_eq(requests[8].positions, [3])
  @test.assert_eq(requests[9].positions, [4])
}

///|
test "stopping at any request boundary preserves only known Interesting best" {
  fn oracle(values : ReadOnlyArray[Int32]) -> @core.Verdict {
    if values.contains(1) && values.contains(4) {
      Interesting
    } else {
      NotInteresting
    }
  }
  let (requests, _) = trace(5, oracle)
  for cut in 0..<=requests.length() {
    let reducer = @core.Reducer::new(5)
    let mut expected_best = None
    for _ in 0..<cut {
      let request = reducer.next().unwrap()
      let verdict = oracle(request.positions)
      if verdict == Interesting {
        expected_best = Some(request.positions)
      }
      @test.assert_eq(
        reducer.submit(request.id, verdict),
        verdict == Interesting,
      )
    }
    let before = reducer.snapshot()
    reducer.stop(BudgetExhausted)
    let stopped = reducer.snapshot()
    @test.assert_eq(stopped.best_positions, expected_best)
    @test.assert_eq(stopped.feedback_count, cut.to_int64())
    @test.assert_eq(reducer.next(), None)
    if before.stop_reason is Some(_) {
      @test.assert_eq(stopped, before)
    } else {
      @test.assert_eq(stopped.stop_reason, Some(Stopped(BudgetExhausted)))
      assert_true(stopped.minimality != Verified)
    }
    if expected_best is Some(best) {
      @test.assert_eq(oracle(best), Interesting)
    }
  }
}

///|
test "invalid feedback cannot corrupt a pending request or accepted result" {
  try @core.Reducer::new(-1) catch {
    @core.InvalidLength(-1) => ()
    error => raise error
  } noraise {
    _ => fail("negative length was accepted")
  }
  let reducer = @core.Reducer::new(3)
  let request = reducer.next().unwrap()
  let before = reducer.snapshot()
  try reducer.submit(request.id + 1, Interesting) catch {
    @core.UnexpectedFeedback(expected=Some(id), received~) => {
      @test.assert_eq(id, request.id)
      @test.assert_eq(received, request.id + 1)
    }
    error => raise error
  } noraise {
    _ => fail("out-of-order feedback was accepted")
  }
  @test.assert_eq(reducer.snapshot(), before)
  @test.assert_eq(reducer.next(), Some(request))
  reducer.submit(request.id, Interesting) |> ignore
  let accepted = reducer.snapshot()
  try reducer.submit(request.id, NotInteresting) catch {
    @core.UnexpectedFeedback(_) => ()
    error => raise error
  } noraise {
    _ => fail("duplicate feedback was accepted")
  }
  @test.assert_eq(reducer.snapshot(), accepted)
  for
    cause in [
      @core.BudgetExhausted,
      @core.ExecutionError,
      @core.Interrupted,
      @core.UserStopped,
    ] {
    let session = @core.Reducer::new(1)
    let pending = session.next().unwrap()
    session.stop(cause)
    let stopped = session.snapshot()
    @test.assert_eq(stopped.stop_reason, Some(Stopped(cause)))
    @test.assert_eq(stopped.best_positions, None)
    try session.submit(pending.id, Interesting) catch {
      @core.UnexpectedFeedback(_) => ()
      error => raise error
    } noraise {
      _ => fail("feedback after stop was accepted")
    }
    @test.assert_eq(session.snapshot(), stopped)
  }
}

///|
test "Interesting during final checks restarts proof and clears old witnesses" {
  let reducer = @core.Reducer::new(3)
  let mut first_single = true
  let mut final_improvements = 0
  while reducer.next() is Some(request) {
    assert_true(reducer.snapshot().feedback_count < 100)
    let verdict : @core.Verdict = match request.phase {
      Initial => Interesting
      Search =>
        if request.positions.is_empty() {
          NotInteresting
        } else {
          Unresolved
        }
      MinimalityCheck =>
        if first_single {
          first_single = false
          Unresolved
        } else if request.positions.contains(2) {
          final_improvements += 1
          Interesting
        } else {
          NotInteresting
        }
    }
    reducer.submit(request.id, verdict) |> ignore
  }
  let state = reducer.snapshot()
  assert_true(final_improvements >= 2)
  @test.assert_eq(state.best_positions, Some([2]))
  @test.assert_eq(state.minimality_checked, 1)
  assert_true(state.unresolved_count > 0)
  // Scripted Unresolved simulates unavailable search evidence. Audit the final
  // certificate with the independent, deterministic underlying target.
  audit([0, 1, 2], { snapshot: state, best: Some([2]), }, values => {
    if values.contains(2) {
      Interesting
    } else {
      NotInteresting
    }
  })
}

///|
test "partial final checks remain incomplete on interruption" {
  let reducer = @core.Reducer::new(3)
  while reducer.next() is Some(request) {
    if request.phase == MinimalityCheck {
      reducer.submit(request.id, NotInteresting) |> ignore
      break
    }
    reducer.submit(
      request.id,
      if request.phase == Initial {
        Interesting
      } else {
        NotInteresting
      },
    )
    |> ignore
  }
  let saved = reducer.snapshot()
  @test.assert_eq(saved.minimality_checked, 1)
  reducer.stop(Interrupted)
  @test.assert_eq(reducer.snapshot().minimality, Incomplete)
  @test.assert_eq(reducer.snapshot().minimality_required, 3)
  @test.assert_eq(saved.best_positions, Some([0, 1, 2]))
  @test.assert_eq(reducer.next(), None)
}
