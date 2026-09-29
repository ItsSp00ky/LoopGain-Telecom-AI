"""Every page must run without raising, whether or not the backend APIs are up.

Does not require GIS/KPI/churn to be running: a page reporting a service
"unreachable" is the expected degraded path (see Home.py's docstring), not a
test failure. A Python exception during the script run is the failure this
guards against.
"""

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_DIR = Path(__file__).resolve().parent
PAGES = [
    "Home.py",
    "pages/1_GIS_Planning.py",
    "pages/2_Network_KPI.py",
    "pages/3_Congestion_Steering.py",
    "pages/4_Customer_Churn.py",
    "pages/5_Assistants.py",
]


class PlatformShellSmokeTests(unittest.TestCase):
    def test_every_page_runs_without_raising(self):
        for page in PAGES:
            with self.subTest(page=page):
                at = AppTest.from_file(str(APP_DIR / page))
                at.run(timeout=30)
                self.assertEqual([str(e) for e in at.exception], [])


if __name__ == "__main__":
    unittest.main()
