///|
fn parse_config() -> @native.Config raise {
  let args = @env.args()
  let mut separator = args.length()
  for i in 1..<args.length() {
    if args[i] == "--" {
      separator = i
      break
    }
  }
  let command = @argparse.Command(
    "moonreduce",
    version=@native.version,
    about="Reduce LF-delimited file bytes. After -- supply COMMAND [ARGS...].\nThe absolute candidate path is appended as the final argument; no implicit shell.",
    options=[
      @argparse.OptionArg(
        "output",
        required=true,
        about="New output file; existing files are rejected.",
      ),
      @argparse.OptionArg(
        "report",
        required=true,
        about="New JSON report file.",
      ),
      @argparse.OptionArg(
        "timeout-ms",
        default_values=["2000"],
        allow_hyphen_values=true,
      ),
      @argparse.OptionArg(
        "max-tests",
        default_values=["1000"],
        allow_hyphen_values=true,
      ),
    ],
    positionals=[
      @argparse.PositionArg(
        "INPUT",
        num_args=@argparse.ValueRange(lower=1, upper=1),
      ),
    ],
  )
  let matches = command.parse(argv=args[1:separator])
  guard separator + 1 < args.length() else {
    raise @native.UsageError("missing -- COMMAND [ARGS...]")
  }
  guard !args[separator + 1].is_empty() else {
    raise @native.UsageError("COMMAND must not be empty")
  }
  {
    input: matches.values["INPUT"][0],
    output: matches.values["output"][0],
    report: matches.values["report"][0],
    timeout_ms: integer_option(
      matches.values["timeout-ms"][0],
      "--timeout-ms",
      1,
    ),
    max_tests: integer_option(matches.values["max-tests"][0], "--max-tests", 2),
    command: ReadOnlyArray::from_array(args[separator + 1:]),
  }
}

///|
fn integer_option(
  value : String,
  option : String,
  minimum : Int32,
) -> Int32 raise {
  guard !value.is_empty() && value.iter().all(c => c >= '0' && c <= '9') else {
    raise @native.UsageError(
      "\{option} must be a decimal integer in \{minimum}..2147483647",
    )
  }
  let number = @string.parse_int64(value) catch {
    _ =>
      raise @native.UsageError(
        "\{option} is out of range (\{minimum}..2147483647)",
      )
  }
  guard number >= minimum.to_int64() && number <= 2147483647L else {
    raise @native.UsageError("\{option} must be in \{minimum}..2147483647")
  }
  number.to_int()
}
