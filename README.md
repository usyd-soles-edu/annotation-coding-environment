<p align="center">
  <img src="src/ace/static/logo.svg" alt="ACE logo" width="200">
</p>

<p align="center">
  <a href="https://doi.org/10.5281/zenodo.20488468"><img src="https://zenodo.org/badge/1223111193.svg" alt="DOI"></a>
</p>

ACE is an open-source desktop application for collaborative qualitative coding of text. It supports small research teams that need a lightweight way to import sources, build a shared codebook, annotate passages, compare coding patterns, and export data for further analysis.

## Citation

Harianto, J., Van Den Berg, F., Lilje, O., Pang, R., & Widjaja, M. (2026). *Annotation Coding Environment (ACE) for collaborative qualitative coding* (Version 1.4.3) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.20488469

## Features

- Import text from CSV files or folders of text documents.
- Build a grouped codebook for fast keyboard-driven coding.
- Highlight passages and assign one or more codes to each passage.
- Add source-level notes while coding.
- Review coded text, code counts, source maps, and code timelines.
- Compare coding across coders using agreement summaries.
- Export annotations, codebooks, notes, and raw coding data for analysis in R, Python, Excel, or other tools.
- Work locally with `.ace` project files; no cloud storage or user account is required.

## Download

Pre-built installers are on the [Releases page](https://github.com/usyd-soles-edu/annotation-coding-environment/releases/latest), but source installation is also available for people who are comfortable with the command line.

- **macOS (Apple Silicon)**: download `ACE_*_aarch64.dmg`, open it, then drag ACE to Applications. On first launch, right-click and choose Open to bypass Gatekeeper.
- **Windows**: download `ACE_*_x64-setup.exe` and run the installer. If SmartScreen warns you, click "More info" then "Run anyway".

Intel Macs are not currently supported. The macOS and Windows builds are not code-signed yet.

## Install from source

If you are comfortable with the command line, see [Install from source](INSTALL.md). The guide includes Git and `uv` setup for people who do not already have them installed.

## Documentation

The user guide is published with GitHub Pages at <https://usyd-soles-edu.github.io/annotation-coding-environment/>.

## Notes on development

ACE was initially developed without AI assistance. Later development used Claude and GPT-5 to support code auditing, debugging, release preparation, and some user interface design decisions. All code changes were reviewed and tested before release.

## Licence

ACE is released under the MIT License. Use it, modify it, and adapt it for your own research workflow.
