# ACE guide sample: Manchester Folk-Methods

Full import-ready sample derived from the University of Manchester dataset cited below.

## Import options

- CSV import: `sources.csv` contains all 19 interview transcripts.
- Folder import: `sources/` contains the same 19 transcripts as `.txt` files.
- Codebook import: `codebook.csv` is converted from the deposited PDF codebook.

The original codebook has deeper nesting than ACE's import format. To preserve the
full codebook in ACE, the top-level PDF headings are used as ACE folders and nested
codes are named with their path, for example `Design Negative > Steps`.

The transcript file names and CSV source IDs are normalised to `P01` through `P19`
so both import routes produce the same source IDs and a natural sort order.

## Attribution

Derived from:

Fflur, Myfanwy (2026). Identifying "Folk-Methods" Employed With Fitness
Applications By Users With Chronic Mobility Issues To Improve Application Design -
Survey Results, Interview Transcripts and Codebook. University of Manchester.
Dataset. https://doi.org/10.48420/31900453.v1

Original dataset licence: Creative Commons Attribution 4.0 International
(CC BY 4.0).
