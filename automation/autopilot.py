from __future__ import annotations
import argparse,json,os,re,sys
from datetime import datetime
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import CANVAS,TAIL_SEC,append_history,count_words,parse_srt,probe_duration,probe_json,run,slugify,voice_budget,write_json
from content import generate_art,generate_plan
from voice import synthesize

def annotation(image:Path,out:Path,duration_ms:int,label:str,subtitle:str,cues:list[dict],steps:list[str]):
    w,h=Image.open(image).size; mx,top,bottom=max(20,int(w*.035)),max(60,int(h*.07)),max(60,int(h*.07)); draw_ms=max(1500,duration_ms-700)
    stage=[]
    if cues:
        span=max(1,cues[-1]["endMs"]); stage=[{"step":steps[i],"targetMs":round(span*(i+1)/5)} for i in range(5)]
    write_json(out,{"sceneId":out.stem,"canvas":{"width":w,"height":h},"storyBasis":label,"sceneDurationMs":duration_ms,"voiceCues":cues,"stageTimeline":stage,"elements":[{"id":"main-subject","label":label,"sequence":1,"narrativeRole":"nét vẽ tiến triển liên tục theo timeline LucyLab","subtitle":subtitle[:1000],"type":"subject","region":{"x":mx,"y":top,"width":w-2*mx,"height":h-top-bottom},"reveal":{"direction":"top_to_bottom","startMs":100,"durationMs":draw_ms,"maskPaddingPx":18,"protectedRegions":[]},"handPath":{"start":[w//2,top],"end":[w//2,h-bottom],"easing":"easeInOut"}}]})
def renderer_python()->Path:
    out=run([sys.executable,"scripts/prepare_env.py"],True); m=re.search(r"ENV_PY=(.+)",out)
    if not m: raise RuntimeError("prepare_env.py did not return ENV_PY")
    return Path(m.group(1).strip())
def render(py:Path,image:Path,ann:Path,out:Path,mode:str):
    run([str(py),"scripts/render_stream_whiteboard.py",str(image),str(ann),str(out),"assets/drawing-hand.png","--ink-path",mode,"--color-fill","contour-wipe","--cap-long-edge","1920","--fps","30","--pause","light"])
def mux(hook:Path,main:Path,voice:Path,out:Path):
    silent=out.with_name("silent.mp4"); run(["ffmpeg","-y","-i",str(hook),"-i",str(main),"-filter_complex","[0:v][1:v]concat=n=2:v=1:a=0[v]","-map","[v]","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r","30","-movflags","+faststart",str(silent)])
    run(["ffmpeg","-y","-i",str(silent),"-i",str(voice),"-filter_complex",f"[1:a]apad=pad_dur={TAIL_SEC:.3f}[a]","-map","0:v:0","-map","[a]","-c:v","copy","-c:a","aac","-b:a","160k","-shortest","-movflags","+faststart",str(out)])
def qa(video:Path,voice:Path)->dict:
    info=probe_json(video); ss=info.get("streams",[]); v=next((x for x in ss if x.get("codec_type")=="video"),None); a=next((x for x in ss if x.get("codec_type")=="audio"),None)
    if not v or not a: raise RuntimeError("QA: missing video/audio")
    if (int(v.get("width") or 0),int(v.get("height") or 0))!=CANVAS: raise RuntimeError("QA: not 1080x1920")
    if v.get("codec_name")!="h264" or a.get("codec_name")!="aac": raise RuntimeError("QA: expected H.264 + AAC")
    fd,vd=probe_duration(video),probe_duration(voice); tail=fd-vd
    if fd>60 or not .1<=tail<=1.0: raise RuntimeError(f"QA: duration/tail failed final={fd:.2f}s tail={tail:.2f}s")
    return {"status":"PASS","finalDurationSec":round(fd,3),"voiceDurationSec":round(vd,3),"tailSec":round(tail,3),"width":1080,"height":1920,"videoCodec":"h264","audioCodec":"aac"}
def caption(p:dict)->str: return (str(p.get("caption","")).strip()+"\n\n"+" ".join("#"+str(x).lstrip("#") for x in p.get("hashtags",[]))).strip()
def publish(video:Path,title:str,desc:str)->str:
    import requests
    pid=os.environ["META_PAGE_ID"]; token=os.environ["META_PAGE_ACCESS_TOKEN"]; ver=os.getenv("META_GRAPH_VERSION","v26.0"); endpoint=f"https://graph.facebook.com/{ver}/{pid}/video_reels"
    r=requests.post(endpoint,data={"upload_phase":"start","access_token":token},timeout=60); r.raise_for_status(); j=r.json(); vid=str(j["video_id"]); url=j.get("upload_url") or f"https://rupload.facebook.com/video-upload/{ver}/{vid}"
    headers={"Authorization":f"OAuth {token}","Content-Type":"application/octet-stream","offset":"0","file_size":str(video.stat().st_size)}
    with video.open("rb") as f: u=requests.post(url,headers=headers,data=f,timeout=600); u.raise_for_status()
    f=requests.post(endpoint,data={"upload_phase":"finish","video_id":vid,"video_state":"PUBLISHED","title":title[:255],"description":desc[:5000],"access_token":token},timeout=120); f.raise_for_status()
    if not f.json().get("success"): raise RuntimeError(f"Facebook publish failed: {f.text[:500]}")
    return vid
def self_test():
    b=voice_budget(46); assert b["target_words"]==182 and b["min_words"]<=182<=b["max_words"]; assert slugify("Hello Fish 123") == "hello-fish-123"
    t=Path(__file__).resolve().parents[1]/".selftest.srt"; t.write_text("1\n00:00:00,000 --> 00:00:01,250\nXin chào\n",encoding="utf-8"); assert parse_srt(t)[0]["endMs"]==1250; t.unlink(); print("autopilot self-test: PASS")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--slot",type=int,default=int(os.getenv("VIDEO_SLOT","1"))); ap.add_argument("--publish",action="store_true"); ap.add_argument("--output-root",default="output"); ap.add_argument("--target-voice-sec",type=float,default=float(os.getenv("TARGET_VOICE_SEC","46"))); ap.add_argument("--self-test",action="store_true"); args=ap.parse_args()
    if args.self_test: self_test(); return 0
    if int(os.getenv("GITHUB_RUN_ATTEMPT","1"))!=1: raise RuntimeError("do not rerun a workflow attempt that may have created a paid LucyLab export")
    plan=generate_plan(args.slot,args.target_voice_sec); budget=voice_budget(args.target_voice_sec); words=count_words(plan["voice_script"])
    if not budget["min_words"]<=words<=budget["max_words"]: raise RuntimeError("voice preflight failed before LucyLab")
    job=f"{datetime.now():%Y%m%d-%H%M%S}-slot{args.slot}-{slugify(plan['subject'])}"; work=Path(__file__).resolve().parents[1]/args.output_root/job; work.mkdir(parents=True,exist_ok=True); write_json(work/"plan.json",plan)
    final_art,hook_art=generate_art(plan,work); tts=synthesize(plan["voice_script"],work,job); voice,srt=work/"voice.wav",work/"voice.srt"; voice_sec=probe_duration(voice)
    if not 20<=voice_sec<=58.5: raise RuntimeError(f"LucyLab duration outside safe range: {voice_sec:.2f}s")
    cues=parse_srt(srt); hook_ms=2800; total_ms=round((voice_sec+TAIL_SEC)*1000); main_ms=max(8000,total_ms-hook_ms); steps=plan["steps"]
    annotation(hook_art,work/"hook.annotation.json",hook_ms,"contrast hook",plan["hook_line"],[x for x in cues if x["startMs"]<hook_ms],steps)
    annotation(final_art,work/"main.annotation.json",main_ms,plan["subject"],plan["voice_script"],cues,steps)
    py=renderer_python(); render(py,hook_art,work/"hook.annotation.json",work/"hook.mp4","grid"); render(py,final_art,work/"main.annotation.json",work/"main.mp4","skeleton"); mux(work/"hook.mp4",work/"main.mp4",voice,work/"final.mp4")
    report=qa(work/"final.mp4",voice); write_json(work/"qa_report.json",report); vid=publish(work/"final.mp4",plan["title"],caption(plan)) if args.publish else None; append_history(plan,vid)
    result={"job_id":job,"title":plan["title"],"subject":plan["subject"],"voice_words":words,"lucylab_export_id":tts.get("projectExportId"),"qa":report,"final_video":str(work/"final.mp4"),"facebook_video_id":vid}; write_json(work/"result.json",result); print(json.dumps(result,ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
