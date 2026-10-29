///|
/// Black-box postcondition checker: no reducer helpers, search state, or stored
/// minimality witnesses are used to reconstruct candidates or judge them.
fn[T : Eq + @debug.Debug] audit(
  original : ArrayView[T],
  result : @core.ReductionResult[T],
  oracle : (ReadOnlyArray[T]) -> @core.Verdict,
) -> Unit raise {
  let state = result.snapshot
  @test.assert_eq(
    state.original_positions,
    ReadOnlyArray::makei(original.length(), i => i),
  )
  let initial = oracle(ReadOnlyArray::from_array(original))
  @test.assert_eq(state.initial_verdict, Some(initial))
  if initial != Interesting {
    @test.assert_eq(result.best, None)
    @test.assert_eq(state.best_positions, None)
    @test.assert_eq(state.minimality, NotChecked)
    @test.assert_eq(state.feedback_count, 1)
    @test.assert_eq(
      state.stop_reason,
      Some(
        if initial == Unresolved {
          InitialUnresolved
        } else {
          InitialNotInteresting
        },
      ),
    )
    return
  }
  let best = result.best.unwrap()
  let positions = state.best_positions.unwrap()
  @test.assert_eq(best.length(), positions.length())
  let mut previous = -1
  for i, position in positions {
    assert_true(position > previous && position < original.length())
    @test.assert_eq(best[i], original[position])
    previous = position
  }
  @test.assert_eq(oracle(best), Interesting)
  // Rebuild every single deletion independently, without without_range().
  let mut all_not_interesting = true
  let mut any_interesting = false
  let mut any_unresolved = false
  for deleted in 0..<best.length() {
    let candidate = []
    for i, value in best {
      if i != deleted {
        candidate.push(value)
      }
    }
    match oracle(ReadOnlyArray::from_array(candidate)) {
      Interesting => {
        any_interesting = true
        all_not_interesting = false
      }
      NotInteresting => ()
      Unresolved => {
        any_unresolved = true
        all_not_interesting = false
      }
    }
  }
  match state.stop_reason {
    Some(Completed) => {
      assert_true(all_not_interesting)
      @test.assert_eq(state.minimality, Verified)
      @test.assert_eq(state.minimality_checked, best.length())
    }
    Some(Unresolved) => {
      assert_true(any_unresolved && !any_interesting)
      @test.assert_eq(state.minimality, BlockedByUnresolved)
      @test.assert_eq(state.minimality_checked, best.length())
    }
    Some(Stopped(_)) => assert_true(state.minimality != Verified)
    _ =>
      fail("Interesting input must retain a best and a valid terminal reason")
  }
  @test.assert_eq(state.minimality_required, best.length())
}

///|
fn mask_of(values : ReadOnlyArray[Int32]) -> Int32 {
  let mut mask = 0
  for value in values {
    mask = mask | (1 << value)
  }
  mask
}
