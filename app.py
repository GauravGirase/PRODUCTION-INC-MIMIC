import json
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ErpMonolith:
    """Small stand-in for an ERP process that owns scan and batch state."""

    def __init__(self, leak_enabled=True):
        self.leak_enabled = leak_enabled
        self.retained_batches = []
        self.scans_processed = 0
        self.batches_run = 0
        self.lock = threading.Lock()

    def record_scan(self, sku, quantity):
        with self.lock:
            self.scans_processed += 1
        return {"sku": sku, "quantity": quantity, "accepted": True}

    def run_tuesday_batch(self, rows=5000):
        batch_rows = [
            {
                "sku": f"SKU-{index:06d}",
                "warehouse": "WH-01",
                "available": index % 17,
                "reconciliation_note": "inventory reconciliation " * 20,
            }
            for index in range(rows)
        ]
        with self.lock:
            self.batches_run += 1
            if self.leak_enabled:
                self.retained_batches.append(batch_rows)
        return len(batch_rows)

    def metrics(self):
        with self.lock:
            retained_rows = sum(len(batch) for batch in self.retained_batches)
            return {
                "scans_processed": self.scans_processed,
                "batches_run": self.batches_run,
                "retained_batches": len(self.retained_batches),
                "retained_rows": retained_rows,
            }


ERP = ErpMonolith(leak_enabled=os.getenv("ERP_LEAK_ENABLED", "true").lower() == "true")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_json(200, {"status": "ok"})
        elif self.path == "/metrics":
            self.send_json(200, ERP.metrics())
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/scan":
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            self.send_json(200, ERP.record_scan(payload.get("sku", "unknown"), payload.get("quantity", 0)))
        elif self.path == "/admin/run-batch":
            rows = int(self.headers.get("X-Batch-Rows", "5000"))
            self.send_json(200, {"processed": ERP.run_tuesday_batch(rows)})
        else:
            self.send_json(404, {"error": "not found"})

    def send_json(self, status, body):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format_string, *args):
        return


def scheduler(stop_event):
    last_run = None
    while not stop_event.is_set():
        now = datetime.now()
        run_key = now.strftime("%Y-%m-%d")
        if now.weekday() == 1 and now.hour == 9 and last_run != run_key:
            ERP.run_tuesday_batch()
            last_run = run_key
        stop_event.wait(15)


def main():
    port = int(os.getenv("PORT", "8080"))
    stop_event = threading.Event()
    threading.Thread(target=scheduler, args=(stop_event,), daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"ERP monolith listening on :{port}; leak={ERP.leak_enabled}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        stop_event.set()
        server.shutdown()


if __name__ == "__main__":
    main()