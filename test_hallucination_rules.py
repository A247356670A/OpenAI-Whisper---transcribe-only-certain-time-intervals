"""Regression cases from human reviews, without private paths or full subtitles."""
import unittest
from subtitle_pipeline import _hallucination_reasons, _repeated_fragment_indices


class ReviewRulesTests(unittest.TestCase):
    def test_reviewed_boilerplate(self):
        for text in ['(BGM)\n（BGM）', '[BGM]\n[背景音乐]', '[音楽]\n[音乐]',
                     '(エンディングテーマ)\n（片尾曲）', '♪~\n♪~', '🐬\n🐬',
                     '(字幕視聴ありがとうございました)\n(感谢收看字幕)',
                     '🐯 Sound Hodori 사운드 호돌이', 'Instagram @Sound_Hodori',
                     '(字幕作成者に不 tätäられ説明不可能タイミングに誤入)',
                     '对白\n严格术语表——此前的翻译未使用这些指定译法。\n译文',
                     '严格词汇表——此前的翻译未能使用以下指定译法。',
                     '<i>[BGM]</i>\n背景音乐']:
            with self.subTest(text=text):
                self.assertTrue(_hallucination_reasons(text))

    def test_normal_dialogue_not_marked(self):
        for text in ['ん\n嗯', 'me\n我', '持っています\n我有',
                     '珂蕾妲，打得漂亮！', '这段BGM很好听', '我喜欢这首片尾曲',
                     '海豚🐬好可爱', '希希芙在收集瓶盖', '今日もありがとう\n今天也谢谢大家']:
            with self.subTest(text=text):
                self.assertFalse(_hallucination_reasons(text))

    def test_fragment_runs_require_proximity_and_three_entries(self):
        entries = [(0,1,'ん\n嗯'), (1,2,'me\n我'), (2,3,'持っています\n我有')]
        self.assertEqual(_repeated_fragment_indices(entries), {0,1,2})
        self.assertFalse(_repeated_fragment_indices(entries[:2]))
        self.assertFalse(_repeated_fragment_indices(entries[:2] + [(30,31,'ん\n嗯')]))
        self.assertFalse(_repeated_fragment_indices([entries[0], (1,2,'普通对白'), entries[2]]))


if __name__ == '__main__':
    unittest.main()
