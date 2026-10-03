import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from scripts.check_daily_health import aware_time, check_health


class DailyHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        (self.root / '.runtime/scheduled').mkdir(parents=True)
        self.report = self.root / 'data/2026-10-02.json'
        self.tc = self.root / 'data/smm_copper_concentrate_index_2026.csv'
        self.state_path = self.root / '.runtime/scheduled/2026-10-02.state.json'
        self.now = aware_time('2026-10-03T12:00:00+08:00')

    def success(self):
        self.report.write_text('{"date":"2026-10-02"}', encoding='utf-8')
        self.tc.write_text('test TC bytes', encoding='utf-8')
        state = {'report_date': '2026-10-02', 'status': 'success',
                 'completed_at': '2026-10-03T10:00:00+08:00', 'verified_main_sha': 'a' * 40,
                 'verified_report_sha256': hashlib.sha256(self.report.read_bytes()).hexdigest(),
                 'verified_tc_sha256': hashlib.sha256(self.tc.read_bytes()).hexdigest(),
                 'stages': {key: {'status': 'success'} for key in
                            ('report', 'validate:content', 'typecheck', 'python-tests', 'npm-test', 'build', 'publication')}}
        self.save(state)
        return state

    def save(self, state):
        self.state_path.write_text(json.dumps(state), encoding='utf-8')

    def test_frozen_beijing_date_boundary_and_deadline(self):
        cases = [('2026-10-02T22:59:59Z', '2026-10-01', True),
                 ('2026-10-02T23:00:00Z', '2026-10-02', False),
                 ('2026-10-03T02:59:59Z', '2026-10-02', False),
                 ('2026-10-03T03:00:00Z', '2026-10-02', True),
                 ('2026-12-31T23:00:00Z', '2026-12-31', False),
                 ('2028-02-29T23:00:00Z', '2028-02-29', False)]
        for stamp, date, alert in cases:
            with self.subTest(stamp=stamp):
                result = check_health(self.root, aware_time(stamp))
                self.assertEqual(result['report_date'], date)
                self.assertEqual(result['alert'], alert)

    def test_success_requires_matching_local_inputs_and_stages(self):
        state = self.success()
        self.assertFalse(check_health(self.root, self.now)['alert'])
        self.report.write_text('{"date":"2026-10-02", "correction":true}', encoding='utf-8')
        self.assertEqual(check_health(self.root, self.now)['status'], 'verification_required')
        state = self.success()
        self.tc.write_text('changed TC', encoding='utf-8')
        self.assertTrue(check_health(self.root, self.now)['alert'])
        state = self.success()
        del state['stages']['publication']
        self.save(state)
        self.assertEqual(check_health(self.root, self.now)['status'], 'verification_required')

    def test_missing_state_does_not_mean_ai_never_started(self):
        self.report.write_text('{"date":"2026-10-02"}', encoding='utf-8')
        result = check_health(self.root, self.now)
        self.assertEqual(result['status'], 'verification_required')
        self.assertIn('AI start is unknown', result['reason'])

    def test_legacy_success_is_not_hash_verified(self):
        state = self.success()
        del state['verified_report_sha256']
        self.save(state)
        self.assertEqual(check_health(self.root, self.now)['status'], 'verification_required')
        self.report.unlink()
        self.assertEqual(check_health(self.root, self.now)['status'], 'missing_report')

    def test_failed_corrupt_stale_and_future_states_alert(self):
        state = self.success()
        state.update(status='failed', error='CI failed')
        self.save(state)
        self.assertEqual(check_health(self.root, self.now)['status'], 'failed')
        state['status'] = 'running'
        self.save(state)
        self.assertEqual(check_health(self.root, self.now)['status'], 'overdue')
        self.assertFalse(check_health(self.root, aware_time('2026-10-03T08:00:00+08:00'))['alert'])
        state = self.success()
        state['completed_at'] = '2026-10-04T10:00:00+08:00'
        self.save(state)
        self.assertEqual(check_health(self.root, self.now)['status'], 'invalid_evidence')
        for value in ('{', 'null', '[]', '{"status":"success"}'):
            self.state_path.write_text(value, encoding='utf-8')
            self.assertEqual(check_health(self.root, self.now)['status'], 'invalid_evidence')
            self.assertEqual(self.state_path.read_text(encoding='utf-8'), value)
            self.assertEqual(check_health(self.root, aware_time('2026-10-03T08:00:00+08:00'))['status'], 'invalid_evidence')

    def test_invalid_clock_and_grace_rejected(self):
        with self.assertRaises(ValueError):
            aware_time('2026-10-03T12:00:00')
        with self.assertRaises(ValueError):
            check_health(self.root, datetime(2026, 10, 3))
        for value in (0, -1, 1441, True):
            with self.assertRaises(ValueError):
                check_health(self.root, self.now, value)


if __name__ == '__main__':
    unittest.main()
