# vlm_run

VLM (Gemini 3.8 Flash) on UMI industrial recordings: task identification and repetition (cycle) counting, from MCAPs
or MP4s, locally or as Gemini Batch API runs over S3. Until 2026-11-24 this lived untracked in `tag_tracking_v2/`;
paths now point to `vlm_run/`.

```
run_vlm_repetitions.py          runner: prompt sets, request building (images or MCAP views), Gemini / OpenRouter, checks
configs/config.json             models, prices, prompt sets, frame grid, checks (keys come from env: GEMINI_API_KEY, ...)
prompts/                        every prompt set (config.json prompt.sets points here)
  final_prompts/                image prompts 1.0 (output: task, n_repetitions, counting_reasoning, repetitions)
  final_prompts_v1.1/           1.0 + small objects, follow the UMI grippers, re-check before 0
  final_prompts_v1.2/           canonical_task (task folder) first, no calibration/inspection tasks, count only,
                                confidences for canonical_task, task and n_repetitions
  final_video_prompts/, final_video_prompts_v1.1/, final_video_prompts_v1.2/   same for video input (Files API)
  chatgpt_prompts/, mcap_prompts/   earlier prompt sets
vlm_scripts_reports/            S3 batch driver, tools and reports, as one project (README.md there)
  scripts/                      run_s3_vlm.py, check_results.py, video_token_test.py, prompt_test.py,
                                make_report_csv.py, make_task_only.py, s3_video_inventory.py
  configs/, run.sh, setup_instance.sh, requirements.txt
  reports/                      vlm_findings.md / .csv, run CSVs, S3 head-video inventory (durations), manual count sheet
```

Not in git (see `.gitignore`): `.env` files with API keys, and the run data under `vlm_scripts_reports/`
(`work/`, `results/`, `snapshots/`, `video_test/`, `task_only/`, logs).

Setup: `cd vlm_run/vlm_scripts_reports && ./setup_instance.sh && cp .env.example .env` (fill `GEMINI_API_KEY`;
`AWS_PROFILE=prod` on a laptop, empty on EC2 with an instance role), then `./run.sh --list`.
