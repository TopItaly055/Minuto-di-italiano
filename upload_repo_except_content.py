import os, json, base64, requests
from pathlib import Path
GITHUB_API="https://api.github.com"
token=os.environ["GH_TOKEN"].strip(); repo=os.environ["REPO"].strip()
branch=os.environ.get("BRANCH","main").strip()
root=Path(os.environ["PROJECT_ROOT"]).resolve()
hdr={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json"}
EXCLUDE_DIRS={".git",".github",".idea",".vscode","venv","__pycache__","node_modules","content"}
EXCLUDE_FILES={".DS_Store",".env","user_stats.pkl"}
def skip(p:Path):
    for part in p.parts:
        if part in EXCLUDE_DIRS: return True
    return p.name in EXCLUDE_FILES
def get_sha(rel):
    u=f"{GITHUB_API}/repos/{repo}/contents/{rel}"
    r=requests.get(u,headers=hdr,params={"ref":branch},timeout=30)
    return r.json().get("sha") if r.status_code==200 else None
def put(abs_path, rel):
    u=f"{GITHUB_API}/repos/{repo}/contents/{rel}"
    b64=base64.b64encode(Path(abs_path).read_bytes()).decode()
    cur=get_sha(rel)
    if cur:
        curc=requests.get(u,headers=hdr,params={"ref":branch},timeout=30).json().get("content","").strip()
        if curc==b64: print("[SKIP]",rel); return
    payload={"message":f"Update {rel}","content":b64,"branch":branch}
    if cur: payload["sha"]=cur
    r=requests.put(u,headers=hdr,data=json.dumps(payload),timeout=60)
    if r.status_code not in (200,201): raise SystemExit(f"ERR {rel} {r.status_code} {r.text[:200]}")
    print("[OK]",rel)
count=0
for p in sorted(root.rglob("*")):
    if p.is_dir() or skip(p): continue
    rel=str(p.relative_to(root))
    put(str(p), rel); count+=1
print("DONE",count)
