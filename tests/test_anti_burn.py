from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

from timeline_core.anti_burn import FILENAME, availability, freeze, apply, scene_controls, segment_controls
from timeline_core.store import Store, digest
from timeline_core.duplicate import duplicate_without_generations


class AntiBurnTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".test-tmp"
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.file = Path(self.temp.name) / FILENAME
        self.file.write_bytes(b"fake weights for loader contract tests")
        self.paths = SimpleNamespace(get_filename_list=lambda kind:["nested/" + FILENAME],
            get_full_path=lambda kind,name:str(self.file), get_full_path_or_raise=lambda kind,name:str(self.file))

    def tearDown(self):
        self.temp.cleanup()

    def test_off_and_independent_starts_never_resolve_or_load_weights(self):
        with patch("timeline_core.anti_burn.availability", side_effect=AssertionError("must not resolve")):
            self.assertEqual(freeze({}, {}, {"id":"source"}, [])["reason"], "disabled")
            frozen = freeze({"anti_burn":{"enabled":True}}, {}, None, [])
            self.assertEqual(frozen["reason"], "independent_start")
            self.assertFalse(frozen["applied"])
            model = object()
            self.assertIs(apply(model, frozen)[0], model)

    def test_inheritance_override_hash_and_actual_model_only_application(self):
        with patch.dict("sys.modules", {"folder_paths":self.paths}):
            scene = {"anti_burn":{"enabled":True,"strength":.6}}
            frozen = freeze(scene, {}, {"id":"source"}, [])
            self.assertEqual((frozen["strength"],frozen["filename"],frozen["sha256"]),(.6,"nested/"+FILENAME,digest(self.file)))
            scene["anti_burn"]["strength"] = 1
            self.assertEqual(frozen["strength"],.6)
            self.assertFalse(freeze(scene,{"anti_burn":{"mode":"off"}}, {"id":"source"}, [])["applied"])
            custom = freeze({}, {"anti_burn":{"mode":"on","strength":.4}}, {"id":"source"}, [])
            with patch("timeline_core.loras.apply_loras",return_value=("patched",[{"sha256":digest(self.file)}])) as loader:
                model, receipt = apply("original", custom)
                self.assertEqual(model,"patched")
                self.assertTrue(receipt["applied"])
                self.assertEqual(loader.call_args.args[1][0]["strength"],.4)
            self.file.write_bytes(b"replaced after queue")
            with self.assertRaisesRegex(ValueError,"changed after queueing"):
                apply("original",custom)

    def test_missing_ambiguous_and_duplicate_manual_entry(self):
        with patch.dict("sys.modules",{"folder_paths":self.paths}):
            self.paths.get_filename_list=lambda kind:[]
            self.assertFalse(availability()["available"])
            with self.assertRaisesRegex(ValueError,"not found"):
                freeze({"anti_burn":{"enabled":True}}, {}, {"id":"source"}, [])
            self.paths.get_filename_list=lambda kind:[FILENAME,"copy/"+FILENAME]
            self.assertIn("Multiple",availability()["warning"])
            self.paths.get_filename_list=lambda kind:[FILENAME]
            with self.assertRaisesRegex(ValueError,"normal LoRA list"):
                freeze({}, {"anti_burn":{"mode":"on"}}, {"id":"source"}, [{"filename":FILENAME}])

    def test_invalid_controls_rejected(self):
        for value in (True,False,0,-.5,2.1,float("nan"),"0.5"):
            with self.subTest(value=value),self.assertRaises(ValueError):
                scene_controls({"enabled":True,"strength":value})
        with self.assertRaises(ValueError):scene_controls({"enabled":"yes"})
        with self.assertRaises(ValueError):segment_controls({"mode":"auto"})

    def test_scene_persistence_queue_guard_snapshot_and_blueprint_copy(self):
        state=Store.create(self.temp.name,"Anti-Burn")
        store=Store(self.temp.name,state["id"])
        scene=state["scenes"][0]
        state=store.command(state["revision"],"set_scene_anti_burn",{"scene_id":scene["id"],"anti_burn":{"enabled":True,"strength":.5}})
        settings={"scene_id":scene["id"],"mode":"new","profile":"fl2va","seconds":5,"fields":{"detailed_description":"[Shot 1] Waves roll."}}
        _,job=store.queue(state["revision"],settings)
        self.assertEqual(job["snapshot"]["anti_burn"]["reason"],"independent_start")
        store.fail(job["id"],"fixture cleanup")
        # A persisted source archive, with the exact finalized take pointer.
        state=store.load();parent=state["scenes"][0]["segments"][0]
        archive=store.asset("takes/source/original.mmh3");archive.parent.mkdir(parents=True);archive.write_bytes(b"fake source")
        source={"id":"source","segment_id":parent["id"],"scene_id":scene["id"],"latent_path":"takes/source/original.mmh3",
            "latent_sha256":digest(archive),"latent_resource_id":"resource","width":768,"height":448,
            "plan":job["snapshot"]["plan"],"snapshot":job["snapshot"]}
        state["takes"]["source"]=source;parent["takes"]=["source"];parent["active_output"]={"kind":"single_take","take_id":"source"}
        store._commit(state)
        extension={**settings,"mode":"extend","source_take_id":"source"}
        before=deepcopy(store.load())
        with patch("timeline_core.anti_burn.availability", return_value={"available":False,"warning":"Anti-Burn LoRA not found."}):
            with self.assertRaisesRegex(ValueError,"not found"):store.queue(before["revision"],extension)
        self.assertEqual(store.load(),before)  # no orphan segment or job on failure
        with patch.dict("sys.modules",{"folder_paths":self.paths}):
            state,job=store.queue(before["revision"],extension)
        self.assertTrue(job["snapshot"]["anti_burn"]["applied"])
        store.fail(job["id"],"fixture cleanup")
        copied=duplicate_without_generations(store,"Anti-Burn copy")
        self.assertEqual(copied["scenes"][0]["anti_burn"],{"enabled":True,"strength":.5})
        self.assertEqual(copied["takes"],{})
