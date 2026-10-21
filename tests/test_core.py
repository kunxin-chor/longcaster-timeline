import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import ModuleType, SimpleNamespace

from timeline_core.compiler import compile_prompt, effective_references
from timeline_core.store import Store, Conflict, atomic_json, digest, duration, fingerprint, uid
from timeline_core.engine import mh3_api, model_checkpoint_names, sanitized
from timeline_core.store import PIN


def reference(name, scope="project", owner=None, role="subject", **kwargs):
    return dict(id=uid(), token_name=name, display_name=name, scope=scope, owner_id=owner,
                role=role, kind="image", enabled=True, asset_path="assets/test.png", asset_sha256="abc", **kwargs)


class CompilerTests(unittest.TestCase):
    def dependency_modules(self):
        package = ModuleType("test_extension.mmh3_media")
        package.__file__ = str(Path(__file__).resolve().parent / "fake_mh3" / "mmh3_media" / "__init__.py")
        def never_execute(*args, **kwargs):
            raise AssertionError("Capability preflight must not execute dependency functions")
        package.build_h3_continuation_handover = never_execute
        api = ModuleType(package.__name__ + ".public_api"); api.MMH3_ADAPTER_API_VERSION = 1
        archive = ModuleType(package.__name__ + ".archive")
        contract = ModuleType(package.__name__ + ".h3_contract"); contract.H3_LATENT_CONTRACT_VERSION = 2
        class Media:
            create = staticmethod(never_execute)
            get_primary = never_execute
            set_extension_value = never_execute
        api.MMH3Media = Media
        for name in ("pack_h3_result", "validate_generation_model_family", "build_h3_continuation_handover"):
            setattr(api, name, never_execute)
        for name in ("load_archive", "save_archive", "get_resource_payload"): setattr(archive, name, never_execute)
        for name in ("h3_latent_contract_from_resource", "validate_h3_continuation_compatibility"): setattr(contract, name, never_execute)
        return package, api, archive, contract

    def test_api_facade_uses_actual_module_boundaries_and_records_revision(self):
        package,api,archive,contract=self.dependency_modules()
        modules = {module.__name__: module for module in (package, api, archive, contract)}
        for revision in (PIN,"386980fc2dfddfebcf77cec43782eca2f351e4ae","a"*40):
            with self.subTest(revision=revision),patch.dict("sys.modules", modules), patch("timeline_core.engine.subprocess.run", return_value=SimpleNamespace(stdout=revision,returncode=0)):
                facade = mh3_api()
                self.assertIs(facade.load_archive, archive.load_archive)
                self.assertIs(facade.h3_latent_contract_from_resource, contract.h3_latent_contract_from_resource)
                self.assertFalse(hasattr(api, "load_archive"))
                self.assertEqual(facade.longcaster_dependency["git_revision"],revision)
                self.assertEqual(facade.longcaster_dependency["reviewed_revision"],PIN)

    def test_zip_install_without_git_still_checks_required_api(self):
        modules={module.__name__:module for module in self.dependency_modules()}
        with patch.dict("sys.modules",modules),patch("timeline_core.engine.subprocess.run",side_effect=FileNotFoundError("git")):
            facade=mh3_api()
            self.assertIsNone(facade.longcaster_dependency["git_revision"])
            self.assertEqual(facade.longcaster_dependency["validation"],"required_signatures_checked")

    def test_incompatible_api_version_and_missing_exports_are_rejected(self):
        package,api,archive,contract=self.dependency_modules()
        modules={module.__name__:module for module in (package,api,archive,contract)}
        with patch.dict("sys.modules",modules),patch("timeline_core.engine.subprocess.run",return_value=SimpleNamespace(stdout=PIN,returncode=0)):
            contract.H3_LATENT_CONTRACT_VERSION=3
            with self.assertRaisesRegex(RuntimeError,"detected API 1, latent contract 3"):mh3_api()
            contract.H3_LATENT_CONTRACT_VERSION=2
            api.MMH3_ADAPTER_API_VERSION=2
            with self.assertRaisesRegex(RuntimeError,"detected API 2"):mh3_api()
            api.MMH3_ADAPTER_API_VERSION=1
            del archive.save_archive
            with self.assertRaisesRegex(RuntimeError,"save_archive is missing"):mh3_api()

    def test_incompatible_continuation_signature_is_rejected_before_execution(self):
        package,api,archive,contract=self.dependency_modules()
        def old_handover(source,*,source_origin,target_frames,video_handover_frames):
            raise AssertionError("Should never execute")
        api.build_h3_continuation_handover=old_handover
        modules={module.__name__:module for module in (package,api,archive,contract)}
        with patch.dict("sys.modules",modules),patch("timeline_core.engine.subprocess.run",return_value=SimpleNamespace(stdout=PIN,returncode=0)):
            with self.assertRaisesRegex(RuntimeError,"build_h3_continuation_handover"):
                mh3_api()

    def test_checkpoint_family_is_taken_from_model_branch(self):
        graph = {"1":{"class_type":"LongCasterTimelineExecute", "inputs":{"model":["2",0],"clip":["3",0]}},
            "2":{"inputs":{"model":["4",0]}}, "3":{"inputs":{"model_name":"text-ref2va.safetensors"}},
            "4":{"inputs":{"unet_name":"video-fl2va.safetensors"}}}
        self.assertEqual(model_checkpoint_names(graph), ["video-fl2va.safetensors"])
        self.assertEqual(sanitized({"api_key":"private","sampler":"euler"}), {"api_key":"[redacted]","sampler":"euler"})

    def test_subject_and_picture_indices_are_independent(self):
        result = compile_prompt({"subject_definitions": "<Subject 1> is the traveller in <picture.hero>.", "detailed_description": "<Subject 1> in <picture.coast>",
            "retention_analysis": "<picture.coast>: preserve setting"}, [reference("coast", role="picture"), reference("hero")])
        self.assertEqual(result["resolved_fields"]["detailed_description"], "<Subject 1> in <Picture 1>")
        self.assertIn("<Picture 2>", result["resolved_fields"]["subject_definitions"])
        self.assertEqual(result["resolved_fields"]["retention_analysis"], "<Picture 1>: preserve setting")
        self.assertEqual(result["images"][1]["native_label"], "<Picture 2>")

    def test_scope_override_is_explicit_and_does_not_mutate_parent(self):
        parent = reference("hero")
        override = reference("hero", "scene", "s", overrides=parent["id"])
        disabled = reference("hero", "segment", "g", overrides=parent["id"]); disabled["enabled"] = False
        refs = [parent, override, disabled, reference("light", "segment", "other", role="picture")]
        resolved = effective_references(refs, "s", "g")
        self.assertEqual(len(resolved), 1)
        self.assertFalse(resolved[0]["enabled"])
        self.assertTrue(parent["enabled"])
        self.assertEqual(effective_references(refs, "s", "other")[0]["id"], override["id"])
        with self.assertRaisesRegex(ValueError, "disabled"):
            compile_prompt({"summary": "<picture.hero>"}, resolved)

    def test_missing_ambiguous_and_invalid_names_fail_before_encoding(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            compile_prompt({"summary": "<missing>"}, [])
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            compile_prompt({}, [reference("hero"), reference("Hero")])
        with self.assertRaisesRegex(ValueError, "non-reserved"):
            compile_prompt({}, [reference("summary")])
        with self.assertRaisesRegex(ValueError, "no supplied"):
            compile_prompt({"summary": "<Picture 2>"}, [reference("hero")])

    def test_authored_times_and_dialogue_are_unchanged(self):
        text = '[Shot 1] At 00:00.000 <Subject 1> says <d>[Chinese] 我不知道！</d>'
        result = compile_prompt({"subject_definitions":"<Subject 1> is a person.","detailed_description": text}, [reference("hero")])
        self.assertEqual(result["authored_fields"]["detailed_description"], text)
        self.assertEqual(result["resolved_fields"]["detailed_description"], text)


class StoreTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / ".test-tmp"
        temporary_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        state = Store.create(self.temp.name, "Test")
        self.store = Store(self.temp.name, state["id"])
        self.scene = state["scenes"][0]["id"]
        with self.store.locked():
            state = self.store._read(); state["references"] = [reference("hero")]; self.store._commit(state)
        self.settings = dict(scene_id=self.scene, profile="ref2va", mode="new", width=768, height=448,
            seconds=5, seed=3, fields={"subject_definitions":"<Subject 1> is the person in <picture.hero>.","detailed_description": "[Shot 1] <Subject 1> walks."})

    def tearDown(self):
        self.temp.cleanup()

    def command(self, action, **payload):
        return self.store.command(self.store.load()["revision"], action, payload)

    def queue(self, **updates):
        return self.store.queue(self.store.load()["revision"], {**self.settings, **updates})

    def finish(self, job):
        self.store.claim(job["id"])
        take_id = uid(); path = self.store.asset(f"takes/{take_id}/original.mmh3")
        path.parent.mkdir(parents=True); path.write_bytes(b"fake archive: persistence test only " + take_id.encode())
        take = self.store.complete(job["id"], dict(take_id=take_id, latent_path=str(path.relative_to(self.store.path)),
            latent_sha256=digest(path), latent_resource_id=uid()), {"test_only": True})
        self.store.stage(job["id"],"complete")
        return take

    def ready_preview(self, take):
        relative=f"takes/{take['id']}/preview.mp4"
        self.store.asset(relative).write_bytes(b"fake preview for persistence tests")
        atomic_json(self.store.asset(f"takes/{take['id']}/preview.json"), {"status":"ready", "source_sha256":take["latent_sha256"],"path":relative})

    def test_duration_native_grid_and_hidden_delivery_context(self):
        for c in (0, 39, 90, 141):
            plan = duration(5, c)
            self.assertEqual((plan["sampled_frames"]-5)%17, 0)
            self.assertEqual(plan["new_frames"], plan["sampled_frames"]-c)
            self.assertEqual(plan["delivery"]["start"], c)
        with self.assertRaises(ValueError): duration(15, 141)
        with self.assertRaises(ValueError): duration(float("nan"))

    def test_queue_freezes_reference_order_prompt_and_source(self):
        _, job = self.queue(); take = self.finish(job); self.ready_preview(take); self.command("finalize", take_id=take["id"])
        state, extension = self.queue(mode="extend", source_take_id=take["id"], context=39)
        self.assertEqual(extension["snapshot"]["source"]["id"], take["id"])
        self.assertEqual(extension["snapshot"]["source"]["latent_sha256"], take["latent_sha256"])
        self.assertEqual(extension["snapshot"]["plan"]["context_frames"], 39)
        self.assertFalse(extension["snapshot"]["auto_frame"])
        self.assertEqual(extension["snapshot"]["prompt_timing"], "authored")
        original = copy.deepcopy(extension["snapshot"])
        self.command("reference", reference_id=state["references"][0]["id"], token_name="new_hero")
        self.assertEqual(self.store.load()["jobs"][extension["id"]]["snapshot"], original)

    def test_decode_edge_policy_is_frozen_without_changing_masks_or_prompt_clock(self):
        _, job = self.queue(decode_edge_frames=4)
        self.assertEqual(job["snapshot"]["decode_edge"]["frames"], 0)
        take = self.finish(job); self.ready_preview(take); self.command("finalize", take_id=take["id"])
        with self.assertRaisesRegex(ValueError, "Decode-edge frames"):
            self.queue(mode="extend", source_take_id=take["id"], context=39, decode_edge_frames=True)
        _, extension = self.queue(mode="extend", source_take_id=take["id"], context=39, decode_edge_frames=4)
        snap = extension["snapshot"]
        self.assertEqual(snap["decode_edge"]["frames"], 4)
        self.assertEqual(snap["plan"]["mask_profile"], "hard_av_v1")
        self.assertEqual(snap["prompt_timing"], "authored")
        self.assertEqual(snap["plan"]["new_frames"], snap["plan"]["sampled_frames"] - 39)
        self.assertEqual(self.store.load()["jobs"][extension["id"]]["snapshot"], snap)

    def test_acceptance_report_does_not_claim_legacy_takes_have_runtime_evidence(self):
        from timeline_core.acceptance import report
        _, job = self.queue(); take = self.finish(job)
        self.ready_preview(take); self.command("finalize", take_id=take["id"])
        _, extension = self.queue(mode="extend", source_take_id=take["id"], context=39)
        child = self.finish(extension)
        evidence = report(self.store)
        self.assertEqual(evidence["summary"], {"takes":2,"continuations":1,"verified_contexts":0,"measured_seams":0})
        self.assertIsNone(evidence["takes"][1]["context_check"])
        self.assertEqual(evidence["finalized_timeline"][0]["video_frame_range"], [0,124])
        self.assertEqual(evidence["finalized_timeline"][0]["planned_review_pcm_range_48000"], [0,248000])
        self.assertEqual(evidence["takes"][1]["source_sha256"], take["latent_sha256"])

    def test_failed_context_evidence_retains_take_for_review_but_blocks_finalization(self):
        _, job = self.queue(); take = self.finish(job); self.ready_preview(take)
        with self.store.locked():
            state = self.store._read()
            state["takes"][take["id"]]["receipt"]["continuation_check"] = {"passed":False}
            self.store._commit(state)
        with self.assertRaisesRegex(ValueError, "saved for review"):
            self.command("finalize", take_id=take["id"])
        self.assertTrue(self.store.asset(take["latent_path"]).is_file())
        self.assertEqual(self.store.preview(take["id"])["status"], "ready")
        self.assertIsNone(self.store.load()["scenes"][0]["segments"][0]["active_output"])

    def test_source_must_be_explicit_finalized_take_and_geometry_matches(self):
        _, first = self.queue(); a = self.finish(first)
        _, second = self.queue(segment_id=a["segment_id"]); b = self.finish(second)
        self.ready_preview(a); self.command("finalize", take_id=a["id"])
        with self.assertRaisesRegex(ValueError, "explicitly finalized"):
            self.queue(mode="extend", source_take_id=b["id"])
        with self.assertRaisesRegex(ValueError, "project resolution"):
            self.queue(mode="extend", source_take_id=a["id"], width=800)
        _, extension = self.queue(mode="extend", source_take_id=a["id"])
        self.assertEqual(extension["snapshot"]["source"]["id"], a["id"])

    def image_source(self):
        _, job = self.queue(); take = self.finish(job); self.ready_preview(take)
        self.command("finalize", take_id=take["id"])
        with self.store.locked():
            state=self.store._read();state["references"]=[];self.store._commit(state)
        return take

    def test_image_restart_crosses_profile_without_motion_overlap_and_regenerates_from_original_parent(self):
        parent=self.image_source()
        settings=dict(mode="extend",profile="fl2va",continuation_method="last_frame",source_take_id=parent["id"],
                      fields={"detailed_description":"[Shot 1] A person continues walking."},context=141)
        _,job=self.queue(**settings);snapshot=job["snapshot"]
        self.assertEqual(snapshot["continuation_method"],"last_frame")
        self.assertEqual(snapshot["source"]["id"],parent["id"])
        self.assertEqual(snapshot["plan"]["context_frames"],0)
        self.assertEqual(snapshot["plan"]["delivery"],{"start":0,"end":124})
        self.assertEqual(snapshot["plan"]["mask_profile"],"first_frame_keyframe_v1")
        child=self.finish(job);self.ready_preview(child);self.command("finalize",take_id=child["id"])
        _,replacement=self.queue(**{**settings,"mode":"regenerate","segment_id":child["segment_id"],"source_take_id":child["id"]})
        self.assertEqual(replacement["snapshot"]["source"]["id"],parent["id"])
        self.assertEqual(replacement["snapshot"]["plan"]["context_frames"],0)

    def test_image_restart_rejects_incompatible_model_controls_and_unknown_method(self):
        parent=self.image_source()
        settings=dict(mode="extend",profile="fl2va",continuation_method="last_frame",source_take_id=parent["id"],
                      fields={"detailed_description":"[Shot 1] A person walks."})
        for extra in ({"refine":{"enabled":True}}, {"decode_edge_frames":1}, {"continuation_protection":"color_stable"}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):self.queue(**{**settings,**extra})
        with self.assertRaisesRegex(ValueError,"Choose latent, last-frame or video-reference"):
            self.queue(**{**settings,"continuation_method":"video"})
        with self.assertRaisesRegex(ValueError,"source generation profile"):
            self.queue(**{**settings,"continuation_method":"latent"})

    def test_image_restart_rejects_enabled_reference_assets(self):
        _,job=self.queue();parent=self.finish(job);self.ready_preview(parent);self.command("finalize",take_id=parent["id"])
        with self.assertRaisesRegex(ValueError,"Exclude reference assets"):
            self.queue(mode="extend",profile="fl2va",continuation_method="last_frame",source_take_id=parent["id"],fields={"detailed_description":"Walking."})

    def test_ref2va_image_restart_retains_named_reference_prompt_and_controls(self):
        _,job=self.queue();parent=self.finish(job);self.ready_preview(parent);self.command("finalize",take_id=parent["id"])
        _,child=self.queue(mode="extend",profile="ref2va",continuation_method="last_frame",source_take_id=parent["id"])
        snapshot=child["snapshot"]
        self.assertEqual(snapshot["profile"],"ref2va")
        self.assertEqual(snapshot["plan"]["context_frames"],0)
        self.assertEqual(snapshot["source"]["id"],parent["id"])
        self.assertEqual(snapshot["compiled"]["authored_fields"],parent["snapshot"]["compiled"]["authored_fields"])
        self.assertEqual(snapshot["compiled"]["images"][:-1],parent["snapshot"]["compiled"]["images"])
        self.assertEqual(snapshot["compiled"]["images"][0]["native_label"],"<Picture 1>")
        self.assertEqual(snapshot["compiled"]["images"][-1]["native_label"],"<Picture 2>")
        self.assertEqual(snapshot["compiled"]["images"][-1]["source_archive_sha256"],parent["latent_sha256"])
        self.assertIn("<Picture 2> as its first frame",snapshot["compiled"]["prompt"])
        child_take=self.finish(child);self.ready_preview(child_take);self.command("finalize",take_id=child_take["id"])
        _,replacement=self.queue(mode="regenerate",profile="ref2va",continuation_method="last_frame",segment_id=child_take["segment_id"])
        self.assertEqual(replacement["snapshot"]["compiled"],snapshot["compiled"])

    def test_ref2va_last_frame_can_be_the_only_picture_reference(self):
        parent=self.image_source()
        _,job=self.queue(mode="extend",profile="ref2va",continuation_method="last_frame",source_take_id=parent["id"],fields={"detailed_description":"Continue walking."})
        self.assertEqual(job["snapshot"]["compiled"]["images"][0]["native_label"],"<Picture 1>")

    def test_last_frame_short_motion_plan_retains_picture_prompt_and_no_audio_prefix(self):
        parent=self.image_source()
        _,job=self.queue(mode="extend",profile="ref2va",continuation_method="last_frame",image_motion_frames=22,source_take_id=parent["id"],fields={"detailed_description":"Continue walking."},pdd_warmup="auto")
        snapshot=job["snapshot"]
        self.assertEqual(snapshot["plan"]["context_frames"],22)
        self.assertEqual(snapshot["plan"]["audio"]["context_steps"],0)
        self.assertEqual(snapshot["plan"]["mask_profile"],"picture_short_video_context_v1")
        self.assertEqual(snapshot["image_motion_frames"],22)
        self.assertEqual(snapshot["pdd_warmup"]["mode"],"auto")
        self.assertIn("keyframe completion",snapshot["compiled"]["prompt"])

    def test_claim_idempotence_and_snapshot_tampering(self):
        _, job = self.queue(); self.store.claim(job["id"])
        with self.assertRaises(Conflict): self.store.claim(job["id"])
        self.store.fail(job["id"], "test")
        _, job = self.queue()
        with self.store.locked():
            state=self.store._read(); state["jobs"][job["id"]]["snapshot"]["seed"] = 99; self.store._commit(state)
        with self.assertRaisesRegex(ValueError, "changed after"):
            self.store.claim(job["id"])

    def test_queued_and_running_cancellation_have_different_acknowledgement(self):
        _, job = self.queue(); self.command("cancel", job_id=job["id"])
        with self.assertRaises(Conflict): self.store.claim(job["id"])
        self.command("resolve_cancel", job_id=job["id"])
        _, running = self.queue(); self.store.claim(running["id"]); self.command("cancel", job_id=running["id"])
        with self.assertRaisesRegex(ValueError, "acknowledge"):
            self.command("resolve_cancel", job_id=running["id"])
        self.store.fail(running["id"], "interrupted")
        self.assertEqual(self.store.load()["jobs"][running["id"]]["status"], "cancelled")

    def test_preview_failure_does_not_remove_sampled_take(self):
        _, job = self.queue(); take = self.finish(job)
        self.assertIsNone(self.store.view()["takes"][take["id"]]["preview"])
        atomic_json(self.store.asset(f"takes/{take['id']}/preview.json"), {"status":"failed", "error":"FFmpeg missing"})
        self.store.fail(job["id"], "preview failed")
        self.assertEqual(self.store.load()["jobs"][job["id"]]["status"], "succeeded")
        self.assertTrue(self.store.asset(take["latent_path"]).is_file())
        with self.assertRaisesRegex(ValueError, "preview before finalizing"):
            self.command("finalize", take_id=take["id"])

    def test_crash_recovery_is_idempotent(self):
        _, job = self.queue(); self.store.recover(); state=self.store.load()
        self.assertEqual(state["jobs"][job["id"]]["status"], "failed")
        self.store.recover(); self.assertEqual(state["revision"], self.store.load()["revision"])

    def test_revision_conflict_and_path_traversal(self):
        with self.assertRaises(Conflict): self.store.command(0, "create_scene", {"name":"wrong"})
        with self.assertRaises(ValueError): self.store.asset("../escape")

    def test_effective_reference_edit_checks_other_contexts(self):
        state=self.store.load()
        segment_id=state["scenes"][0]["segments"][0]["id"]
        parent=state["references"][0]
        state=self.command("reference", reference_id=parent["id"], scope="segment", owner_id=segment_id, enabled=False)
        self.assertTrue(state["references"][0]["enabled"])
        self.assertFalse(self.store.view()["effective_references"][segment_id][0]["enabled"])

    def finalized(self, job):
        take=self.finish(job); self.ready_preview(take); self.command("finalize", take_id=take["id"])
        return take

    def test_project_and_each_scene_start_with_an_independent_first_segment(self):
        state=self.store.load(); first=state["scenes"][0]["segments"][0]
        self.assertEqual(first["name"], "Segment 01")
        self.assertEqual(first["working_draft"]["scene_id"], self.scene)
        self.assertEqual(first["working_draft"]["segment_id"], first["id"])
        second=self.command("create_scene", name="Next scene")["scenes"][-1]
        self.assertEqual(len(second["segments"]), 1)
        self.assertEqual(second["segments"][0]["name"], "Segment 01")
        self.assertNotEqual(first["id"], second["segments"][0]["id"])
        _,job=self.queue(scene_id=second["id"], segment_id=second["segments"][0]["id"])
        self.assertIsNone(job["snapshot"]["source"])
        self.assertEqual(job["snapshot"]["plan"]["context_frames"], 0)

    def test_cannot_append_before_tail_is_finalized(self):
        with self.assertRaisesRegex(ValueError, "finalize the current tail"):
            self.command("create_segment", scene_id=self.scene)
        _,job=self.queue();a=self.finalized(job)
        with self.assertRaisesRegex(ValueError, "extending the finalized"):
            self.command("create_segment",scene_id=self.scene)
        state=self.command("create_segment",scene_id=self.scene,after_segment_id=a["segment_id"],draft={**self.settings,"mode":"extend","source_take_id":a["id"]})
        child=state["scenes"][0]["segments"][-1]
        self.assertEqual(child["name"], "Segment 02")
        self.assertEqual(child["working_draft"]["source_take_id"],a["id"])

    def test_replace_first_segment_stays_independent_and_keeps_original(self):
        _,job=self.queue();a=self.finalized(job)
        _,replacement=self.queue(mode="regenerate",segment_id=a["segment_id"],source_take_id=a["id"],seed=9)
        self.assertIsNone(replacement["snapshot"]["source"])
        self.assertEqual(replacement["snapshot"]["plan"]["context_frames"],0)
        candidate=self.finalized(replacement)
        state=self.store.load()
        self.assertEqual(len(state["scenes"][0]["segments"]),1)
        self.assertEqual(state["scenes"][0]["segments"][0]["active_output"]["take_id"],candidate["id"])
        self.assertEqual(state["takes"][a["id"]],a)

    def test_replace_tail_reuses_original_parent_not_tail_own_end(self):
        _,job=self.queue();a=self.finalized(job)
        _,extension=self.queue(mode="extend",source_take_id=a["id"]);b=self.finalized(extension)
        _,replacement=self.queue(mode="regenerate",segment_id=b["segment_id"],source_take_id=b["id"],seed=42)
        self.assertEqual(replacement["snapshot"]["source"]["id"],a["id"])
        self.assertEqual(replacement["snapshot"]["plan"]["context_frames"],39)
        self.assertEqual(len(self.store.load()["scenes"][0]["segments"]),2)

    def test_non_tail_replacement_and_historical_finalization_are_rejected(self):
        _,job=self.queue();a=self.finish(job)
        _,alternative=self.queue(segment_id=a["segment_id"]);old_alternative=self.finish(alternative)
        self.ready_preview(a);self.command("finalize",take_id=a["id"])
        _,extension=self.queue(mode="extend",source_take_id=a["id"]);self.finalized(extension)
        with self.assertRaisesRegex(ValueError, "Only the tail"):
            self.queue(mode="regenerate",segment_id=a["segment_id"])
        self.ready_preview(old_alternative)
        with self.assertRaisesRegex(ValueError, "Only the tail"):
            self.command("finalize",take_id=old_alternative["id"])

    def test_migrate_only_empty_scenes_and_do_not_duplicate_first_segment(self):
        with self.store.locked():
            state=self.store._read();state["scenes"][0]["segments"]=[];self.store._commit(state)
        migrated=self.command("ensure_scene",scene_id=self.scene)
        repeated=self.command("ensure_scene",scene_id=self.scene)
        self.assertEqual(migrated,repeated)
        self.assertEqual(len(repeated["scenes"][0]["segments"]),1)


if __name__ == "__main__": unittest.main()


class FastH3ProvenanceTests(unittest.TestCase):
    def test_fast_h3_loader_checkpoint_is_recorded_through_selected_configuration(self):
        from timeline_core.engine import model_checkpoint_sources
        graph={
            'execute':{'class_type':'LongCasterTimelineExecute','inputs':{'configuration':['switch',0]}},
            'switch':{'class_type':'LongCasterTimelineConfigurationSwitch','inputs':{'select':'A','source_a':['config',0],'source_b':['unused',0]}},
            'config':{'class_type':'LongCasterTimelineConfiguration','inputs':{'model':['sampling',6],'profile':'fl2va'}},
            'sampling':{'class_type':'MMH3H3SamplingPreset','inputs':{'model':['loader',0]}},
            'loader':{'class_type':'MMH3FastH3V2Model','inputs':{'checkpoint':'fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors'}},
            'unused':{'class_type':'UNETLoader','inputs':{'unet_name':'unselected_ref2va.safetensors'}},
        }
        self.assertEqual(model_checkpoint_sources(graph),[{'checkpoint':'fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors','ref_patch_node':None}])
