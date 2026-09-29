from __future__ import annotations
import hashlib, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "state/history.json"
CANVAS = (1080, 1920)
PAPER = (245, 235, 215)
CHI_MAI_ID = "cLZiqtzLcKYqwYrWJemAJK"
WPS, WPS_MIN, WPS_MAX = 3.95, 3.85, 4.00
TAIL_SEC = 0.75
TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")

def run(cmd:list[str], capture=False)->str:
    p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=capture)
    if p.returncode:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout if capture else ''}\n{p.stderr if capture else ''}")
    return p.stdout if capture else ""

def probe_duration(path:Path)->float:
    return float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],True).strip())

def probe_json(path:Path)->dict:
    return json.loads(run(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(path)],True))

def digest(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()
def count_words(text:str)->int: return len(re.findall(r"\S+",text.strip()))
def voice_budget(sec:float)->dict:
    return {"target_sec":sec,"target_words":round(sec*WPS),"min_words":max(1,round(sec*WPS_MIN)-2),"max_words":round(sec*WPS_MAX)+2}
def write_json(path:Path,data)->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(path)
def slugify(s:str)->str:
    x=re.sub(r"[^a-z0-9]+","-",s.lower().encode("ascii","ignore").decode()).strip("-")
    return x[:48] or "drawing-reel"
def load_history(limit=30)->list[dict]:
    try: data=json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception: return []
    return data[-limit:] if isinstance(data,list) else []
def append_history(plan:dict,video_id:str|None)->None:
    from datetime import datetime
    data=load_history(1000); data.append({"created_at":datetime.now().isoformat(timespec="seconds"),"title":plan.get("title"),"subject":plan.get("subject"),"video_id":video_id})
    HISTORY.parent.mkdir(parents=True,exist_ok=True); HISTORY.write_text(json.dumps(data[-200:],ensure_ascii=False,indent=2),encoding="utf-8")
def _ms(t):
    h,m,s,ms=t; return ((int(h)*60+int(m))*60+int(s))*1000+int(ms.ljust(3,"0"))
def parse_srt(path:Path)->list[dict]:
    text=path.read_text(encoding="utf-8-sig").replace("\r\n","\n").replace("\r","\n"); out=[]
    for block in re.split(r"\n\s*\n",text.strip()):
        lines=[x.strip() for x in block.splitlines() if x.strip()]; idx=next((i for i,x in enumerate(lines) if "-->" in x),None)
        if idx is None: continue
        times=TIME_RE.findall(lines[idx])
        if len(times)>=2: out.append({"index":len(out)+1,"startMs":_ms(times[0]),"endMs":_ms(times[1]),"text":" ".join(lines[idx+1:])})
    return out
