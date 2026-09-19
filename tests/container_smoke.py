"""Build images first, then verify production API/worker containers share durable jobs."""

import json
import subprocess
import time
import urllib.request
from uuid import uuid4


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def main() -> None:
    suffix = uuid4().hex[:10]
    volume, api, worker = (
        f"personlogy-smoke-{kind}-{suffix}" for kind in ("data", "api", "worker")
    )
    created = []
    try:
        docker("volume", "create", volume)
        common = [
            "--mount",
            f"source={volume},target=/workspace/data",
            "-e",
            "PKS_SQLITE_PATH=/workspace/data/smoke.sqlite3",
            "-e",
            "PKS_PDF_STORAGE_ROOT=/workspace/data/files",
            "-e",
            "PKS_LLM_PROVIDER=none",
            "-e",
            "PKS_STORAGE_BACKEND=sqlite",
            "-e",
            "PKS_QUEUE_BACKEND=sqlite",
            "-e",
            "PKS_QUEUE_POLL_INTERVAL_SECONDS=0.1",
        ]
        docker(
            "run",
            "-d",
            "--name",
            api,
            "-p",
            "127.0.0.1::8000",
            *common,
            "personlogy-optimization-api",
        )
        created.append(api)
        address = docker("port", api, "8000/tcp").splitlines()[0]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path: str, payload=None):
            data = json.dumps(payload).encode() if payload is not None else None
            req = urllib.request.Request(
                f"http://{address}/v1{path}",
                data=data,
                headers={"Content-Type": "application/json", "X-Idempotency-Key": suffix},
            )
            with opener.open(req, timeout=3) as response:
                return json.load(response)

        deadline = time.monotonic() + 30
        while True:
            try:
                health = request("/health/ready")
                assert health["status"] == "ok"
                break
            except (OSError, AssertionError):
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.25)
        docker("run", "-d", "--name", worker, *common, "personlogy-optimization-worker")
        created.append(worker)
        job = request("/jobs", {"kind": "container.smoke", "payload": {}})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = request(f"/jobs/{job['id']}")
            if current["status"] == "succeeded":
                print(
                    json.dumps(
                        {
                            "status": "passed",
                            "api": api,
                            "worker": worker,
                            "job_id": job["id"],
                            "attempt": current["attempt"],
                        }
                    )
                )
                return
            time.sleep(0.25)
        raise AssertionError("container worker did not complete the API job")
    finally:
        for name in reversed(created):
            subprocess.run(["docker", "logs", "--tail", "5", name], check=False)
            subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL)
        subprocess.run(["docker", "volume", "rm", volume], check=False, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
