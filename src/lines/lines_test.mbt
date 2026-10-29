///|
test "LF byte segmentation and concatenation preserve exact bytes" {
  let cases : Array[(Bytes, Array[Bytes])] = [
    (b"", []),
    (b"a", [b"a"]),
    (b"a\n", [b"a\n"]),
    (b"\n", [b"\n"]),
    (b"\n\n", [b"\n", b"\n"]),
    (b"a\r\nb\r\n", [b"a\r\n", b"b\r\n"]),
    (b"a\n\nb", [b"a\n", b"\n", b"b"]),
    (b"\x00\xff\r\n \t\nlast\xfe", [b"\x00\xff\r\n", b" \t\n", b"last\xfe"]),
  ]
  for (input, expected) in cases {
    let segments = @lines.split(input)
    @test.assert_eq(segments.map(segment => segment.to_owned()), expected)
    for mask in 0..<(1 << expected.length()) {
      let selected = []
      let mut reference = b""
      for i, segment in expected {
        if (mask & (1 << i)) != 0 {
          selected.push(i)
          reference = reference + segment
        }
      }
      @test.assert_eq(
        @lines.assemble(segments, ReadOnlyArray::from_array(selected)),
        reference,
      )
    }
  }
}
