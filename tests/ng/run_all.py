"""Run every NG test module in one go and write the result to a file.

Used for the session log; PowerShell swallows the unittest output when it is piped, and the
full run takes longer than one command's timeout.
"""
import glob
import io
import os
import sys
import traceback
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "full_run.txt")

names = [os.path.basename(p)[:-3] for p in sorted(glob.glob(os.path.join(HERE, "test_*.py")))]
handle = io.open(OUT, "w", encoding="utf-8")
handle.write("modules: %d\n%s\n\n" % (len(names), ", ".join(names)))
try:
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=1, stream=handle).run(suite)
    handle.write("\nran=%d failures=%d errors=%d skipped=%d\n"
                 % (result.testsRun, len(result.failures), len(result.errors), len(result.skipped)))
except Exception:
    handle.write(traceback.format_exc())
handle.close()
