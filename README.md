# AI News Gmail Brief

A safety-first Python automation service that reads only explicitly allowlisted Gmail labels, extracts AI-news-related signal from messages and safe external links, sends a weekly intelligence brief, and then moves only successfully processed allowlisted messages to Gmail Trash.

## Safety Model

- The service refuses to run when `GMAIL_LABEL_ALLOWLIST` is empty.
- Gmail searches use exact resolved label IDs only. It never scans the whole inbox.
- Every fetched message is checked again for the exact allowlisted label ID before parsing.
- Cleanup checks the exact label boundary a third time before moving anything to Trash.
- `RUN_MODE=dry_run` is the default and never sends, deletes, modifies, archives, marks read, or labels Gmail messages.
- Live cleanup requires both `RUN_MODE=live` and `DELETE_AFTER_SUCCESS=true`.
- Cleanup runs only after report generation succeeds and Gmail returns a sent message ID.
- Delete means Gmail Trash. Permanent deletion is intentionally unsupported to keep Gmail permissions narrow.

## Gmail Permissions

The app uses these OAuth scopes:

- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.send`

`gmail.modify` is needed to read allowlisted messages and move processed messages to Trash. The app does not request full mailbox access and does not permanently delete messages.

## Setup

1. Create a Google Cloud OAuth desktop client with the Gmail API enabled.
2. Download the OAuth client JSON as `credentials.json`.
3. Create a local environment file:

```powershell
Copy-Item .env.example .env
```

4. Edit `.env` and set:

```env
GMAIL_LABEL_ALLOWLIST=["AI News","AI Startups"]
SUMMARY_RECIPIENT_EMAIL=you@example.com
RUN_MODE=dry_run
DELETE_AFTER_SUCCESS=false
MAX_EMAILS_PER_RUN=50
MAX_LINKS_PER_EMAIL=5
SUMMARY_TIME_WINDOW=last 7 days
```

5. Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

6. Run locally in dry-run mode first:

```powershell
python -m src.main
```

The first run opens a local OAuth consent flow and writes `token.json`. Keep both `credentials.json` and `token.json` out of Git.

## Live Mode

Use live mode only after reviewing dry-run logs:

```env
RUN_MODE=live
DELETE_AFTER_SUCCESS=true
```

In live mode, the service sends the report first. Only after Gmail confirms the sent message ID does it move the exact processed message IDs to Trash.

## Weekly Scheduling

This repository includes `.github/workflows/weekly.yml`, scheduled for Mondays at 08:00 UTC. It runs tests first, then runs the service. Keep the workflow in `dry_run` until repository secrets and variables are configured and a dry run has been reviewed.

Required GitHub secrets:

- `GMAIL_CREDENTIALS_JSON`
- `GMAIL_TOKEN_JSON`

Recommended repository variables:

- `GMAIL_LABEL_ALLOWLIST`
- `SUMMARY_RECIPIENT_EMAIL`
- `RUN_MODE`
- `DELETE_AFTER_SUCCESS`
- `MAX_EMAILS_PER_RUN`
- `MAX_LINKS_PER_EMAIL`
- `SUMMARY_TIME_WINDOW`

## Tests

The tests use only the Python standard library:

```powershell
python -m unittest discover -s tests -v
```

Covered guardrails:

- exact label filtering
- dry-run mode
- deletion only after successful send
- no deletion after send failure
- duplicate link removal
- skipping unsafe, tracking, action, local, and irrelevant links

## Report Structure

Subject:

```text
Weekly AI Intelligence Brief — [date range]
```

Body sections:

- Executive summary
- Top 5 most important developments
- AI engineering and developer tools
- AI agents and automation
- Startups, products, and business opportunities
- Research or technical breakthroughs
- Market signals and trends
- Actionable ideas for my own AI/startup projects
- Links worth reading
- Ignored/noisy items summary
- Processed email count and processed link count

The summarizer synthesizes topics, claims, relevance, and practical actions from extracted article text. It does not just echo titles.
