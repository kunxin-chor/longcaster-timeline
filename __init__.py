"""LongCaster Timeline: app UI and a narrow external-sampling execution node."""
WEB_DIRECTORY = "./web/extension"
try:
    from .nodes import LongCasterTimelineExecute
    from .timeline_core.configuration import LongCasterTimelineConfiguration, LongCasterTimelineConfigurationSwitch, LongCasterTimelineModelSwitch
    from .timeline_core.routes import register
    NODE_CLASS_MAPPINGS = {"LongCasterTimelineModelSwitch": LongCasterTimelineModelSwitch,"LongCasterTimelineExecute": LongCasterTimelineExecute, "LongCasterTimelineConfiguration": LongCasterTimelineConfiguration, "LongCasterTimelineConfigurationSwitch": LongCasterTimelineConfigurationSwitch}
    NODE_DISPLAY_NAME_MAPPINGS = {"LongCasterTimelineExecute": "LongCaster Timeline — Execution"}
    NODE_DISPLAY_NAME_MAPPINGS.update({"LongCasterTimelineModelSwitch": "LongCaster Timeline - Model Switch","LongCasterTimelineConfiguration": "LongCaster Timeline - Configuration", "LongCasterTimelineConfigurationSwitch": "LongCaster Timeline - Configuration Switch"})
    register()
except ImportError as exc:
    # Source/store tests do not require a ComfyUI/PyTorch environment.
    if exc.name not in ("folder_paths", "server", "aiohttp", "comfy_execution"):
        raise
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
