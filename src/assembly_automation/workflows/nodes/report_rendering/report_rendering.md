# Report rendering

This deterministic node validates `report.json` and creates executive and
engineering-detail views from the same content model. The active product format
is self-contained HTML: images are embedded, so each file can be opened or
downloaded independently.

The executive profile contains scorecards, executive conclusions, findings and
recommendations. The engineering profile additionally includes every assembly
step, subprocess assessment, part profile and linked decision. A rendering
manifest records output files, rendered item counts, settings, images used and
missing images.

PDF is intentionally unsupported. The unstable backend and its execution path
were removed, so configuration validation rejects `pdf`. Add PDF again only
after selecting and independently validating a stable product backend.
