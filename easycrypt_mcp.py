#!/usr/bin/env python3
"""MCP server for EasyCrypt.

Tools:
  compile    — Compile a file, optionally stopping at a line/column to show goals.
  search     — Search for lemmas by pattern.
  locate     — Locate where a name is defined.
  print      — Print the definition of a name.
  file_outline — List top-level declarations in a file with line numbers.
"""

import os
import re
import subprocess
from typing import Optional

import pexpect
from mcp.server.fastmcp import FastMCP

EC_BIN = os.environ.get(
    "EASYCRYPT_BIN",
    os.path.join(os.path.dirname(__file__), "..", "ec.native"),
)
PROMPT_RE = r"\[(\d+)\|([a-z]+)\]>"

mcp = FastMCP("easycrypt")

# ---------------------------------------------------------------
# Background REPL (lazy-initialized)
# ---------------------------------------------------------------

_repl: Optional[pexpect.spawn] = None
_repl_imports: set[str] = set()


def _ensure_repl() -> pexpect.spawn:
    global _repl
    if _repl is None or not _repl.isalive():
        _repl = pexpect.spawn(
            EC_BIN, ["cli", "-emacs"], encoding="utf-8", timeout=60,
        )
        _repl.setecho(False)
        _repl.expect(PROMPT_RE)
        _repl_imports.clear()
    return _repl


def _repl_send(command: str) -> str:
    repl = _ensure_repl()
    repl.sendline(command)
    repl.expect(PROMPT_RE)
    return repl.before.strip()


def _repl_require(theory: str) -> Optional[str]:
    """Require-import a theory if not already loaded. Returns error or None."""
    if theory in _repl_imports:
        return None
    raw = _repl_send(f"require import {theory}.")
    if "[error-" in raw:
        return f"ERROR loading {theory}: {_parse_repl_output(raw)}"
    _repl_imports.add(theory)
    return None


def _parse_repl_output(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        if line.startswith("[W]"):
            continue
        # Skip standalone marker lines ("+", "|", "*")
        if line.strip() in ("+", "|", "*"):
            continue
        m = re.match(r"\[error-\d+-\d+\](.*)", line)
        if m:
            lines.append(f"ERROR: {m.group(1)}")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


# ---------------------------------------------------------------
# compile
# ---------------------------------------------------------------

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

    # stdout has goal output (from -upto or -lastgoals)
    output = (result.stdout or "").strip()

    # stderr has progress bars, stack traces, and error messages.
    # Error lines look like: [critical] [file: line N ...] message
    # or (with -script): E critical file: line N ...
    errors = []
    for line in (result.stderr or "").splitlines():
        # Non-script format: [critical] or [error] markers
        m = re.match(r"\s*\[(critical|error)\]\s*(.*)", line)
        if m:
            errors.append(f"{m.group(1)}: {m.group(2)}")
            continue
        # -script format
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
    line: Optional[int] = None,
    column: Optional[int] = None,
    timeout: int = 120,
) -> str:
    """Compile an EasyCrypt file.

    Without line/column: compiles the whole file and reports success or errors.
    With line (and optional column): compiles up to that position, then prints
    all open proof goals at that point.

    On failure, shows the error message and the blocking goal state.

    Args:
        file_path: Path to the .ec file
        line: Optional line number to stop at and show goals
        column: Optional column number (requires line)
        timeout: Timeout in seconds (default: 120)
    """
    upto = None
    if line is not None:
        upto = str(line) if column is None else f"{line}:{column}"

    r = _run_compile(file_path, upto=upto, timeout=timeout)

    if r["success"]:
        if r["output"]:
            # -upto prints goals to stdout
            return f"OK\n\n{r['output']}"
        return "OK"

    parts = ["FAILED"]
    if r["errors"]:
        parts.append("\n".join(r["errors"]))
    if r["output"]:
        parts.append(r["output"])
    return "\n\n".join(parts)


# ---------------------------------------------------------------
# search / locate / print  (REPL-backed)
# ---------------------------------------------------------------

def _require_theories(theories: Optional[list[str]]) -> Optional[str]:
    """Require-import a list of theories. Returns first error or None."""
    if not theories:
        return None
    for theory in theories:
        err = _repl_require(theory)
        if err:
            return err
    return None


@mcp.tool()
def ec_search(pattern: str, theories: Optional[list[str]] = None) -> str:
    """Search for lemmas matching a pattern.

    Use _ as a wildcard. Examples: "(_ + 0)", "(_ * (_ + _))".

    Args:
        pattern: Search pattern
        theories: Theories to load first (e.g., ["Int", "List"])
    """
    err = _require_theories(theories)
    if err:
        return err
    raw = _repl_send(f"search {pattern}.")
    return _parse_repl_output(raw) or "No results found."


@mcp.tool()
def ec_locate(name: str, theories: Optional[list[str]] = None) -> str:
    """Locate where a name is defined (which theory/module).

    Args:
        name: Name to locate (e.g., "addzC", "map")
        theories: Theories to load first (e.g., ["Int", "List"])
    """
    err = _require_theories(theories)
    if err:
        return err
    raw = _repl_send(f"locate {name}.")
    return _parse_repl_output(raw) or f"Could not locate '{name}'."


@mcp.tool()
def ec_print(name: str, theories: Optional[list[str]] = None) -> str:
    """Print the definition of a type, operator, lemma, or axiom.

    The theory is auto-loaded from the qualified name (e.g., "Int.addz0"
    auto-requires Int). Additional theories can be passed explicitly.

    Args:
        name: Qualified name (e.g., "Int.addz0", "List.map", "int")
        theories: Extra theories to load first (e.g., ["IntDiv"])
    """
    # Auto-require from qualified prefix
    parts = name.split(".")
    if len(parts) >= 2:
        auto = [parts[0]]
        if theories:
            auto = auto + [t for t in theories if t != parts[0]]
        theories = auto
    err = _require_theories(theories)
    if err:
        return err
    raw = _repl_send(f"print {name}.")
    return _parse_repl_output(raw) or f"No definition found for '{name}'."


# ---------------------------------------------------------------
# file_outline
# ---------------------------------------------------------------

# Top-level keyword patterns that start declarations.
# Each tuple: (regex, label, name-capture-group-index-or-None)
_OUTLINE_PATTERNS = [
    (re.compile(r"^\s*(lemma|axiom|schema)\s+(\w+)"), None, 2),
    (re.compile(r"^\s*(op|pred|abbrev)\s+(\[.*?\]\s+)?(\w+)"), None, 3),
    (re.compile(r"^\s*(type)\s+(\w+)"), None, 2),
    (re.compile(r"^\s*(module)\s+(type\s+)?(\w+)"), "module type" if None else None, 3),
    (re.compile(r"^\s*(theory|section)\s+(\w+)"), None, 2),
    (re.compile(r"^\s*(clone)\s+(?:import\s+|export\s+)?(\S+)"), None, 2),
    (re.compile(r"^\s*(require)\s+(?:import\s+|export\s+)?(.+?)\.?\s*$"), None, 2),
    (re.compile(r"^\s*(realize)\s+(\w+)"), None, 2),
    (re.compile(r"^\s*(instance)\s+(\w+)"), None, 2),
]


@mcp.tool()
def ec_file_outline(file_path: str) -> str:
    """List top-level declarations in an EasyCrypt file with line numbers.

    Returns one line per declaration: "LINE_NUMBER KIND NAME"

    Args:
        file_path: Path to the .ec file
    """
    try:
        with open(file_path) as f:
            lines = f.readlines()
    except OSError as e:
        return f"ERROR: {e}"

    entries = []
    for lineno, line in enumerate(lines, 1):
        # Skip lines inside proofs (indented tactic lines)
        stripped = line.rstrip()
        if not stripped or stripped.startswith("(*"):
            continue

        for pattern, label_override, name_group in _OUTLINE_PATTERNS:
            m = pattern.match(line)
            if m:
                kind = label_override or m.group(1)
                # Detect "module type" specifically
                if kind == "module" and m.group(2) and "type" in m.group(2):
                    kind = "module type"
                name = m.group(name_group)
                entries.append(f"{lineno} {kind} {name}")
                break

    if not entries:
        return "No declarations found."
    return "\n".join(entries)


if __name__ == "__main__":
    mcp.run()
