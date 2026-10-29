///|
/// This executable is a capability probe, not the reduction CLI.
async fn main {
  let args = @env.args()
  let fixture = @fs.realpath("tests/fixtures/oracle.py")
  if args.length() == 3 && args[1] == "--interrupt" {
    interrupt_probe(fixture, args[2], "tree")
  } else if args.length() == 3 && args[1] == "--interrupt-stubborn" {
    interrupt_probe(fixture, args[2], "stubborn")
  } else {
    @async.with_timeout(20000, () => run_probes(fixture))
  }
}

///|
async fn run_probes(fixture : String) -> Unit {
  let work = @fs.tmpdir(prefix="moonreduce probe ")
  defer @fs.rmdir(work, recursive=true)
  let candidate = work + "/candidate with spaces.bin"
  let bytes = Bytes::makei(256, i => i.to_byte()) + b"\r\nlast line\x00\xff"
  @fs.write_file(candidate, bytes, create_mode=CreateNew)
  assert_eq(@fs.read_file(candidate).binary(), bytes)
  let empty = work + "/empty"
  @fs.write_file(empty, b"", create_mode=CreateNew)
  assert_eq(@fs.read_file(empty).binary(), b"")
  // Exercise non-overwriting rename and atomic replacement on this filesystem.
  let staged = work + "/staged"
  @fs.write_file(staged, bytes, create_mode=CreateNew)
  try @fs.rename(staged, candidate, replace=false) catch {
    @os_error.OSError(_) as err if err.is_EEXIST() => ()
    err => raise err
  } noraise {
    _ => fail("non-overwriting rename replaced an existing file")
  }
  assert_eq(@fs.read_file(staged).binary(), bytes)
  assert_eq(@fs.read_file(candidate).binary(), bytes)
  @fs.rename(staged, candidate, replace=true)
  assert_eq(@fs.read_file(candidate).binary(), bytes)
  try
    @fs.write_file(candidate, b"must not replace", create_mode=CreateNew)
  catch {
    @os_error.OSError(_) as err if err.is_EEXIST() => ()
    err => raise err
  } noraise {
    _ => fail("CreateNew overwrote an existing file")
  }
  assert_eq(@fs.read_file(candidate).binary(), bytes)
  println(
    "PASS byte round trip, empty file, exclusive create, atomic replacement",
  )

  // Copy the fixture so that the executable's own path also contains spaces.
  let spaced_executable = work + "/oracle with spaces.py"
  @fs.write_file(
    spaced_executable,
    @fs.read_file(fixture),
    create_mode=CreateNew,
  )
  @fs.chmod(spaced_executable, 0o700)
  for code in [0, 1, 2, 7, 124, 137] {
    assert_eq(
      @process.run(spaced_executable, ["exit", code.to_string(), candidate]),
      code,
    )
  }
  for signal in [9, 11, 15] {
    assert_eq(
      @process.run(spaced_executable, ["signal", signal.to_string(), candidate]),
      -signal,
    )
  }
  try @process.run(work + "/does not exist", []) catch {
    @os_error.OSError(_) as err if err.is_ENOENT() => ()
    err => raise err
  } noraise {
    _ => fail("missing command did not raise ENOENT")
  }
  println("PASS exit 0/1/2/7/124/137, signals -9/-11/-15, missing executable")

  for code in [0, 1, 2, 124, 137] {
    let directory = work + "/isolated-exit-" + code.to_string()
    @fs.mkdir(directory)
    assert_eq(
      run_isolated(
        spaced_executable,
        ["exit", code.to_string(), candidate],
        directory,
        2000,
      ),
      Some(code),
    )
  }
  let signal_dir = work + "/isolated-signal"
  @fs.mkdir(signal_dir)
  assert_eq(
    run_isolated(
      spaced_executable,
      ["signal", "9", candidate],
      signal_dir,
      2000,
    ),
    Some(-9),
  )
  let missing_dir = work + "/isolated-missing"
  @fs.mkdir(missing_dir)
  assert_eq(
    run_isolated(work + "/does not exist", [], missing_dir, 2000),
    Some(127),
  )
  println(
    "PASS setsid preserves oracle exit/signal results; launch failure stays an error",
  )

  let unusual_args = [
    "two words", "literal;$(echo unsafe)*", "quote\"and'quote", "line\nbreak",
  ]
  let argv_args = ["argv"]
  argv_args.append(unusual_args)
  argv_args.push(candidate)
  let argv_dir = work + "/argv"
  @fs.mkdir(argv_dir)
  assert_eq(run_isolated(spaced_executable, argv_args, argv_dir, 2000), Some(0))
  let observed = @fs.read_file(argv_dir + "/stdout.log").json()
  let expected = unusual_args.copy()
  expected.push(candidate)
  assert_eq(observed.stringify(), Json(expected).stringify())
  println(
    "PASS argv array, literal shell characters, spaced executable/candidate paths",
  )

  let large_dir = work + "/large"
  @fs.mkdir(large_dir)
  assert_eq(
    run_isolated(spaced_executable, ["large", candidate], large_dir, 5000),
    Some(0),
  )
  assert_eq(@fs.file_size(large_dir + "/stdout.log"), 8388608L)
  assert_eq(@fs.file_size(large_dir + "/stderr.log"), 8388608L)
  let diagnostic = @fs.open(large_dir + "/stderr.log", mode=ReadOnly)
  defer diagnostic.close()
  assert_eq(diagnostic.read_some(max_len=4096).unwrap().length(), 4096)
  println(
    "PASS 8 MiB per output stream redirected to files, diagnostic read <= 4096 bytes",
  )

  let tree_dir = work + "/tree"
  @fs.mkdir(tree_dir)
  assert_eq(
    run_isolated(spaced_executable, ["tree", tree_dir], tree_dir, 500),
    None,
  )
  assert_eq(@process.run(spaced_executable, ["check-tree", tree_dir]), 0)
  assert_true(@fs.exists(tree_dir + "/reaped"))
  assert_true(@fs.exists(tree_dir + "/worker-reaped"))
  let hard_dir = work + "/hard"
  @fs.mkdir(hard_dir)
  assert_eq(
    run_isolated(spaced_executable, ["stubborn", hard_dir], hard_dir, 300),
    None,
  )
  assert_eq(@process.run(spaced_executable, ["check-tree", hard_dir]), 0)
  println(
    "PASS timeout: process group stopped, ordinary children reaped, SIGKILL escalation",
  )

  // A synchronous request is materialized and judged asynchronously, then fed back.
  // The actual reducer state machine belongs to stage 1.
  let request : @core.CandidateRequest = { id: 0, positions: [0, 2], }
  assert_eq(request.positions, [0, 2])
  let status = @process.run(spaced_executable, ["exit", "0", candidate])
  let verdict : @core.Verdict = match status {
    0 => Interesting
    1 => NotInteresting
    2 => Unresolved
    _ => fail("execution error is not an oracle verdict")
  }
  match verdict {
    Interesting => assert_eq(request.id, 0)
    _ => fail("request/feedback probe failed")
  }
  println(
    "PASS synchronous core request -> async Native call -> synchronous feedback",
  )
  println(
    "{\"stage\":0,\"probe\":\"passed\",\"dependency\":\"moonbitlang/async@0.22.4\"}",
  )
}

///|
async fn interrupt_probe(
  fixture : String,
  evidence : String,
  mode : String,
) -> Unit {
  defer @async.protect_from_cancel(() => {
    @fs.write_file(
      evidence + "/cleanup-finished",
      b"done",
      create_mode=CreateNew,
    )
  })
  run_isolated(fixture, [mode, evidence], evidence, 30000) |> ignore
}
