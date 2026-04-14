import argparse
import asyncio
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

from openai_codex_sdk import Codex, Thread
from openai_codex_sdk.errors import ThreadRunError
from openai_codex_sdk import parsing as codex_parsing
from openai_codex_sdk.types import UnknownThreadItem
from termcolor import cprint

REPO = "oracle/graalpython"
PROJECT_DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GHAPI = "https://api.github.com"
CODEX = Codex()
MAX_ISSUE_TEXT_CHARS = 700
CODEX_BATCH_SIZE = 1
CODEX_STDIO_READ_LIMIT = 1024 * 1024


def _log_info(message: str) -> None:
    cprint(message, "cyan")


def _log_success(message: str) -> None:
    cprint(message, "green")

### Ayncio subprocess limit patching and codex issue preparation
def _patch_codex_stdio_limit(limit: int = CODEX_STDIO_READ_LIMIT) -> None:
    """Raise asyncio subprocess stream limit used by openai_codex_sdk.

    This avoids ValueError("Separator is found, but chunk is longer than limit")
    when Codex emits a very large JSON line in experimental-json mode.
    """
    create_subprocess_exec = asyncio.create_subprocess_exec
    if getattr(create_subprocess_exec, "_gh_issues_limit_patched", False):
        return

    async def _create_subprocess_exec_with_limit(*args, **kwargs):
        kwargs.setdefault("limit", limit)
        return await create_subprocess_exec(*args, **kwargs)

    setattr(_create_subprocess_exec_with_limit, "_gh_issues_limit_patched", True)
    asyncio.create_subprocess_exec = _create_subprocess_exec_with_limit


_patch_codex_stdio_limit()


def _patch_codex_parse_file_change_in_progress() -> None:
    """Work around SDK validation strictness for in-progress file_change events.

    Some SDK versions model file_change status as completed|failed, while streamed
    events may emit in_progress. When that happens, parsing crashes the whole run.
    We fall back to UnknownThreadItem for any item payload that fails strict parsing.
    """
    original_parse_thread_item = codex_parsing.parse_thread_item
    if getattr(original_parse_thread_item, "_gh_issues_file_change_patch", False):
        return

    def _safe_parse_thread_item(data):
        try:
            return original_parse_thread_item(data)
        except Exception:
            if isinstance(data, dict) and isinstance(data.get("type"), str):
                return UnknownThreadItem.model_validate(data)
            raise

    setattr(_safe_parse_thread_item, "_gh_issues_file_change_patch", True)
    codex_parsing.parse_thread_item = _safe_parse_thread_item


_patch_codex_parse_file_change_in_progress()


def _trim_text(value: str, max_chars: int = MAX_ISSUE_TEXT_CHARS) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "\n...[truncated]"


def _prepare_issues_for_codex(issues: list[dict]) -> list[dict]:
    prepared: list[dict] = []
    for issue in issues:
        prepared.append(
            {
                "issue_id": issue.get("issue_id"),
                "title": _trim_text(str(issue.get("title", "")), max_chars=220),
                "author": _trim_text(str(issue.get("author", "")), max_chars=80),
                "labels": issue.get("labels", []),
                "description": _trim_text(str(issue.get("description", ""))),
            }
        )
    return prepared

### Batching
def _chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _extract_json_payload(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
        if match:
            return match.group(1)
    return stripped


def _candidate_files_for_issue(issue: dict, max_files: int = 5) -> list[str]:
    terms = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", str(issue.get("title", "")))
    terms.extend(str(x) for x in issue.get("labels", []))
    terms = [t.lower() for t in terms if t.lower() not in {"issue", "error", "python", "graalpy", "graalpython"}]
    terms = terms[:4]
    if not terms:
        return []

    pattern = "|".join(re.escape(t) for t in terms)
    cmd = [
        "grep",
        "-RIlE",
        "--exclude-dir=.git",
        "--exclude-dir=venv",
        "--exclude-dir=build",
        "--exclude-dir=dist",
        "--exclude-dir=__pycache__",
        "--binary-files=without-match",
        pattern,
        PROJECT_DIRECTORY,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []

    files = []
    for line in result.stdout.splitlines():
        rel = line.replace(f"{PROJECT_DIRECTORY}/", "")
        files.append(rel)
        if len(files) >= max_files:
            break
    return files


async def _codex_prompt_async(prompt: str, thread: Thread) -> tuple[str, dict[str, int]]:
    try:
        turn = await thread.run(prompt)
    except ThreadRunError as exc:
        raise SystemExit(
            "Codex access test failed. Ensure the token from "
            "~/.codex/config.toml provider OCA_ACCESS_TOKEN is exported\n"
            f"Details: {exc}"
        ) from exc
    usage = turn.usage
    usage_dict = {
        "input_tokens": usage.input_tokens if usage else 0,
        "cached_input_tokens": usage.cached_input_tokens if usage else 0,
        "output_tokens": usage.output_tokens if usage else 0,
    }
    return turn.final_response, usage_dict


def codex_sort_issues(
    issues: list[dict],
    workers: int = 1,
    print_token_usage: bool = False,
    max_files_to_read: int = 5,
    short_output: bool = False,
) -> str:
    _log_info("Sorting issues with Codex...")
    compact_issues = _prepare_issues_for_codex(issues)
    by_id = {issue["issue_id"]: issue for issue in compact_issues}
    easy_ai_fix: list[dict] = []
    non_relevant: list[dict] = []
    
    batches = _chunks(compact_issues, CODEX_BATCH_SIZE)

    async def _classify_batch(
        batch: list[dict], index: int, total: int, sem: asyncio.Semaphore
    ) -> tuple[list[dict], dict[str, int]]:
        async with sem:
            thread_options: dict[str, object] = {
                "approvalPolicy": "never",
                "sandboxMode": "read-only",
                "webSearchEnabled": False,
                "networkAccessEnabled": False,
                "workingDirectory": PROJECT_DIRECTORY,
            }
            thread = CODEX.start_thread(thread_options)

            codebase_instruction = (
                "Read only the local files needed for this issue. "
                f"Read at most {max_files_to_read} files, and skim only minimal relevant sections."
            )
            candidate_files = _candidate_files_for_issue(batch[0], max_files=max_files_to_read)
            
            prompt = (
                "Classify each issue into one of: easy-ai-fix, non-relevant, ignore. "
                "Use short reasoning (<=120 chars). "
                "Assign no longer relevant only if the issue is already fixed. "
                "Do not assign easy-ai-fix if the issue appears already solved. "
                "Return JSON array only with entries (do not include ignored ones): "
                "{\"issue_id\": number, \"category\": \"easy-ai-fix|non-relevant\", \"title\": string, \"author\": string, \"reason\": string}. "
                f"No markdown, no extra text. {codebase_instruction}\n\n"
                f"candidate_files (optional, prefer these first): {json.dumps(candidate_files)}\n\n"
                f"issues_json:\n{json.dumps(batch, ensure_ascii=True, indent=2)}"
            )
            response, usage = await _codex_prompt_async(prompt, thread)
            _log_success(f"Processed batch {index}/{total}")
            return json.loads(_extract_json_payload(response)), usage

    async def _run_all() -> list[tuple[list[dict], dict[str, int]]]:
        sem = asyncio.Semaphore(max(1, workers))
        tasks = [
            asyncio.create_task(_classify_batch(batch, i, len(batches), sem))
            for i, batch in enumerate(batches, start=1)
        ]
        return await asyncio.gather(*tasks)

    parsed_batches = asyncio.run(_run_all())
    token_usage = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
    }

    for parsed, usage in parsed_batches:
        token_usage["input_tokens"] += usage["input_tokens"]
        token_usage["cached_input_tokens"] += usage["cached_input_tokens"]
        token_usage["output_tokens"] += usage["output_tokens"]
        for item in parsed:
            issue_id = item.get("issue_id")
            category = item.get("category")
            if issue_id not in by_id or category not in {"easy-ai-fix", "non-relevant"}:
                continue
            enriched = {"issue_id": issue_id} if short_output else {
                "issue_id": issue_id,
                "title": by_id[issue_id]["title"],
                "author": by_id[issue_id]["author"],
                "reason": _trim_text(str(item.get("reason", "")), max_chars=160),
            }
            if category == "easy-ai-fix":
                if not any(existing["issue_id"] == issue_id for existing in easy_ai_fix):
                    easy_ai_fix.append(enriched)
            else:
                if not any(existing["issue_id"] == issue_id for existing in non_relevant):
                    non_relevant.append(enriched)

    if print_token_usage:
        total = (
            token_usage["input_tokens"]
            + token_usage["cached_input_tokens"]
            + token_usage["output_tokens"]
        )
        _log_info(
            "Token usage: "
            f"input={token_usage['input_tokens']}, "
            f"cached_input={token_usage['cached_input_tokens']}, "
            f"output={token_usage['output_tokens']}, "
            f"total={total}"
        )

    return json.dumps(
        {
            "non-relevant": non_relevant,
            "easy-ai-fix": easy_ai_fix,
        },
        ensure_ascii=True,
        indent=2,
    )


async def codex_fix_issue(issue_id: int, max_rounds: int = 8) -> str:
    thread = CODEX.start_thread(
        {
            "approvalPolicy": "never",
            "sandboxMode": "workspace-write",
            "webSearchEnabled": False,
            "networkAccessEnabled": False,
            "workingDirectory": PROJECT_DIRECTORY,
        }
    )
    prompt = (
        f"Attempt to fix github {REPO} issue #{issue_id} in the local codebase. "
        "Read only the local files needed. "
        "Skim only minimal relevant sections. "
        "Make changes and run relevant tests. "
        "At the end of your response, return ONLY JSON with this schema: "
        "{\"fixed\": boolean, \"summary\": string}."
    )

    last_response = ""
    rounds = max(1, max_rounds)
    for round_idx in range(1, rounds + 1):
        _log_info(f"Codex fix round {round_idx}/{rounds}...")
        response, _ = await _codex_prompt_async(prompt, thread)
        last_response = response
        _log_info(f"Codex response (round {round_idx}):")
        print(response)

        fixed = False
        try:
            payload = json.loads(_extract_json_payload(response))
            fixed = bool(payload.get("fixed", False))
        except (json.JSONDecodeError, TypeError):
            fixed = False

        if fixed:
            _log_success(f"Codex marked issue #{issue_id} as fixed in round {round_idx}.")
            return response

        prompt = (
            f"Issue #{issue_id} is not fixed yet. Continue iterating: "
            "inspect remaining failures, adjust code, and rerun relevant tests. "
            "When done, return ONLY JSON with this schema: "
            "{\"fixed\": boolean, \"summary\": string}."
        )

    _log_info(f"Reached max rounds ({rounds}) for issue #{issue_id} without confirmed fix.")
    return last_response

### Issue categorizing

def sort_issues(args: argparse.Namespace):
    def print_issue_result(category: str, issues: dict):
        iss = issues.get(category, [])
        _log_success(f"{category.capitalize()} issues:")
        for issue in iss:
            issue_id = issue.get("issue_id", "?")
            title = issue.get("title")
            reason = issue.get("reason")
            if title is None and reason is None:
                _log_info(f"- #{issue_id}")
            elif reason is None:
                _log_info(f"- #{issue_id}: {title}")
            elif title is None:
                _log_info(f"- #{issue_id} (reason: {reason})")
            else:
                _log_info(f"- #{issue_id}: {title} (reason: {reason})")
    
    issues = get_issues(limit=args.limit, label=args.label)
    _log_info(f"Fetched {len(json.loads(issues))} issues. Now sorting with Codex...")
    sorted_issues = codex_sort_issues(
        json.loads(issues),
        workers=args.codex_workers,
        print_token_usage=args.print_token_usage,
        max_files_to_read=max(0, args.codex_max_files),
        short_output=args.short_output,
    )
    
    if args.json_output:
        print(sorted_issues)
    else:
        sorted_issues_data = json.loads(sorted_issues)
        print_issue_result("non-relevant", sorted_issues_data)
        print_issue_result("easy-ai-fix", sorted_issues_data)

### GitHub API interaction

def build_github_request(url: str, query_params: dict[str, str], token: str | None = None) -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    full_url = f"{url}?{urllib.parse.urlencode(query_params)}"
    return urllib.request.Request(full_url, headers=headers, method="GET")


def get_issues(limit: int = 30, label: str | None = None) -> str:
    issues = []
    page = 1
    while len(issues) < limit:
        per_page = min(100, max(1, limit - len(issues)))
        query_params = {
            "state": "open",
            "per_page": per_page,
            "page": page,
        }
        if label:
            query_params["labels"] = label
        url = f"{GHAPI}/repos/{REPO}/issues"
        req = build_github_request(url, query_params, token=os.getenv("GITHUB_TOKEN"))
        with urllib.request.urlopen(req) as resp:
            raw_issues = json.loads(resp.read())

        if not raw_issues:
            break

        for item in raw_issues:
            if "pull_request" in item:
                continue
            issues.append(
                {
                    "issue_id": item["number"],
                    "title": item.get("title", ""),
                    "description": item.get("body") or "",
                    "date": item.get("created_at", ""),
                    "author": item.get("user", {}).get("login", ""),
                    "labels": [label.get("name", "") for label in item.get("labels", [])],
                }
            )
            if len(issues) >= limit:
                break
        page += 1

    return json.dumps(issues, ensure_ascii=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-workers", type=int, default=1, help="Parallel Codex workers")
    parser.add_argument("--print-token-usage", action="store_true", help="Print Codex token usage")

    subparsers = parser.add_subparsers(dest="command", required=True)
    issues_parser = subparsers.add_parser("get-issues", help="Fetch and sort GitHub issues")
    issues_parser.add_argument("--limit", type=int, default=30, help="Maximum number of issues to fetch")
    issues_parser.add_argument("--label", type=str, help="Filter issues by label")
    issues_parser.add_argument("--codex-max-files", type=int, default=5, help="Max local files Codex should read per issue")
    issues_parser.add_argument("--short-output", action="store_true", help="Output only issue IDs in each category")
    issues_parser.add_argument("--json-output", action="store_true", help="Output only JSON result")

    fix_parser = subparsers.add_parser("fix-issue", help="Attempt to fix an issue with Codex")
    fix_parser.add_argument("--issue-id", type=int, required=True, help="ID of the issue to fix")
    fix_parser.add_argument("--max-rounds", type=int, default=8, help="Maximum iterative Codex fix rounds")

    args = parser.parse_args()

    if args.command == "get-issues":
        sort_issues(args)

    elif args.command == "fix-issue":
        issue_id = args.issue_id
        _log_info(f"Attempting to fix issue #{issue_id} with Codex...")
        fix = asyncio.run(codex_fix_issue(issue_id, max_rounds=max(1, args.max_rounds)))
        try:
            payload = json.loads(_extract_json_payload(fix))
            print(json.dumps(payload, ensure_ascii=True, indent=2))
        except (json.JSONDecodeError, TypeError):
            print(fix)

if __name__ == "__main__":
    main()
