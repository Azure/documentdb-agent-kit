"""Run the exact JavaScript guidance examples without a database or model."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node.js is required for JavaScript snippet contracts")
class ApiGuidanceContracts(unittest.TestCase):
    def test_markdown_examples(self):
        """The Node runner fails if any extracted-example assertion fails."""
        scenario = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [shutil.which("node"), "--test", str(scenario / "test-snippets.cjs")],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
