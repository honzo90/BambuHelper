"""WebUI keeps at most two requests to the panel in flight (internal RAM, see app.js)."""

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

HARNESS = r"""
const fs = require('fs');
let inflight = 0, peak = 0;
const timers = [];
global.location = {origin: 'http://10.0.0.5'};
// The 8 s hang guard runs on demand; everything else completes on the next tick.
global.setTimeout = (fn, ms) => { timers.push(fn); return timers.length; };
global.clearTimeout = () => {};
global.window = {fetch: (u) => {
  inflight++; peak = Math.max(peak, inflight);
  return new Promise((resolve) => { if (u !== '/hang') setImmediate(() => { inflight--; resolve(u); }); });
}};
eval(fs.readFileSync(process.argv[1], 'utf8').split('/* ============ Loader')[0]);
const f = window.fetch;
(async () => {
  const urls = ['/a', '/b', '/c', '/d', '/e', 'http://10.0.0.5/f'];
  const got = await Promise.all(urls.map((u) => f(u)));
  if (JSON.stringify(got) !== JSON.stringify(urls)) throw new Error('order ' + got);
  if (peak !== 2) throw new Error('peak ' + peak);
  peak = 0; inflight = 0;
  const ext = f('https://api.github.com/repos/x');      // other host: not queued
  if (peak !== 1) throw new Error('external not passed through');
  inflight = 0; peak = 0;
  f('/hang'); f('/hang');
  let after = false; f('/after').then(() => { after = true; });
  await new Promise((r) => setImmediate(r));
  if (after) throw new Error('third request ran while two hang');
  timers.splice(0).forEach((fn) => fn());                // 8 s elapse
  await new Promise((r) => setImmediate(() => setImmediate(r)));
  if (!after) throw new Error('hung requests did not free their slots');
  console.log('OK');
})().catch((e) => { console.error(e.message); process.exit(1); });
"""


@unittest.skipUnless(shutil.which("node"), "Node.js not on PATH")
class RequestLimiter(unittest.TestCase):
    def test_limits_panel_requests_to_two(self):
        result = subprocess.run(
            ["node", "-e", HARNESS, "--", str(ROOT / "web" / "app.js")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
