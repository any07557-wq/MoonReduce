///|
test "exhaustive Boolean predicates on every subsequence through length four" {
  for length in 0..<=4 {
    let original = Array::makei(length, i => i)
    let subset_count = 1 << length
    let truth_table_count = 1 << subset_count
    for table in 0..<truth_table_count {
      fn oracle(values : ReadOnlyArray[Int32]) -> @core.Verdict {
        if ((table >> mask_of(values)) & 1) == 1 {
          Interesting
        } else {
          NotInteresting
        }
      }
      audit(original, @core.reduce(original, oracle), oracle)
    }
  }
}

///|
test "exhaustive three-valued predicates through length three" {
  for length in 0..<=3 {
    let original = Array::makei(length, i => i)
    let subset_count = 1 << length
    let powers = [1]
    for _ in 0..<subset_count {
      powers.push(powers.last().unwrap() * 3)
    }
    for table in 0..<powers[subset_count] {
      fn oracle(values : ReadOnlyArray[Int32]) -> @core.Verdict {
        match table / powers[mask_of(values)] % 3 {
          0 => NotInteresting
          1 => Interesting
          _ => Unresolved
        }
      }
      audit(original, @core.reduce(original, oracle), oracle)
    }
  }
}
