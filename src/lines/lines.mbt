///|
/// LF belongs to its preceding segment. A final LF adds no empty segment.
pub fn split(data : Bytes) -> Array[BytesView] {
  let segments = []
  let mut start = 0
  for i in 0..<data.length() {
    if data[i] == 0x0a {
      segments.push(data[start:i + 1])
      start = i + 1
    }
  }
  if start < data.length() {
    segments.push(data[start:])
  }
  segments
}

///|
/// Positions come from the ordered reducer; bytes are never decoded.
pub fn assemble(
  segments : ArrayView[BytesView],
  positions : ReadOnlyArray[Int32],
) -> Bytes {
  let output = @buffer.Buffer()
  for position in positions {
    output.write_bytes(segments[position])
  }
  output.to_bytes()
}
