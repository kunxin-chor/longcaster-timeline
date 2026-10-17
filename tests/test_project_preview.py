from pathlib import Path
import subprocess
import re
import tempfile
import time
import unittest

from timeline_core.store import Store, atomic_json, new_scene, uid
from timeline_core.project_preview import plan_project_preview, render_project_preview, cached_preview, request_project_preview


class ProjectPreviewTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / '.test-tmp'
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.data = Store.create(self.temp.name, 'Preview')
        self.store = Store(self.temp.name, self.data['id'])

    def tearDown(self):
        self.temp.cleanup()

    def take(self, scene, frames=24, finalized=True):
        segment = {'id': uid(), 'name': 'Segment', 'takes': [], 'active_output': None}
        scene['segments'].append(segment)
        take_id = uid()
        take = dict(id=take_id, segment_id=segment['id'], scene_id=scene['id'], number=1,
                    width=128, height=72, latent_sha256='a'*64,
                    plan=dict(new_frames=frames, context_frames=39, sampled_frames=frames+39))
        self.data['takes'][take_id] = take
        segment['takes'].append(take_id)
        if finalized: segment['active_output'] = dict(take_id=take_id)
        source = self.store.asset(f'takes/{take_id}/preview.mp4')
        source.parent.mkdir(parents=True)
        source.write_bytes(b'fixture')
        atomic_json(source.with_suffix('.json'), dict(status='ready', source_sha256=take['latent_sha256'],
                   path=f'takes/{take_id}/preview.mp4'))
        self.save()
        return take, source

    def save(self):
        atomic_json(self.store.manifest, self.data)

    def test_order_drafts_and_no_second_overlap_trim(self):
        a, _ = self.take(self.data['scenes'][0], 24)
        b, _ = self.take(self.data['scenes'][0], 48, False)
        scene = new_scene('Second scene'); self.data['scenes'].append(scene)
        c, _ = self.take(scene, 72)
        before = self.store.manifest.read_bytes()
        finalized = plan_project_preview(self.store)
        review = plan_project_preview(self.store, True, b['id'])
        self.assertEqual([e['take_id'] for e in finalized['entries']], [a['id'], c['id']])
        self.assertEqual([e['frames'] for e in review['entries']], [24, 48, 72])
        self.assertEqual([e['start_frame'] for e in review['entries']], [0, 24, 72])
        self.assertEqual([e['scene_start_frame'] for e in review['entries']], [0, 24, 0])
        self.assertEqual(review['frames'], 144)
        self.assertEqual(review['draft_count'], 1)
        self.assertEqual(before, self.store.manifest.read_bytes())
        earlier = plan_project_preview(self.store, True, a['id'])
        self.assertEqual([entry['take_id'] for entry in earlier['entries']], [a['id'], b['id'], c['id']])
        self.assertEqual(before, self.store.manifest.read_bytes())

    def test_generated_draft_before_planned_tail_is_playable_and_read_only(self):
        scene=self.data['scenes'][0]
        first,_=self.take(scene,24)
        second,_=self.take(scene,24)
        draft,_=self.take(scene,48,False)
        planned={'id':uid(),'name':'Planned segment','takes':[],'active_output':None,'planned':True}
        scene['segments'].append(planned);self.save()
        before=self.store.manifest.read_bytes()
        for selected in (None,draft['id'],first['id']):
            review=plan_project_preview(self.store,True,selected,scene['id'])
            self.assertEqual([entry['take_id'] for entry in review['entries']],[first['id'],second['id'],draft['id']])
            self.assertEqual([entry['start_frame'] for entry in review['entries']],[0,24,48])
            self.assertEqual(review['frames'],96);self.assertEqual(review['draft_count'],1)
        finalized=plan_project_preview(self.store,False,scene_id=scene['id'])
        self.assertEqual([entry['take_id'] for entry in finalized['entries']],[first['id'],second['id']])
        self.assertEqual(before,self.store.manifest.read_bytes())

    def test_scene_preview_scope_does_not_include_other_scenes(self):
        first,_=self.take(self.data['scenes'][0],24)
        scene=new_scene('Second');self.data['scenes'].append(scene)
        second,_=self.take(scene,48)
        plan=plan_project_preview(self.store,scene_id=scene['id'])
        self.assertEqual([entry['take_id'] for entry in plan['entries']],[second['id']])
        self.assertEqual(plan['frames'],48)
        self.assertEqual(plan['entries'][0]['start_frame'],0)
        with self.assertRaisesRegex(ValueError,'scene not found'):plan_project_preview(self.store,scene_id='missing')
        with self.assertRaisesRegex(ValueError,'another scene'):plan_project_preview(self.store,True,first['id'],scene['id'])

    def test_missing_finalized_preview_and_changed_source(self):
        take, source = self.take(self.data['scenes'][0])
        key = plan_project_preview(self.store)['key']
        source.write_bytes(b'changed preview')
        self.assertNotEqual(key, plan_project_preview(self.store)['key'])
        source.unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            plan_project_preview(self.store)
        with self.assertRaises(ValueError): cached_preview(self.store, '../project.json')

    def test_unready_drafts_are_skipped(self):
        take, source = self.take(self.data['scenes'][0], finalized=False)
        source.with_suffix('.json').unlink()
        self.assertEqual(request_project_preview(self.store, True)['status'], 'empty')
        with self.assertRaisesRegex(ValueError, 'Rebuild'):
            plan_project_preview(self.store, True, take['id'])

    def test_real_movie_preserves_frame_count_audio_and_sources(self):
        try:
            import imageio_ffmpeg
        except ImportError:
            self.skipTest('imageio-ffmpeg is required for the real media integration check')
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        originals = []
        for frames, color, finalized in [(24, 'red', True), (48, 'blue', False)]:
            take, source = self.take(self.data['scenes'][0], frames, finalized)
            subprocess.run([ffmpeg, '-y', '-v', 'error', '-f', 'lavfi', '-i',
                f'color=c={color}:s=128x72:r=24:d={frames/24}', '-f', 'lavfi', '-i',
                f'sine=frequency=440:sample_rate=48000:duration={frames/24}',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)], check=True, capture_output=True)
            originals.append((source, source.read_bytes()))
        selected=take['id']
        self.data['scenes'][0]['segments'].append({'id':uid(),'name':'Future planned segment','takes':[],'active_output':None,'planned':True})
        self.save()
        before = self.store.manifest.read_bytes()
        plan = plan_project_preview(self.store, True, selected)
        result = request_project_preview(self.store, True, selected)
        self.assertEqual(result['status'], 'building')
        deadline = time.monotonic() + 10
        while result['status'] == 'building' and time.monotonic() < deadline:
            time.sleep(.05)
            result = request_project_preview(self.store, True, selected)
        self.assertEqual(result['status'], 'ready', result.get('error'))
        self.assertEqual(result['version'], 2)
        self.assertEqual(result['encoding'], 'scrub_gop12_v1')
        self.assertEqual(result['frames'], 72)
        self.assertEqual(result['seconds'], 3)
        self.assertTrue(result['context_already_trimmed'])
        self.assertEqual(cached_preview(self.store, plan['key'])['sha256'], result['sha256'])
        self.assertEqual(request_project_preview(self.store, True)['status'], 'ready')
        movie = self.store.asset(result['path'])
        video = subprocess.run([ffmpeg, '-v', 'error', '-i', str(movie), '-map', '0:v:0',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], check=True, capture_output=True).stdout
        info=subprocess.run([ffmpeg,'-hide_banner','-i',str(movie),'-vf','showinfo','-an','-f','null','-'],check=True,capture_output=True).stderr.decode(errors='replace')
        keyframes=[int(m.group(1)) for m in re.finditer(r'n:\s*(\d+)[^\n]*iskey:1',info)]
        self.assertEqual(keyframes,[0,12,24,36,48,60])
        self.assertEqual(len(video), 72*128*72*3)
        self.assertGreater(video[0], 200)  # red first scene
        self.assertGreater(video[24*128*72*3+2], 200)  # blue at exact seam
        audio = subprocess.run([ffmpeg, '-v', 'error', '-i', str(movie), '-map', '0:a:0',
            '-t', '3', '-f', 's16le', '-ar', '48000', '-ac', '2', 'pipe:1'], check=True, capture_output=True).stdout
        self.assertEqual(len(audio), 3*48000*2*2)
        self.assertEqual(before, self.store.manifest.read_bytes())
        for path, original in originals: self.assertEqual(path.read_bytes(), original)


    def test_raw_and_lanczos_upscaled_exports_are_real_media(self):
        try:import imageio_ffmpeg
        except ImportError:self.skipTest('imageio-ffmpeg required')
        from timeline_core.production import export_production
        take,source=self.take(self.data['scenes'][0],24)
        tool=imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([tool,'-y','-v','error','-f','lavfi','-i','color=c=red:s=128x72:r=24:d=1','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,capture_output=True)
        original=source.read_bytes();result=export_production(self.store,'raw');deadline=time.monotonic()+10
        while result['status']=='building' and time.monotonic()<deadline:
            time.sleep(.05);result=export_production(self.store,'raw')
        self.assertEqual(result['status'],'ready');self.assertEqual(result['frames'],24)
        self.store.command(self.store.load()['revision'],'set_upscale',{'width':512,'height':288})
        manifest=self.store.manifest.read_bytes();scaled=export_production(self.store,'upscaled')
        self.assertEqual(scaled['method'],'lanczos')
        pixels=subprocess.run([tool,'-v','error','-i',str(self.store.asset(scaled['path'])),'-map','0:v:0','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,capture_output=True).stdout
        self.assertEqual(len(pixels),24*512*288*3)
        self.assertEqual(source.read_bytes(),original);self.assertEqual(self.store.manifest.read_bytes(),manifest)
