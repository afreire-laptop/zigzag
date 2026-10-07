"""Checks a running container stack through its public entry point. Standard library only.

python3 scripts/smoke_check.py http://127.0.0.1:8080 [create|verify PROJECT_ID]
"""

import json
import sys
import time
import urllib.error
import urllib.request


def request(base: str, path: str, body: object | None = None) -> tuple[int, dict[str, str], bytes]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method="POST" if body is not None else "GET")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, {k.lower(): v for k, v in res.headers.items()}, res.read()
    except urllib.error.HTTPError as err:
        return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()


def check(condition: bool, message: str) -> None:
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        sys.exit(1)


def create(base: str) -> str:
    status, headers, body = request(base, "/healthz")
    check(status == 200, "nginx health endpoint answers")
    status, headers, body = request(base, "/")
    check(status == 200 and b'<div id="root">' in body, "the app document is served")
    check("default-src 'self'" in headers.get("content-security-policy", ""), "a content security policy is sent")
    check(headers.get("cache-control") == "no-cache", "the app document is revalidated")
    asset = body.split(b'src="/assets/')[1].split(b'"')[0].decode()
    status, headers, _ = request(base, f"/assets/{asset}")
    check(status == 200 and "immutable" in headers.get("cache-control", ""), "hashed assets are cached for good")
    status, _, body = request(base, "/review/deep/link")
    check(status == 200 and b'<div id="root">' in body, "unknown app paths fall back to the app")
    status, headers, body = request(base, "/api/nothing-here")
    check(
        status == 404 and headers.get("content-type", "").startswith("application/problem+json"),
        "API errors pass through instead of the app fallback",
    )
    status, _, body = request(base, "/api/status")
    fixtures = json.loads(body)["fixtures"]
    check(status == 200 and fixtures is not None, "the API runs in fixture mode by default")
    brief = fixtures["briefs"][0]["text"]
    status, headers, body = request(base, "/api/projects", {"brief": brief})
    operation = json.loads(body)
    check(
        status == 202 and headers.get("location") == f"/api/operations/{operation['id']}",
        "model work starts as an operation",
    )
    status, headers, body = request(base, f"/api/operations/{operation['id']}/events")
    check(headers.get("content-type", "").startswith("text/event-stream"), "notifications stream as server-sent events")
    events = [json.loads(line[6:]) for line in body.decode().splitlines() if line.startswith("data: ")]
    check(events[-1]["status"] == "succeeded", "the operation reaches its persisted end over SSE")
    project_id = events[-1]["result"]["projectId"]
    status, _, body = request(base, "/api/projects/current")
    check(json.loads(body)["project"]["id"] == project_id, "the new project is current")
    return project_id


def verify(base: str, project_id: str) -> None:
    deadline = time.monotonic() + 60
    while True:
        try:
            status, _, body = request(base, "/api/projects/current")
            if status == 200:
                break
        except OSError:
            pass
        if time.monotonic() > deadline:
            check(False, "the stack answers after the restart")
        time.sleep(1)
    status, _, body = request(base, f"/api/projects/{project_id}")
    check(status == 200 and json.loads(body)["id"] == project_id, "the project survived the restart")


if __name__ == "__main__":
    base_url, action = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "create"
    if action == "create":
        print(create(base_url))
    else:
        verify(base_url, sys.argv[3])
