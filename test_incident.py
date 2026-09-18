import unittest

from app import ErpMonolith


class OomIncidentTest(unittest.TestCase):
    def test_tuesday_batch_retains_memory_across_runs(self):
        service = ErpMonolith(leak_enabled=True)

        service.run_tuesday_batch(rows=100)
        service.run_tuesday_batch(rows=100)

        self.assertEqual(service.metrics()["retained_batches"], 2)
        self.assertEqual(service.metrics()["retained_rows"], 200)

    def test_fixed_batch_releases_completed_state(self):
        service = ErpMonolith(leak_enabled=False)

        service.run_tuesday_batch(rows=100)
        service.run_tuesday_batch(rows=100)

        self.assertEqual(service.metrics()["retained_batches"], 0)
        self.assertEqual(service.metrics()["retained_rows"], 0)


if __name__ == "__main__":
    unittest.main()