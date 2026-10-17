"""Named, frozen external sampling configurations; no model imports here."""
from copy import deepcopy
import math

from .store import fingerprint
from .vendor.lenient_switch.lenient_switch_node import SimpleSelectorSwitch

TYPE = "LONGCASTER_CONFIGURATION"
SLOTS = ("A", "B", "C", "D", "E")


def scrub(value, key=""):
    if key.casefold() in ("token", "api_key", "password", "secret", "authorization", "cookie"):
        return "[redacted]"
    if isinstance(value, dict): return {str(k): scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, list): return [scrub(v) for v in value]
    return value


def ancestry(graph, root):
    output = {}; visiting = set()
    def visit(node_id):
        node_id = str(node_id)
        if node_id in visiting: raise ValueError("Configuration contains a dependency cycle.")
        if node_id in output: return
        record = graph.get(node_id)
        if not isinstance(record, dict): raise ValueError(f"Configuration node {node_id} is missing.")
        visiting.add(node_id)
        inputs = record.get("inputs", {})
        if not isinstance(inputs, dict): raise ValueError("Invalid configuration inputs.")
        inputs = deepcopy(inputs)
        if record.get("class_type") == "LongCasterTimelineModelSwitch":
            selected = inputs.get("select")
            if selected not in SLOTS or not isinstance(inputs.get("source_" + selected.lower()), list):
                raise ValueError("Model switch is missing its selected source.")
            for slot in SLOTS:
                if slot != selected: inputs.pop("source_" + slot.lower(), None)
        output[node_id] = {"class_type": record.get("class_type"), "inputs": inputs}
        for value in inputs.values():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) in graph:
                visit(value[0])
        visiting.remove(node_id)
    visit(root)
    return scrub(output)


def descriptor(graph, pack_id, selector_id=None, slot=None):
    pack_id = str(pack_id)
    pack = graph.get(pack_id, {})
    if pack.get("class_type") != "LongCasterTimelineConfiguration":
        raise ValueError("Connect a LongCaster Configuration node to each configuration path.")
    inputs = pack.get("inputs", {})
    name = inputs.get("name", "")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ValueError("Configuration name must contain 1-120 characters.")
    profile = inputs.get("profile")
    if profile not in ("ref2va", "fl2va"): raise ValueError("Invalid configuration mode.")
    for field in ("model", "sampler", "sigmas"):
        link = inputs.get(field)
        if not isinstance(link, list) or len(link) != 2 or str(link[0]) not in graph:
            raise ValueError(f"Connect {field.upper()} for configuration {name}.")
    upstream = ancestry(graph, pack_id)
    for record in upstream.values():
        if record.get("class_type") == "LongCasterTimelineModelSwitch" and record["inputs"].get("profile") != profile:
            raise ValueError("Model switch profile is incompatible with the generation configuration.")
    switch_values = {key:record["inputs"]["select"] for key,record in upstream.items() if record.get("class_type") == "LongCasterTimelineModelSwitch"}
    return {**({"switch_values": switch_values} if switch_values else {}), "id": pack_id, "name": name.strip(), "profile": profile,
            "selector_id": str(selector_id) if selector_id is not None else None,
            "slot": slot, "upstream": upstream, "upstream_sha256": fingerprint(upstream)}


def freeze_configuration(value):
    if value is None: return None
    if not isinstance(value, dict): raise ValueError("Invalid generation configuration.")
    graph = value.get("upstream")
    if not isinstance(graph, dict) or len(graph) > 2000: raise ValueError("Invalid configuration graph.")
    selector = value.get("selector_id"); slot = value.get("slot")
    if (selector is None) != (slot is None) or (slot is not None and slot not in SLOTS):
        raise ValueError("Invalid configuration selector.")
    result = descriptor(graph, value.get("id", ""), selector, slot)
    if result.get("switch_values", {}) != value.get("switch_values", {}):
        raise ValueError("Frozen model switch selections do not match the configuration.")
    for field in ("name", "profile"):
        if result[field] != value.get(field): raise ValueError("Configuration definition changed; select it again.")
    return result


def configuration_difference(queued, executed, path="configuration"):
    """Compare settings after ComfyUI's in-place INT/FLOAT validation casts.

    JSON serializes 12 and 12.0 differently, but those are the same numeric
    setting. Booleans remain a distinct category: True must not equal 1.
    Stored provenance hashes keep their original, immutable representation.
    """
    if isinstance(queued, bool) or isinstance(executed, bool):
        return None if type(queued) is type(executed) and queued == executed else path
    if isinstance(queued, (int, float)) and isinstance(executed, (int, float)):
        # No tolerance: a genuinely different float must still fail validation.
        return None if math.isfinite(queued) and math.isfinite(executed) and queued == executed else path
    if type(queued) is not type(executed): return path
    if isinstance(queued, dict):
        if queued.keys() != executed.keys(): return path + ".keys"
        for key in queued:
            difference = configuration_difference(queued[key], executed[key], f"{path}.{key}")
            if difference: return difference
        return None
    if isinstance(queued, list):
        if len(queued) != len(executed): return path + ".length"
        for index, (before, after) in enumerate(zip(queued, executed)):
            difference = configuration_difference(before, after, f"{path}[{index}]")
            if difference: return difference
        return None
    return None if queued == executed else path


def verify_configuration(expected, actual, graph, execution_id):
    if expected is None:
        if actual is not None: raise ValueError("This job was queued for direct inputs, not a configuration.")
        return
    if not isinstance(actual, dict): raise ValueError("The queued generation configuration is not connected.")
    execution = graph.get(str(execution_id), {}).get("inputs", {})
    selector_id = expected["selector_id"]
    root_id = selector_id if selector_id is not None else expected["id"]
    if execution.get("configuration") != [root_id, 0]:
        raise ValueError("Execution configuration connection changed after queueing.")
    if selector_id is not None:
        selector = graph.get(selector_id, {})
        inputs = selector.get("inputs", {})
        if (selector.get("class_type") != "LongCasterTimelineConfigurationSwitch" or
            inputs.get("select") != expected["slot"] or
            inputs.get("source_"+expected["slot"].lower()) != [expected["id"], 0]):
            raise ValueError("Configuration selector changed after queueing.")
    current = descriptor(graph, expected["id"], selector_id, expected["slot"])
    if expected.get("upstream_sha256") != fingerprint(expected["upstream"]):
        raise ValueError("Frozen upstream configuration fingerprint is invalid.")
    # The raw current hash can differ solely because FLOAT 12 became 12.0.
    fields = ("id", "name", "profile", "selector_id", "slot", "upstream")
    difference = configuration_difference({k:expected[k] for k in fields}, {k:current[k] for k in fields})
    if not difference:
        difference = configuration_difference({k:expected[k] for k in fields if k != "upstream"},
            {k:actual.get(k) for k in fields if k != "upstream"}, "resolved_configuration")
    if difference:
        raise ValueError(f"Upstream configuration differs at {difference} after queueing. Generate a fresh take.")


class LongCasterTimelineConfiguration:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"name": ("STRING", {"default": "REF2VA baseline"}),
            "profile": (["ref2va", "fl2va"],), "model": ("MODEL",),
            "sampler": ("SAMPLER",), "sigmas": ("SIGMAS",)}, "hidden": {"unique_id": "UNIQUE_ID"}}
    RETURN_TYPES = (TYPE,)
    RETURN_NAMES = ("configuration",)
    FUNCTION = "pack"
    CATEGORY = "LongCaster Timeline"

    def pack(self, name, profile, model, sampler, sigmas, unique_id):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError("Give this configuration a name of 1-120 characters.")
        return ({"model": model, "sampler": sampler, "sigmas": sigmas,
                 "metadata": {"id": str(unique_id), "name": name.strip(), "profile": profile,
                              "selector_id": None, "slot": None}},)


class LongCasterTimelineConfigurationSwitch(SimpleSelectorSwitch):
    """Typed adapter around the bundled MIT SimpleSelectorSwitch lazy router."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"select": (list(SLOTS), {"default": "A", "tooltip": "Timeline overrides this per queued job."})},
            "optional": {"source_"+slot.lower(): (TYPE, {"lazy": True}) for slot in SLOTS},
            "hidden": {"unique_id": "UNIQUE_ID"}}
    RETURN_TYPES = (TYPE,)
    RETURN_NAMES = ("configuration",)
    CATEGORY = "LongCaster Timeline"

    def check_lazy_status(self, select, unique_id=None, **kwargs):
        return super().check_lazy_status(select, False, True, **kwargs)

    def run(self, select, unique_id=None, **kwargs):
        result = super().run(select, False, True, **kwargs)[0]
        if result is None: raise ValueError(f"Configuration slot {select} is not connected.")
        return ({**result, "metadata": {**result["metadata"], "selector_id": str(unique_id), "slot": select}},)


class LongCasterTimelineModelSwitch:
    """Named lazy MODEL selector. Sampling configuration stays downstream."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"select": (list(SLOTS), {"default": "A"}),
            "name": ("STRING", {"default": "Model source"}),
            "profile": (["ref2va", "fl2va"],),
            **{"label_"+slot.lower(): ("STRING", {"default": "Source "+slot}) for slot in SLOTS}},
            "optional": {"source_"+slot.lower(): ("MODEL", {"lazy": True}) for slot in SLOTS}}
    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "run"
    CATEGORY = "LongCaster Timeline"

    def check_lazy_status(self, select, **kwargs):
        key = "source_" + str(select).lower()
        return [key] if select in SLOTS and kwargs.get(key) is None else []

    def run(self, select, name, profile, **kwargs):
        key = "source_" + str(select).lower()
        if select not in SLOTS or kwargs.get(key) is None:
            raise ValueError(f"Model switch {name}: slot {select} is not connected.")
        return (kwargs[key],)
