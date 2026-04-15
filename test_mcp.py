#!/usr/bin/env python3
"""Tests for the EasyCrypt MCP server."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
from easycrypt_mcp import (
    ec_compile, ec_print_goals, ec_file_outline,
    cli_open, cli_step, cli_undo, cli_search, cli_print, cli_locate, cli_close,
)

PASS = 0
FAIL = 0


def check(name: str, result: str, *conditions: tuple[str, bool]):
    global PASS, FAIL
    ok = True
    for desc, cond in conditions:
        if not cond:
            print(f"  FAIL: {name}: {desc}")
            print(f"        got: {result!r}")
            FAIL += 1
            ok = False
    if ok:
        PASS += 1
        print(f"  ok: {name}")


def write_tmp(code: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".ec", delete=False)
    f.write(code)
    f.close()
    return f.name


def clean_eco(path: str):
    eco = os.path.splitext(path)[0] + ".eco"
    if os.path.exists(eco):
        os.unlink(eco)


# ===============================================================
# Compile mode: ec_compile
# ===============================================================
print("\n=== ec_compile ===")

# 1. Successful compilation
path = write_tmp("lemma foo : true = true.\nproof. trivial. qed.\n")
r = ec_compile(path)
check("compile success", r,
      ("starts with OK", r.startswith("OK")),
      ("no FAILED", "FAILED" not in r))
os.unlink(path)

# 2. Failed compilation (incomplete proof)
path = write_tmp("lemma foo : true = false.\nproof.\n  trivial.\nqed.\n")
r = ec_compile(path)
check("compile failure", r,
      ("starts with FAILED", r.startswith("FAILED")),
      ("mentions error", "cannot save" in r or "critical" in r.lower()))
os.unlink(path)

# 3. Compile nonexistent file
r = ec_compile("/nonexistent/file.ec")
check("compile nonexistent", r,
      ("fails", "FAILED" in r or "ERROR" in r))

# 4. Compile with syntax error
path = write_tmp("lemma foo : .\n")
r = ec_compile(path)
check("compile syntax error", r,
      ("fails", "FAILED" in r))
os.unlink(path)


# ===============================================================
# Compile mode: ec_print_goals
# ===============================================================
print("\n=== ec_print_goals ===")

# 5. Goals with line and column
path = write_tmp("lemma foo : true /\\ true.\nproof.\n  split.\n  trivial.\n  trivial.\nqed.\n")
clean_eco(path)
r = ec_print_goals(path, line=3, column=5)
check("ec_print_goals with goals", r,
      ("shows goal", "true" in r.lower()),
      ("no FAILED", "FAILED" not in r))
clean_eco(path)
os.unlink(path)

# 6. Past end (proof already done)
path = write_tmp("lemma foo : true = true.\nproof.\n  trivial.\nqed.\n")
clean_eco(path)
r = ec_print_goals(path, line=4)
check("ec_print_goals past proof", r,
      ("no FAILED", "FAILED" not in r))
clean_eco(path)
os.unlink(path)

# 7. Line 1 (before any command)
path = write_tmp("lemma foo : true = true.\nproof.\n  trivial.\nqed.\n")
clean_eco(path)
r = ec_print_goals(path, line=1)
check("ec_print_goals line 1", r,
      ("no FAILED", "FAILED" not in r))
clean_eco(path)
os.unlink(path)

# 8. Nonexistent file
r = ec_print_goals("/nonexistent/file.ec", line=1)
check("ec_print_goals nonexistent", r,
      ("fails", "FAILED" in r or "ERROR" in r))


# ===============================================================
# Compile mode: ec_file_outline
# ===============================================================
print("\n=== ec_file_outline ===")

# 9. Basic outline
path = write_tmp("""\
require import Int List.

op double (x : int) = x + x.

type color = [Red | Green | Blue].

lemma foo : 1 + 1 = 2.
proof. trivial. qed.

module M = {
  var x : int
  proc f() : int = { x <- 1; return x; }
}.

module type MT = {
  proc g() : int
}.

theory T.
  op id (x : int) = x.
end T.

pred is_pos (x : int) = 0 < x.

axiom ax_true : true.

clone import Ring with type t <- int.

abbrev dbl = double.

section S.
end S.
""")
r = ec_file_outline(path)
check("outline require", r, ("has require", "require" in r and "Int List" in r))
check("outline op", r, ("has op double", "op double" in r))
check("outline type", r, ("has type color", "type color" in r))
check("outline lemma", r, ("has lemma foo", "lemma foo" in r))
check("outline module", r, ("has module M", "module M" in r))
check("outline module type", r, ("has module type MT", "module type MT" in r))
check("outline theory", r, ("has theory T", "theory T" in r))
check("outline pred", r, ("has pred is_pos", "pred is_pos" in r))
check("outline axiom", r, ("has axiom ax_true", "axiom ax_true" in r))
check("outline clone", r, ("has clone Ring", "clone Ring" in r or "clone" in r))
check("outline abbrev", r, ("has abbrev dbl", "abbrev dbl" in r))
check("outline section", r, ("has section S", "section S" in r))
os.unlink(path)

# 10. Empty file
path = write_tmp("")
r = ec_file_outline(path)
check("outline empty", r, ("no declarations", r == "No declarations found."))
os.unlink(path)

# 11. Nonexistent file
r = ec_file_outline("/nonexistent/file.ec")
check("outline nonexistent", r, ("error", "ERROR" in r))

# 12. Indented declarations
path = write_tmp("  lemma inner : true.\n")
r = ec_file_outline(path)
check("outline indented lemma", r, ("matches indented", "lemma inner" in r))
os.unlink(path)

# 12b. Outline with upto_line
path = write_tmp("require import Int.\n\nop foo (x : int) = x.\n\nlemma bar : true.\nproof. trivial. qed.\n")
r = ec_file_outline(path, upto_line=3)
check("outline upto_line=3", r,
      ("has require", "require" in r),
      ("has op foo", "op foo" in r),
      ("no lemma", "lemma" not in r))
r = ec_file_outline(path, upto_line=1)
check("outline upto_line=1", r,
      ("has require", "require" in r),
      ("no op", "op" not in r))
os.unlink(path)


# ===============================================================
# Interactive mode: cli_open
# ===============================================================
print("\n=== cli_open ===")

# 13. Open and see goals after split
path = write_tmp("lemma foo : true /\\ true.\nproof.\n  split.\n  trivial.\n  trivial.\nqed.\n")
r = cli_open(path, line=3)
check("cli_open with goals", r,
      ("has line number", r.startswith("[line ")),
      ("line 3", "[line 3]" in r),
      ("shows goal", "true" in r.lower()),
      ("no ERROR", "ERROR" not in r))
os.unlink(path)

# 14. Open with mid-file error (stops at error line)
path = write_tmp("lemma foo : true /\\ true.\nproof.\n  nonsense_tactic.\n  split.\n")
r = cli_open(path, line=4)
check("cli_open mid-file error", r,
      ("has line number", "[line 3]" in r),
      ("shows error", "<tty>:" in r),
      ("stopped before line 4", "[line 4]" not in r))
os.unlink(path)

# 15. Open nonexistent file
r = cli_open("/nonexistent/file.ec", line=1)
check("cli_open nonexistent", r,
      ("error", "ERROR" in r))


# ===============================================================
# Interactive mode: cli_step
# ===============================================================
print("\n=== cli_step ===")

# 15. Step through a proof and verify file is edited
path = write_tmp("lemma bar : true /\\ true.\nproof.\n")
r = cli_open(path, line=2)
check("cli_step: open", r,
      ("shows goal", "true" in r.lower()))

r = cli_step("  split.")
check("cli_step: split", r,
      ("has line number", r.startswith("[line ")),
      ("line 3", "[line 3]" in r),
      ("shows subgoal", "true" in r.lower()))

r = cli_step("  trivial.")
check("cli_step: trivial 1", r,
      ("line 4", "[line 4]" in r),
      ("progressed", "true" in r.lower() or "No more" in r or "no" in r.lower()))

r = cli_step("  trivial.")
check("cli_step: trivial 2", r,
      ("line 5", "[line 5]" in r),
      ("done", "No more goals" in r or "no" in r.lower() or "added" in r.lower()))

# Verify the file was edited
with open(path) as f:
    content = f.read()
check("cli_step: file edited", content,
      ("has split", "split." in content),
      ("has trivial", "trivial." in content))
os.unlink(path)

# 15b. Rejected step should not modify the file
path = write_tmp("lemma qux : true /\\ true.\nproof.\n")
r = cli_open(path, line=2)
r = cli_step("  nonsense_tactic.")
check("cli_step: rejected not in file", r,
      ("error in output", "<tty>:" in r or "error" in r.lower()))
with open(path) as f:
    content = f.read()
check("cli_step: file unchanged after reject", content,
      ("no nonsense", "nonsense" not in content))
# Valid step should still work after rejection
r = cli_step("  split.")
check("cli_step: works after reject", r,
      ("shows goal", "true" in r.lower()))
with open(path) as f:
    content = f.read()
check("cli_step: file has split after reject", content,
      ("has split", "split." in content))
os.unlink(path)


# ===============================================================
# Interactive mode: cli_undo
# ===============================================================
print("\n=== cli_undo ===")

# 16. Step then undo
path = write_tmp("lemma baz : true /\\ true.\nproof.\n")
r = cli_open(path, line=2)

r = cli_step("  split.")
check("cli_undo: after split", r,
      ("shows subgoal", "true" in r.lower()))

r = cli_step("  trivial.")

# Undo back to after proof (line 2)
r = cli_undo(line=2)
check("cli_undo: back to proof", r,
      ("has line number", "[line " in r),
      ("shows original goal", "true" in r.lower()))

# Verify file was restored (no split/trivial)
with open(path) as f:
    content = f.read()
check("cli_undo: file restored", content,
      ("no split", "split" not in content),
      ("no trivial", "trivial" not in content))
os.unlink(path)

# 16b. Undo to before open line is clamped to open line
path = write_tmp("require import Int.\nlemma baz : true /\\ true.\nproof.\n")
r = cli_open(path, line=3)
r = cli_step("  split.")
r = cli_undo(line=1)  # before open line=3, should clamp to 3
check("cli_undo: clamp to open line", r,
      ("line 3", "[line 3]" in r),
      ("shows original goal", "true" in r.lower()))
# Verify steps were removed
with open(path) as f:
    content = f.read()
check("cli_undo: clamped file restored", content,
      ("no split", "split" not in content))
os.unlink(path)

# 16c. File tail is preserved after step and undo
path = write_tmp("lemma foo : true /\\ true.\nproof.\n  admit.\nqed.\n")
r = cli_open(path, line=2)  # open at "proof.", tail = ["  admit.\n", "qed.\n"]
r = cli_step("  split.")
with open(path) as f:
    content = f.read()
check("cli_step: tail preserved", content,
      ("has admit", "admit" in content),
      ("has qed", "qed" in content),
      ("has split", "split" in content))
r = cli_undo(line=2)
with open(path) as f:
    content = f.read()
check("cli_undo: tail preserved", content,
      ("has admit", "admit" in content),
      ("has qed", "qed" in content),
      ("no split", "split" not in content))
r = cli_step("  split.")
cli_close()
with open(path) as f:
    content = f.read()
check("cli_close: tail preserved", content,
      ("has admit", "admit" in content),
      ("has qed", "qed" in content),
      ("has split", "split" in content))
os.unlink(path)


# ===============================================================
# Interactive mode: cli_search / cli_print / cli_locate
# ===============================================================
print("\n=== cli_search / cli_print / cli_locate ===")

# 17. Open a file that imports Int, then search/print/locate
path = write_tmp("require import Int.\n\nlemma foo : 1 + 0 = 1.\nproof.\n")
r = cli_open(path, line=4)

r = cli_search("(_ + 0)")
check("cli_search", r,
      ("finds addz0", "addz0" in r))

r = cli_print("addz0")
check("cli_print", r,
      ("has lemma", "lemma" in r.lower() or "axiom" in r.lower()))

r = cli_locate("addz0")
check("cli_locate", r,
      ("finds it", "Int" in r or "addz0" in r))
os.unlink(path)

# 18. Search/print/locate without session
r = cli_close()
r = cli_search("(_ + 0)")
check("cli_search no session", r, ("error", "ERROR" in r))
r = cli_print("addz0")
check("cli_print no session", r, ("error", "ERROR" in r))
r = cli_locate("addz0")
check("cli_locate no session", r, ("error", "ERROR" in r))


# ===============================================================
# Interactive mode: cli_close
# ===============================================================
print("\n=== cli_close ===")

# 19. Close an open session
path = write_tmp("lemma foo : true = true.\nproof.\n")
cli_open(path, line=2)
r = cli_close()
check("cli_close open session", r, ("closed", "closed" in r.lower()))
os.unlink(path)

# 20. Close when no session is open
r = cli_close()
check("cli_close no session", r, ("no session", "No open session" in r))

# 21. Other cli tools fail after close
r = cli_step("trivial.")
check("cli_step after close", r, ("error", "ERROR" in r))
r = cli_undo(line=1)
check("cli_undo after close", r, ("error", "ERROR" in r))


# ===============================================================
# Summary
# ===============================================================
print(f"\n{'='*40}")
print(f"Results: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
