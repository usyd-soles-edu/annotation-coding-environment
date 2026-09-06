# README demonstrations

These GIFs record real ACE interactions using fictional student interviews about group assignments and simulated annotations by Alex, Sam and Taylor. Agreement scores are computed from the demonstration project files; they are not research findings.

| File | Workflow | Duration | Size |
| --- | --- | --- | --- |
| ace-coding.gif | Mouse coding, keyboard coding and navigation between sources, text and codebook | 32.66 s | 448 KB |
| ace-review-dictionary.gif | Review codes, filter a source, edit and save a definition | 19.16 s | 355 KB |
| ace-coder-agreement.gif | Compute agreement, inspect per-code guidance and compare coder pairs | 19.62 s | 1.39 MB |

All clips are 1200 × 740, loop, and show shortcuts at bottom centre without caption headings. Frames were captured with Playwright and encoded with Pillow using a shared palette per clip. Mouse movement is shown with a small ring. The native agreement file picker was supplied with demo paths before recording; file preview and agreement calculations use the real application endpoints.

Review and agreement captures completed in Chromium without page errors. Firefox and WebKit checks confirmed the saved definition, matching source/coder context, and expandable agreement guidance. Real Safari painting has not been manually checked.

Local generation material is retained under tmp/readme-demos/ (gitignored). Completed researcher files are separate from the disposable coding and review copies. Reset the disposable copies before repeating captures; preserve the completed researcher files for agreement. The main README references these GIFs with repository-relative paths.

The agreement clip keeps its original sequence and dimensions. Focus is moved off both the selected-files and results headings before every captured frame so their focus outlines are absent; application CSS is unchanged.

The README displays ace-home.png and the three GIFs in a 2×2 grid below Features. The home screenshot is also 1200 × 740. Each image links to its full-size asset.

Captured from ACE 1.7.0. README captions record this capture version and should only be updated when the corresponding media is recaptured. The gallery uses a bordered 2×2 HTML table with plain images and text captions; there are no individual image frames.
