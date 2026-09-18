#!/usr/bin/env python3
"""Drive the lab toward OOM while printing the signals that explain why."""

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(url, method="GET", body=None, headers=None):
    encoded_body = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=encoded_body, headers=headers or {}, method=method)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def run_batch(base_url, rows):
    return request_json(
        f"{base_url}/admin/run-batch",
        method="POST",
        headers={"X-Batch-Rows": str(rows)},
    )


def send_scan(base_url, worker_id):
    return request_json(
        f"{base_url}/scan",
        method="POST",
        body={"sku": f"LOAD-{worker_id}", "quantity": 1},
        headers={"Content-Type": "application/json"},
    )


def docker_memory(container_name):
    if shutil.which("docker") is None:
        return "docker CLI unavailable"
    result = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}} memory={{.MemUsage}}",
            container_name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or result.stderr.strip() or "container not found"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--rows", type=int, default=25000)
    parser.add_argument("--batches", type=int, default=100)
    parser.add_argument("--scan-workers", type=int, default=0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--container", default="pi-1-erp-1")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    try:
        print("Initial metrics:", request_json(f"{base_url}/metrics"), flush=True)
    except (HTTPError, URLError) as error:
        print(f"Cannot reach {base_url}: {error}", file=sys.stderr)
        return 1

    scan_executor = ThreadPoolExecutor(max_workers=args.scan_workers) if args.scan_workers else None
    try:
        for batch_number in range(1, args.batches + 1):
            started = time.monotonic()
            result = run_batch(base_url, args.rows)
            metrics = request_json(f"{base_url}/metrics")
            elapsed = time.monotonic() - started
            print(
                f"batch={batch_number}/{args.batches} processed={result['processed']} "
                f"elapsed={elapsed:.2f}s metrics={metrics}",
                flush=True,
            )
            if scan_executor:
                list(scan_executor.map(lambda worker: send_scan(base_url, worker), range(args.scan_workers)))
            print(f"container: {docker_memory(args.container)}", flush=True)
            time.sleep(args.interval)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        print(f"Load stopped because the service became unavailable: {error}", file=sys.stderr)
        print("This is the expected point at which the container may have hit its memory limit.")
        return 2
    finally:
        if scan_executor:
            scan_executor.shutdown(wait=False, cancel_futures=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())