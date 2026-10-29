///|
extern "C" fn exit_process(code : Int32) -> Unit = "exit"

///|
async fn main {
  let config = parse_config() catch {
    error => {
      let message = match error {
        @native.UsageError(message) => message
        _ => error.to_string()
      }
      @stdio.stderr.write("MoonReduce: \{message}\n")
      exit_process(2)
      return
    }
  }
  let result = @async.handle_cancellation(() => {
    @native.run(config) catch {
      @native.UsageError(message) => {
        @stdio.stderr.write("MoonReduce: \{message}\n")
        2
      }
      error => {
        @stdio.stderr.write(
          "MoonReduce execution error: \{error.to_string()}\n",
        )
        4
      }
    }
  })
  exit_process(result.unwrap_or(130))
}
