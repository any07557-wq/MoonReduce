/* Test-only Linux fault injection. Never linked into or loaded by normal CLI. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int before_write(int fd, size_t size) {
  const char *prefix = getenv("MOONREDUCE_TEST_WRITE_PREFIX");
  const char *arm = getenv("MOONREDUCE_TEST_ARM_WRITE");
  if (prefix && (!arm || access(arm, F_OK) == 0)) {
    char link[64], path[4096];
    snprintf(link, sizeof link, "/proc/self/fd/%d", fd);
    ssize_t length = readlink(link, path, sizeof path - 1);
    if (length >= 0) {
      path[length] = '\0';
      if (strncmp(path, prefix, strlen(prefix)) == 0) {
        const char *gate = getenv("MOONREDUCE_TEST_WRITE_GATE");
        if (gate) {
          char ready[4096], release[4096];
          snprintf(ready, sizeof ready, "%s.ready", gate);
          snprintf(release, sizeof release, "%s.release", gate);
          int marker = open(ready, O_WRONLY | O_CREAT, 0600);
          if (marker >= 0) close(marker);
          while (access(release, F_OK) != 0) usleep(10000);
        } else {
          static atomic_int partial_written;
          if (atomic_exchange(&partial_written, 1) == 0 && size > 1)
            return 1;
          errno = ENOSPC;
          return -1;
        }
      }
    }
  }
  return 0;
}

ssize_t write(int fd, const void *buffer, size_t size) {
  typedef ssize_t (*write_fn)(int, const void *, size_t);
  write_fn real_write = (write_fn)dlsym(RTLD_NEXT, "write");
  int fault = before_write(fd, size);
  if (fault < 0) return -1;
  return real_write(fd, buffer, fault ? size / 2 : size);
}

ssize_t pwrite(int fd, const void *buffer, size_t size, off_t offset) {
  typedef ssize_t (*write_fn)(int, const void *, size_t, off_t);
  write_fn real_write = (write_fn)dlsym(RTLD_NEXT, "pwrite");
  int fault = before_write(fd, size);
  if (fault < 0) return -1;
  return real_write(fd, buffer, fault ? size / 2 : size, offset);
}

int posix_spawn(pid_t *pid, const char *path,
                const posix_spawn_file_actions_t *actions,
                const posix_spawnattr_t *attr, char *const argv[],
                char *const envp[]) {
  typedef int (*spawn_fn)(pid_t *, const char *,
                         const posix_spawn_file_actions_t *,
                         const posix_spawnattr_t *, char *const[], char *const[]);
  spawn_fn real_spawn = (spawn_fn)dlsym(RTLD_NEXT, "posix_spawn");
  const char *fault = getenv("MOONREDUCE_TEST_FAIL_SPAWN");
  const char *arm = getenv("MOONREDUCE_TEST_FAIL_SPAWN_ARM");
  int result = fault && strcmp(path, fault) == 0 && (!arm || access(arm, F_OK) == 0)
      ? EACCES : real_spawn(pid, path, actions, attr, argv, envp);
  const char *audit = getenv("MOONREDUCE_TEST_SPAWN_LOG");
  if (audit && strcmp(path, "/usr/bin/setsid") == 0) {
    int fd = open(audit, O_WRONLY | O_APPEND | O_CREAT, 0600);
    if (fd >= 0) {
      char line[96];
      int size = snprintf(line, sizeof line, "%d %d\n",
                          result == 0 ? (int)*pid : -1, result);
      if (write(fd, line, (size_t)size) != size) _exit(95);
      close(fd);
    } else {
      _exit(96);
    }
  }
  return result;
}
