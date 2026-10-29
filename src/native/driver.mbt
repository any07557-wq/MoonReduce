///|
/// End-to-end Native driver. Preflight errors propagate to the CLI boundary.
pub async fn run(config : Config) -> Int32 {
  let started_at = @async.now()
  let paths = prepare(config)
  let source = @fs.read_file(paths.input).binary()
  let segments = @lines.split(source)
  let mut report_written = false
  let self : Run = {
    config,
    paths,
    source,
    segments,
    reducer: @core.Reducer::new(segments.length()),
    started_at,
    tests_started: 0,
    launch_attempts: 0,
    launch_failures: 0,
    phase_counts: { "initial": 0, "search": 0, "minimality": 0, "final": 0 },
    interesting: 0,
    not_interesting: 0,
    unresolved: 0,
    timeouts: 0,
    oracle_errors: 0,
    interrupted_tests: 0,
    initial_check: "not_run",
    final_revalidation: "not_run",
    stop_reason: "execution_error",
    search_stop_reason: "not_started",
    phase: "initial",
    output_saved: false,
    interrupted: false,
    error: None,
    last_exit_code: None,
    stdout_prefix: "",
    stderr_prefix: "",
    stdout_truncated: false,
    stderr_truncated: false,
  }
  let outcome = @async.handle_cancellation(() => {
    self.execute() catch {
      error => self.record_error(error)
    }
  })
  if outcome is None || @async.is_being_cancelled() {
    self.interrupted = true
    if self.error is None {
      self.stop_reason = "interrupted"
      if self.phase != "final" {
        self.search_stop_reason = "interrupted"
      }
      if self.phase == "final" && self.final_revalidation == "not_run" {
        self.final_revalidation = "interrupted"
      } else if self.phase == "initial" && self.initial_check == "not_run" {
        self.initial_check = "interrupted"
      }
    }
    self.reducer.stop(Interrupted)
  }
  @async.protect_from_cancel(() => {
    try self.write_report() catch {
      error => self.record_error(error)
    } noraise {
      _ => report_written = true
    }
    self.print_summary(report_written~) catch {
      error => {
        self.record_error(error)
        // A closed stdout pipe must not leave a JSON exit_code=0 while the CLI
        // returns 4. Revise only the report this invocation already published.
        if report_written {
          self.write_report(replace=true) catch {
            error => {
              self.record_error(error)
              @fs.remove(paths.report) catch {
                error => self.record_error(error)
              }
            }
          }
        }
        @stdio.stderr.write(
          "MoonReduce: execution_error; exit code: 4; " +
          self.error.unwrap_or("summary write failed") +
          "\n",
        ) catch {
          _ => ()
        }
      }
    }
    self.exit_code()
  })
}

///|
async fn Run::execute(self : Run) -> Unit {
  while self.reducer.next() is Some(request) {
    if request.phase != Initial &&
      self.tests_started >= self.config.max_tests - 1 {
      self.reducer.stop(BudgetExhausted)
      break
    }
    self.phase = match request.phase {
      Initial => "initial"
      Search => "search"
      MinimalityCheck => "minimality"
    }
    let bytes = @lines.assemble(self.segments, request.positions)
    let verdict = self.invoke(bytes)
    if request.phase == Initial {
      self.initial_check = verdict_name(verdict)
    }
    if verdict == Interesting {
      // Publish before committing the core best, preserving the previous best
      // and its report metadata if the atomic write fails.
      atomic_write(self.paths.output, bytes, replace=self.output_saved)
      self.reducer.submit(request.id, verdict) |> ignore
      self.output_saved = true
    } else {
      self.reducer.submit(request.id, verdict) |> ignore
    }
  }
  let state = self.reducer.snapshot()
  match state.stop_reason {
    Some(InitialNotInteresting) => {
      self.stop_reason = "initial_not_interesting"
      return
    }
    Some(InitialUnresolved) => {
      self.stop_reason = "initial_unresolved"
      return
    }
    Some(Stopped(BudgetExhausted)) =>
      self.search_stop_reason = "budget_exhausted"
    _ => self.search_stop_reason = "completed"
  }
  let best = state.best_positions.unwrap()
  guard self.output_saved else {
    fail("known Interesting result was not saved")
  }
  guard self.tests_started < self.config.max_tests else {
    fail("final call was not reserved")
  }
  self.phase = "final"
  let verdict = self.invoke(
    @lines.assemble(self.segments, best),
    revalidate=true,
  )
  self.final_revalidation = verdict_name(verdict)
  self.stop_reason = match verdict {
    NotInteresting => "final_not_interesting"
    Unresolved => "final_unresolved"
    Interesting =>
      if self.search_stop_reason == "budget_exhausted" {
        "budget_exhausted"
      } else if state.minimality == BlockedByUnresolved {
        "unresolved"
      } else if state.minimality == Verified {
        "completed"
      } else {
        fail("reduction ended without a minimality decision")
      }
  }
}

///|
fn Run::record_error(self : Run, error : Error) -> Unit {
  self.error = Some(
    match self.error {
      None => error_message(error)
      Some(first) => first + "; additionally: " + error_message(error)
    },
  )
  self.stop_reason = "execution_error"
  if self.phase == "final" {
    if self.final_revalidation == "not_run" {
      self.final_revalidation = "error"
    }
  } else {
    self.search_stop_reason = "execution_error"
    if self.phase == "initial" && self.initial_check == "not_run" {
      self.initial_check = "error"
    }
  }
  self.reducer.stop(ExecutionError)
}

///|
fn verdict_name(verdict : @core.Verdict) -> String {
  match verdict {
    Interesting => "interesting"
    NotInteresting => "not_interesting"
    Unresolved => "unresolved"
  }
}

///|
fn error_message(error : Error) -> String {
  match error {
    OracleError(message) | UsageError(message) => message
    _ => error.to_string()
  }
}

///|
fn minimality_name(minimality : @core.Minimality) -> String {
  match minimality {
    Verified => "verified"
    BlockedByUnresolved => "blocked_by_unresolved"
    Incomplete => "incomplete"
    NotChecked => "not_checked"
  }
}

///|
fn Run::exit_code(self : Run) -> Int32 {
  match self.stop_reason {
    "completed" => 0
    "budget_exhausted" | "unresolved" => 1
    "initial_not_interesting" | "initial_unresolved" => 3
    "interrupted" => 130
    _ => 4
  }
}
