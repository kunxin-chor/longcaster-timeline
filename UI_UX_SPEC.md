# LongCaster Timeline — UI/UX Implementation Specification

**Status:** Approved design direction; adaptable during implementation  
**Target:** `kunxin-chor/longcaster`, `timeline` branch  
**Purpose:** Implementation instructions for Sol  
**Design authority:** Latest user feedback, then the approved mockup and requirements below

> **User clarification — 2026-10-17:** This is an implementation baseline, not an immutable screen contract. The developer may override UI details while implementing and in response to the user's feedback. This clarification takes precedence over clauses below labelled non-negotiable, prohibiting redesign or requiring an exact match. Use implementation judgment without requesting approval for every layout adjustment; record material deviations and their reason so the result is reviewable. Existing data/source immutability and explicit generation behavior remain applicable unless the user changes them.

> **Specification integration:** [ARCHITECTURE.md](ARCHITECTURE.md) governs domain/runtime contracts and [MILESTONES.md](MILESTONES.md) governs delivery. Browsing a source take is distinct from changing the finalized output. A last-frame default applies only after explicit Image-pathway selection and confirmation; it never injects an image into latent continuation. A finalized composite is a splice/output-selection record retaining independent source latents, not a newly merged sampled latent. The target repository/branch and approved mockup named above are implementation references; this documentation update does not claim they were inspected.

## 1. Objective

Build LongCaster Timeline as a professional AI video generation and directing workstation.

The interface should feel like professional creative software, with the visual density and precision of Adobe Premiere Pro, but optimized for **video generation rather than traditional video editing**.

LongCaster's main workflow is:

**Select a finalized segment → Review its selected Take → Prepare the next generation → Generate → Review Takes → Finalize → Continue.**

The user must be able to perform this workflow without navigating between multiple screens.

### Non-negotiable principles

1. The primary workflow fits within one unified workspace.
2. Two preview monitors are always visible side by side in the center.
3. Two prompt editors are always visible directly beneath their respective preview monitors.
4. The left inspector displays the current finalized segment and its frozen settings.
5. The right inspector contains three distinct panels, stacked vertically, not placed side by side.
6. Past Takes are displayed vertically, from top to bottom.
7. Splicing is available only for finalized segments, through the left side.
8. The selected-take splice timeline appears only when the current finalized segment has an active splice composition.
9. All major regions should be resizable, with persistent layout preferences.
10. Do not turn the workspace into a card manager or ComfyUI-style node editor.

Preserve the established LongCaster architecture and milestones.

---

## 2. Overall Screen Layout

Organize the application into three primary columns plus a bottom timeline.

| Region | Purpose | Suggested starting width |
|---|---|---:|
| Left Inspector | Current finalized segment | 19% |
| Center Workspace | Scene header, two previews, two prompts | 59% |
| Right Inspector | Next segment configuration and generation | 22% |

The proportions are initial layout targets, not rigid pixel dimensions.

All three column boundaries should support resizing.

### Center workspace organization

At the top:

**Current Scene Name** — e.g. `Scene 01 — A New Horizon`

A **Settings** button appears beside the scene name to open scene-level settings.

Below the scene header, show project, scene and segment timecodes.

Then organize the center into two equal functional columns.

**Left center column**
- Current Segment Preview
- Current Segment Prompt Editor (read-only)

**Right center column**
- New Generated Preview
- Next Generation Prompt Editor (editable)

Each prompt editor sits directly beneath its corresponding preview.

The primary operation toolbar sits beneath these editors and above the timeline.

### Bottom timeline

A large horizontal timeline spans the workspace below the primary editing region.

It contains scenes and their ordered segments.

Only when the current finalized segment has a splice composition should additional Selected Take rows appear beneath that segment.

### Viewport behavior

At a typical 1920×1080 display, the header, both monitors, both prompt editors, operation toolbar and primary timeline must be visible together.

Avoid page-level vertical scrolling. Use internal scrolling for long reference lists, Take lists, prompt text and inspector content.

The timeline should be vertically resizable.

---

## 3. Left Inspector — Current Segment Settings

### Purpose

The left inspector represents the **currently selected finalized segment**.

Its information must be sourced from that segment's selected immutable Take or finalized composite Take.

It is the historical source, not an editable copy of the next generation's settings.

### Header

Display:

- Current Segment Settings
- Segment identifier
- Frozen / Finalized status

Example:

**Current Segment Settings — Segment 03 — Frozen**

### Section A — Past Takes

Display all saved Takes for the current segment vertically.

Each Take appears as a compact horizontal row containing:

- Thumbnail
- Take number or name
- Duration
- Status
- Selection highlight
- Optional context menu

Example:

**Past Takes**

Take 1 — 8.0s  
Take 2 — 8.0s  
Take 3 — 8.0s

A user selects a Take to inspect or preview.

Selection must not overwrite, remove or modify other Takes.

Clearly distinguish the currently finalized Take from another Take being previewed.

Support shortlisting when M2 Take management is available.

### Section B — Selected Take

Display a small summary of the currently selected Take, including its thumbnail, duration, generation identity and finalized status.

The selected Take controls the left preview and the frozen configuration being inspected.

### Section C — Splicing

**Splicing is accessible only on the left inspector, and only for finalized segments.**

Users must not splice an unfinished next-generation segment.

The inspector may expose a Splice action when a finalized segment has multiple eligible Takes.

When a splice composition exists, display:

- Selected source Takes
- Splice parts and frame ranges
- Edit Splice action
- Finalized composite status

Splicing must be nondestructive and preserve all original Takes.

Do not automatically show a splice section containing empty rows for segments that have never been spliced.

### Section D — Frozen Settings

The left inspector must allow inspection of **all effective settings used for the selected Take**, including:

- References, assets and resolved H3 reference mappings
- LoRAs and their strengths
- Continuation mode and source
- Latent continuation method or image source
- Drift-control method
- Generation duration and resolution
- Steps, seed, sampler and effective sigmas
- Model and relevant generation parameters
- Full effective upstream ComfyUI configuration and version information

These may use collapsible groups within the inspector, but must be accessible without leaving the main workspace.

Use compact read-only summaries when sections are collapsed.

### Regenerate and Unlock

Provide a **Regenerate** action for the selected finalized segment.

Regenerate opens a new editable generation draft on the right, targeting the same segment.

Unlock on the source prompt creates an editable copy for regeneration.

Neither action may change the existing immutable Take.

---

## 4. Center — Dual Preview Monitors

Two independent preview monitors must always appear side by side.

### Left monitor — Current Segment Preview

Shows the selected Take from the finalized current segment.

Features:

- Play / Pause
- Scrubbing and seeking
- Frame stepping
- Current time / duration
- Audio controls
- Fullscreen
- Selected Take indication

If the finalized segment uses a composite/spliced Take, preview the selected finalized composition while retaining access to its underlying source Takes.

### Right monitor — New Generated Window

Shows the currently selected generated Take from the right inspector.

Before generation, display a meaningful empty state such as:

*No generated Take yet. Configure the next segment and select Generate.*

During generation, show status and progress without replacing or hiding the monitor.

After generation, show the resulting video for review.

### Monitor synchronization

Support synchronized playback and scrubbing when appropriate for comparison.

Users should also be able to play either monitor independently.

Where practical, synchronize both monitors to the relevant source/new-generation boundary for visual continuity review.

Do not require synchronization at all times.

---

## 5. Center — Permanently Visible Prompt Editors

Both prompt editors must always remain present directly beneath the monitors.

Do not hide either editor behind inspector tabs, alternate workspaces or a separate prompt-management page.

### Left Prompt Editor — Current Segment

Read-only by default.

Displays the exact effective prompt associated with the selected immutable Take.

Must support all native H3 prompt fields:

- `subject_definitions`
- `summary`
- `retention_analysis`
- `detailed_description`
- `overall_soundscape`
- `non_diegetic_music`

The editor should support field selection, inspecting inherited content, and expanding longer text into a larger editor/viewer.

Do not automatically modify a historical Take's prompt when project or scene prompts change.

### Right Prompt Editor — Next Generation

Fully editable.

Supports the same six native H3 prompt fields.

Uses the previously agreed hierarchy:

**Project base → Scene Inherit/Edit/Disable → Segment append**

Scene `Edit` is a full independent override, not additive text. Segment-level prompt content is additive.

Include:

- Field selector
- Compact editable content area
- Expand editor button
- Prompt draft history
- Save/new/copy draft controls
- Compiled prompt preview
- Reference-token autocomplete

The editor must remain useful within its normal panel size without requiring a modal for every edit.

### Named references

The director should write:

`<hero> walks toward <house>.`

LongCaster's new H3 prompt compiler resolves these tokens to H3-compatible reference labels for generation.

Do not force the user to manually type `<Subject 1>` or `<Picture 1>`.

### Retention Analysis Editor

When `retention_analysis` is the active prompt field, show the specialized structured Retention Analysis Editor within the same prompt-editor region.

Allow the user to choose a named reference, select a relationship/use-case template and edit the resulting retention text.

Use the agreed visual markers:

- `fully_preserved`
- `partially_preserved`
- `attribute_transfer`
- `weak_reference`

Audio-specific markers are handled separately.

Switching to any other prompt field restores the normal editor.

**The main prompt editor remains visible; only the selected field's editing controls change.**

---

## 6. Right Inspector — Next Segment Settings

The right inspector is deliberately divided into **three separate panels stacked from top to bottom**.

Do not arrange these panels horizontally or merge them into one tabbed component.

The three panels are:

1. References & Miscellaneous Settings
2. Takes
3. Generation Settings

Each panel should have its own header and collapsible body.

All three headers should remain easily accessible at normal desktop resolution.

### Panel A — References & Miscellaneous Settings

This panel manages the editable effective configuration of the next generation.

Include:

**References**
- Named references such as `<hero>` or `<house>`
- Inherited project/scene references
- Segment-level additions and overrides
- Reference thumbnails and source types
- Latent-reference strength controls where applicable
- Effective reference status and missing-asset warnings

**LoRAs**
- Inherited project/scene LoRAs
- Segment-level additions, overrides and disables
- Effective strengths
- Relevant activation words

**Other settings**
- Applicable shot/segment metadata
- Additional media input settings
- Other per-segment settings not belonging to continuation or core generation

Keep the organization compact.

The inspector should clearly distinguish inherited values from segment-specific overrides.

Scene-wide references and LoRAs are edited through the scene header's Settings button, not silently changed from the next-segment inspector.

### Panel B — Takes

This is the Take manager for the next generation or regeneration target.

Display generated Takes vertically, using the same compact row design as the left inspector.

Each row contains a thumbnail, Take identifier, duration, generation status and context menu.

Supported actions, according to milestone availability:

- Select a Take for preview
- Inspect its saved settings
- Shortlist
- Regenerate as a new Take
- Finalize selected Take

Place the **Finalize** action within this Take panel.

Finalize is available when a valid generated Take has been selected and can be committed.

The generated Take is immutable. Finalizing it records its timeline selection without removing alternative Takes.

Before any Take exists, show an empty state rather than fake sample Takes.

**Do not place splice creation or editing controls in this panel.** Splicing happens only after the segment is finalized and is accessed from the left inspector.

### Panel C — Generation Settings

This is the principal control panel for generating the next segment.

Use conditional controls based on the selected continuation type.

#### Continuation Type

Provide two primary choices:

**Latent**  
**Image**

These are mutually exclusive continuation pathways.

#### When Latent is selected

Show:

**Latent Continuation Method**

Provide selectable methods based on the strategies actually implemented and supported by the current backend.

The initial M1 baseline is hard-masked latent continuation.

Do not display placeholder algorithms as working methods.

**Drift Control Method**

A separate selector for the available drift-control techniques.

Continuation method and drift-control method must not be confused with one another.

The selected method must be validated against the current generation workflow.

**Motion Context**

Allow selection of applicable context lengths, initially 39, 90 and 141 frames where supported.

Display the corresponding context duration.

**Advanced**

Provide the relevant additional controls, including experimental decode-edge correction only when implemented and validated.

#### When Image is selected

Hide latent-specific controls.

Display:

**Source Image / Frame Selector**

Default: last frame of the selected source segment.

Allow selection of a different eligible frame from the current Take or another explicitly selected source, according to supported image-continuation workflows.

Display a thumbnail and the actual source frame/time.

The user must be able to confirm which image will be used for generation.

Do not silently include the latent-continuation context when the Image pathway is selected.

#### General Generation Settings

Always display applicable controls and effective values, including:

- Requested generation duration
- Resolved frame count
- Resolution
- Frame rate
- Seed
- Steps and other applicable sampling settings
- Effective model/sampler information
- Advanced settings when relevant

Values supplied or controlled externally through ComfyUI should be shown as such. Do not silently override externally supplied `MODEL`, `SAMPLER` or `SIGMAS`.

Do not introduce accelerator-specific modes into this inspector.

#### Generate

Place a prominent **Generate** button at the bottom of this panel.

Generate creates a new immutable Take for review.

It must not automatically finalize the Take.

Display progress and errors in context.

---

## 7. Scene Header and Settings

The scene header appears above the center editing workspace.

Display the current scene name and a **Settings** button.

Scene Settings must support editing applicable scene-wide configuration, including:

- Scene identity/name
- Scene prompt overrides
- Scene references
- Scene LoRAs
- Other scene-level defaults

Preserve project → scene → segment inheritance.

Edits to scene defaults should affect applicable future effective settings but must not mutate historical Take snapshots.

Project management remains accessible through the top-level Project control.

---

## 8. Generation Operations Toolbar

Place the operation toolbar between the prompt editors and the timeline.

Buttons:

| Operation | Action |
|---|---|
| New Scene | Create a new scene |
| Split + Bridge | Split the appropriate existing segment and prepare a connecting generation |
| Extend Scene | Generate a continuation after the selected position |
| Prepend Scene | Generate content before an existing segment |
| Bridge Scene | Prepare generation between two appropriate endpoints |

These are **generation-placement operations**, not conventional video-editor commands.

When the user selects an operation:

1. Resolve the correct source and target positions.
2. Populate the right-side generation workspace.
3. Set appropriate initial continuation settings.
4. Preserve the current finalized source Take.
5. Allow the user to edit the new generation before submitting it.

The target operation must remain visible and identifiable.

Milestone-specific operations should be enabled only when implemented. Do not present nonfunctional buttons as working features.

### Discard Extension

Provide a clearly labeled **Discard Extension** action near the new-generation area.

This removes the pending extension/target from the active working sequence, subject to confirmation for destructive changes.

Do not label destructive deletion as a generic Undo operation.

Never delete or modify the finalized source Take as a side effect.

---

## 9. Primary Scene / Segment Timeline

The timeline is a major part of the workspace, not a decorative strip.

Represent:

**Project → Scene → Segment**

Each scene contains ordered segments.

Display:

- Scene regions/names
- Segment boundaries
- Segment thumbnails
- Segment identifiers
- Relative durations
- Ruler and timecodes
- Playhead
- Selected segment highlight
- Pending generation position
- Generated/finalized state

### Timeline interactions

Support:

- Click to select a segment
- Scrub to a time
- Zoom in/out around cursor
- Horizontal scrolling
- Snap to applicable boundaries
- Context-sensitive operations
- Scene/segment navigation
- Responsive dragging where applicable

The active finalized segment determines the source context displayed on the left.

The pending or selected generation target determines what is shown on the right.

Timeline selection and contextual generation operations must remain synchronized with the central monitors and inspectors.

### Keyboard behavior

Preserve agreed controls:

- `Space`: Play/Pause
- `Left` / `Right`: Frame stepping when not editing text
- `Alt + Plus` / `Alt + Minus`: Timeline zoom
- Appropriate keyboard shortcuts for navigation and selection

Do not trigger timeline shortcuts while the user is typing inside a prompt or another text input.

---

## 10. Conditional Selected Take Splice Timeline

This behavior is important and must not be misinterpreted.

**The Selected Take 1 / Selected Take 2 rows are not permanent timeline tracks.**

They are contextual controls used for a finalized segment that has a splice composition.

### Visibility rules

Show the splice rows only when:

- The current source segment is finalized.
- That segment has a splice composition being inspected or edited.

Otherwise, the primary scene/segment timeline occupies the normal timeline space.

Do not show empty Selected Take rows beneath every segment.

### Position and width

The splice rows must be positioned **directly beneath the selected segment and restricted to that segment's horizontal span**.

They are not full-scene or full-project editing tracks.

The rows move and resize with the selected segment when the timeline zoom or layout changes.

### Splice behavior

Within the selected segment, allow the user to:

- Select two eligible source Takes.
- Choose relevant ranges.
- Adjust splice boundaries.
- Review the resulting composition.
- Finalize a composite Take without overwriting originals.

The composite Take must retain independent source-latent provenance and frame mappings.

Splicing remains a Milestone 2 functionality, but its UI placement and data integration should be designed accordingly.

---

## 11. State and Operation Model

Do not treat the entire screen as one mutable segment editor.

There are two separate contexts.

### Current Segment Context

Represents:

- Selected finalized segment
- Selected immutable Take or composition
- Frozen references, LoRAs, prompts and generation settings
- Source preview
- Splicing when applicable

### Generation Target Context

Represents:

- Active generation operation
- Destination segment or replacement-Take target
- Editable prompt draft
- Editable effective settings
- Generated but not yet finalized Takes
- Selected output preview

### Important transitions

**Extend**

The finalized source remains on the left. The right side prepares a new segment after it.

**Regenerate**

The finalized source remains on the left. The right side prepares a new Take targeting that same segment.

**Generate**

A new immutable Take is created and displayed on the right for review.

**Finalize**

The chosen right-side Take becomes the selected finalized result at its intended timeline position.

**Select another finalized segment**

Update the left inspector, source preview and frozen prompt to reflect that segment.

**Edit splice**

Only available for the selected finalized segment, using the left inspector and its conditional splice rows.

Never accidentally modify source Take data during any transition.

---

## 12. Visual Design Standards

Use a professional, polished dark interface.

### Styling

- Cohesive charcoal/navy surfaces
- Compact typography with clear hierarchy
- Restrained blue accent for active controls and selection
- Consistent spacing and border radii
- Subtle panel separation
- Recognizable but unobtrusive icons
- Clear disabled, loading, selected, frozen and finalized states

Avoid excessive glowing effects, oversized controls, decorative gradients and large unused card padding.

### Density

The application should feel like professional desktop software.

Aim for compact Take rows, efficiently spaced form controls, small section headers and high information density without sacrificing readability.

### Resizing

Users should be able to resize:

- Left inspector width
- Right inspector width
- Timeline height
- Relative preview and prompt workspace heights where practical

Persist layout preferences and support Reset Layout.

Do not permanently hide required prompt editors or either preview monitor as the default behavior.

### Responsiveness

Optimize first for desktop displays.

At narrower widths, preserve the dual-monitor and prompt-editor relationship for as long as practical.

If space becomes insufficient, use sensible internal scrolling or a compact layout rather than silently dropping important controls.

---

## 13. Empty, Loading and Error States

Handle the following conditions explicitly:

**No finalized source selected:** show a useful source-empty state.

**No generated Take yet:** show an empty generated preview and Take list without fabricated results.

**Generation running:** show generation status and progress in the right monitor/Take section.

**Generation failed:** retain editable prompt/settings and display a recoverable error.

**Missing original latent:** disable incompatible latent continuation, explain why, and allow explicit selection of Image continuation.

**Unavailable reference or LoRA:** show actionable validation warnings.

**No splice composition:** hide the splice rows entirely.

**Generation result awaiting Finalize:** distinguish it visually from a finalized segment.

**Discard confirmation:** identify exactly what pending data will be discarded, without affecting the immutable source.

---

## 14. Milestone Alignment

### M1 — Core Generation Timeline

Implement the full basic screen structure:

- Three-column workspace
- Dual previews
- Two persistent prompt editors
- Scene settings
- Frozen current-segment inspector
- Stacked next-segment inspector panels
- Named references and inherited settings
- New H3 prompt compiler
- Retention Analysis Editor
- Latent/Image continuation selection
- Applicable drift-control settings
- Generate and Finalize workflow
- Initial immutable Take handling
- Basic timeline navigation
- Resizable workspace

Only the functionality actually delivered in M1 needs to be interactive. The architecture should accommodate future Take and splice controls.

### M2 — Multiple Takes and Splicing

Activate:

- Multiple Takes per segment
- Shortlisting
- Vertical Take history management
- Finalized-only splicing controls
- Contextual Selected Take splice rows
- Non-destructive composite Takes

### M3 — Split and Prepend

Activate Split + Bridge and Prepend operations, including appropriate continuation boundary selection.

### M4 — New Scene and Bridge Scene

Complete scene creation/placement workflows and cross-scene bridging.

Scene creation and basic scene management remain part of M1; M4 adds the advanced placement and bridging behaviors.

### M5 — Production / Upscaling

Integrate future upscaling and derived media operations without replacing original Take assets.

Do not make the M1 UI dependent on M5 functionality.

---

## 15. Implementation Instructions for Sol

Before making changes:

1. Inspect the current `timeline` branch and its implemented frontend/backend architecture.
2. Review the latest approved mockup and compare it against the current UI.
3. Identify what can be retained and what must be restructured.
4. Preserve the existing Project → Scene → Segment → Shot data architecture and immutable Take requirements.
5. Avoid introducing new UI frameworks or dependencies without a specific reason.

### Implementation priorities

First implement the overall three-column layout, scene header, dual monitors, dual prompt editors, right inspector stacking and timeline positioning.

Then connect the UI to real segment, Take, prompt and generation state.

Then implement the inspector interactions, conditional fields, operation-state transitions and milestone-appropriate controls.

Do not spend time on cosmetic polishing while major panels are incorrectly positioned or interactions are disconnected.

### Visual verification

Test at minimum:

- 1920×1080
- 2560×1440
- 1366×768

Confirm that on desktop:

- The two preview monitors remain side by side.
- Both prompt editors remain visible beneath them.
- The left inspector retains frozen source settings.
- The right inspector has three vertically stacked panels.
- Past Takes are vertical lists.
- The timeline remains usable.
- Selected Take splice rows appear only in the correct finalized-segment context.
- All controls remain accessible when panels resize.

### Functional verification

Test:

- Selecting a finalized segment
- Switching its selected Take
- Inspecting frozen settings
- Creating a new generation draft
- Changing Latent/Image continuation
- Changing latent and drift-control methods
- Selecting an image source
- Editing all six H3 prompt fields
- Editing retention-analysis definitions
- Generating and selecting a Take
- Finalizing a Take
- Regenerating without mutating existing Takes
- Discarding a pending extension
- Hiding/showing conditional splice rows
- Reloading the project with the correct UI and persistent layout state

## 16. Acceptance Criteria

Implementation is acceptable only when:

1. The UI matches the agreed **one-screen, three-column layout**.
2. Two preview windows are simultaneously visible in the center.
3. The source and generation prompt editors are simultaneously visible.
4. The left inspector is dedicated to finalized source settings.
5. The right inspector contains exactly three primary vertically stacked sections: References & Misc, Takes, Generation Settings.
6. Both Past Takes lists use vertical rows, not thumbnail carousels.
7. Latent generation exposes method and drift-control selectors.
8. Image generation exposes its source-frame selector.
9. Generate and Finalize are separate actions.
10. Finalized segment splicing is accessible only from the left.
11. Splice rows appear only for an applicable selected finalized segment and occupy only that segment's horizontal span.
12. Frozen Take snapshots remain immutable.
13. The timeline, previews, prompts and inspectors stay synchronized with selection and generation state.
14. The interface remains compact, resizable and visually cohesive.

**Do not redesign the screen into another interface concept. Implement the approved LongCaster Timeline layout and behavior.**

At completion, provide screenshots of the implemented UI, a summary of changed files, test results and any remaining milestone-gated functionality.
