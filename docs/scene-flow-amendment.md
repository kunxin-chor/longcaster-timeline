# Scene and segment flow amendment - 2026-10-17

This user-feedback amendment takes precedence over earlier first-slice flow descriptions.

- A project starts with Scene 01 containing Segment 01, already selected and editable. Every newly created scene contains its own Segment 01.
- Generate produces the first segment independently. Extend appends a new segment after the finalized tail within that same scene.
- Replace is a separate same-segment operation restricted to the scene tail. A replacement is a new immutable take. Finalizing it changes the segment's active output; previous takes remain available.
- First-segment replacement has no parent continuation source. Later replacement reuses the replaced take's original parent source/context, never that take's own ending.
- Earlier segments are read-only for generation/replacement/finalized-output changes. Enforce this in backend commands and execution preflight, not solely by disabling a button.
- The timeline ruler, clip lane and playhead support continuous pointer-drag scrubbing across segment boundaries. Convert scene time to local preview frames, wait for metadata on file changes, and preserve the pending generation draft.
- Full prompt paste distributes text into the six H3 fields, preserving authored shots, dialogue, reference names and timestamps. The same parser backs a previewable Paste prompt dialog and direct paste in editable textareas. Invalid/duplicate boundaries must not silently discard text.

See [implementation evidence](../IMPLEMENTATION_NOTES.md) for the delivered behavior, tests and remaining native GPU/quality gates.
