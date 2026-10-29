///|
/// The probe uses async process APIs, util-linux setsid, and procps-ng kill.
/// No shell parses the oracle command. Each caller supplies a fresh directory.
async fn run_isolated(
  executable : String,
  args : Array[String],
  directory : String,
  timeout_ms : Int32,
) -> Int32? {
  @async.with_task_group(group => {
    let argv = ["--", executable]
    argv.append(args)
    let process = @process.spawn(
      group,
      "/usr/bin/setsid",
      argv,
      stdin=@process.redirect_from_file("/dev/null"),
      stdout=@process.redirect_to_file(
        directory + "/stdout.log",
        create_mode=CreateNew,
        permission=0o600,
      ),
      stderr=@process.redirect_to_file(
        directory + "/stderr.log",
        create_mode=CreateNew,
        permission=0o600,
      ),
      // Protect the complete escalation even if the group leader exits early.
      cancel_handler=pid => {
        @async.protect_from_cancel(() => stop_group(pid, startup_fallback=true))
      },
    )
    // Also clean remaining group members after ordinary exit or timeout.
    // Keeping cleanup outside the library's cancellation handler matters:
    // that handler is normally cancelled as soon as its direct child exits.
    defer @async.protect_from_cancel(() => {
      stop_group(process.pid, startup_fallback=false)
    })
    @async.with_timeout_opt(timeout_ms, () => process.wait())
    // On timeout the wait task is cancelled; the process task remains in the
    // enclosing task group, which waits for it and reaps it after cleanup.
  })
}

///|
async fn stop_group(pid : Int32, startup_fallback~ : Bool) -> Unit {
  let result = send_signal("TERM", "-\{pid}")
  if result == 1 && startup_fallback {
    // Cancellation can race setsid before the new session exists.
    send_signal("TERM", pid.to_string()) |> ignore
  }
  @async.sleep(100)
  send_signal("KILL", "-\{pid}") |> ignore
}

///|
async fn send_signal(signal : String, target : String) -> Int32 {
  let status = @process.run(
    "/usr/bin/kill",
    ["--signal", signal, "--", target],
    stdout=@process.redirect_to_file("/dev/null"),
    stderr=@process.redirect_to_file("/dev/null"),
  )
  // kill returns 1 for an already absent group. It cannot be Interesting.
  guard status == 0 || status == 1 else {
    fail("kill helper failed: \{status}")
  }
  status
}
