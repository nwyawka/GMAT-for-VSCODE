from pathlib import Path
import tempfile
import unittest

from gmat_headless.results import read_table
from gmat_headless.runner import GmatError, find_startup_file, prepare_run


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_prepare_run_redirects_outputs(self) -> None:
        bin_dir = self.root / "install" / "bin"
        bin_dir.mkdir(parents=True)
        executable = bin_dir / "GmatConsole"
        executable.write_text("", encoding="utf-8")
        executable.chmod(0o755)
        (self.root / "install" / "gmat_startup_file.txt").write_text(
            "ROOT_PATH = ../\nOUTPUT_PATH = ../output/\nLOG_FILE = OUTPUT_PATH/GmatLog.txt\n",
            encoding="utf-8",
        )
        script = self.root / "mission.script"
        script.write_text("BeginMissionSequence;\n", encoding="utf-8")
        run = prepare_run(script, executable, self.root / "runs")
        self.assertEqual(run.script.read_text(), script.read_text())
        self.assertIn(f"OUTPUT_PATH              = {run.output_dir}/", run.startup_file.read_text())

    def test_missing_startup_file_is_clear(self) -> None:
        executable = self.root / "GmatConsole"
        executable.write_text("")
        with self.assertRaisesRegex(GmatError, "startup"):
            find_startup_file(executable)

    def test_read_csv_table(self) -> None:
        report = self.root / "report.csv"
        report.write_text("time,x,y\n0,1,2\n1,3,4\n", encoding="utf-8")
        self.assertEqual(read_table(report), (["time", "x", "y"], [["0", "1", "2"], ["1", "3", "4"]]))


if __name__ == "__main__":
    unittest.main()

