///|
/// Synchronous convenience API. The input structure is copied once; reference
/// elements are not deep-copied and must stay stable during reduction. Callback
/// errors propagate. Use Reducer directly to retain a best on early exit or to
/// enforce a budget. No final revalidation is hidden inside this function.
pub fn[T] reduce(
  input : ArrayView[T],
  oracle : (ReadOnlyArray[T]) -> Verdict raise?,
) -> ReductionResult[T] raise {
  let original = ReadOnlyArray::from_array(input)
  let reducer = Reducer::new(original.length())
  while reducer.next() is Some(request) {
    let verdict = oracle(request.positions.map(position => original[position]))
    reducer.submit(request.id, verdict) |> ignore
  }
  let snapshot = reducer.snapshot()
  {
    snapshot,
    best: snapshot.best_positions.map(positions => {
      positions.map(position => original[position])
    }),
  }
}
