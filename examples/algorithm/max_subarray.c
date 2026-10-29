/* Artificially injected bug, not a discovered production defect.
 * Original example code, MIT. Empty subarray is allowed (answer >= 0). */
#include <stdio.h>

#ifndef INJECT_BUG
#define INJECT_BUG 0
#endif

int main(void) {
  long long n;
  if (scanf("%lld", &n) != 1 || n < 0 || n > 4096) return 3;
  long long running = 0, best = 0;
  for (long long i = 0; i < n; ++i) {
    long long value;
    if (scanf("%lld", &value) != 1 || value < -1000 || value > 1000) return 3;
#if INJECT_BUG
    /* BUG: a negative item does not always destroy a profitable prefix.
     * Example: a positive prefix can bridge a small negative item. */
    running = value < 0 ? 0 : running + value;
#else
    running += value;
    if (running < 0) running = 0;
#endif
    if (running > best) best = running;
  }
  char extra;
  if (scanf(" %c", &extra) != EOF) return 3;
  if (printf("%lld\n", best) < 0) return 3;
  return 0;
}
