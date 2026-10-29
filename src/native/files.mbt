///|
async fn entry_exists(path : String) -> Bool {
  try @fs.kind(path, follow_symlink=false) catch {
    @os_error.OSError(_) as error if error.is_ENOENT() => return false
    error => raise error
  } noraise {
    _ => true
  }
}

///|
async fn destination(raw : String) -> String {
  let (parent, name) = match raw.rev_split_once("/") {
    Some((parent, name)) =>
      (if parent.is_empty() { "/" } else { parent.to_owned() }, name.to_owned())
    None => (".", raw)
  }
  guard !name.is_empty() && name != "." && name != ".." else {
    raise UsageError("output and report must name files")
  }
  let parent = @fs.realpath(parent)
  parent + (if parent == "/" { "" } else { "/" }) + name
}

///|
/// test -ef compares device/inode identity, including existing hard links.
async fn same_file(left : String, right : String) -> Bool {
  let code = @process.run(
    "/usr/bin/test",
    [left, "-ef", right],
    stdout=@process.redirect_to_file("/dev/null"),
    stderr=@process.redirect_to_file("/dev/null"),
  )
  match code {
    0 => true
    1 => false
    _ => fail("file identity helper failed: \{code}")
  }
}

///|
async fn prepare(config : Config) -> Paths {
  for helper in ["/usr/bin/setsid", "/usr/bin/kill", "/usr/bin/test"] {
    guard @fs.can_execute(helper) else {
      fail("required helper is not executable: \{helper}")
    }
  }
  let input = @fs.realpath(config.input)
  guard @fs.kind(input) is Regular else {
    raise UsageError("INPUT must be a regular file")
  }
  let output = destination(config.output)
  let report = destination(config.report)
  for path in [output, report] {
    if input == path || same_file(input, path) {
      raise UsageError("output/report refers to the input file: \{path}")
    }
  }
  if output == report || same_file(output, report) {
    raise UsageError("output and report must be different files")
  }
  for path in [output, report] {
    if entry_exists(path) {
      raise UsageError(
        "refusing existing output/report (including symlinks): \{path}",
      )
    }
  }
  { input, output, report, }
}

///|
async fn reserve(path : String) -> Unit {
  @async.protect_from_cancel(() => {
    try @fs.create(path, permission=0o600) catch {
      @os_error.OSError(_) as error if error.is_EEXIST() =>
        raise UsageError("refusing existing output/report: \{path}")
      error => raise error
    } noraise {
      file => file.close()
    }
  })
}

///|
/// Only destinations exclusively reserved by this invocation may be replaced.
async fn atomic_write(path : String, data : &@io.Data) -> Unit {
  @async.protect_from_cancel(() => {
    let random = match @env.rand(16) {
      Some(bytes) => bytes
      None => fail("OS randomness unavailable")
    }
    let staged = path + ".moonreduce-" + @hex.encode(random)
    let file = @fs.create(staged, permission=0o600)
    let mut closed = false
    defer (if !closed { file.close() })
    defer (if entry_exists(staged) { @fs.remove(staged) })
    file.write(data)
    file.close()
    closed = true
    @fs.rename(staged, path, replace=true)
  })
}

///|
async fn read_prefix(path : String) -> (String, Bool) {
  let file = @fs.open(path, mode=ReadOnly)
  defer file.close()
  let bytes = file.read_some(max_len=4096).unwrap_or(b"")
  (@utf8.decode_lossy(bytes), file.size() > bytes.length().to_int64())
}
