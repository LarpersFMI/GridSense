# Historical grid comparison: 54-feature control

These files preserve the original grid process, started before the 50-feature cleanup.
Its variants have 54/59/67 features. Do not compare these scores directly with the
50-feature extras or current grid reports in the parent directory.

The old runner captured the training-table file hash at the end, not the bytes loaded
at startup. That hash can describe the later 50-feature table, so it is **not valid
provenance for the in-memory 54-feature input**. Preserve the metadata as historical
evidence rather than silently replacing its hash or pretending this was a new run.

The parent reports were rerun strictly from cache with a 50-feature control and
55/63-feature grid variants, capturing and verifying the input bytes for that run.
Neither run evaluated the test set or replaced production model artifacts.