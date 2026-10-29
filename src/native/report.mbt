///|
async fn Run::write_report(self : Run) -> Unit {
  let state = self.reducer.snapshot()
  let best_size = state.best_positions.map(positions => {
    @lines.assemble(self.segments, positions).length()
  })
  let report : Json = {
    "schema_version": 1,
    "tool_version": version,
    "input": self.paths.input,
    "output": if self.output_saved {
      Json(self.paths.output)
    } else {
      Json::null()
    },
    "oracle_argv": Json(self.config.command),
    "original_bytes": self.source.length(),
    "original_segments": self.segments.length(),
    "best_bytes": optional_int(best_size),
    "best_segments": optional_int(
      state.best_positions.map(positions => positions.length()),
    ),
    "best_positions": match state.best_positions {
      Some(positions) => Json(positions)
      None => Json::null()
    },
    "stop_reason": self.stop_reason,
    "search_stop_reason": self.search_stop_reason,
    "initial_check": self.initial_check,
    "final_revalidation": self.final_revalidation,
    "minimality": minimality_name(state.minimality),
    "minimality_checked": state.minimality_checked,
    "minimality_required": state.minimality_required,
    "tests_started": self.tests_started,
    "launch_attempts": self.launch_attempts,
    "launch_failures": self.launch_failures,
    "tests_by_phase": Json(self.phase_counts),
    "interesting": self.interesting,
    "not_interesting": self.not_interesting,
    "unresolved": self.unresolved,
    "timeouts": self.timeouts,
    "oracle_errors": self.oracle_errors,
    "error": match self.error {
      Some(message) => Json(message)
      None => Json::null()
    },
    "last_exit_code": optional_int(
      self.last_exit_code.filter(code => code >= 0),
    ),
    "last_signal": optional_int(
      self.last_exit_code.filter(code => code < 0).map(code => -code),
    ),
    "max_tests": self.config.max_tests,
    "timeout_ms": self.config.timeout_ms,
    "elapsed_ms": Json((@async.now() - self.started_at).to_double()),
    "had_unresolved": self.unresolved > 0,
    "interrupted": self.interrupted,
    "cache_enabled": false,
    "cache_hits": 0,
    "output_saved": self.output_saved,
    "diagnostics": {
      "stdout": self.stdout_prefix,
      "stderr": self.stderr_prefix,
      "stdout_truncated": self.stdout_truncated,
      "stderr_truncated": self.stderr_truncated,
    },
  }
  atomic_write(self.paths.report, report)
}

///|
fn optional_int(value : Int32?) -> Json {
  match value {
    Some(value) => Json(value)
    None => Json::null()
  }
}

///|
async fn Run::print_summary(self : Run, report_written~ : Bool) -> Unit {
  let state = self.reducer.snapshot()
  let size = if self.output_saved {
    @lines.assemble(self.segments, state.best_positions.unwrap())
    .length()
    .to_string()
  } else {
    "none"
  }
  @stdio.stdout.write(
    "MoonReduce: \{self.stop_reason}\n" +
    "Final revalidation: \{self.final_revalidation}; minimality: \{minimality_name(state.minimality)}\n" +
    "Bytes: \{self.source.length()} -> \{size}; oracle starts: \{self.tests_started}/\{self.config.max_tests}; timeouts: \{self.timeouts}\n",
  )
  if self.output_saved {
    @stdio.stdout.write("Output: \{self.paths.output}\n")
  }
  if report_written {
    @stdio.stdout.write("Report: \{self.paths.report}\n")
  }
  if self.error is Some(message) {
    @stdio.stderr.write("MoonReduce error: \{message}\n")
    if !self.stderr_prefix.is_empty() {
      @stdio.stderr.write(self.stderr_prefix + "\n")
    }
  }
}
