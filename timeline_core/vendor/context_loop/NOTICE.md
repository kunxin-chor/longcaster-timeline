Source: https://github.com/ethanfel/ComfyUI-MiniMaxH3-Context-Loop
Pinned revision: 43afeffcc570beb5f7382593e79e4b211c7e02f6
Copyright (C) 2026 NikoDemon80 and upstream contributors.
License: GPL-3.0 (LICENSE supplied verbatim).

drift_control.py and latent_color_carry.py are from this revision.
Timeline modification: detach model_options if a custom MODEL clone shares its dictionary, preventing mutation of the caller.
contracts_v05.py contains only the two unmodified recipe constants needed by these modules.
The Timeline adapter is timeline_core/drift.py.

Timeline modification to latent_color_carry.py: optional decoded_current keyword reuses the exact decoded prefix already measured for statistics, avoiding a duplicate VAE decode. Color mathematics is unchanged.
