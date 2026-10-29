///|
/// Caller-owned domain types: no serialization, files, processes or Shrink impl.
enum Operation {
  Credit(Int32)
  Debit(Int32)
  Reset
} derive(Eq)

///|
struct Entry {
  id : Int32
  operation : Operation
} derive(Eq)

///|
enum Signature {
  Same
  ResetKeptBalance
  InvalidTransaction
}

///|
fn replay(entries : ReadOnlyArray[Entry], injected_bug~ : Bool) -> Int32? {
  let mut balance = 0
  for entry in entries {
    match entry.operation {
      Credit(amount) => {
        guard amount >= 0 && amount <= 1000 else { return None }
        balance += amount
      }
      Debit(amount) => {
        guard amount >= 0 && amount <= balance else { return None }
        balance -= amount
      }
      Reset => if !injected_bug { balance = 0 }
    }
  }
  Some(balance)
}

///|
fn classify(entries : ReadOnlyArray[Entry]) -> Signature {
  match
    (replay(entries, injected_bug=false), replay(entries, injected_bug=true)) {
    (Some(expected), Some(actual)) =>
      if actual > expected {
        ResetKeptBalance
      } else {
        Same
      }
    _ => InvalidTransaction
  }
}

///|
fn verdict(entries : ReadOnlyArray[Entry]) -> @reduce.Verdict {
  match classify(entries) {
    ResetKeptBalance => Interesting
    Same => NotInteresting
    InvalidTransaction => Unresolved
  }
}

///|
fn run_example() -> Unit raise {
  let input : Array[Entry] = [
    { id: 10, operation: Credit(0), },
    { id: 11, operation: Credit(12), },
    { id: 12, operation: Debit(0), },
    { id: 13, operation: Reset, },
    { id: 14, operation: Credit(0), },
    { id: 15, operation: Credit(3), },
    { id: 16, operation: Debit(1), },
    { id: 17, operation: Credit(0), },
  ]
  let result = @reduce.reduce(input[:], verdict)
  let best = result.best.unwrap()
  let positions = result.snapshot.best_positions.unwrap()
  assert_true(best.length() < input.length())
  assert_true(best.length() == positions.length())
  // Independent checks through public results, not the core's proof flag.
  assert_true(classify(best) is ResetKeptBalance)
  let mut previous = -1
  for index, position in positions {
    assert_true(position > previous && position < input.length())
    assert_true(input[position] == best[index])
    previous = position
  }
  for removed in 0..<best.length() {
    let remaining = []
    for index, entry in best {
      if index != removed {
        remaining.push(entry)
      }
    }
    assert_true(classify(ReadOnlyArray::from_array(remaining[:])) is Same)
  }
  assert_true(result.snapshot.minimality is Verified)
  assert_true(verdict([{ id: 99, operation: Debit(100), }]) is Unresolved)
  println(
    "ledger integration: \{input.length()} -> \{best.length()} entries; " +
    "\{result.snapshot.feedback_count} core callbacks; positions=\{@debug.to_string(positions)}; " +
    "target independently replayed; \{best.length()} deletions NotInteresting",
  )
  println(
    "replayed balances: reference=\{replay(best, injected_bug=false).unwrap()}; " +
    "injected=\{replay(best, injected_bug=true).unwrap()}",
  )
  for entry in best {
    match entry.operation {
      Credit(amount) => println("id=\{entry.id} Credit(\{amount})")
      Debit(amount) => println("id=\{entry.id} Debit(\{amount})")
      Reset => println("id=\{entry.id} Reset")
    }
  }
}

///|
fn main {
  run_example() catch {
    error => abort(error.to_string())
  }
}

///|
test "typed ledger contract through the public dependency" {
  run_example()
}
