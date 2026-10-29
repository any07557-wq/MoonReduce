///|
/// Keep the raising timeout: with_timeout_opt stalled this nested wait in the
/// stage 1 regression. The outer task group still waits for/reaps its child.
async fn Run::invoke(
  self : Run,
  expected : Bytes,
  revalidate~ : Bool = false,
) -> @core.Verdict {
  let mut started = false
  let mut classified = false
  let mut failure : Error? = None
  // Every controlled start has exactly one terminal classification, including
  // failures in process cleanup and cancellation before a verdict is obtained.
  defer (if started && !classified {
    if failure is Some(_) || !@async.is_being_cancelled() {
      self.oracle_errors += 1
    } else {
      self.interrupted_tests += 1
    }
  })
  // errdefer also runs for cancellation on this toolchain. Capture actual
  // errors as values so an interrupted call is not misreported as an error.
  let outcome : Result[@core.Verdict, Error] = try {
    self.last_exit_code = None
    self.stdout_prefix = ""
    self.stderr_prefix = ""
    self.stdout_truncated = false
    self.stderr_truncated = false
    let work = @fs.tmpdir(prefix="moonreduce oracle ")
    defer @async.protect_from_cancel(() => {
      // Diagnostics are best effort evidence, but their failure is still an I/O
      // error. Always remove the work directory even when reading them fails.
      defer @fs.rmdir(work, recursive=true)
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
              cleanup_group(pid, startup_fallback=true)
            })
          },
        )
        self.tests_started += 1
        started = true
        self.phase_counts[self.phase] = self.phase_counts.get_or_default(
            self.phase,
            0,
          ) +
          1
        child
      })
      defer @async.protect_from_cancel(() => {
        cleanup_group(process.pid, startup_fallback=false)
      })
      Some(@async.with_timeout(self.config.timeout_ms, () => process.wait())) catch {
        @async.TimeoutError => {
          self.timeouts += 1
          self.unresolved += 1
          classified = true
          None
        }
        error => raise error
      }
    })
    self.last_exit_code = status
    guard @fs.read_file(candidate).binary() == expected else {
      if revalidate {
        // A misbehaving oracle must not leave a corrupted "saved best" behind.
        // This restores prior evidence; it does not claim a new revalidation.
        atomic_write(self.paths.output, expected)
      }
      raise OracleError("oracle modified the candidate file")
    }
    Ok(
      match status {
        None => Unresolved
        Some(0) => {
          self.interesting += 1
          classified = true
          Interesting
        }
        Some(1) => {
          self.not_interesting += 1
          classified = true
          NotInteresting
        }
        Some(2) => {
          self.unresolved += 1
          classified = true
          Unresolved
        }
        Some(code) =>
          if code < 0 {
            raise OracleError(
              "oracle killed by signal \{-code}; this is an execution error",
            )
          } else {
            raise OracleError(
              "oracle/exec exited \{code}; expected normal exit 0, 1 or 2",
            )
          }
      },
    )
  } catch {
    error => Err(error)
  }
  match outcome {
    Ok(verdict) => verdict
    Err(error) => {
      failure = Some(error)
      raise error
    }
  }
}

///|
async fn cleanup_group(pid : Int32, startup_fallback~ : Bool) -> Unit {
  errdefer {
    // Also applies after a normally exited group leader: process cancellation
    // is no longer available there, but live descendants still need killing.
    let @process.CancellationHandler(hard) = @process.hard_cancel()
    hard(-pid)
    hard(pid)
  }
  stop_group(pid, startup_fallback~)
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
