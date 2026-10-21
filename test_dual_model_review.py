"""Offline regression tests: no ASR models or paid API calls needed."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from dual_model_review import (prepare_package, batches, apply_proposals,
                              export_package, reconcile, endpoint_url, call_api)


class DualReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.w = self.root / 'w.srt'
        self.q = self.root / 'q.srt'
        self.w.write_text('1\n00:00:01,000 --> 00:00:03,000\n今日は渡瀬さんと遊びます\n\n'
                          '2\n00:00:04,000 --> 00:00:05,000\n消さない台詞\n', encoding='utf-8')
        self.q.write_text('1\n00:00:01,100 --> 00:00:02,000\n今日は四月一日さんと\n\n'
                          '2\n00:00:02,000 --> 00:00:03,000\n遊びます\n\n'
                          '3\n00:00:06,000 --> 00:00:07,000\nここにいたんだね\n', encoding='utf-8')
        self.package = prepare_package(self.w, self.q)

    def tearDown(self):
        self.temp.cleanup()

    def proposal(self):
        return {'edits': [{'whisper_id': 0, 'qwen_id': 0, 'old': '渡瀬',
                           'new': '四月一日', 'reason': '人名对照'}],
                'additions': [], 'uncertain': []}

    def test_temporal_many_to_many_and_whisper_only(self):
        self.assertEqual(self.package['matches'], [[0, 1], []])
        self.assertEqual(self.package['addition_candidates'], [2])
        self.assertEqual(list(batches(self.package))[0]['editable_ids'], [0])

    def test_local_edit_and_preservation(self):
        output = [dict(x) for x in self.package['whisper']['cues']]
        records = apply_proposals(self.package, next(batches(self.package)), self.proposal(), output, set())
        self.assertTrue(records[0]['accepted'])
        self.assertEqual(output[0]['text'], '今日は四月一日さんと遊びます')
        self.assertEqual(output[1]['text'], '消さない台詞')
        self.assertEqual(output[0]['timing'], self.package['whisper']['cues'][0]['timing'])

    def test_invalid_edits_rejected(self):
        for field, value in [('whisper_id', -1), ('qwen_id', 2), ('new', ''),
                             ('new', '不存在名字'), ('old', '今日は渡瀬さんと遊びます')]:
            with self.subTest(field=field, value=value):
                proposal = self.proposal()
                proposal['edits'][0][field] = value
                output = [dict(x) for x in self.package['whisper']['cues']]
                records = apply_proposals(self.package, next(batches(self.package)), proposal, output, set())
                self.assertFalse(records[0]['accepted'])
                self.assertEqual(output, self.package['whisper']['cues'])

    def test_add_only_exact_uncovered_cue(self):
        output = [dict(x) for x in self.package['whisper']['cues']]
        batch = list(batches(self.package))[-1]
        result = {'edits': [], 'additions': [{'qwen_id': 0}, {'qwen_id': 2}, {'qwen_id': 2}], 'uncertain': []}
        records = apply_proposals(self.package, batch, result, output, set())
        self.assertEqual([x['accepted'] for x in records], [False, True, False])
        self.assertEqual(output[-1], self.package['qwen']['cues'][2])

    def test_boilerplate_addition_rejected(self):
        self.package['qwen']['cues'][2]['text'] = 'ご視聴ありがとうございました'
        result = {'edits': [], 'additions': [{'qwen_id': 2}], 'uncertain': []}
        records = apply_proposals(self.package, list(batches(self.package))[-1], result,
                                  [dict(x) for x in self.package['whisper']['cues']], set())
        self.assertFalse(records[0]['accepted'])

    def test_export_and_complete(self):
        before = self.w.read_bytes()
        dest = export_package(self.package, self.root)
        self.assertNotIn(str(self.root), (dest/'review_package.json').read_text(encoding='utf-8'))
        status, target = reconcile(self.package, dest, lambda b: self.proposal() if b['editable_ids'] else
                                  {'edits': [], 'additions': [], 'uncertain': []}, threading.Event(), lambda *a: None)
        self.assertEqual(status, 'complete')
        self.assertIn('消さない台詞', target.read_text(encoding='utf-8-sig'))
        self.assertEqual(before, self.w.read_bytes())

    def test_failure_and_cancel_are_partial(self):
        for cancelled in (False, True):
            dest = export_package(self.package, self.root)
            event = threading.Event()
            if cancelled:
                event.set()
            status, target = reconcile(self.package, dest, lambda b: None, event, lambda *a: None)
            self.assertEqual(status, 'cancelled' if cancelled else 'failed')
            self.assertIn('_partial', target.name)
            self.assertIn('渡瀬', target.read_text(encoding='utf-8-sig'))

    def test_url_validation(self):
        self.assertEqual(endpoint_url('https://api.openai.com/v1/'), 'https://api.openai.com/v1/chat/completions')
        for url in ['http://remote/v1', 'https://name:secret@host/v1', 'https://host/v1?key=abc']:
            with self.assertRaises(ValueError):
                endpoint_url(url)

    def test_equivalent_text_skips_api(self):
        self.package['qwen']['cues'][0]['text'] = '今日は渡瀬さんと'
        work = list(batches(self.package))
        self.assertEqual(len(work), 1)
        self.assertFalse(work[0]['editable_ids'])

    def test_mocked_api(self):
        response = json.dumps({'choices': [{'finish_reason': 'stop',
                              'message': {'content': json.dumps(self.proposal())}}]}).encode()
        with patch('dual_model_review.request.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = response
            self.assertEqual(call_api('https://example.test/v1', 'secret', 'configured-model', {}), self.proposal())
            req = opener.return_value.open.call_args.args[0]
            self.assertEqual(json.loads(req.data)['response_format'], {'type': 'json_object'})

    def test_truncated_response_not_applied(self):
        response = json.dumps({'choices': [{'finish_reason': 'length',
                              'message': {'content': json.dumps(self.proposal())}}]}).encode()
        with patch('dual_model_review.request.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = response
            with self.assertRaises(ValueError):
                call_api('https://example.test/v1', 'secret', 'configured-model', {})

    def test_unsorted_timestamps_and_overlapping_long_cue(self):
        self.w.write_text('1\n00:00:10,000 --> 00:00:11,000\n短句\n\n'
                          '2\n00:00:00,000 --> 00:00:20,000\n长句\n', encoding='utf-8')
        package = prepare_package(self.w, self.q)
        self.assertEqual(package['matches'], [[], [0, 1, 2]])
        self.assertEqual(package['addition_candidates'], [])

    def test_zero_duration_whisper_preserved_and_reported(self):
        self.w.write_text('1\n00:00:45,560 --> 00:00:45,560\n保留原话\n', encoding='utf-8')
        package = prepare_package(self.w, self.q)
        self.assertEqual(package['matches'], [[]])
        self.assertEqual(package['warnings'][0]['source'], 'Whisper')
        destination = export_package(package, self.root)
        self.assertTrue((destination / '时间轴提醒.txt').exists())
        status, target = reconcile(package, destination,
                                  lambda b: {'edits': [], 'additions': [], 'uncertain': []},
                                  threading.Event(), lambda *args: None)
        self.assertEqual(status, 'complete')
        self.assertIn('00:00:45,560 --> 00:00:45,560\n保留原话', target.read_text(encoding='utf-8-sig'))
        report = json.loads((destination / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['changes'][0]['type'], 'zero_duration')

    def test_zero_duration_qwen_not_used_or_added(self):
        self.q.write_text('1\n00:00:01,560 --> 00:00:01,560\n四月一日\n\n'
                          '2\n00:00:45,560 --> 00:00:45,560\n保留原话\n', encoding='utf-8')
        package = prepare_package(self.w, self.q)
        self.assertEqual(package['matches'], [[], []])
        self.assertEqual(package['addition_candidates'], [])
        self.assertEqual(len(package['warnings']), 2)
        self.assertEqual(len(package['qwen']['cues']), 2)
        self.assertEqual(list(batches(package)), [])

    def test_reversed_time_still_rejected(self):
        self.q.write_text('1\n00:00:46,560 --> 00:00:45,560\n逆序\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '无效时间段'):
            prepare_package(self.w, self.q)


if __name__ == '__main__':
    unittest.main()
