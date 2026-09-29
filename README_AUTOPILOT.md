# Whiteboard Channel Autopilot

Autonomous pipeline layered on `srt-whiteboard-animation`:

`idea -> original drawing -> crude contrast hook -> LucyLab Chi Mai voice + SRT -> whiteboard render -> QA -> Facebook Page Reel`

## Voice integration (from HANDU V1.4 production rules)

- default LucyLab voice: Chi Mai `cLZiqtzLcKYqwYrWJemAJK`;
- plan narration at ~3.95 Vietnamese words/sec (planning band 3.85-4.00);
- word-count preflight happens before the paid TTS call;
- one immutable LucyLab job per script; `projectExportId` is persisted in `tts.json`;
- ambiguous or duplicate paid TTS retries are refused;
- real LucyLab WAV + SRT define the actual duration/timeline;
- final video keeps a 0.75s tail and must pass 0.1-1.0s tail QA.

The first 2.8s is a deliberately crude contrast drawing. The main drawing then progresses continuously over the real LucyLab voice window. `stageTimeline` stores five teaching milestones from the real SRT for later semantic-region refinement.

## Required GitHub Actions secrets

- `OPENAI_API_KEY`
- `LUCYLAB_API_KEY`
- `META_PAGE_ID`
- `META_PAGE_ACCESS_TOKEN`

Recommended variables:

- `OPENAI_TEXT_MODEL=gpt-5.6-luna`
- `OPENAI_IMAGE_MODEL=gpt-image-2`
- `OPENAI_IMAGE_QUALITY=medium`
- `LUCYLAB_SPEED=1.0`
- `TARGET_VOICE_SEC=46.0`
- `META_GRAPH_VERSION=v26.0`
- `AUTO_PUBLISH_ENABLED=false` initially; set to `true` only after a manual pilot passes review.

`LUCYLAB_VOICE_ID` is optional. If omitted, Chi Mai is used.

## Schedule

The workflow runs at 08:15, 13:15 and 19:15 Vietnam time. Manual runs default to **not publishing**. Scheduled runs publish only when `AUTO_PUBLISH_ENABLED=true` and hard QA passes.

Do not use **Re-run jobs** after a run may have reached LucyLab. Retrieve the 30-day artifact containing `tts.json` and reconcile the saved `projectExportId` instead.
