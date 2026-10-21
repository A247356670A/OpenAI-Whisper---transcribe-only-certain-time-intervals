"""Qwen contract tests with fake inference: never download weights in tests."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import tempfile
import unittest
import numpy as np
import qwen_pipeline as q


def result(text, spans):
    return NS(text=text, time_stamps=[NS(text=t,start_time=s,end_time=e) for t,s,e in spans])


class QwenTests(unittest.TestCase):
    def test_symbols_with_no_timestamps_do_not_abort(self):
        for text in ('♪~', '……', '。', "'", '🐬'):
            with self.subTest(text=text):
                r=NS(text=text,time_stamps=None)
                model=NS()
                self.assertEqual(q.aligned_entries(r,0,60),[])
                fixed=q.ensure_alignment(model,r,np.zeros(16000),16000,0,lambda _:None)
                self.assertEqual(fixed.text,'')

    def test_real_text_missing_alignment_retries_once(self):
        from unittest.mock import Mock
        stamps=result('あ',[('あ',.2,.8)]).time_stamps
        aligner=Mock()
        aligner.align.return_value=[stamps]
        for missing in (None,[]):
            aligner.reset_mock()
            fixed=q.ensure_alignment(NS(forced_aligner=aligner),NS(text='あ',time_stamps=missing),
                                     np.zeros(16000),16000,30,lambda _:None)
            aligner.align.assert_called_once()
            self.assertEqual(q.aligned_entries(fixed,30,1),[(30.2,30.8,'あ')])

    def test_failed_retry_reports_text_and_offset(self):
        from unittest.mock import Mock
        aligner=Mock()
        aligner.align.return_value=[[]]
        with self.assertRaisesRegex(ValueError,'59.400.*こんにちは'):
            q.ensure_alignment(NS(forced_aligner=aligner),NS(text='こんにちは',time_stamps=None),
                               np.zeros(16000),16000,59.4,lambda _:None)
        aligner.align.assert_called_once()

    def test_punctuation_and_global_offset(self):
        r = result('「ロクシー」、待って！', [('ロクシー',1,2),('待って',2.2,3)])
        self.assertEqual(q.aligned_entries(r, 100, 5), [(101,103,'「ロクシー」、待って！')])

    def test_pause_leaves_a_gap_for_b(self):
        r=result('あ。はい！',[('あ',0,1),('はい',4,5)])
        self.assertEqual(q.aligned_entries(r,0,6),[(0,1,'あ。'),(4,5,'はい！')])

    def test_missing_or_mismatched_alignment_fails(self):
        for r in [NS(text='文字',time_stamps=None),result('文字',[('字',0,1)]),result('字',[('字',0,float('nan'))])]:
            with self.assertRaises(ValueError): q.aligned_entries(r,0,2)
        self.assertEqual(q.aligned_entries(NS(text='',time_stamps=None),0,2),[])

    def test_chunk_coverage(self):
        data=np.arange(25001,dtype=np.float32)
        chunks=list(q.audio_chunks(data,1000,10))
        np.testing.assert_array_equal(np.concatenate([x for _,x in chunks]),data)
        consumed=0
        for start,x in chunks:
            self.assertEqual(start,consumed/1000)
            self.assertLessEqual(len(x),10000)
            consumed+=len(x)

    def test_full_workflow_offsets_empty_b_and_vad(self):
        for filter_on in (False,True):
            with self.subTest(filter=filter_on), tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'video.mp4'
                source.touch()
                class Model:
                    def __init__(self): self.calls=[]
                    def transcribe(self, **kwargs):
                        self.calls.append(kwargs)
                        if len(self.calls)==1:
                            return [result('最初。',[('最初',0,2)])]
                        return [result('補完！',[('補完',0,1)])]
                model=Model()
                progress=[]
                with patch.object(q,'_load_runtime',return_value=(model,NS(),NS())), \
                     patch.object(q.pipeline,'_load_audio_mono_16k',return_value=(np.zeros(80000,dtype=np.float32),16000)), \
                     patch.object(q.pipeline,'filter_b_segments_with_silero',return_value=([],[[2,5]])) as vad:
                    outputs=q.run_qwen_two_pass(source,tmp,context='ロクシー',filter_b_speech=filter_on,
                        progress_callback=lambda *args:progress.append(args))
                self.assertTrue(outputs.merged.exists())
                self.assertIn('_Qwen_A',outputs.first_pass.name)
                self.assertEqual(model.calls[0]['language'],'Japanese')
                self.assertEqual(model.calls[0]['context'],'ロクシー')
                self.assertTrue(model.calls[0]['return_time_stamps'])
                if filter_on:
                    vad.assert_called_once()
                    self.assertEqual(outputs.second_pass.read_text(),'')
                else:
                    vad.assert_not_called()
                    b=q.pipeline.parse_srt(outputs.second_pass)
                    self.assertEqual(b[0][:2],[2.0,3.0])
                self.assertEqual(progress[-1],('subtitle_b',1,1))

    def test_invalid_settings_before_loading(self):
        with patch.object(q,'_load_runtime') as load:
            for seconds in [0,float('nan'),121]:
                with self.assertRaises(ValueError):q.run_qwen_two_pass('missing','.',chunk_seconds=seconds)
            load.assert_not_called()

    def test_gui_dispatch_keeps_whisper_separate(self):
        import inspect
        from queue import Queue
        import subtitle_gui as gui
        method=gui.SubtitleApp._run_worker
        args={name: '' for name,p in inspect.signature(method).parameters.items()
              if name!='self' and p.default is inspect.Parameter.empty}
        args.update(mode='full',video='test.mp4',output='.',merge_gap=1.,duplicate_threshold=.5,
                    gpu_acceleration=False,filter_b_speech=False)
        for engine in ('Whisper','Qwen3-ASR'):
            app=NS(events=Queue())
            with patch.object(gui,'run_qwen_two_pass',return_value='qwen') as qwen, \
                 patch.object(gui,'run_two_pass_transcription',return_value='whisper') as whisper:
                method(app,**args,asr_engine=engine)
                self.assertEqual(qwen.call_count,engine=='Qwen3-ASR')
                self.assertEqual(whisper.call_count,engine=='Whisper')
                self.assertEqual(app.events.get()[0],'success')


if __name__=='__main__':unittest.main()
