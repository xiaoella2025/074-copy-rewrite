import base64,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import server,cover_motion,cover_images,task_cover,image_motion

MP4=b'\x00\x00\x00\x18ftypisom'+b'\0'*20
class CoverMotionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.addCleanup(patch.stopall)
  self.data=Path(self.tmp.name);patch.object(server,'DATA_DIR',self.data).start();self.folder=self.data/'tasks/t';self.folder.mkdir(parents=True)
  task_cover.write(self.folder/'client_config.json',{'cover':{'mode':'titled','ratio':'3:4'}});task_cover.write(self.folder/'02-meta.json',{'title':'封面'})
  out=io.BytesIO();Image.new('RGB',(32,48),'red').save(out,'PNG');task_cover.commit(server,'t',1,out.getvalue(),{'prompt':'精确封面文字'})
  patch.object(server,'load_settings',return_value={'runninghub':{'api_key':'fixture-wallet','base_url':'https://fixture.invalid'}}).start()
  self.render=patch.object(server,'make_intro_video',side_effect=lambda im,au,target,*a,**kw:Path(target).write_bytes(MP4)).start()
  self.calls=[]
  def request(backend,path,body,cfg):
   self.calls.append(path)
   return {'taskId':'paid-fixture','status':'SUCCESS' if path.endswith('/query') else 'RUNNING','results':[{'url':'https://fixture.invalid/v.mp4'}]}
  patch.object(image_motion,'_request',side_effect=request).start();patch.object(image_motion,'_upload',return_value='https://fixture.invalid/image.png').start()
  patch.object(image_motion,'_download',side_effect=lambda url,path:Path(path).write_bytes(MP4)).start()
 def test_local_animation_reuses_renderer_and_preserves_scene_assets(self):
  before=task_cover.paths(self.folder,1)[1].read_bytes();result=cover_motion.action(server,'t',1,'animation',{'operation_id':'local'})
  self.assertEqual(result['result']['engine'],'local-panzoom');self.assertEqual(cover_motion.media(server,'t',1,'animation.mp4').read_bytes(),MP4)
  cover_motion.action(server,'t',1,'animation',{'operation_id':'local'});self.render.assert_called_once();self.assertEqual(self.calls,[])
  self.assertEqual(task_cover.paths(self.folder,1)[1].read_bytes(),before);self.assertFalse((self.folder/'04-intro-videos.json').exists())
 def test_ai_uses_wallet_engine_and_same_confirmation_reuses_receipt(self):
  data={'operation_id':'ai-once','prompt':'文字保持不变','duration_sec':6}
  first=cover_motion.action(server,'t',1,'generate',data);second=cover_motion.action(server,'t',1,'generate',data)
  self.assertEqual(first['result']['engine'],'runninghub-i2v');self.assertEqual(first,second)
  self.assertEqual(sum(not p.endswith('/query') for p in self.calls),1)
 def test_completed_cover_video_creates_child_and_keeps_original_bytes(self):
  task_cover.write(self.folder/'06-draft-meta.json',{'ok':True,'draft_dir':'existing'})
  before={p.relative_to(self.folder):p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}
  result=cover_motion.action(server,'t',1,'animation',{'operation_id':'completed'})
  self.assertNotEqual(result['task_id'],'t');self.assertEqual(before,{p.relative_to(self.folder):p.read_bytes() for p in self.folder.rglob('*') if p.is_file()})
 def test_unknown_video_blocks_image_mutation_and_never_resubmits(self):
  _,_,folder=cover_motion.workspace(server,'t',1,True);task_cover.write(folder/'04-video-meta.json',{'items':{'1':{'status':'unknown'}}})
  with self.assertRaisesRegex(ValueError,'在途'):task_cover.action(server,'t','save',{'title':'changed'})
  with self.assertRaises(ValueError):cover_motion.action(server,'t',1,'query',{})
  self.assertEqual(self.calls,[])
 def test_view_and_default_prompt_are_read_only(self):
  before=list(self.folder.rglob('*'));self.assertFalse(cover_motion.view(server,'t',1)['result'])
  self.assertIn('文字',cover_motion.action(server,'t',1,'prompt',{})['prompt']);self.assertEqual(before,list(self.folder.rglob('*')))
 def test_cover_slots_keep_separate_videos(self):
  task_cover.commit(server,'t',2,task_cover.paths(self.folder,1)[1].read_bytes(),{'prompt':'second'})
  cover_motion.action(server,'t',1,'animation',{'operation_id':'one'})
  self.assertFalse(cover_motion.view(server,'t',2)['result'])

 def test_ai_copy_failure_preserves_existing_video_and_reuses_paid_result(self):
  data={'operation_id':'copy-once','prompt':'文字保持不变','duration_sec':6};cover_motion.action(server,'t',1,'generate',data)
  destination=cover_motion.media(server,'t',1,'ai.mp4');old=MP4+b'old-valid-video'*100;destination.write_bytes(old)
  def broken(src,dest):Path(dest).write_bytes(MP4);raise OSError('copy interrupted')
  with patch('shutil.copyfile',side_effect=broken):
   with self.assertRaises(OSError):cover_motion.action(server,'t',1,'generate',data)
  self.assertEqual(destination.read_bytes(),old);self.assertTrue(cover_motion.view(server,'t',1)['restoring'])
  cover_motion.action(server,'t',1,'query',{});self.assertEqual(destination.read_bytes(),MP4)
  self.assertEqual(sum(not p.endswith('/query') for p in self.calls),1)

if __name__=='__main__':unittest.main()
