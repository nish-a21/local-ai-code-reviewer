# Local AI Code Reviewer

A privacy-first code review tool. AI runs locally via Ollama — no code leaves your machine.

---

## Setup (One Time)

### Step 1 — Install Ollama
Download from https://ollama.com and install it.

### Step 2 — Pull the model
```bash
ollama pull qwen2.5-coder:3b
```

### Step 3 — Clone and install
```bash
git clone <your-repo>
cd local-ai-reviewer
pip install -r requirements.txt
```

### Step 4 — Configure environment
Edit the `.env` file:
```
GITHUB_SECRET=any_secret_you_choose
GITHUB_TOKEN=your_github_personal_access_token
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b
```

---

## Run

```bash
# Terminal 1 — Start Ollama
ollama serve

# Terminal 2 — Start the app
python app.py
```

Open http://localhost:5000

---

## GitHub Webhook Setup (For Auto PR Reviews)

1. Go to your GitHub repo → Settings → Webhooks → Add webhook
2. Payload URL: `https://your-ngrok-url/webhook`
3. Content type: `application/json`
4. Secret: same as GITHUB_SECRET in your .env
5. Event: Pull requests only

To expose your local server to GitHub (development):
```bash
ngrok http 5000
```
Copy the https URL and use it as your webhook payload URL.

---

## Usage

**Manual:** Paste code → Select language → Click Review

**Automatic:** Raise a PR on GitHub → Review appears as a comment automatically

---

## Supported Languages
Python, JavaScript, TypeScript, Java, C++, C, Go, Rust, PHP, Ruby, SQL, and more.
