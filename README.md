# Tuesday 09:00 ERP OOM lab

This lab reproduces a legacy monolith that crashes at a fixed weekly time even though traffic and deployments are unchanged. The scheduled Tuesday batch retains every completed batch in `retained_batches`; the worker scan endpoint is collateral damage when the process is restarted.

## Run the cheapest check

```powershell
python -m unittest -v
```

The first test proves that repeated batch execution grows retained state. The second is the control case: completed state is discarded when the leak is disabled.

## Run it locally

```powershell
$env:ERP_LEAK_ENABLED = "true"
python app.py
```

In another terminal, run the batch repeatedly and observe the application-owned counter:

```powershell
Invoke-RestMethod -Method Post http://localhost:8080/admin/run-batch -Headers @{"X-Batch-Rows"="5000"}
Invoke-RestMethod http://localhost:8080/metrics
```

The real incident investigation should correlate this counter with RSS/heap metrics, GC activity, restart counts, and the scheduler's exact timestamp. Traffic dashboards alone do not disprove a scheduled leak.

## 3. Drive the lab toward OOM

Keep `docker compose up --build` running in one terminal. In a second terminal, run the load driver:

```powershell
python load_oom.py --rows 25000 --batches 100 --interval 1
```

The driver prints `retained_rows` from the application and samples Docker's memory usage after every batch. To add worker scan traffic while the batch runs:

```powershell
python load_oom.py --rows 25000 --batches 100 --scan-workers 20
```

The scan requests are collateral traffic; the growing `retained_rows` counter is the OOM cause. With the Compose limit of 256 MB, the service will eventually restart or reject requests. Observe the restart with:

```powershell
docker compose ps
docker compose logs --tail=100
```

## Confirm the repair

```powershell
$env:ERP_LEAK_ENABLED = "false"
python app.py
```

Run the batch several times. `retained_batches` and `retained_rows` must remain zero while `/scan` continues to return HTTP 200.

## Build and deploy

```powershell
docker build -t example/erp-monolith:oom-lab .
docker compose up --build
kubectl apply -f deployment.yaml
kubectl rollout status deployment/erp-monolith
kubectl get pods -l app=erp-monolith
```

The memory limit intentionally makes the failure visible. In a real rollout, ship the fix with `ERP_LEAK_ENABLED=false`, use a canary, and watch worker scan success rate, pod restarts, memory working set, and batch duration before increasing traffic.

## Incident response sequence

1. Protect warehouse operations: pause the Tuesday batch, route scans to a healthy replica, and preserve logs and heap evidence before restarts.
2. Prove timing: compare scheduler logs, process RSS, GC or heap snapshots, restart events, and scan traffic around 09:00 for at least two Tuesdays.
3. Identify retention: take a heap profile during the rise and inspect collections retaining completed batch rows, caches, queues, or database results.
4. Mitigate: disable the batch or cap its chunk size, restart one unhealthy replica at a time, and keep readiness separate from liveness.
5. Fix: process batches in bounded chunks, release references after commit, and add a regression test for stable memory over repeated runs.
6. Deploy: canary the fix before 09:00 Tuesday, verify memory slope rather than only a point-in-time value, and keep rollback available.

## Quick testing on EC2
- Launch the EC2 (ubuntu)
- ssh
- run the script to setup
```bash
chmod +x ./setup_ec2.sh
sudo bash setup_ec2.sh
```
- check the container stat
```bash
sudo docker stats
```
