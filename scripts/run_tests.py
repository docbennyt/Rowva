import subprocess
import os

cwd = os.path.dirname(os.path.dirname(__file__))
result = subprocess.run(["py", "-m", "pytest", "tests/", "-q", "--tb=short"], cwd=cwd, capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:")
    print(result.stderr)
print("Exit code:", result.returncode)
