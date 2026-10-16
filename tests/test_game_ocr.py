import sentencepiece,ctranslate2
import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from windowwords import ocr,game_ocr
from windowwords.core import Box,Line,Word
from windowwords.storage import Store
from windowwords.backup import export_backup,import_backup


class GameOCRTests(unittest.TestCase):
    def test_engine_choice_is_independent_of_image_profile(self):
        row=Line('Hello',Box(0,0,20,12),())
        for mode,_,_ in ocr.PROFILES:
            with self.subTest(mode=mode),patch('windowwords.game_ocr.read',return_value=(row,)) as read:
                image=Image.new('RGB',(80,40),'yellow')
                self.assertEqual(ocr.read(image,mode,'game'),(row,))
                self.assertEqual(read.call_args.args[0].size,image.size)

    def test_metrics_are_filtered_for_both_engines(self):
        rows=(Line('132 FPS',Box(1,1,30,10),()),Line('NOON',Box(1,20,30,15),()))
        with patch('windowwords.game_ocr.read',return_value=rows):
            self.assertEqual(ocr.read(Image.new('RGB',(80,40)),engine='game'),(rows[1],))

    def test_unknown_engine_does_not_silently_fall_back(self):
        with self.assertRaises(ValueError):ocr.read(Image.new('RGB',(80,40)),engine='wrong')

    def test_word_boxes_preserve_clickable_words_and_physical_coordinates(self):
        polygon=[[10,20],[110,20],[110,40],[10,40]]
        words=[[[10,20],[50,20],[50,40],[10,40]],[[65,20],[110,20],[110,40],[65,40]]]
        result=game_ocr.convert([[polygon,'Hello world',.99,words,['Hello','world'],[.99,.98]]],200,100)
        self.assertEqual(result[0].box,Box(10,20,100,20))
        self.assertEqual([w.text for w in result[0].words],['Hello','world'])
        self.assertEqual(result[0].words[1].box,Box(65,20,45,20))

    def test_invalid_geometry_and_low_confidence_are_ignored(self):
        row=[[[1,2],[3,2],[3,4],[1,4]],'text',.2,[],[],[]]
        self.assertEqual(game_ocr.convert([row],100,100),())
        row[2]=.99;row[0][0][0]=float('nan')
        self.assertEqual(game_ocr.convert([row],100,100),())

    def test_character_fragments_are_joined_at_actual_word_boundaries(self):
        pieces=[Word(c,Box(x,10,8,14)) for c,x in zip('Helloworld',[10,18,26,34,42,65,73,81,89,97])]
        result=game_ocr.aligned_words('Hello world',pieces)
        self.assertEqual([w.text for w in result],['Hello','world'])
        self.assertEqual(result[0].box,Box(10,10,40,14))
        self.assertEqual(result[1].box,Box(65,10,40,14))

    def test_missing_word_alignment_keeps_line_without_fabricated_words(self):
        row=[[[1,2],[31,2],[31,14],[1,14]],'Hello world',.99,[],[],[]]
        result=game_ocr.convert([row],100,100)
        self.assertEqual(len(result[0].words),1)
        self.assertEqual(result[0].words[0].text,'Hello world')

    def test_engine_choice_survives_backup_and_profile_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'first');settings=store.settings()
            self.assertEqual(settings['ocr_engine'],'windows')
            settings['ocr_engine']='game';settings['profiles']={'Example':{'filter':'yellow','ocr_engine':'game'}}
            store.save_settings(settings);self.assertEqual(store.settings()['ocr_engine'],'game')
            file=Path(folder)/'backup.json';export_backup(store,settings,file)
            target=Store(Path(folder)/'second');import_backup(target,file)
            self.assertEqual(target.settings()['ocr_engine'],'game')
            self.assertEqual(target.settings()['profiles']['Example']['ocr_engine'],'game')

    def test_image_is_bgr_and_session_is_reused(self):
        with patch.object(game_ocr,'_engine',None),patch.object(game_ocr,'create_engine') as create:
            create.return_value.return_value=([],None)
            create.return_value.text_rec.return_value=([],None)
            create.return_value.cal_rec_boxes.return_value=[]
            for _ in range(2):self.assertEqual(game_ocr.read(Image.new('RGB',(80,40),(255,0,0))),())
            create.assert_called_once()
            self.assertEqual(create.return_value.call_args.args[0][0,0].tolist(),[0,0,255])

    def test_tight_line_crop_uses_full_crop_ctc_alignment(self):
        with patch.object(game_ocr,'_engine',None),patch.object(game_ocr,'create_engine') as create:
            create.return_value.return_value=([],None)
            create.return_value.text_rec.return_value=([('Hello',.99,None)],None)
            poly=[[0,0],[80,0],[80,40],[0,40]]
            create.return_value.cal_rec_boxes.return_value=[['Hello',.99,[poly],['Hello'],[.99]]]
            result=game_ocr.read(Image.new('RGB',(80,40)))
            self.assertEqual(result[0].text,'Hello')
            self.assertEqual(result[0].words[0].box,Box(0,0,80,40))
