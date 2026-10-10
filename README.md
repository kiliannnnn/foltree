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
| **Select Folder…** | scan a folder and show its structure |
| **Format** | switch between formats — your edits are converted, not lost |
| **Max depth** | stop after N levels; deeper content is marked `...` |
| **Show sizes & counts** | file sizes, plus per-folder file counts and totals |
| **Respect .gitignore** | apply the scanned folder's own `.gitignore` on top of your patterns |
| **Ignore patterns** | one per line, gitignore syntax |
| **Copy / Copy for README** | plain, or wrapped in a ```` ``` ```` block ready to paste into Markdown |
| **Save as…** | to `.txt` / `.md` / `.json` / `.yaml` |
| **Create Folders…** | pick a destination, preview exactly what will be made, optionally add a README |

Scan options apply as soon as you change them. If you have edited the text,
nothing is overwritten: the status bar tells you to press `F5` instead, and
`Ctrl+Z` undoes a rescan or a Clear anyway.

While you type or paste, the status bar shows how the text is understood
(*Reads as Tree: 3 folders, 7 files*), so you know before building. The
create dialog's preview marks every folder with a trailing `/`, which is where
a guess about an extensionless name such as `bin` or `LICENSE` would show.

The app remembers your format, options, ignore patterns, theme, window size,
last folder and last destination.

Shortcuts (`⌘` instead of `Ctrl` on macOS): `Ctrl+O` open · `F5` / `Ctrl+R`
rescan · `Ctrl+S` save · `Ctrl+Shift+C` copy · `Ctrl+Enter` create ·
`Ctrl+A` select all · `Ctrl+Z` undo.

Scanning runs on a background thread, so large folders never freeze the
window.

### Paste anything

The text side is built for structures as people actually paste them:

- **A whole chat answer.** Only the first ```` ``` ```` code block is read, so the
  prose around it does not turn into folders.
- **Comments.** `main.py  # entry point`, `utils/ // helpers`, `docs ← here` —
  the comment is dropped (`C#` and `issue#12.md` are kept).
- **Any tree style.** `├──`, `├─`, `|--`, `+---`, guides of any width, the
  output of `tree` (including its footer) and Windows `tree /F` / `tree /A`.
- **Path lists**, one per line, from `find .` or `git ls-files`.
- **Folder emoji** such as `📁 src` mark a folder and are not part of the name.

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

`indented`, `tree`, `ascii`, `markdown`, `json`, `yaml`, `paths` — every one
of them round-trips, so you can scan in one format and build from another.
`build` auto-detects the input format unless you pass `-f`. Short names work
too: `md`, `yml`, `txt`.

```bash
git ls-files | foltree build -o ../skeleton   # an empty copy of a repo's layout
foltree scan . -f paths | grep test            # one path per line, for scripts
```

`build` creates every entry it is given, including names like `.env` or
`build/` that `scan` skips by default; pass `--ignore` to leave some out.
`--readme` writes the README inside the new top folder and never replaces a
README that already has content.

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
│   ├── settings.py  # remembered app preferences
│   └── gui.py       # desktop app
├── packaging/       # standalone app build
├── tests/
├── run.sh
└── run.bat
```

Both directions share one tree model, which is what makes round-tripping
reliable — the old version parsed and rendered text directly.

```bash
python -m unittest discover -s tests -t .
```

Standard library only. The GUI tests skip themselves when no display is
available; to run them headless on Linux use
`xvfb-run python -m unittest discover -s tests -t .`.

### Standalone app

`packaging/build.py` bundles the desktop app with its own Python and Tk, so
whoever downloads it does not need either:

```bash
pip install pyinstaller -r requirements.txt
python packaging/build.py      # -> dist/Foltree-<version>-<platform>.zip / .tar.gz
```

PyInstaller only builds for the platform it runs on. Push a `v*` tag (or run
the **app** workflow by hand) to build Windows, macOS and Linux in CI; each
bundle is opened once as a smoke test and the archives are attached to the run
as artifacts. Drop `icon.ico` / `icon.icns` into `packaging/` to give the app
an icon.

## 🔁 Upgrading from 3.0

- **The editor starts empty.** The example is a hint drawn over it, so there
  is nothing to delete before pasting.
- **"Auto 'output' folder" is gone.** *Create Folders…* asks where to build
  (defaulting to the last place you used) and shows a preview first.
- **`foltree build` no longer applies the default ignore list.** A structure
  that lists `.env` or `vendor/` now gets them; use `--ignore` to skip things.
- **`--readme` writes inside the new top folder**, next to what it describes.
- Folder counts on parsed text no longer claim a size of `0 B`.

## 🔁 Upgrading from v2

A few behaviours changed on purpose:

- **`FoltreeGUI.py` is gone.** Launch with `run.sh` / `run.bat`, `foltree`, or
  `python -m foltree` instead.
- **Ignore patterns are gitignore syntax, not substrings.** `.git` no longer
  also hides `.gitignore`, and `dist` no longer hides `distribution`.
- **"Clean Tree" is now just "Tree".** The old "Tree" format emitted `├──` for
  every entry and mis-nested deep folders; the corrected renderer replaces both.
- **Directories are written with a trailing `/`.** That is what lets an empty
  folder survive a round-trip instead of being rebuilt as a file.
- **Existing files are no longer truncated** when building into a folder that
  already has content. Pass `--overwrite` if you want the old behaviour.

Fixed along the way: the crash when creating folders without the *output*
checkbox ticked (`filedialog` was never imported), the README that described
the scanned folder instead of the structure you typed, ignored folders whose
children were still listed, `LICENSE` and `Dockerfile` being created as
directories, `.github` being created as a file, and structures containing `..`
being able to write outside the output folder.

## 💡 Ideas

- Drag and drop a folder onto the window
- Optional file contents (e.g. `main.py: print("hi")`) when building
- Watch a folder and keep a README section in sync
- Structure diffing (what changed since last scan)
- Templates for common project layouts

## 🤝 Contributing

Issues and enhancement requests welcome.

## 📄 License

MIT.
