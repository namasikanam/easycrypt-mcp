#!/usr/bin/env python3
"""Tests for the EasyCrypt MCP server."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
from easycrypt_mcp import (
    ec_compile, print_goals, ec_search, ec_locate, ec_print, ec_file_outline,
    _repl, _repl_imports,
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


# ---------------------------------------------------------------
# ec_compile
# ---------------------------------------------------------------
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
      ("fails", "FAILED" in r or "ERROR" in r or r.startswith("FAILED")))

# 4. Compile with syntax error
path = write_tmp("lemma foo : .\n")
r = ec_compile(path)
check("compile syntax error", r,
      ("fails", "FAILED" in r))
os.unlink(path)

# ---------------------------------------------------------------
# print_goals
# ---------------------------------------------------------------
print("\n=== print_goals ===")

# 5. Print goals with line and column
path = write_tmp("lemma foo : true /\\ true.\nproof.\n  split.\n  trivial.\n  trivial.\nqed.\n")
eco = os.path.splitext(path)[0] + ".eco"
if os.path.exists(eco):
    os.unlink(eco)
r = print_goals(path, line=3, column=5)
check("print_goals with goals", r,
      ("shows goal", "true" in r.lower()),
      ("no FAILED", "FAILED" not in r))
os.unlink(path)
if os.path.exists(eco):
    os.unlink(eco)

# 6. Print goals past end (proof already done)
path = write_tmp("lemma foo : true = true.\nproof.\n  trivial.\nqed.\n")
eco = os.path.splitext(path)[0] + ".eco"
if os.path.exists(eco):
    os.unlink(eco)
r = print_goals(path, line=4)
check("print_goals past proof", r,
      ("no FAILED", "FAILED" not in r))
os.unlink(path)
if os.path.exists(eco):
    os.unlink(eco)

# 7. Print goals at line 1 (before any command)
path = write_tmp("lemma foo : true = true.\nproof.\n  trivial.\nqed.\n")
eco = os.path.splitext(path)[0] + ".eco"
if os.path.exists(eco):
    os.unlink(eco)
r = print_goals(path, line=1)
check("print_goals line 1", r,
      ("no FAILED", "FAILED" not in r))
os.unlink(path)
if os.path.exists(eco):
    os.unlink(eco)

# 8. Print goals on nonexistent file
r = print_goals("/nonexistent/file.ec", line=1)
check("print_goals nonexistent", r,
      ("fails", "FAILED" in r or "ERROR" in r))

# ---------------------------------------------------------------
# ec_file_outline
# ---------------------------------------------------------------
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
check("outline require", r,
      ("has require", "require" in r and "Int List" in r))
check("outline op", r,
      ("has op double", "op double" in r))
check("outline type", r,
      ("has type color", "type color" in r))
check("outline lemma", r,
      ("has lemma foo", "lemma foo" in r))
check("outline module", r,
      ("has module M", "module M" in r))
check("outline module type", r,
      ("has module type MT", "module type MT" in r))
check("outline theory", r,
      ("has theory T", "theory T" in r))
check("outline pred", r,
      ("has pred is_pos", "pred is_pos" in r))
check("outline axiom", r,
      ("has axiom ax_true", "axiom ax_true" in r))
check("outline clone", r,
      ("has clone Ring", "clone Ring" in r or "clone" in r))
check("outline abbrev", r,
      ("has abbrev dbl", "abbrev dbl" in r))
check("outline section", r,
      ("has section S", "section S" in r))
os.unlink(path)

# 10. Empty file
path = write_tmp("")
r = ec_file_outline(path)
check("outline empty", r,
      ("no declarations", r == "No declarations found."))
os.unlink(path)

# 11. Nonexistent file
r = ec_file_outline("/nonexistent/file.ec")
check("outline nonexistent", r,
      ("error", "ERROR" in r))

# 12. Indented declarations (inside proof/section) should still match
path = write_tmp("  lemma inner : true.\n")
r = ec_file_outline(path)
check("outline indented lemma", r,
      ("matches indented", "lemma inner" in r))
os.unlink(path)

# ---------------------------------------------------------------
# ec_print
# ---------------------------------------------------------------
print("\n=== ec_print ===")

# 13. Print with auto-require
r = ec_print("Int.addz0")
check("print Int.addz0", r,
      ("has lemma", "lemma" in r.lower() or "axiom" in r.lower()),
      ("mentions addz0", "addz0" in r))

# 14. Print builtin (no require needed)
r = ec_print("bool")
check("print bool", r,
      ("has type", "type" in r.lower()),
      ("mentions bool", "bool" in r))

# 15. Print nonexistent
r = ec_print("nonexistent_thing_xyz")
check("print nonexistent", r,
      ("error or not found", "no such object" in r.lower() or "ERROR" in r or "No definition" in r))

# 16. Print with explicit theories
r = ec_print("map", theories=["List"])
check("print List.map via theories", r,
      ("has op", "op" in r.lower()),
      ("mentions map", "map" in r))

# 17. Print deeply qualified name
r = ec_print("IntDiv.edivzP")
check("print IntDiv.edivzP", r,
      ("not error loading", "ERROR loading" not in r))

# ---------------------------------------------------------------
# ec_search
# ---------------------------------------------------------------
print("\n=== ec_search ===")

# 18. Search with theories
r = ec_search("(_ + 0)", theories=["Int"])
check("search (_ + 0)", r,
      ("finds addz0", "addz0" in r))

# 19. Search with no results
r = ec_search("(xyzzy_nonexistent _)")
check("search no results", r,
      ("no results or error", "No results" in r or "ERROR" in r or "error" in r.lower()))

# 20. Search without loading needed theory
r = ec_search("(true)")
check("search basic", r,
      ("no crash", True))

# ---------------------------------------------------------------
# ec_locate
# ---------------------------------------------------------------
print("\n=== ec_locate ===")

# 21. Locate with theories
r = ec_locate("map", theories=["List"])
check("locate map", r,
      ("finds List.map", "List" in r and "map" in r))

# 22. Locate nonexistent
r = ec_locate("xyzzy_nonexistent_name")
check("locate nonexistent", r,
      ("not found", "Could not locate" in r))

# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------
print(f"\n{'='*40}")
print(f"Results: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
