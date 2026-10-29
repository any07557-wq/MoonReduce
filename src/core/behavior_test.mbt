///|
test "initial rejection is explicit and has no known best" {
  for verdict in [@core.NotInteresting, @core.Unresolved] {
    let mut calls = 0
    let result = @core.reduce(["already passing"], _ => {
      calls += 1
      verdict
    })
    @test.assert_eq(calls, 1)
    audit(["already passing"], result, _ => verdict)
  }
}

///|
test "empty input still requires initial confirmation" {
  for verdict in [@core.Interesting, @core.NotInteresting, @core.Unresolved] {
    let input : Array[Int32] = []
    let mut calls = 0
    let result = @core.reduce(input, _ => {
      calls += 1
      verdict
    })
    @test.assert_eq(calls, 1)
    audit(input, result, _ => verdict)
  }
}

///|
test "single element really tests deletion to empty" {
  for
    empty_verdict in [@core.Interesting, @core.NotInteresting, @core.Unresolved] {
    fn oracle(values : ReadOnlyArray[Int32]) -> @core.Verdict {
      if values.is_empty() {
        empty_verdict
      } else {
        Interesting
      }
    }
    let seen = []
    let result = @core.reduce([7], values => {
      seen.push(values)
      oracle(values)
    })
    @test.assert_eq(seen, [[7], []])
    audit([7], result, oracle)
  }
}

///|
test "nonempty input explicitly tests deleting everything before chunk search" {
  let seen = []
  let result = @core.reduce([0, 1, 2, 3], values => {
    seen.push(values)
    if values.is_empty() || values.length() == 4 {
      Interesting
    } else {
      NotInteresting
    }
  })
  @test.assert_eq(seen, [[0, 1, 2, 3], []])
  @test.assert_eq(result.best, Some([]))
  audit([0, 1, 2, 3], result, values => {
    if values.is_empty() || values.length() == 4 {
      Interesting
    } else {
      NotInteresting
    }
  })
}

///|
test "duplicate values stay distinct and retain original order" {
  let original = ["noise", "same", "middle", "same", "tail"]
  fn oracle(values : ReadOnlyArray[String]) -> @core.Verdict {
    if values.filter(value => value == "same").length() == 2 &&
      values.contains("middle") {
      Interesting
    } else {
      NotInteresting
    }
  }
  let result = @core.reduce(original, oracle)
  @test.assert_eq(result.best, Some(["same", "middle", "same"]))
  @test.assert_eq(result.snapshot.best_positions, Some([1, 2, 3]))
  audit(original, result, oracle)
}

///|
test "several positions must occur together" {
  let original = [0, 1, 2, 3, 4, 5, 6]
  for required in [[1, 5], [0, 3, 6]] {
    fn oracle(values : ReadOnlyArray[Int32]) -> @core.Verdict {
      if required.all(value => values.contains(value)) {
        Interesting
      } else {
        NotInteresting
      }
    }
    let result = @core.reduce(original, oracle)
    @test.assert_eq(result.best, Some(ReadOnlyArray::from_array(required)))
    audit(original, result, oracle)
  }
}

///|
test "nonmonotonic target can have a smaller solution outside the retained best" {
  fn oracle(values : ReadOnlyArray[Int32]) -> @core.Verdict {
    if values.length() == 4 || mask_of(values) == 3 || mask_of(values) == 4 {
      Interesting
    } else {
      NotInteresting
    }
  }
  let result = @core.reduce([0, 1, 2, 3], oracle)
  @test.assert_eq(result.best, Some([0, 1]))
  @test.assert_eq(oracle([2]), Interesting)
  // A legitimate 1-minimal result need not be a global shortest solution.
  audit([0, 1, 2, 3], result, oracle)
}

///|
test "Unresolved candidates never become the best and block the final proof" {
  fn oracle(values : ReadOnlyArray[Int32]) -> @core.Verdict {
    if values.length() == 3 {
      Interesting
    } else if values.is_empty() {
      NotInteresting
    } else {
      Unresolved
    }
  }
  let result = @core.reduce([0, 1, 2], oracle)
  @test.assert_eq(result.best, Some([0, 1, 2]))
  @test.assert_eq(result.snapshot.minimality, BlockedByUnresolved)
  assert_true(result.snapshot.unresolved_count > 0)
  audit([0, 1, 2], result, oracle)
}

///|
test "historical Unresolved does not replace an independent complete proof" {
  fn oracle(values : ReadOnlyArray[Int32]) -> @core.Verdict {
    if values.is_empty() {
      Unresolved
    } else if values.contains(0) && values.contains(2) {
      Interesting
    } else {
      NotInteresting
    }
  }
  let result = @core.reduce([0, 1, 2], oracle)
  @test.assert_eq(result.best, Some([0, 2]))
  @test.assert_eq(result.snapshot.minimality, Verified)
  assert_true(result.snapshot.unresolved_count > 0)
  audit([0, 1, 2], result, oracle)
}

///|
test "synchronous wrapper snapshots the input and adds no hidden oracle calls" {
  let original = [0, 1, 2]
  let mut calls = 0L
  fn predicate(values : ReadOnlyArray[Int32]) -> @core.Verdict {
    if values.contains(1) {
      Interesting
    } else {
      NotInteresting
    }
  }
  let result = @core.reduce(original, values => {
    original[1] = 99
    calls += 1
    predicate(values)
  })
  @test.assert_eq(result.best, Some([1]))
  @test.assert_eq(result.snapshot.feedback_count, calls)
  audit([0, 1, 2], result, predicate)
}

///|
suberror OracleFailure {
  DeliberateFailure
}

///|
test "callback errors propagate rather than becoming Interesting or Unresolved" {
  let mut calls = 0
  try
    @core.reduce([1, 2], _ => {
      calls += 1
      if calls == 1 {
        Interesting
      } else {
        raise DeliberateFailure
      }
    })
  catch {
    DeliberateFailure => @test.assert_eq(calls, 2)
    error => raise error
  } noraise {
    _ => fail("callback error was swallowed")
  }
}
