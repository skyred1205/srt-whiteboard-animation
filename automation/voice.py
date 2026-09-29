from __future__ import annotations
import hashlib,json,os,time
from pathlib import Path
import requests
from common import CHI_MAI_ID,digest,probe_duration,write_json

ENDPOINT=os.getenv("LUCYLAB_ENDPOINT","https://api.lucylab.io/json-rpc")
def rpc(method:str,input_data:dict,retries=3)->dict:
    key=os.getenv("LUCYLAB_API_KEY","").strip()
    if not key: raise RuntimeError("missing LUCYLAB_API_KEY")
    headers={"Authorization":f"Bearer {key}","Content-Type":"application/json","User-Agent":"srt-whiteboard-autopilot/1.0"}; last=None
    for i in range(retries):
        try:
            r=requests.post(ENDPOINT,headers=headers,json={"method":method,"input":input_data},timeout=60)
            if r.status_code in (401,403): raise RuntimeError("LucyLab authentication failed")
            r.raise_for_status(); b=r.json();
            if b.get("error"): raise RuntimeError(f"LucyLab {method}: {b['error']}")
            if not isinstance(b.get("result"),dict): raise RuntimeError("LucyLab response missing result")
            return b["result"]
        except Exception as e:
            last=e
            if i+1<retries: time.sleep(min(2**i,8))
    raise RuntimeError(f"LucyLab {method} failed: {last}")
def download(url:str,path:Path):
    with requests.get(url,stream=True,timeout=120) as r:
        r.raise_for_status();
        with path.open("wb") as f:
            for chunk in r.iter_content(262144):
                if chunk: f.write(chunk)
def synthesize(text:str,work:Path,job_id:str)->dict:
    wav,srt,state_path=work/"voice.wav",work/"voice.srt",work/"tts.json"; voice_id=os.getenv("LUCYLAB_VOICE_ID",CHI_MAI_ID).strip() or CHI_MAI_ID; speed=float(os.getenv("LUCYLAB_SPEED","1.0"))
    if not .95<=speed<=1.08: raise ValueError("LUCYLAB_SPEED must be 0.95..1.08")
    fp=hashlib.sha256(json.dumps({"text":text,"voiceId":voice_id,"speed":speed},sort_keys=True,ensure_ascii=False).encode()).hexdigest(); state={}
    if state_path.exists():
        state=json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("fingerprint")!=fp: raise RuntimeError("LucyLab checkpoint mismatch")
        if state.get("state")=="completed" and wav.exists() and srt.exists() and state.get("files",{}).get("voice.wav")==digest(wav) and state.get("files",{}).get("voice.srt")==digest(srt): return state
    export_id=str(state.get("projectExportId") or "")
    if not export_id and state: raise RuntimeError("TTS_CREATION_UNCERTAIN: reconcile checkpoint before another paid request")
    if not export_id:
        state={"schemaVersion":1,"jobId":job_id,"voiceAlias":"chi-mai","voiceId":voice_id,"speed":speed,"fingerprint":fp,"state":"creation-pending"}; write_json(state_path,state)
        created=rpc("ttsLongText",{"text":text,"userVoiceId":voice_id,"speed":speed},1); export_id=str(created.get("projectExportId") or "")
        if not export_id: raise RuntimeError("TTS_CREATION_UNCERTAIN: no projectExportId")
        state.update(state="polling",projectExportId=export_id); write_json(state_path,state)
    deadline=time.monotonic()+int(os.getenv("LUCYLAB_POLL_TIMEOUT_SEC","900"))
    while time.monotonic()<deadline:
        st=rpc("getExportStatus",{"projectExportId":export_id},3); status=str(st.get("state") or "")
        if status=="failed": state.update(state="failed",error=st.get("error")); write_json(state_path,state); raise RuntimeError("LucyLab export failed")
        if status=="completed":
            if not st.get("url") or not st.get("srtUrl"): raise RuntimeError("LucyLab completed without audio/SRT")
            download(st["url"],wav); download(st["srtUrl"],srt); dur=round(probe_duration(wav)*1000)
            if dur<=0 or "-->" not in srt.read_text(encoding="utf-8-sig"): raise RuntimeError("invalid LucyLab output")
            state.update(state="completed",durationMs=dur,files={"voice.wav":digest(wav),"voice.srt":digest(srt)}); write_json(state_path,state); return state
        time.sleep(float(os.getenv("LUCYLAB_POLL_INTERVAL_SEC","2.5")))
    raise TimeoutError(f"LucyLab timeout; preserved projectExportId {export_id}")
