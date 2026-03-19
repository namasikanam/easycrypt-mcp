## Prerequisite

* `easycrypt` with options `-lastgoals` and `-upto`: https://github.com/namasikanam/easycrypt
* Python 3.11+
* [uv](https://docs.astral.sh/uv/getting-started/installation/): a Python package manager

## Installation

Step 1: install this project as a package.
```
uv pip install --system -e .
```

Step 2: add this mcp to Claude Code.
```
# user level (recommended)
claude mcp add -s user easycrypt-mcp uvx easycrypt-mcp

# project level
claude mcp add -s user easycrypt-mcp uvx easycrypt-mcp
```

TODO: VSCode / Cursor / Mistral Vibe

## Tools

The intended way of using this MCP is to write a proof skeleton (lemmas with admitted) in compile mode, and prove each `admit` in the interactive mode one by one.

### Compile Mode

In compile mode, the agent edit EasyCrypt files and compiles through the EasyCrypt files from the command line.

- `ec_compile(file_path, timeout)`: compile a whole file, report success/errors, the last unproven goals will be returned.
- `ec_print_goals(file_path, line, column?, timeout)`: compile up to a position and print proof goals there. If the compilation fails, the last unproven goals should be returned.
- `ec_file_outline(file_path, upto_line?)`: list top-level declarations of an EasyCrypt file, possibly up to a specific line

### Interactive Mode

In interactive mode, the agent opens

- `cli_open(file_path, line)`: open an interactive session at a specific line. If the compilation up to this line fails, the failing line number and the proof goals there should be returned.
- `cli_step(input)`: send a tactic command to proceed on the current goal. If the input tactic can be sucessfully applied, it will be inserted into the file; if the tactic is rejected, it will not be written.
- `cli_undo(line)`: jump back to a given line, the undo-ed steps should be discarded.
- `cli_locate(name)`: find which theory contains this definition
- `cli_print(name)`: print a definition
- `cli_search(pattern)`: search lemmas satisfying a given pattern
- `cli_close()`: close the interactive session

