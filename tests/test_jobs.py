import unittest
from backend.jobs import JobManager, JobCancelled
class JobTests(unittest.TestCase):
    def test_complete(self):
        m=JobManager(); j=m.create(); m.update(j,'work',30); m.complete(j,{'text':'ok'}); self.assertEqual(m.get(j)['progress'],100)
    def test_cancel(self):
        m=JobManager(); j=m.create(); self.assertTrue(m.cancel(j)); self.assertRaises(JobCancelled,m.check_cancelled,j); m.mark_cancelled(j); self.assertEqual(m.get(j)['status'],'cancelled')
