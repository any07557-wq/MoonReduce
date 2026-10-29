#!/usr/bin/env python3
"""Package a committed local Git snapshot; never publish or include the worktree."""
import argparse
import copy
import gzip
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOP = {".gitignore", "LICENSE", "README.md", "moon.mod"}
EXTENSIONS = {
    "src": {".mbt", ".pkg", ".md"},
    "examples": {".py", ".c", ".sh", ".md", ".mbt", ".pkg", ".mod", ".work"},
    "scripts": {".py", ".sh"},
    "tests": {".py", ".c", ".sh", ".mbt"},
    "docs": {".md"},
}
REPORT_DOCUMENTS = {"docs/report.schema.json", "docs/report.example.json"}
EXCLUDED_PARTS = {"_build", "target", ".mooncakes", ".repos", ".git", ".agents",
                  ".aws", ".codex", "__pycache__", "results", "logs", "node_modules"}
REQUIRED = {"LICENSE", "README.md", "moon.mod", "src/core/reducer.mbt",
            "src/cmd/moonreduce/main.mbt", "docs/SPEC.md", "docs/STATUS.md",
            "tests/fixtures/reduce_oracle.py", "examples/algorithm/oracle.py",
            "examples/moonbit-consumer/moon.work"}


def include_source(name):
    path = PurePosixPath(name)
    parts = path.parts
    if (path.is_absolute() or not parts or any(part in ("..", ".") for part in parts)
            or any(ord(char) < 32 for char in name)):
        return False
    if any(part in EXCLUDED_PARTS or part.startswith(".env") or
           part.lower() in {"credentials", "secrets", "id_rsa", "id_ed25519", ".netrc"}
           for part in parts):
        return False
    if path.stem.lower() in {"credentials", "secrets"}:
        return False
    if name in TOP or name in REPORT_DOCUMENTS:
        return True
    if len(parts) < 2:
        return False
    return (path.suffix in EXTENSIONS.get(parts[0], set()) or
            (parts[0] == "examples" and path.name == ".gitignore"))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=30).stdout


def snapshot(ref):
    commit = git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    selected = []
    for row in git("ls-tree", "-r", "-z", commit).split(b"\0"):
        if not row:
            continue
        metadata, encoded_name = row.split(b"\t", 1)
        name = encoded_name.decode("utf-8")
        if include_source(name):
            mode, kind, _ = metadata.split()
            if mode not in (b"100644", b"100755") or kind != b"blob":
                raise ValueError(f"source entry must be a regular committed file: {name}")
            selected.append(name)
    missing = REQUIRED - set(selected)
    if missing:
        raise ValueError(f"snapshot lacks required source: {sorted(missing)}")
    return commit, selected


def package(output_dir, ref="HEAD"):
    commit, selected = snapshot(ref)
    prefix = f"moonreduce-source-{commit[:12]}/"
    filename = prefix[:-1] + ".tar.gz"
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / filename
    checksum = output_dir / (filename + ".sha256")
    if os.path.lexists(archive) or os.path.lexists(checksum):
        raise FileExistsError("archive/checksum already exists; choose a new output directory")
    # git archive reads object data, never staged/unstaged files or author _build.
    raw = git("archive", "--format=tar", "--prefix=" + prefix, commit, "--", *selected)
    timestamp = int(git("show", "-s", "--format=%ct", commit))
    with tempfile.TemporaryDirectory(prefix=".moonreduce-source-", dir=output_dir) as directory:
        temporary = Path(directory)
        packed = temporary / filename
        with packed.open("wb") as stream, gzip.GzipFile(
                fileobj=stream, filename="", mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as target:
                with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as source:
                    members = source.getmembers()
                    files = {member.name.removeprefix(prefix)
                             for member in members if member.isfile()}
                    if files != set(selected):
                        raise ValueError("git archive omitted/changed selected files (check .gitattributes)")
                    for member in members:
                        in_root = member.name.startswith(prefix) or (
                            member.isdir() and member.name == prefix.rstrip("/"))
                        if not (member.isdir() or member.isfile()) or not in_root:
                            raise ValueError(f"unexpected archive entry: {member.name}")
                        normalized = copy.copy(member)
                        normalized.uid = normalized.gid = 0
                        normalized.uname = normalized.gname = ""
                        normalized.mtime = timestamp
                        normalized.pax_headers = {}
                        target.addfile(normalized, source.extractfile(member) if member.isfile() else None)
                origin = tarfile.TarInfo(prefix + "SOURCE_COMMIT")
                payload = (commit + "\n").encode("ascii")
                origin.size = len(payload)
                origin.mode = 0o644
                origin.mtime = timestamp
                target.addfile(origin, io.BytesIO(payload))
        digest = hashlib.sha256(packed.read_bytes()).hexdigest()
        sums = temporary / checksum.name
        sums.write_text(f"{digest}  {filename}\n", encoding="ascii")
        # Same-directory hard links publish complete files without replacing an existing path.
        os.link(packed, archive)
        try:
            os.link(sums, checksum)
        except OSError:
            archive.unlink()
            raise
    return archive, checksum, commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--ref", default="HEAD", help="committed ref (default HEAD)")
    args = parser.parse_args()
    try:
        archive, checksum, commit = package(args.output_dir, args.ref)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr.decode(errors="replace"), file=sys.stderr)
        print(f"Source packaging failed: {error}", file=sys.stderr)
        return 1
    print(f"Source commit: {commit}\nArchive: {archive}\nSHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
