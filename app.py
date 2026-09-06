import os
import hmac
import hashlib
import requests
import json
import threading

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    Response,
    stream_with_context
)
from dotenv import load_dotenv


# ─── CONFIGURATION ───────────────────────────────────────────────

load_dotenv()

app = Flask(__name__)

GITHUB_SECRET = os.getenv("GITHUB_SECRET", "your_webhook_secret")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")


# ─── SYSTEM PROMPT ───────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a strict code review assistant.

Your ONLY source of truth is the code/diff provided by the user.

DO NOT invent code, behavior, checks, validations, error handling, outputs, or functionality.

Before describing any function, inspect the actual implementation.

If the code says:

    def divide(a, b):
        return a / b

you MUST describe it as performing direct division with NO zero-division check.

Do not say an exception is caught unless there is an explicit try/except.
Do not say an error is printed unless there is an explicit print/log statement.
Do not say validation exists unless validation code is actually present.

For every issue:
- Give the exact file name.
- Give the actual line number when available.
- Quote or reference the relevant code behavior.
- Explain why it is a problem.
- Give a concrete fix.

Only report issues that are directly supported by the code.

Use this format:

## Summary
Briefly describe what the changed code actually does.

## Issues Found

### [CRITICAL/MEDIUM/LOW] Issue title
- File:
- Line:
- Problem:
- Evidence:
- Why it matters:
- Suggested Fix:

If there are no real issues, say:
"No significant issues found."

## Overall Assessment
Give a short assessment based ONLY on the supplied code.
"""

# ─── OLLAMA CALL ─────────────────────────────────────────────────

def review_code(code, language="auto", follow_up=None, history=None):
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    if history:
        messages.extend(history)
    else:
        messages.append({
            "role": "user",
            "content": (
                f"Please review this {language} code:\n\n"
                f"```{language}\n{code}\n```"
            )
        })

    if follow_up:
        messages.append({
            "role": "user",
            "content": follow_up
        })

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.0}
            },
            timeout=120
        )

        response.raise_for_status()
        data = response.json()

        return data["message"]["content"], None

    except requests.exceptions.ConnectionError:
        return (
            None,
            "Cannot connect to Ollama. Make sure Ollama is running on your machine."
        )
    except requests.exceptions.Timeout:
        return (
            None,
            "Request timed out. The model is taking too long to respond."
        )
    except Exception as e:
        return None, str(e)


# ─── ROUTES ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", model=OLLAMA_MODEL)


@app.route("/api/review", methods=["POST"])
def api_review():
    data = request.get_json()

    code = data.get("code", "").strip()
    language = data.get("language", "auto")

    if not code:
        return jsonify({"error": "No code provided."}), 400

    if len(code) > 50000:
        return jsonify({"error": "Code too large."}), 400

    def generate():
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Review this {language} code:\n\n"
                                f"```{language}\n{code}\n```"
                            )
                        }
                    ],
                    "stream": True,
                    "options": {"temperature": 0.0}
                },
                stream=True,
                timeout=(10, 300)
            )

            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)

                    token = (
                        chunk.get("message", {})
                        .get("content", "")
                    )

                    if token:
                        yield (
                            f"data: "
                            f"{json.dumps({'token': token})}"
                            f"\n\n"
                        )

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield (
                f"data: "
                f"{json.dumps({'error': str(e)})}"
                f"\n\n"
            )

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json()

    code = data.get("code", "").strip()
    language = data.get("language", "auto")
    question = data.get("question", "").strip()
    history = data.get("history", [])

    if not question:
        return jsonify({"error": "No question provided."}), 400

    if not history and not code:
        return jsonify({"error": "No code context available."}), 400

    if not history:
        history = [
            {
                "role": "user",
                "content": (
                    f"Please review this {language} code:\n\n"
                    f"```{language}\n{code}\n```"
                )
            }
        ]

    history.append({
        "role": "user",
        "content": question
    })

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    }
                ] + history,
                "stream": False,
                "options": {"temperature": 0.2}
            },
            timeout=120
        )

        response.raise_for_status()

        result = response.json()["message"]["content"]

        history.append({
            "role": "assistant",
            "content": result
        })

        return jsonify({
            "reply": result,
            "history": history
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/models", methods=["GET"])
def api_models():
    try:
        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=5
        )

        models = [
            model["name"]
            for model in response.json().get("models", [])
        ]

        return jsonify({
            "models": models,
            "current": OLLAMA_MODEL
        })

    except Exception:
        return jsonify({
            "models": [],
            "current": OLLAMA_MODEL,
            "error": "Ollama not reachable"
        })


@app.route("/api/status", methods=["GET"])
def api_status():
    try:
        requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=3
        )

        return jsonify({
            "ollama": "connected",
            "model": OLLAMA_MODEL
        })

    except Exception:
        return jsonify({
            "ollama": "disconnected",
            "model": OLLAMA_MODEL
        })


# ─── BACKGROUND PR REVIEW ────────────────────────────────────────

def process_pull_request(pr_number, repo, diff_url):
    try:
        # Fetch the PR diff
        headers = {}

        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
            headers["Accept"] = "application/vnd.github.v3.diff"

        diff_response = requests.get(
            diff_url,
            headers=headers,
            timeout=30
        )

        diff_response.raise_for_status()
        diff = diff_response.text

        if not diff.strip():
            print(f"PR #{pr_number}: empty diff")
            return

        # Limit very large diffs
        if len(diff) > 30000:
            diff = (
                diff[:30000]
                + "\n\n"
                + "[Diff truncated — showing first 30000 characters]"
            )

        # IMPORTANT:
        # Send a very explicit instruction to the model.
        review_prompt = f"""
You are reviewing a GitHub Pull Request.

IMPORTANT:
The following content is the ACTUAL GitHub diff.
Analyze ONLY the code that appears in this diff.

DO NOT invent code that is not present.
DO NOT assume that checks, validations, exception handling,
logging, or error handling exist unless you can see them.

For example, if you see:

def divide(a, b):
    return a / b

then the code has NO division-by-zero check.

If you see:

divide(10, 0)

then this call can raise ZeroDivisionError.

Do not claim that the exception is caught or handled unless
there is actual try/except code in the diff.

Now analyze this exact diff:

--- BEGIN DIFF ---
{diff}
--- END DIFF ---

Return the review using exactly this structure:

## Summary
Describe only what the changed code actually does.

## Issues Found

For each real issue:

### [CRITICAL/MEDIUM/LOW] Issue title

- File: exact filename
- Line: exact changed line if available
- Problem: what is wrong
- Evidence: describe the exact code that causes the issue
- Why it matters: explain the consequence
- Suggested Fix: provide a concrete correction

Only report issues that are actually supported by the diff.

## Overall Assessment
Give a short assessment of the actual code.

IMPORTANT FINAL CHECK:
Before generating your answer, verify every factual statement against
the diff. Never claim that a check, validation, exception handler,
logging statement, or other functionality exists unless it is
actually visible in the diff.
"""

        review, error = review_code(
            review_prompt,
            language="text"
        )

        if error:
            print(
                f"Review error for PR #{pr_number}: {error}"
            )
            return

        # Post review to GitHub
        if GITHUB_TOKEN:
            comment_url = (
                f"https://api.github.com/repos/{repo}"
                f"/issues/{pr_number}/comments"
            )

            comment_body = (
                "## 🤖 Local AI Code Review\n\n"
                f"*Reviewed by `{OLLAMA_MODEL}` running locally — "
                "no code was sent to any external AI provider.*"
                "\n\n---\n\n"
                f"{review}"
            )

            comment_response = requests.post(
                comment_url,
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                },
                json={"body": comment_body},
                timeout=15
            )

            comment_response.raise_for_status()

        print(
            f"Reviewed PR #{pr_number} on {repo}"
        )

    except Exception as e:
        print(
            f"Background webhook error for PR #{pr_number}: {e}"
        )

# ─── GITHUB WEBHOOK ──────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def github_webhook():
    # Verify signature
    signature = request.headers.get(
        "X-Hub-Signature-256",
        ""
    )

    body = request.get_data()

    expected = (
        "sha256="
        + hmac.new(
            GITHUB_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
    )

    if not hmac.compare_digest(signature, expected):
        return jsonify({
            "error": "Invalid signature"
        }), 403

    event = request.headers.get(
        "X-GitHub-Event",
        ""
    )

    payload = request.get_json()

    if event == "pull_request":
        action = payload.get("action", "")

        if action in ["opened", "synchronize"]:
            pr = payload["pull_request"]

            diff_url = pr["diff_url"]
            pr_number = pr["number"]
            repo = payload["repository"]["full_name"]

            # Start the review in a background thread.
            # This allows the webhook to respond to GitHub immediately.
            thread = threading.Thread(
                target=process_pull_request,
                args=(pr_number, repo, diff_url),
                daemon=True
            )

            thread.start()

            # Immediately acknowledge the webhook.
            return jsonify({
                "status": "accepted",
                "message": "Pull request review started in background",
                "pr": pr_number
            }), 200

    return jsonify({
        "status": "ignored"
    }), 200


# ─── RUN APPLICATION ─────────────────────────────────────────────

if __name__ == "__main__":
    print(
        "\n"
        "  Local AI Code Reviewer\n"
        f"  Model : {OLLAMA_MODEL}\n"
        f"  Ollama: {OLLAMA_URL}\n"
        "  Open  : http://localhost:5000\n"
    )

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True
    )
