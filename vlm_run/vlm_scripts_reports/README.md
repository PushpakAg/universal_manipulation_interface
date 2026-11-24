# vlm_scripts_reports

Repetition VLM (final_prompts, same request building and checks as `vlm_run/run_vlm_repetitions.py`) on
every head MP4 under an S3 prefix, as ONE Gemini Batch API job: 3 fps, media resolution low, half price.

Default source (`configs/s3_run.json`):

```
s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/<station>/[<date>/]<taskNN>/<episode>/*_head.mp4
```

Every station (station1, station2, station3), every task and every episode; some stations have a date folder
between station and task, some do not. The task is its whole path (`station1/2026-11-21/task01`), so equal task names
of different stations or dates never mix; the prompt gets the folder name (`task01`) as `context.task_folder`.
On 2026-11-24: 1,171 episodes in 25 tasks (station1 799, station2 112, station3 260; `reports/s3_head_video_summary.csv`).
Prompt set `final_v1.2` (canonical task, count, confidences). Results keep the usual name `<name>_vlm_result.json`
(locally and next to each MP4 in S3); results of an earlier prompt version are redone and overwritten.

## How it runs

1. Lists every `*_head.mp4` under the prefix.
2. Prepares each episode in parallel processes: download, sample at 3 fps, build the Gemini request
   (low media resolution, ~280 tokens per image; thinking level medium). Requests are cached in `work_dir`; the MP4 is deleted after
   sampling unless `keep_videos`.
3. Writes all requests to one JSONL, uploads it with the Gemini Files API and submits ONE batch job
   (file input up to 2 GB, so long episodes such as task04/episode_000000, ~460 images, fit; a second job is made
   only above `max_batch_mb`).
4. Waits, downloads the batch output and writes each episode's results into its own local folder.
5. Uploads each parsed result into the S3 folder of its MP4:
   `<task>/<episode>/<name>_head.mp4` -> `<task>/<episode>/<name>_vlm_result.json`
   (`--no-upload` keeps it local; `--upload-only` pushes existing local results; failed episodes are not uploaded).

## Layout

```
vlm_scripts_reports/          project root: every relative path (configs, work/, results/, .env) resolves here
  scripts/                    all Python scripts (run them from the root: python scripts/<name>.py, or ./run.sh)
  configs/s3_run.json
  reports/
  run.sh  setup_instance.sh  requirements.txt  .env.example
  work/ results/ snapshots/ video_test/ task_only/   run data (git-ignored)
```

## Files

| File | Purpose |
|---|---|
| `scripts/run_s3_vlm.py` | the driver (list, prepare, batch, collect, summary) |
| `scripts/check_results.py` | checks local and S3 results per episode (problems, totals, optional CSV) |
| `scripts/video_token_test.py` | video input (Files API) token and cost test |
| `scripts/prompt_test.py` | old vs v1.1 prompts on images and video in one batch |
| `scripts/make_report_csv.py` | builds the run CSVs in `reports/` |
| `scripts/make_manual_counts.py` | `reports/manual_counts.csv`: one row per episode (all stations), VLM answer next to the manual count; rerun after each batch (manual columns kept) |
| `scripts/make_task_only.py` | task-only result files (canonical task per folder + manual count) |
| `scripts/s3_video_inventory.py` | head-video inventory (episodes, durations) of an S3 prefix -> `reports/` |
| `reports/` | findings (md, csv), run CSVs, S3 inventory, manual count sheet |
| `configs/s3_run.json` | source, model, fps, media resolution, workers, output dirs, batch split size |
| `.env` / `.env.example` | `AWS_PROFILE`, region, `GEMINI_API_KEY` (git-ignored; shell wins; key falls back to `vlm_run/.env`) |
| `requirements.txt` | boto3, av, opencv-python-headless, numpy |
| `setup_instance.sh` | creates `.venv` here and installs the requirements |
| `run.sh` | runs `scripts/run_s3_vlm.py` with that venv |

The whole `vlm_run/` folder must sit next to this one (the driver imports `run_vlm_repetitions.py` and
uses its `configs/config.json` and `prompts/`).

## Setup

```bash
cd vlm_run/vlm_scripts_reports
./setup_instance.sh
# laptop: AWS_PROFILE=prod in .env, and: aws sso login --profile prod
# EC2: leave AWS_PROFILE empty; the instance role needs s3:ListBucket, s3:GetObject and s3:PutObject on the prefix
```

## Run

```bash
./run.sh --list                          # episodes in S3
./run.sh --dry-run                       # prepare everything, print request size and cost estimate, no Google call
./run.sh                                 # full run: one batch job, waits for it, writes results
./run.sh --task task04 --limit 2         # a subset: task04 of every station/date, 2 episodes each
./run.sh --task station1/2026-11-21      # one station/date (also: station1, or station1/2026-11-21/task01)
./run.sh --source s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/station2/2026-11-22/   # one folder
./run.sh --resume                        # interrupted while waiting: collect the submitted job(s)
./run.sh --summary-only
./run.sh --debug                         # also frames/ and raw_response.json per episode
```

On an instance run it detached: `nohup ./run.sh > run.log 2>&1 &`. Batch jobs take minutes to 24 h.

## Output (one folder per episode)

```
results/<station>/[<date>/]<task>/<episode>/<name>_vlm_result.json     response, code flags, step -> time, usage, cost, batch name, S3 video
results/<station>/[<date>/]<task>/<episode>/step_table.json     step -> t_s and frame index
results/<station>/[<date>/]<task>/<episode>/frames/             (--debug) the JPEGs the model saw
results/<station>/[<date>/]<task>/<episode>/raw_response.json   (--debug) the batch output line
results/summary.csv      task path, episode, canonical task, task, count, the three confidences, flags, cost
results/batches/<id>/job.json                batch name, input file, episodes, state, cost
```

After a run: `python scripts/make_manual_counts.py` refreshes the VLM columns of `reports/manual_counts.csv`.

A rerun skips episodes whose `<name>_vlm_result.json` has a parsed response from the current prompt set; results of
an earlier prompt version are redone and overwritten; `--force` redoes everything.
