"""Exercise the release gate against the staged bytes, not only filenames."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['clean', 'log', 'staged_secret', 'working_secret'])
def test_source_gate(tmp_path, case):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / 'scripts').mkdir()
    shutil.copy2(root / 'scripts/check_source.py', tmp_path / 'scripts/check_source.py')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    file = tmp_path / ('runtime.log' if case == 'log' else 'safe.txt')
    token = 'ghp_' + 'A' * 40
    file.write_text(token if case == 'staged_secret' else 'synthetic source')
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True)
    if case == 'staged_secret':
        file.write_text('clean working copy must not hide staged secret')
    if case == 'working_secret':
        file.write_text(token)
    result = subprocess.run(
        [sys.executable, str(tmp_path / 'scripts/check_source.py')],
        capture_output=True, text=True, check=False,
    )
    assert (result.returncode == 0) == (case == 'clean')
    assert token not in result.stdout + result.stderr
