from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from timeline_core.compiler import compile_prompt, effective_references
from timeline_core.configuration import descriptor
from timeline_core.experiments import experiment_plan, create_comparison, update_status, verify_reused_control
from timeline_core.store import Store, atomic_json, blank_segment, digest, uid


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[1]/".test-tmp";parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.data = Store.create(self.temp.name, "Baseline")
        self.source = Store(self.temp.name, self.data["id"])
        self.scene = self.data["scenes"][0]
        self.scene["segments"].extend([blank_segment(self.scene["id"], 2),blank_segment(self.scene["id"], 3)])
        image = self.source.asset("assets/hero.png");image.parent.mkdir();image.write_bytes(b"reference")
        self.data["references"] = [{"id":uid(),"kind":"image","role":"picture","scope":"project","owner_id":None,
            "token_name":"hero","display_name":"Hero","enabled":True,"asset_path":"assets/hero.png","asset_sha256":digest(image)}]
        graph = {"1":{"class_type":"LongCasterTimelineConfiguration","inputs":{"name":"PDD 8","profile":"ref2va","model":["2",0],"sampler":["3",0],"sigmas":["4",0]}},
            "2":{"class_type":"Loader","inputs":{}},"3":{"class_type":"Sampler","inputs":{}},"4":{"class_type":"Sigmas","inputs":{}}}
        configuration = descriptor(graph, "1")
        previous = None
        for index, segment in enumerate(self.scene["segments"]):
            fields = {**segment["working_draft"]["fields"],"subject_definitions":"<Subject 1> is the person in <picture.hero>.","detailed_description":f"[Shot 1] <Subject 1> performs action {index}."}
            compiled = compile_prompt(fields, effective_references(self.data["references"],self.scene["id"],segment["id"]))
            take_id = uid();path = self.source.asset(f"takes/{take_id}/original.mmh3");path.parent.mkdir(parents=True);path.write_bytes(f"latent {index}".encode())
            preview = path.with_name("preview.mp4");preview.write_bytes(b"preview")
            sha = digest(path)
            atomic_json(path.with_name("preview.json"),{"status":"ready","source_sha256":sha,"path":preview.relative_to(self.source.path).as_posix()})
            take = {"id":take_id,"scene_id":self.scene["id"],"segment_id":segment["id"],"latent_path":path.relative_to(self.source.path).as_posix(),
                "latent_sha256":sha,"latent_resource_id":"resource","width":768,"height":448,
                "plan":{"sampled_frames":158 if index else 124,"new_frames":119 if index else 124},
                "snapshot":{"profile":"ref2va","source":deepcopy(previous),"configuration":configuration,"seed":index+100,"width":768,"height":448,
                    "compiled":compiled,"plan":{"requested_seconds":5,"context_frames":39 if index else 0}},
                "receipt":{"continuation_check":{"passed":True}}}
            self.data["takes"][take_id] = take
            segment["takes"] = [take_id];segment["active_output"] = {"kind":"single_take","take_id":take_id}
            previous = {"id":take_id,"latent_sha256":sha}
        # A newer unselected take must never become the common seed.
        self.unused_id = uid(); self.data["takes"][self.unused_id] = {"id":self.unused_id}
        self.scene["segments"][0]["takes"].append(self.unused_id)
        atomic_json(self.source.manifest,self.data)

    def tearDown(self): self.temp.cleanup()

    def test_exact_selected_seed_and_isolated_prompt_blueprints(self):
        before = self.source.manifest.read_bytes()
        plan = experiment_plan(self.source,self.scene["id"],4,reuse_control=False)
        self.assertEqual(plan["seed_take_id"],self.scene["segments"][0]["active_output"]["take_id"])
        self.assertEqual(plan["repeated_last_template"],2)
        result = create_comparison(self.source,self.scene["id"],4,self.data["revision"],reuse_control=False)
        for record in result["projects"]:
            target = Store(self.temp.name,record["id"]); state = target.load()
            self.assertEqual(list(state["takes"]),[plan["seed_take_id"]])
            self.assertEqual(len(state["scenes"][0]["segments"]),5)
            self.assertEqual(state["jobs"],{})
            self.assertNotIn(self.unused_id,state["takes"])
            self.assertEqual(digest(target.asset(state["takes"][plan["seed_take_id"]]["latent_path"])),plan["seed_sha256"])
            for segment in state["scenes"][0]["segments"][1:]:
                self.assertTrue(segment["planned"])
                self.assertEqual(segment["working_draft"]["refine"]["enabled"],record["treatment"]=="h3_refine")
            with self.assertRaises(ValueError): update_status(target,"complete")
        self.assertEqual(self.source.manifest.read_bytes(),before)

    def test_corrupt_archive_changed_references_treated_baseline_and_stale_revision_rejected(self):
        for kind in ("archive","reference","treatment","configuration","source"):
            data = deepcopy(self.data)
            take = data["takes"][self.scene["segments"][1]["active_output"]["take_id"]]
            if kind == "archive": take["latent_sha256"] = "bad"
            if kind == "reference": data["references"][0]["token_name"] = "changed"
            if kind == "treatment": take["snapshot"]["refine"] = {"applied":True}
            if kind == "configuration": take["snapshot"]["configuration"] = {**take["snapshot"]["configuration"],"name":"different"}
            if kind == "source": take["snapshot"]["source"]["id"] = "wrong"
            atomic_json(self.source.manifest,data)
            with self.subTest(kind=kind), self.assertRaises(ValueError): experiment_plan(self.source,self.scene["id"])
        atomic_json(self.source.manifest,self.data)
        with self.assertRaises(ValueError):create_comparison(self.source,self.scene["id"],4,-1)

    def test_standard_and_accelerated_configuration_choices_are_frozen_for_both_arms(self):
        saved = experiment_plan(self.source,self.scene["id"],1)["configuration"]
        for name, kind in (("Standard REF2VA - 20 steps","StandardModel"),("HyperFlow REF2VA - 8 steps","ApplyHyperFlowH3")):
            graph = deepcopy(saved["upstream"])
            graph["1"]["inputs"]["name"] = name
            graph["2"]["class_type"] = kind
            chosen = descriptor(graph,"1")
            plan = experiment_plan(self.source,self.scene["id"],1,chosen,reuse_control=False)
            self.assertTrue(plan["configuration_changed"])
            self.assertEqual(plan["configuration"]["name"],name)
            copies = create_comparison(self.source,self.scene["id"],1,self.data["revision"],chosen,reuse_control=False)
            for arm in copies["projects"]:
                state = Store(self.temp.name,arm["id"]).load()
                self.assertEqual(state["experiment"]["plan"]["configuration"],chosen)
                # The common selected starting take remains immutable.
                seed = state["takes"][plan["seed_take_id"]]
                self.assertEqual(seed["snapshot"]["configuration"]["name"],"PDD 8")

    def test_reuse_option_creates_only_refinement_with_exact_control_provenance(self):
        before = self.source.manifest.read_bytes()
        plan = experiment_plan(self.source,self.scene["id"],2,reuse_control=True)
        self.assertTrue(plan["reuse_control"])
        self.assertEqual(plan["treatments"],["h3_refine"])
        expected = [s["active_output"]["take_id"] for s in self.scene["segments"]]
        self.assertEqual([t["id"] for t in plan["existing_control"]["takes"]],expected)
        result = create_comparison(self.source,self.scene["id"],2,self.data["revision"],reuse_control=True)
        self.assertEqual(len(result["projects"]),1)
        self.assertEqual(result["projects"][0]["treatment"],"h3_refine")
        self.assertEqual(result["existing_control"]["project_id"],self.data["id"])
        target = Store(self.temp.name,result["projects"][0]["id"])
        self.assertEqual(target.load()["experiment"]["plan"]["existing_control"],plan["existing_control"])
        verify_reused_control(target)
        self.assertEqual(self.source.manifest.read_bytes(),before)
        self.assertEqual(self.source.load()["jobs"],{})

    def test_reuse_rejects_short_control_and_different_configuration_without_regenerating_it(self):
        with self.assertRaisesRegex(ValueError,"Only 2 finalized control"):
            experiment_plan(self.source,self.scene["id"],3,reuse_control=True)
        saved = experiment_plan(self.source,self.scene["id"],1)["configuration"]
        graph = deepcopy(saved["upstream"]);graph["1"]["inputs"]["name"] = "Standard REF2VA"
        different = descriptor(graph,"1")
        with self.assertRaisesRegex(ValueError,"different generation configuration"):
            experiment_plan(self.source,self.scene["id"],1,different,reuse_control=True)
        # Selecting a prefix of a longer existing control is valid.
        self.assertEqual(len(experiment_plan(self.source,self.scene["id"],1,reuse_control=True)["existing_control"]["takes"]),2)

    def test_reused_control_is_rechecked_for_changed_selection_or_missing_preview(self):
        result = create_comparison(self.source,self.scene["id"],2,self.data["revision"],reuse_control=True)
        target = Store(self.temp.name,result["projects"][0]["id"])
        baseline = deepcopy(self.data)
        baseline["scenes"][0]["segments"][1]["active_output"]["take_id"] = self.unused_id
        atomic_json(self.source.manifest,baseline)
        with self.assertRaisesRegex(ValueError,"control selection changed"):
            verify_reused_control(target)
        atomic_json(self.source.manifest,self.data)
        take = self.data["takes"][self.scene["segments"][1]["active_output"]["take_id"]]
        self.source.asset(take["latent_path"]).with_name("preview.mp4").unlink()
        with self.assertRaisesRegex(ValueError,"preview must be ready"):
            verify_reused_control(target)

    def test_independent_drift_color_and_combined_arms_reuse_control_without_refinement(self):
        modes=["drift_control","color_stable","drift_color"]
        result=create_comparison(self.source,self.scene["id"],2,self.data["revision"],reuse_control=True,treatments=modes)
        self.assertEqual([a["treatment"] for a in result["projects"]],modes)
        for arm in result["projects"]:
            target=Store(self.temp.name,arm["id"]);state=target.load()
            for segment in state["scenes"][0]["segments"][1:]:
                self.assertEqual(segment["working_draft"]["continuation_protection"],arm["treatment"])
                self.assertFalse(segment["working_draft"]["refine"]["enabled"])
            settings=deepcopy(state["scenes"][0]["segments"][1]["working_draft"])
            settings.update(source_take_id=result["plan"]["seed_take_id"],configuration=result["plan"]["configuration"])
            _,job=target.queue(state["revision"],settings)
            frozen=job["snapshot"]["continuation_protection"]
            self.assertTrue(frozen["applied"])
            self.assertEqual(frozen["mode"],arm["treatment"])
            self.assertEqual(job["snapshot"]["plan"]["mask_profile"],"hard_av_color_prefix_v1" if arm["treatment"]=="color_stable" else "drift_control_av_v1")
            if frozen["color_stable"]:self.assertEqual(frozen["anchor"]["id"],result["plan"]["seed_take_id"])
        self.assertEqual(self.source.load()["jobs"],{})
        for value in ([],["unknown"],["drift_color","drift_color"],"drift_color"):
            with self.assertRaises(ValueError):experiment_plan(self.source,self.scene["id"],1,treatments=value)
