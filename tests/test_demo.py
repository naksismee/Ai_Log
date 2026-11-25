import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = tempfile.TemporaryDirectory(prefix='ai-log-tests-')
os.environ.update(AI_LOG_ANALYZER_DEMO='true', AI_LOG_ANALYZER_DATA_DIR=DATA.name, ENABLE_SCHEDULER='false')
os.environ.pop('OPENAI_API_KEY', None)
os.environ.pop('SLACK_WEBHOOK_URL', None)
sys.path.insert(0, str(ROOT / 'backend'))

from fastapi.testclient import TestClient
from app.main import app


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_sample_analysis_history_matching_and_search(self):
        sample = self.client.get('/sample-log')
        self.assertEqual(sample.status_code, 200)
        response = self.client.post('/analyze-log?alert=false', files={'file': ('recruiter.log', sample.content, 'text/plain')})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['issues_found'], 33)
        self.assertEqual(sorted(cluster['count'] for cluster in result['clusters']), [3, 6, 24])
        self.assertEqual(result['trends']['2026-01-15 09:00'], 24)
        self.assertEqual(self.client.get(f"/runs/{result['run_id']}").status_code, 200)
        recent = self.client.get('/recent-runs').json()['items']
        self.assertIn(result['run_id'], [item['id'] for item in recent])
        repeated = self.client.post('/analyze-log?alert=false', files={'file': ('recruiter.log', sample.content, 'text/plain')}).json()
        self.assertTrue(all(cluster['known_issue'] for cluster in repeated['clusters']))
        search = self.client.get('/semantic-search', params={'q': 'Database connection refused'})
        self.assertEqual(search.status_code, 200)
        self.assertTrue(search.json()['hits'])

    def test_health_and_validation(self):
        self.assertEqual(self.client.get('/health').json(), {'status': 'ok', 'mode': 'demo'})
        self.assertEqual(self.client.post('/analyze-log?threshold=2', files={'file': ('test.log', b'ERROR failed', 'text/plain')}).status_code, 400)
        self.assertEqual(self.client.post('/analyze-log', files={'file': ('test.log', b'', 'text/plain')}).status_code, 400)
        self.assertEqual(self.client.get('/semantic-search', params={'q': ' '}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
