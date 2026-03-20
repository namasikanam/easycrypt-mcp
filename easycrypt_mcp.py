#!/usr/bin/env python3
"""MCP server for EasyCrypt.

Two interaction modes, distinguished by tool-name prefix:

  Compile mode (ec_* tools) — stateless, one-shot subprocess calls.
    ec_compile      — Compile a whole file and report success or errors.
    ec_print_goals  — Compile up to a position and print proof goals.
    ec_file_outline — List top-level declarations with line numbers.

  Interactive mode (cli_* tools) — persistent REPL session.
    cli_open    — Open a file and process up to a given line.
    cli_step    — Send a command to the REPL and append it to the file.
    cli_undo    — Jump back to the state at a given line (undo steps).
    cli_search  — Search for lemmas by pattern in the current session.
    cli_print   — Print a definition in the current session.
    cli_locate  — Locate where a name is defined in the current session.
    cli_close   — Close the session and terminate the REPL.
"""

import os
import re
import subprocess
from typing import Optional

import pexpect
from mcp.server.fastmcp import FastMCP

EC_BIN = os.environ.get("EASYCRYPT_BIN", "easycrypt")
PROMPT_RE = r"\[(\d+)\|([a-z]+)\]>"

mcp = FastMCP("easycrypt")


# ---------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------

def _parse_repl_output(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        # Skip banner lines (normal mode: ">> ...", emacs mode: "[W]...")
        if line.startswith(">> ") or line.startswith("[W]"):
            continue
        if line.strip() in ("+", "|", "*"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _parse_sentences(text: str) -> list[tuple[str, int]]:
    """Parse EasyCrypt text into sentences terminated by '.'.

    Returns a list of (sentence, end_line) tuples where end_line is the
    1-based line number of the terminating '.'.
    Handles nested comments (* ... *) and string literals "...".
    """
    sentences: list[tuple[str, int]] = []
    buf: list[str] = []
    i = 0
    n = len(text)
    line = 1
    comment_depth = 0
    in_string = False

    while i < n:
        ch = text[i]

        if ch == "\n":
            line += 1
            buf.append(ch)
            i += 1
            continue

        if in_string:
            buf.append(ch)
            if ch == '"':
                in_string = False
            i += 1
            continue

        if ch == "(" and i + 1 < n and text[i + 1] == "*":
            comment_depth += 1
            buf.append(ch)
            buf.append("*")
            i += 2
            continue

        if ch == "*" and i + 1 < n and text[i + 1] == ")" and comment_depth > 0:
            comment_depth -= 1
            buf.append(ch)
            buf.append(")")
            i += 2
            continue

        if comment_depth > 0:
            buf.append(ch)
            i += 1
            continue

        if ch == '"':
            in_string = True
            buf.append(ch)
            i += 1
            continue

        if ch == ".":
            next_i = i + 1
            if next_i >= n or text[next_i] in (" ", "\t", "\n", "\r", ")"):
                buf.append(ch)
                sentence = "".join(buf).strip()
                if sentence:
                    sentences.append((sentence, line))
                buf = []
                i = next_i
                continue

        buf.append(ch)
        i += 1

    return sentences


# ===============================================================
# Compile mode (ec_* tools) — stateless subprocess calls
# ===============================================================

def _run_compile(
    file_path: str,
    *,
    upto: Optional[str] = None,
    timeout: int = 120,
) -> dict:
    args = [EC_BIN, "compile", "-lastgoals"]
    if upto:
        args += ["-upto", upto]
    args.append(file_path)

    result = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout,
    )

    output = (result.stdout or "").strip()

    errors = []
    for line in (result.stderr or "").splitlines():
        m = re.match(r"\s*\[(critical|error)\]\s*(.*)", line)
        if m:
            errors.append(f"{m.group(1)}: {m.group(2)}")
            continue
        if line.startswith("E critical") or line.startswith("E error"):
            errors.append(line)

    return {
        "success": result.returncode == 0,
        "output": output,
        "errors": errors,
        "exit_code": result.returncode,
    }


@mcp.tool()
def ec_compile(
    file_path: str,
    timeout: int = 120,
) -> str:
    """Compile an EasyCrypt file and report success or errors.

    Args:
        file_path: Path to the .ec file
        timeout: Timeout in seconds (default: 120)
    """
    r = _run_compile(file_path, timeout=timeout)

    if r["success"]:
        return "OK"

    parts = ["FAILED"]
    if r["errors"]:
        parts.append("\n".join(r["errors"]))
    if r["output"]:
        parts.append(r["output"])
    return "\n\n".join(parts)


@mcp.tool()
def ec_print_goals(
    file_path: str,
    line: int,
    column: Optional[int] = None,
    timeout: int = 120,
) -> str:
    """Compile an EasyCrypt file up to a given position and print all open
    proof goals at that point.

    Stateless — every call reprocesses from scratch.

    Args:
        file_path: Path to the .ec file
        line: Line number to stop at
        column: Optional column number for finer positioning
        timeout: Timeout in seconds (default: 120)
    """
    upto = str(line) if column is None else f"{line}:{column}"
    r = _run_compile(file_path, upto=upto, timeout=timeout)

    if r["success"]:
        return r["output"] if r["output"] else "No open goals."

    parts = ["FAILED"]
    if r["errors"]:
        parts.append("\n".join(r["errors"]))
    if r["output"]:
        parts.append(r["output"])
    return "\n\n".join(parts)


@mcp.tool()
def ec_file_outline(file_path: str, upto_line: Optional[int] = None) -> str:
    """List top-level declarations in an EasyCrypt file with line numbers.

    Returns one line per declaration: "LINE_NUMBER KIND NAME"

    Args:
        file_path: Path to the .ec file
        upto_line: Optional line number; only show declarations up to this line
    """
    try:
        with open(file_path) as f:
            lines = f.readlines()
    except OSError as e:
        return f"ERROR: {e}"

    _OUTLINE_PATTERNS = [
        (re.compile(r"^\s*(lemma|axiom|schema)\s+(\w+)"), None, 2),
        (re.compile(r"^\s*(op|pred|abbrev)\s+(\[.*?\]\s+)?(\w+)"), None, 3),
        (re.compile(r"^\s*(type)\s+(\w+)"), None, 2),
        (re.compile(r"^\s*(module)\s+(type\s+)?(\w+)"), None, 3),
        (re.compile(r"^\s*(theory|section)\s+(\w+)"), None, 2),
        (re.compile(r"^\s*(clone)\s+(?:import\s+|export\s+)?(\S+)"), None, 2),
        (re.compile(r"^\s*(require)\s+(?:import\s+|export\s+)?(.+?)\.?\s*$"), None, 2),
        (re.compile(r"^\s*(realize)\s+(\w+)"), None, 2),
        (re.compile(r"^\s*(instance)\s+(\w+)"), None, 2),
    ]

    max_line = upto_line if upto_line is not None else len(lines)

    entries = []
    for lineno, line in enumerate(lines, 1):
        if lineno > max_line:
            break
        stripped = line.rstrip()
        if not stripped or stripped.startswith("(*"):
            continue
        for pattern, label_override, name_group in _OUTLINE_PATTERNS:
            m = pattern.match(line)
            if m:
                kind = label_override or m.group(1)
                if kind == "module" and m.group(2) and "type" in m.group(2):
                    kind = "module type"
                name = m.group(name_group)
                entries.append(f"{lineno} {kind} {name}")
                break

    if not entries:
        return "No declarations found."
    return "\n".join(entries)


# ===============================================================
# Interactive mode (cli_* tools) — persistent REPL session
# ===============================================================

# Session state
_cli_repl: Optional[pexpect.spawn] = None
_cli_path: Optional[str] = None
_cli_lines: list[str] = []       # current file content as lines
_cli_open_line: int = 0          # line passed to cli_open (minimum for undo)
_cli_cursor: int = 0             # 1-based line: last processed line


def _cli_reset() -> None:
    global _cli_repl, _cli_path, _cli_lines, _cli_open_line, _cli_cursor
    if _cli_repl is not None and _cli_repl.isalive():
        _cli_repl.close()
    _cli_repl = None
    _cli_path = None
    _cli_lines = []
    _cli_open_line = 0
    _cli_cursor = 0


def _cli_start_repl() -> pexpect.spawn:
    global _cli_repl
    if _cli_repl is not None and _cli_repl.isalive():
        _cli_repl.close()
    _cli_repl = pexpect.spawn(
        EC_BIN, ["cli"], encoding="utf-8", timeout=120,
    )
    _cli_repl.setecho(False)
    _cli_repl.expect(PROMPT_RE)
    return _cli_repl


def _cli_feed_until(target_line: int) -> tuple[str, int]:
    """Feed sentences parsed from _cli_lines to the REPL up to target_line.

    Returns (raw_output, processed_line).
    """
    global _cli_cursor
    repl = _cli_repl
    assert repl is not None

    content = "".join(_cli_lines)
    sentences = _parse_sentences(content)

    last_output = ""
    processed_line = _cli_cursor

    # Skip sentences already processed (end_line <= _cli_cursor)
    for sentence, end_line in sentences:
        if end_line <= _cli_cursor:
            continue
        if end_line > target_line:
            break
        repl.sendline(sentence)
        repl.expect(PROMPT_RE)
        last_output = repl.before.strip()
        processed_line = end_line
        if "<tty>:" in last_output:
            break

    _cli_cursor = processed_line
    return last_output, processed_line


def _cli_send(command: str) -> str:
    """Send a single command to the REPL.  Returns raw output."""
    repl = _cli_repl
    assert repl is not None
    repl.sendline(command)
    repl.expect(PROMPT_RE)
    return repl.before.strip()


def _cli_write_file() -> None:
    """Write _cli_lines to disk."""
    with open(_cli_path, "w") as f:
        f.writelines(_cli_lines)


def _cli_replay_to(target_line: int) -> tuple[str, int]:
    """Restart REPL and replay up to target_line."""
    global _cli_cursor
    _cli_cursor = 0
    _cli_start_repl()
    return _cli_feed_until(target_line)


@mcp.tool()
def cli_open(
    file_path: str,
    line: int,
) -> str:
    """Open an EasyCrypt file and process it up to a given line.

    Starts a fresh interactive REPL session.  Subsequent cli_step, cli_undo,
    cli_search, cli_print, and cli_locate calls operate in this session.

    Args:
        file_path: Path to the .ec file
        line: Line number to process up to
    """
    file_path = os.path.realpath(file_path)
    _cli_reset()

    global _cli_path, _cli_lines, _cli_open_line

    try:
        with open(file_path) as f:
            _cli_lines = f.readlines()
    except OSError as e:
        return f"ERROR: {e}"

    _cli_path = file_path
    _cli_open_line = line

    _cli_start_repl()
    raw, processed_line = _cli_feed_until(line)
    output = _parse_repl_output(raw) or "No open goals."
    return f"[line {processed_line}] {output}"


@mcp.tool()
def cli_step(
    input: str,
) -> str:
    """Send a command to the interactive REPL and append it to the file.

    The input (e.g., a tactic like "split." or "trivial.") is sent to the
    REPL and inserted into the file after the current position.

    Requires an open session (cli_open).

    Args:
        input: EasyCrypt command to execute (e.g., "split.", "trivial.")
    """
    if _cli_repl is None or not _cli_repl.isalive():
        return "ERROR: no open session.  Call cli_open first."

    global _cli_cursor

    # Send to REPL
    raw = _cli_send(input)

    # If rejected, don't modify the file
    if "<tty>:" in raw:
        output = _parse_repl_output(raw)
        return f"[line {_cli_cursor}] {output}"

    # Insert the text into _cli_lines after _cli_cursor
    text = input if input.endswith("\n") else input + "\n"
    new_lines = text.splitlines(keepends=True)
    insert_at = _cli_cursor  # 0-based index = 1-based line
    for i, nl in enumerate(new_lines):
        _cli_lines.insert(insert_at + i, nl)
    _cli_cursor += len(new_lines)

    _cli_write_file()

    output = _parse_repl_output(raw) or "No open goals."
    return f"[line {_cli_cursor}] {output}"


@mcp.tool()
def cli_undo(
    line: int,
) -> str:
    """Undo interactive steps back to the state at a given line.

    Removes any step-added content after the target line, restarts the
    REPL, and replays up to that line.

    Requires an open session (cli_open).

    Args:
        line: Line number to jump back to
    """
    if _cli_path is None:
        return "ERROR: no open session.  Call cli_open first."

    # Clamp: cannot undo before the line passed to cli_open
    if line < _cli_open_line:
        line = _cli_open_line

    # Truncate _cli_lines to target line and replay
    _cli_lines[:] = _cli_lines[:line]
    _cli_write_file()
    raw, processed_line = _cli_replay_to(line)
    output = _parse_repl_output(raw) or "No open goals."
    return f"[line {processed_line}] {output}"


@mcp.tool()
def cli_search(pattern: str) -> str:
    """Search for lemmas matching a pattern in the current interactive session.

    Uses the file session's REPL, so all theories loaded by the file are
    available.

    Requires an open session (cli_open).

    Args:
        pattern: Search pattern (use _ as wildcard, e.g., "(_ + 0)")
    """
    if _cli_repl is None or not _cli_repl.isalive():
        return "ERROR: no open session.  Call cli_open first."
    raw = _cli_send(f"search {pattern}.")
    return _parse_repl_output(raw) or "No results found."


@mcp.tool()
def cli_print(name: str) -> str:
    """Print the definition of a name in the current interactive session.

    Uses the file session's REPL, so all theories loaded by the file are
    available.

    Requires an open session (cli_open).

    Args:
        name: Name to print (e.g., "addz0", "List.map")
    """
    if _cli_repl is None or not _cli_repl.isalive():
        return "ERROR: no open session.  Call cli_open first."
    raw = _cli_send(f"print {name}.")
    return _parse_repl_output(raw) or f"No definition found for '{name}'."


@mcp.tool()
def cli_locate(name: str) -> str:
    """Locate where a name is defined in the current interactive session.

    Uses the file session's REPL, so all theories loaded by the file are
    available.

    Requires an open session (cli_open).

    Args:
        name: Name to locate (e.g., "addzC", "map")
    """
    if _cli_repl is None or not _cli_repl.isalive():
        return "ERROR: no open session.  Call cli_open first."
    raw = _cli_send(f"locate {name}.")
    return _parse_repl_output(raw) or f"Could not locate '{name}'."


@mcp.tool()
def cli_close() -> str:
    """Close the current interactive session.

    Terminates the REPL process and clears all session state.
    """
    if _cli_repl is None and _cli_path is None:
        return "No open session."
    _cli_reset()
    return "Session closed."


if __name__ == "__main__":
    mcp.run()
