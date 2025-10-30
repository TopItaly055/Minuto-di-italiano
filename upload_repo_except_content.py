import os
import json
import base64
import requests
from pathlib import Path
from typing import Iterable

GITHUB_API = "https://api.github.com"

GH_TOKEN = os.environ.get("GH_TOKEN", "").strip()
REPO = os.environ.get("REPO", "").strip()            # "owner/repo"
BRANCH = os.environ.get("BRANCH", "main").strip()
ROOT = os.environ.get("ROOT", "").strip()            # абсолютный путь к корню проекта

if not GH_TOKEN or not REPO or not ROOT:
    raise SystemExit("Set env vars: GH_TOKEN, REPO (owner/repo), ROOT (project root). Optional: BRANCH=main")

HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# Исключаем каталоги и файлы
EXCLUDE_DIRS = {".git", ".github", ".idea", ".vscode", "venv", "__pycache__", "node_modules", "content"}
EXCLUDE_FILES = {".DS_Store", ".env", "user_stats.pkl"}

# Если хотите ограничить по расширениям — задайте множество; иначе оставьте None
ALLOW_EXTS: Iterable[str] = None
# Пример:
# ALLOW_EXTS = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".cfg", ".ini"}

def should_skip(p: Path) -> bool:
    # Пропускаем по каталогам
    for part in p.parts:
        if part in EXCLUDE_DIRS:
            return True
    # Пропускаем по именам
    if p.name in EXCLUDE_FILES:
        return True
    # Фильтр по расширениям
    if ALLOW_EXTS is not None and p.is_file():
        if p.suffix.lower() not in ALLOW_EXTS:
            return True
    return False

def get_file_sha(repo: str, branch: str, rel_path: str) -> str:
    url = f"{GITHUB_API}/repos/{repo}/contents/{rel_path}"
    r = requests.get(url, headers=HEADERS, params={"ref": branch}, timeout=30)
    if r.status_code == 200:
        try:
            return r.json().get("sha", "")
        except Exception:
            return ""
    return ""

def put_file(repo: str, branch: str, abs_path: Path, rel_path: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/contents/{rel_path}"
    with abs_path.open("rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    # Если файл уже есть и содержимое не менялось — пропускаем
    sha = get_file_sha(repo, branch, rel_path)
    if sha:
        cur = requests.get(url, headers=HEADERS, params={"ref": branch}, timeout=30)
        if cur.status_code == 200:
            cur_b64 = cur.json().get("content", "").strip()
            if cur_b64 == content_b64:
                print(f"[SKIP] {rel_path}: no changes")
                return

    payload = {"message": f"Update {rel_path}", "content": content_b64, "branch": branch}
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=HEADERS, data=json.dumps(payload), timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"PUT {rel_path} failed: {r.status_code} {r.text[:200]}")
    print(f"[OK]   {rel_path}")

def main():
    root = Path(ROOT).resolve()
    if not root.exists():
        raise SystemExit(f"ROOT not found: {root}")

    uploaded, failed = 0, 0
    for p in sorted(root.rglob("*")):
        if p.is_dir() or should_skip(p):
            continue
        rel_path = str(p.relative_to(root))
        try:
            put_file(REPO, BRANCH, p, rel_path)
            uploaded += 1
        except Exception as e:
            failed += 1
            print(f"[ERR]  {rel_path}: {e}")

    print(f"Done. Uploaded={uploaded}, Failed={failed}")
    if failed > 0:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
