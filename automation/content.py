from __future__ import annotations
import base64, json, os, re
from datetime import datetime
from pathlib import Path
import requests
from PIL import Image,ImageFilter,ImageOps
from common import CANVAS,PAPER,WPS,count_words,load_history,voice_budget

API=os.getenv("OPENAI_API_BASE","https://api.openai.com/v1").rstrip("/")
CATS=["animal","tree_or_flower","house_or_architecture","everyday_object","landscape","food","vehicle","fantasy_object"]
def headers():
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key: raise RuntimeError("missing OPENAI_API_KEY")
    return {"Authorization":f"Bearer {key}","Content-Type":"application/json"}
def response_text(prompt:str)->str:
    r=requests.post(API+"/responses",headers=headers(),json={"model":os.getenv("OPENAI_TEXT_MODEL","gpt-5.6-luna"),"input":prompt,"max_output_tokens":2600},timeout=120); r.raise_for_status(); d=r.json(); chunks=[]
    for item in d.get("output",[]):
        for part in item.get("content",[]) or []:
            if part.get("type") in {"output_text","text"}:
                v=part.get("text"); chunks.append(v if isinstance(v,str) else v.get("value","") if isinstance(v,dict) else "")
    return "\n".join(x for x in chunks if x).strip() or str(d.get("output_text") or "")
def _obj(text:str)->dict:
    raw=re.sub(r"^```(?:json)?\s*|\s*```$","",text.strip()); a,b=raw.find("{"),raw.rfind("}")
    obj=json.loads(raw if a<0 else raw[a:b+1]);
    if not isinstance(obj,dict): raise ValueError("expected object")
    return obj
def generate_plan(slot:int,target_sec:float)->dict:
    budget=voice_budget(target_sec); cat=CATS[(datetime.now().toordinal()*3+max(1,slot)-1)%len(CATS)]; recent=[x.get("subject","") for x in load_history(30)]
    base=f'''Create ONE original Vietnamese Facebook Reels drawing tutorial. Never copy another creator's exact artwork, wording, step order, or shot sequence.
Retention: first 0-3s simple contrast hook; then progressive polished drawing; exactly five teaching stages; satisfying completed sketch.
Category: {cat}. Avoid recent subjects: {recent[-20:]}.
LucyLab Chi Mai target {target_sec:.1f}s at {WPS} Vietnamese words/sec. voice_script must have {budget['min_words']}-{budget['max_words']} space-delimited words, target {budget['target_words']}.
Return ONLY JSON: {{"title":"...","subject":"...","hook_line":"max 12 Vietnamese words","voice_script":"...","steps":["...","...","...","...","..."],"image_prompt":"English prompt for a single finished graphite/ink drawing on warm cream paper, centered, no text/labels/hands/watermarks, clean negative space","caption":"1-2 Vietnamese sentences","hashtags":["vechibi"],"drawing_focus":"short English phrase"}}.
voice_script must start with hook_line exactly and then teach five concrete stages (dựng khung, tỉ lệ, nét, khối, bóng/hoàn thiện). Avoid politics, brands, copyrighted characters, celebrities, logos, medical claims.'''
    prompt=base
    for _ in range(3):
        try:
            p=_obj(response_text(prompt)); req={"title","subject","hook_line","voice_script","steps","image_prompt","caption","hashtags","drawing_focus"}
            if req-set(p): raise ValueError(f"missing {sorted(req-set(p))}")
            if not isinstance(p["steps"],list) or len(p["steps"])!=5: raise ValueError("steps must be 5")
            if not str(p["voice_script"]).startswith(str(p["hook_line"])): raise ValueError("script must start with hook")
            n=count_words(str(p["voice_script"]));
            if not budget["min_words"]<=n<=budget["max_words"]: raise ValueError(f"word count {n}")
            p["voice_budget"]={**budget,"actual_words":n}; return p
        except Exception as e: prompt=base+f"\nFix this validation error and return strict JSON only: {e}"
    raise RuntimeError("content plan failed validation")
def generate_art(plan:dict,work:Path)->tuple[Path,Path]:
    prompt=str(plan["image_prompt"])+" Vertical 9:16. Graphite pencil and fine ink, subtle grayscale shading, warm cream paper, dark gray lines, no text/letters/numbers/signature/hand."
    r=requests.post(API+"/images/generations",headers=headers(),json={"model":os.getenv("OPENAI_IMAGE_MODEL","gpt-image-2"),"prompt":prompt,"n":1,"size":"1024x1536","quality":os.getenv("OPENAI_IMAGE_QUALITY","medium"),"background":"opaque"},timeout=300); r.raise_for_status(); b64=(r.json().get("data") or [{}])[0].get("b64_json")
    if not b64: raise RuntimeError("image response missing b64_json")
    raw=work/"generated.png"; raw.write_bytes(base64.b64decode(b64)); src=Image.open(raw).convert("RGB"); src.thumbnail((980,1500),Image.Resampling.LANCZOS)
    final=work/"final-art.png"; canvas=Image.new("RGB",CANVAS,PAPER); canvas.paste(src,((CANVAS[0]-src.width)//2,230+max(0,(1500-src.height)//2))); canvas.save(final)
    g=ImageOps.grayscale(canvas).resize((135,240),Image.Resampling.BILINEAR); edges=ImageOps.autocontrast(g.filter(ImageFilter.FIND_EDGES)); line=edges.point(lambda p:35 if p>85 else 245).resize(CANVAS,Image.Resampling.NEAREST).convert("RGB")
    hook=work/"hook-art.png"; Image.blend(Image.new("RGB",CANVAS,PAPER),line,.72).save(hook); return final,hook
