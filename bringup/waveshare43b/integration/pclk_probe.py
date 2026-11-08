#!/usr/bin/env python3
"""Read-only numeric /monitor/status sampler for physical PCLK trials.

No printer commands, firmware upload, capture or configuration changes.
CPU render counters do not establish physical LCD correctness.
"""

import argparse
import datetime
import ipaddress
import json
from pathlib import Path
import time
import urllib.request

FIELDS = frozenset(
    '''configured wifi_connected mqtt_connected mqtt_attempts
mqtt_last_rc messages valid_reports malformed_reports mqtt_connect_ms pushall_sent
first_data_delay_ms first_core_delay_ms uptime_ms reset_reason
loop_stack_high_water_mark free_heap min_free_heap free_psram display_diag_version
display_requested_pclk_hz display_bounce_pixels display_dcache_line_bytes
display_frames display_last_render_us display_max_render_us
display_legacy_fill_probes display_legacy_fill_mismatches display_fill_readback_errors
has_useful_data useful_age_s data_fresh'''.split()
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ip', required=True)
    ap.add_argument('--mhz', type=int, choices=(12, 14, 16), required=True)
    ap.add_argument('--seconds', type=int, default=180)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    address = ipaddress.IPv4Address(args.ip)
    if not address.is_private or address.is_unspecified or address.is_multicast:
        ap.error('Use the verified local panel IPv4 address.')
    if not 10 <= args.seconds <= 3600 or args.output.exists():
        ap.error('Duration must be 10..3600 seconds and output must be new.')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    report = {
        'started': datetime.datetime.now().astimezone().isoformat(),
        'requested_pclk_hz': args.mhz * 1000000,
        'samples': [],
        'errors': [],
        'physical_lcd': 'PENDING_USER',
        'heavy_mqtt': 'NOT_ESTABLISHED',
    }
    start = time.monotonic()
    with args.output.open('x') as output:
        for i in range(args.seconds // 5 + 1):
            time.sleep(max(0, start + 5 * i - time.monotonic()))
            try:
                with opener.open(f'http://{address}/monitor/status', timeout=4) as response:
                    raw = response.read(8193)
                if len(raw) > 8192:
                    raise ValueError('Response too large')
                data = json.loads(raw)
                if data.get('display_requested_pclk_hz') != report['requested_pclk_hz']:
                    raise ValueError('Wrong or unidentified PCLK variant')
                sample = {
                    k: data[k]
                    for k in FIELDS
                    if k in data and (data[k] is None or type(data[k]) in (int, bool))
                }
                report['samples'].append(
                    {'elapsed_s': round(time.monotonic() - start, 3), 'status': sample}
                )
                if i % 6 == 0:
                    print(json.dumps(sample), flush=True)
            except Exception as error:
                report['errors'].append(
                    {'elapsed_s': round(time.monotonic() - start, 3), 'type': type(error).__name__}
                )
            output.seek(0)
            json.dump(report, output, indent=2)
            output.truncate()
            output.flush()
    print(f'Saved {len(report["samples"])} samples; {len(report["errors"])} errors.')


if __name__ == '__main__':
    main()
