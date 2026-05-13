"""Test all API endpoints from inside the container."""

import urllib.request
import urllib.parse
import json
import uuid


def test(method, path, data=None, headers=None, timeout=30):
    """Send an HTTP request to the API and return (status_code, parsed_body)."""
    url = f"http://localhost:8000{path}"
    req = urllib.request.Request(url, method=method)
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {"raw": str(e)}
        return e.code, body
    except Exception as ex:
        return 0, {"error": str(ex)}


def ok(result):
    """Return True if the HTTP status code is in the 2xx range."""
    return 200 <= result[0] < 300


def check(name, result, detail=""):
    """Print a test result line with status and optional detail."""
    status = "OK" if ok(result) else "FAIL"
    print(f"  {name:30s} -> {result[0]:3d} {status}  {detail}")


print("=" * 60)
print("API ENDPOINT TEST SUITE")
print("=" * 60)

# ---- Public ----
print("\n--- Public Endpoints ---")
check("GET /", test("GET", "/"), "root")
check("GET /health", test("GET", "/health"), "health")
check("GET /api/v1/health", test("GET", "/api/v1/health"), "api health")

# ---- Auth ----
print("\n--- Auth Endpoints ---")
email = f"fulltest{uuid.uuid4().hex[:6]}@test.com"
s, b = test("POST", "/api/v1/auth/register", {"email": email, "password": "Test1234!", "username": "fulltest"})
user_token = b.get("token", {}).get("access_token", "") if isinstance(b, dict) else ""
check("POST /auth/register", (s, b), f"id={b.get('id', '?') if isinstance(b, dict) else '?'}")

# Login (form data)
login_url = "http://localhost:8000/api/v1/auth/login"
login_data = urllib.parse.urlencode({"email": email, "password": "Test1234!", "grant_type": "password"}).encode()
login_req = urllib.request.Request(login_url, data=login_data, method="POST")
login_req.add_header("Content-Type", "application/x-www-form-urlencoded")
try:
    r = urllib.request.urlopen(login_req, timeout=10)
    check("POST /auth/login", (r.status, json.loads(r.read())), "form-based")
except Exception as ex:
    print(f"  POST /auth/login         -> FAIL {ex}")

check(
    "GET /auth/sessions",
    test("GET", "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {user_token}"}),
    "list sessions",
)

# Create session
s, b = test("POST", "/api/v1/auth/session", headers={"Authorization": f"Bearer {user_token}"})
session_token = b.get("token", {}).get("access_token", "") if isinstance(b, dict) else ""
sid = b.get("session_id", "") if isinstance(b, dict) else ""
check("POST /auth/session", (s, b), f"sid={sid[:16]}")

# Update session name (requires form data)
if sid and session_token:
    name_url = f"http://localhost:8000/api/v1/auth/session/{sid}/name"
    name_data = urllib.parse.urlencode({"name": "Test Session"}).encode()
    name_req = urllib.request.Request(name_url, data=name_data, method="PATCH")
    name_req.add_header("Authorization", f"Bearer {session_token}")
    name_req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        r = urllib.request.urlopen(name_req, timeout=10)
        check("PATCH /auth/session/name", (r.status, json.loads(r.read())), "form-based")
    except urllib.error.HTTPError as e:
        check("PATCH /auth/session/name", (e.code, {"detail": "see above"}), f"HTTP {e.code}")

# Delete session
if sid and session_token:
    check(
        "DELETE /auth/session",
        test("DELETE", f"/api/v1/auth/session/{sid}", headers={"Authorization": f"Bearer {session_token}"}),
        "delete",
    )

# ---- Chatbot ----
print("\n--- Chatbot Endpoints ---")
s, b = test("POST", "/api/v1/auth/session", headers={"Authorization": f"Bearer {user_token}"})
chat_token = b.get("token", {}).get("access_token", "") if isinstance(b, dict) else ""
chat_sid = b.get("session_id", "")[:16] if isinstance(b, dict) else "?"

if chat_token:
    s, b = test(
        "POST",
        "/api/v1/chatbot/chat",
        {"messages": [{"role": "user", "content": "Say hi in one word."}]},
        headers={"Authorization": f"Bearer {chat_token}"},
        timeout=60,
    )
    msgs = b.get("messages", []) if isinstance(b, dict) else []
    last_msg = msgs[-1].get("content", "")[:50] if msgs else ""
    check("POST /chatbot/chat", (s, b), f"replies={len(msgs)} last={last_msg}")

# ---- Deep Research ----
print("\n--- Deep Research ---")
s, b = test(
    "POST",
    "/api/v1/research/research",
    {"query": "What is 1+1? Give a one-sentence answer."},
    headers={"Authorization": f"Bearer {user_token}"},
    timeout=120,
)
report = b.get("report", "")[:100] if isinstance(b, dict) else str(b)[:100]
check("POST /research/research", (s, b), f"report={report}")

print("\n" + "=" * 60)
print("TEST SUITE COMPLETE")
print("=" * 60)
