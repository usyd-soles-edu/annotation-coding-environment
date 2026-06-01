# Install ACE from source

These instructions are for people who are comfortable using the command line. You need Git and `uv`, a Python package manager. Check whether you already have them before installing anything.

## 1. Check Git

On macOS, Linux, or Windows, run:

```bash
git --version
```

If that prints a version number, Git is already installed.

### macOS

If Git is missing, run:

```bash
xcode-select --install
```

Follow the prompt to install Apple's command line tools, then open a new Terminal window and run `git --version` again.

### Windows

If Git is missing and you have `winget`, run this in PowerShell:

```powershell
winget install --id Git.Git -e --source winget
```

If `winget` is unavailable, install Git for Windows from <https://git-scm.com/download/win>, then open a new PowerShell window and run `git --version` again.

## 2. Check uv

Run:

```bash
uv --version
```

If that prints a version number, `uv` is already installed.

### macOS or Linux

If `uv` is missing, run:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then either open a new Terminal window or run:

```bash
source "$HOME/.local/bin/env"
```

Check it worked with:

```bash
uv --version
```

### Windows

If `uv` is missing, run this in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then open a new PowerShell window and run `uv --version` again.

## 3. Run ACE

Once both `git --version` and `uv --version` work, run:

```bash
git clone https://github.com/januarharianto/annotation-coding-environment.git
cd annotation-coding-environment
uv run ace
```

ACE will open in your web browser.

After the first install, run ACE from the project folder with:

```bash
uv run ace
```
