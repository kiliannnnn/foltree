# 🌳 Foltree

Turn folders into text, and text back into folders.

- 📝 Document a project's structure for a README
- 🔄 Turn an AI-generated or hand-written structure into real folders and files
- 🎨 Desktop app, plus a CLI for scripts and CI

```
myapp/
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   ├── components/
│   │   └── Button.tsx
│   └── main.ts
├── assets/
├── Dockerfile
└── README.md
```

## 🚀 Quick start

**Windows** — double-click `run.bat`.
**macOS / Linux** — run `./run.sh` (`chmod +x run.sh` once).

The first launch builds a virtual environment and installs the dependencies;
after that it opens straight away. There is nothing to activate and no command
to remember.

Prefer to install it properly?

```bash
pip install -e .
foltree            # opens the app
foltree scan .     # or use the CLI
```

Requires Python 3.9 or newer. On Linux the GUI also needs Tk:
`sudo apt install python3-tk`.

## 🖥️ The app

| | |
|---|---|
| **Select Folder** | scan a folder and show its structure |
| **Format** | switch between formats — your edits are converted, not lost |
| **Max depth** | stop after N levels; deeper content is marked `...` |
| **Show sizes & counts** | file sizes, plus per-folder file counts and totals |
| **Respect .gitignore** | apply the scanned folder's own `.gitignore` on top of your patterns |
| **Mark folders with /** | the trailing slash on directories — see below |
| **Bare names are** | how to read a name with no slash, extension or children |
| **Ignore patterns** | one per line, gitignore syntax |
| **Copy / Save as…** | to the clipboard, or to `.txt` / `.md` / `.json` / `.yaml` |
| **Create Folders** | build whatever is in the editor, after a confirmation showing the counts |

Shortcuts: `Ctrl+O` open · `F5` rescan · `Ctrl+S` save · `Ctrl+Shift+C` copy ·
`Ctrl+Enter` create.

Scanning runs on a background thread, so large folders no longer freeze the
window.

## ⌨️ CLI

```bash
# Print a structure
foltree scan .
foltree scan ~/code/myapp -f markdown -o structure.md
foltree scan . --max-depth 2 --sizes --summary
foltree scan . --gitignore -i "*.log" -i "tmp/"

# Create folders from a structure
foltree build -i structure.txt -o ./scaffold
cat structure.md | foltree build -o ./scaffold
foltree build -i structure.txt -o ./scaffold --dry-run   # preview only
```

`scan` writes to stdout, so it pipes: `foltree scan . | pbcopy`.

### Formats

`indented`, `tree`, `clean`, `ascii`, `markdown`, `json`, `yaml` — every one of
them round-trips, so you can scan in one format and build from another. `build`
auto-detects the input format unless you pass `-f`.

`clean` is `tree` without the vertical guide bars — a lighter look for pasting
into documents. Indentation still encodes depth, so it parses back identically.

```
tree                        clean
────                        ─────
myapp/                      myapp/
├── src/                    ├── src/
│   └── main.ts                 └── main.ts
└── README.md               └── README.md
```

### Telling files from folders

Foltree writes a trailing `/` on directories, which is what lets an empty
folder survive a round-trip — without it, `assets` is indistinguishable from an
extensionless file. Turn it off with `--no-trailing-slash` (or the
**Mark folders with /** switch) if you prefer the plainer look.

When a name arrives with no slash, no extension, no children and no recognised
meaning, `--bare-names` decides how to read it:

```bash
foltree build -i structure.txt -o ./out --bare-names folder   # default
foltree build -i structure.txt -o ./out --bare-names file
```

Stronger evidence always wins over the setting: a trailing `/`, having
children, or a known name like `.github`, `LICENSE` or `Dockerfile` is decided
before it applies. JSON is unaffected either way — it records the type on every
entry, so it is the one format that is always lossless.

### Ignore patterns

Full gitignore syntax: `*.log`, `build/`, `/only-at-root`, `**/tmp`, and `!keep.log`
to re-include. A bare name like `dist` matches a whole path segment, so it no
longer catches `distribution`.

## 🛠️ Development

```
foltree/
├── foltree/
│   ├── node.py      # the shared tree model
│   ├── ignore.py    # gitignore-style matching
│   ├── scanner.py   # filesystem -> tree
│   ├── render.py    # tree -> text
│   ├── parse.py     # text -> tree
│   ├── build.py     # tree -> filesystem
│   ├── cli.py       # command line interface
│   └── gui.py       # desktop app
├── tests/
├── run.sh
└── run.bat
```

Both directions share one tree model, which is what makes round-tripping
reliable — the old version parsed and rendered text directly.

```bash
python -m unittest discover -s tests -t .
```

83 tests, standard library only. The GUI tests skip themselves when no display
is available; CI runs them for real under Xvfb and fails if they report as
skipped, so a broken Tk cannot leave the job silently green.

## 🔁 Upgrading from v2

Everything still works, but a few behaviours changed on purpose:

- **`python FoltreeGUI.py` still runs**, it now forwards to the package.
- **Ignore patterns are gitignore syntax, not substrings.** `.git` no longer
  also hides `.gitignore`, and `dist` no longer hides `distribution`.
- **"Clean Tree" is still there**, as the guide-bar-free style described above.
  The old "Tree" emitted `├──` for every entry and mis-nested deep folders;
  "Tree" is now the corrected renderer.
- **Directories are written with a trailing `/`** by default, which is what
  lets an empty folder survive a round-trip. Turn it off with
  `--no-trailing-slash` if you prefer the old plainer output.
- **Existing files are no longer truncated** when building into a folder that
  already has content. Pass `--overwrite` if you want the old behaviour.

Fixed along the way: the crash when creating folders without the *output*
checkbox ticked (`filedialog` was never imported), the README that described
the scanned folder instead of the structure you typed, ignored folders whose
children were still listed, `LICENSE` and `Dockerfile` being created as
directories, `.github` being created as a file, and structures containing `..`
being able to write outside the output folder.

## 💡 Ideas

- Watch a folder and keep a README section in sync
- Structure diffing (what changed since last scan)
- Templates for common project layouts

## 🤝 Contributing

Issues and enhancement requests welcome.

## 📄 License

MIT.
