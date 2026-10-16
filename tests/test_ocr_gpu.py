import sentencepiece,ctranslate2
import threading,unittest,tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from windowwords import game_ocr,ocr
from windowwords.storage import Store
from windowwords.backup import export_backup,import_backup


class GPUOCRTests(unittest.TestCase):
    def setUp(self):game_ocr.reset()
    def tearDown(self):game_ocr.reset()

    def test_device_reaches_selected_engine(self):
        for device in ('cpu','gpu'):
            with patch('windowwords.game_ocr.read',return_value=()) as read:
                image=Image.new('RGB',(100,80));ocr.read(image,engine='game',device=device)
                self.assertEqual(read.call_args.args[1],device)

    def test_gpu_provider_must_be_active_for_both_models(self):
        engine=Mock()
        engine.text_det.infer.session.get_providers.return_value=['DmlExecutionProvider','CPUExecutionProvider']
        engine.text_rec.session.session.get_providers.return_value=['DmlExecutionProvider','CPUExecutionProvider']
        self.assertTrue(game_ocr.uses_gpu(engine))
        engine.text_rec.session.session.get_providers.return_value=['CPUExecutionProvider']
        self.assertFalse(game_ocr.uses_gpu(engine))

    def test_directml_configuration_disables_unsupported_memory_patterns(self):
        from windowwords._vendor.rapidocr.utils.infer_engine import OrtInferSession
        from onnxruntime import ExecutionMode
        settings=OrtInferSession._init_sess_opts({'use_dml':True,'intra_op_num_threads':2,'inter_op_num_threads':1})
        self.assertFalse(settings.enable_mem_pattern)
        self.assertEqual(settings.execution_mode,ExecutionMode.ORT_SEQUENTIAL)
        self.assertEqual(settings.get_session_config_entry('session.intra_op.allow_spinning'),'0')

    def test_unavailable_gpu_falls_back_and_records_actual_cpu(self):
        with patch('onnxruntime.get_available_providers',return_value=['CPUExecutionProvider']),patch.object(game_ocr,'create_engine') as factory:
            self.assertIs(game_ocr.prepare_engine('gpu'),factory.return_value)
            factory.assert_called_once_with('cpu')
            self.assertEqual(game_ocr.status()['active'],'cpu')
            self.assertEqual(game_ocr.status()['fallback'],'unavailable')

    def test_gpu_initialization_failure_does_not_expose_exception_text(self):
        with patch('onnxruntime.get_available_providers',return_value=['DmlExecutionProvider']),patch.object(game_ocr,'create_engine',side_effect=[RuntimeError('private path'),Mock()]):
            game_ocr.prepare_engine('gpu')
            self.assertEqual(game_ocr.status()['fallback'],'initialization')
            self.assertNotIn('private',str(game_ocr.status()))

    def test_silent_cpu_provider_fallback_is_not_reported_as_gpu(self):
        with patch('onnxruntime.get_available_providers',return_value=['DmlExecutionProvider']),patch.object(game_ocr,'create_engine') as factory,patch.object(game_ocr,'uses_gpu',return_value=False):
            game_ocr.prepare_engine('gpu')
            self.assertEqual([c.args[0] for c in factory.call_args_list],['gpu','cpu'])
            self.assertEqual(game_ocr.status()['active'],'cpu')

    def test_runtime_failure_retries_once_on_cpu_and_keeps_cpu_session(self):
        def prepare(device):
            game_ocr._state={'requested':'gpu','active':'gpu','backend':'directml','fallback':''}
            return Mock()
        with patch.object(game_ocr,'prepare_engine',side_effect=prepare) as factory,patch.object(game_ocr,'create_engine') as cpu,patch.object(game_ocr,'recognize',side_effect=[RuntimeError('lost GPU'),(),()]):
            image=Image.new('RGB',(80,80))
            self.assertEqual(game_ocr.read(image,'gpu'),())
            self.assertEqual(game_ocr.read(image,'gpu'),())
            factory.assert_called_once_with('gpu');cpu.assert_called_once_with('cpu')
            self.assertEqual(game_ocr.status()['active'],'cpu')
            self.assertEqual(game_ocr.status()['fallback'],'inference')

    def test_reset_during_inference_does_not_block_and_retires_session(self):
        entered=threading.Event();finish=threading.Event();failures=[]
        def recognize(*args):entered.set();self.assertTrue(finish.wait(3));return ()
        def run():
            try:game_ocr.read(Image.new('RGB',(80,80)),'cpu')
            except Exception as e:failures.append(e)
        with patch.object(game_ocr,'prepare_engine'),patch.object(game_ocr,'recognize',side_effect=recognize):
            worker=threading.Thread(target=run);worker.start();self.assertTrue(entered.wait(3))
            game_ocr.reset();finish.set();worker.join(3)
            self.assertFalse(worker.is_alive());self.assertEqual(failures,[])
            self.assertIsNone(game_ocr._engine)

    def test_matching_preview_session_survives_save_and_windows_releases_gpu(self):
        with patch.object(game_ocr,'_engine',Mock()),patch.object(game_ocr,'_state',{'requested':'gpu','active':'gpu'}):
            initial=game_ocr._engine;game_ocr.apply_settings('game','gpu',retry=True)
            self.assertIs(game_ocr._engine,initial)
            game_ocr.apply_settings('windows','gpu');self.assertIsNone(game_ocr._engine)

    def test_switching_devices_recreates_only_one_session(self):
        with patch.object(game_ocr,'prepare_engine') as factory,patch.object(game_ocr,'recognize',return_value=()):
            image=Image.new('RGB',(80,80))
            for device in ('cpu','cpu','gpu','gpu','cpu'):game_ocr.read(image,device)
            self.assertEqual([c.args[0] for c in factory.call_args_list],['cpu','gpu','cpu'])

    def test_device_survives_backup_and_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'first');settings=store.settings();self.assertEqual(settings['ocr_device'],'gpu')
            settings['ocr_device']='cpu';settings['profiles']={'Example':{'ocr_engine':'game','ocr_device':'cpu'}}
            store.save_settings(settings);file=Path(folder)/'backup.json';export_backup(store,settings,file)
            target=Store(Path(folder)/'second');import_backup(target,file)
            self.assertEqual(target.settings()['ocr_device'],'cpu')
            self.assertEqual(target.settings()['profiles']['Example']['ocr_device'],'cpu')
