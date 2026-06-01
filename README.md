# ACE: Annotation Coding Environment
ACE is a small qualitative coding tool for researchers who perform qualitative analysis on **text**. It was built to meet the needs of my own research group, and I am sharing it because I think it may be useful to others.

See it in action below:

**TBD: demo GIF**

Some of the features include:

- Import/export in .csv format for rapid follow-up analysis in R, Python, or Excel
- Local projects with no cloud storage or user accounts
- Keyboard-heavy coding workflow for fast annotation
- Hotkeys for all major functions, including code creation and navigation

## Download

Pre-built installers are on the [Releases page](https://github.com/januarharianto/annotation-coding-environment/releases/latest), but I encourage you to install from source if you are comfortable with the command line.

- **macOS (Apple Silicon)**: download `ACE_*_aarch64.dmg`, open it, then drag ACE to Applications. On first launch, right-click and choose Open to bypass Gatekeeper.
- **Windows**: download `ACE_*_x64-setup.exe` and run the installer. If SmartScreen warns you, click "More info" then "Run anyway".

Intel Macs are not currently supported. The macOS and Windows builds are not code-signed yet.

## Install from source

If you are comfortable with the command line, see [Install from source](INSTALL.md). The guide includes Git and `uv` setup for people who do not already have them installed.

## Notes on development

This project first started without any AI assistance, but I later used Claude to help with code auditing and debugging. Claude was also used to help with some user interface design decisions as I am hopeless at JavaScript (but ok at CSS).

## Citation and licence

ACE is released under the MIT License. Use it, modify it, and adapt it for your own research workflow.
