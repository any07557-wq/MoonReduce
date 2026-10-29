///|
pub let version : String = "0.1.0-dev"

///|
pub(all) struct Config {
  input : String
  output : String
  report : String
  command : ReadOnlyArray[String]
  timeout_ms : Int32
  max_tests : Int32
}

///|
pub(all) suberror UsageError {
  UsageError(String)
}

///|
priv suberror OracleError {
  OracleError(String)
}

///|
priv struct Paths {
  input : String
  output : String
  report : String
}

///|
priv struct Run {
  config : Config
  paths : Paths
  source : Bytes
  segments : Array[BytesView]
  reducer : @core.Reducer
  started_at : Int64
  mut tests_started : Int32
  mut launch_attempts : Int32
  mut launch_failures : Int32
  phase_counts : Map[String, Int32]
  mut interesting : Int32
  mut not_interesting : Int32
  mut unresolved : Int32
  mut timeouts : Int32
  mut oracle_errors : Int32
  mut initial_check : String
  mut final_revalidation : String
  mut stop_reason : String
  mut search_stop_reason : String
  mut phase : String
  mut output_saved : Bool
  mut interrupted : Bool
  mut error : String?
  mut last_exit_code : Int32?
  mut stdout_prefix : String
  mut stderr_prefix : String
  mut stdout_truncated : Bool
  mut stderr_truncated : Bool
}
