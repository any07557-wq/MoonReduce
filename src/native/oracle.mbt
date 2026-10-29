///|
/// Keep the raising timeout: with_timeout_opt stalled this nested wait in the
/// stage 1 regression. The outer task group still waits for/reaps its child.
async fn Run::invoke(
  self : Run,
  expected : Bytes,
  revalidate~ : Bool = false,
) -> @core.Verdict {
  self.last_exit_code = None
  self.stdout_prefix = ""
  self.stderr_prefix = ""
  self.stdout_truncated = false
  self.stderr_truncated = false
  let work = @fs.tmpdir(prefix="moonreduce oracle ")
  defer @async.protect_from_cancel(() => {
    if entry_exists(work + "/stdout.log") {
      let (text, truncated) = read_prefix(work + "/stdout.log")
      self.stdout_prefix = text
      self.stdout_truncated = truncated
    }
    if entry_exists(work + "/stderr.log") {
      let (text, truncated) = read_prefix(work + "/stderr.log")
      self.stderr_prefix = text
      self.stderr_truncated = truncated
    }
    @fs.rmdir(work, recursive=true)
  })
  let candidate = if revalidate {
    self.paths.output
  } else {
    let path = work + "/candidate.bin"
    @fs.write_file(path, expected, create_mode=CreateNew, permission=0o600)
    @fs.realpath(path)
  }
  let argv = self.config.command[1:].to_owned()
  argv.push(candidate)
  let stdout = @process.redirect_to_file(
    work + "/stdout.log",
    create_mode=CreateNew,
    permission=0o600,
    shared=true,
  )
  defer stdout.close()
  let stderr = @process.redirect_to_file(
    work + "/stderr.log",
    create_mode=CreateNew,
    permission=0o600,
    shared=true,
  )
  defer stderr.close()
  self.launch_attempts += 1
  let status = @async.with_task_group(group => {
    let process = @async.protect_from_cancel(() => {
      let argv = ["--", self.config.command[0]] + argv
      errdefer {
        self.launch_failures += 1
        self.oracle_errors += 1
      }
      let child = @process.spawn(
        group,
        "/usr/bin/setsid",
        argv,
        stdin=@process.redirect_from_file("/dev/null"),
        stdout~,
        stderr~,
        cancel_handler=pid => {
          @async.protect_from_cancel(() => {
            errdefer {
              // Linux fallback through the existing cancellation primitive.
              let @process.CancellationHandler(hard) = @process.hard_cancel()
              hard(-pid)
              hard(pid)
            }
            stop_group(pid, startup_fallback=true)
          })
        },
      )
      self.tests_started += 1
      self.phase_counts[self.phase] = self.phase_counts.get_or_default(
          self.phase,
          0,
        ) +
        1
      child
    })
    defer @async.protect_from_cancel(() => {
      stop_group(process.pid, startup_fallback=false)
    })
    Some(@async.with_timeout(self.config.timeout_ms, () => process.wait())) catch {
      @async.TimeoutError => None
      error => raise error
    }
  })
  self.last_exit_code = status
  guard @fs.read_file(candidate).binary() == expected else {
    raise OracleError("oracle modified the candidate file")
  }
  match status {
    None => {
      self.unresolved += 1
      self.timeouts += 1
      Unresolved
    }
    Some(0) => {
      self.interesting += 1
      Interesting
    }
    Some(1) => {
      self.not_interesting += 1
      NotInteresting
    }
    Some(2) => {
      self.unresolved += 1
      Unresolved
    }
    Some(code) => {
      self.oracle_errors += 1
      if code < 0 {
        raise OracleError(
          "oracle killed by signal \{-code}; this is an execution error",
        )
      } else {
        raise OracleError(
          "oracle/exec exited \{code}; expected normal exit 0, 1 or 2",
        )
      }
    }
  }
}

///|
async fn stop_group(pid : Int32, startup_fallback~ : Bool) -> Unit {
  let exists = send_signal("TERM", "-\{pid}")
  if !exists {
    if !startup_fallback {
      return
    }
    send_signal("TERM", pid.to_string()) |> ignore
  }
  @async.sleep(100)
  let group_found = send_signal("KILL", "-\{pid}")
  if !group_found && startup_fallback {
    send_signal("KILL", pid.to_string()) |> ignore
  }
}

///|
/// Only ESRCH is an acceptable failed kill. Locale and helper path are fixed.
async fn send_signal(signal : String, target : String) -> Bool {
  let work = @fs.tmpdir(prefix="moonreduce signal ")
  defer @fs.rmdir(work, recursive=true)
  let code = @process.run(
    "/usr/bin/kill",
    ["-" + signal, "--", target],
    extra_env={ "LC_ALL": "C" },
    stdout=@process.redirect_to_file("/dev/null"),
    stderr=@process.redirect_to_file(
      work + "/stderr",
      create_mode=CreateNew,
      permission=0o600,
    ),
  )
  if code == 0 {
    return true
  }
  let (message, truncated) = read_prefix(work + "/stderr")
  if code == 1 && !truncated && message.contains("No such process") {
    false
  } else {
    raise OracleError(
      "signal helper failed (\{code}, \{signal}, target=\{target}): \{message}",
    )
  }
}
