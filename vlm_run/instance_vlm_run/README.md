# instance_vlm_run

Repetition VLM (final_prompts, same request building and checks as `vlm_run/run_vlm_repetitions.py`) on
every head MP4 under an S3 prefix, as ONE Gemini Batch API job: 3 fps, media resolution low, half price.

Default source (`configs/s3_run.json`):

```
s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/station2/2026-11-22/<task>/<episode>/*_head.mp4
```

On 2026-11-24 that prefix held 112 episodes: task01 15, task02 26, task03 21, task04 9, task06 41 (7.7 GB).

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

## Files

| File | Purpose |
|---|---|
| `run_s3_vlm.py` | the driver (list, prepare, batch, collect, summary) |
| `configs/s3_run.json` | source, model, fps, media resolution, workers, output dirs, batch split size |
| `.env` / `.env.example` | `AWS_PROFILE`, region, `GEMINI_API_KEY` (git-ignored; shell wins; key falls back to `vlm_run/.env`) |
| `requirements.txt` | boto3, av, opencv-python-headless, numpy |
| `setup_instance.sh` | creates `.venv` here and installs the requirements |
| `run.sh` | runs `run_s3_vlm.py` with that venv |

The whole `vlm_run/` folder must sit next to this one (the driver imports `run_vlm_repetitions.py` and
uses its `configs/config.json` and `final_prompts/`).

## Setup

```bash
cd vlm_run/instance_vlm_run
./setup_instance.sh
# laptop: AWS_PROFILE=prod in .env, and: aws sso login --profile prod
# EC2: leave AWS_PROFILE empty; the instance role needs s3:ListBucket, s3:GetObject and s3:PutObject on the prefix
```

## Run

```bash
./run.sh --list                          # episodes in S3
./run.sh --dry-run                       # prepare everything, print request size and cost estimate, no Google call
./run.sh                                 # full run: one batch job, waits for it, writes results
./run.sh --task task04 --limit 2         # a subset
./run.sh --resume                        # interrupted while waiting: collect the submitted job(s)
./run.sh --summary-only
./run.sh --debug                         # also frames/ and raw_response.json per episode
```

On an instance run it detached: `nohup ./run.sh > run.log 2>&1 &`. Batch jobs take minutes to 24 h.

## Output (one folder per episode)

```
results/station2/2026-11-22/<task>/<episode>/<name>_vlm_result.json     response, code flags, step -> time, usage, cost, batch name, S3 video
results/station2/2026-11-22/<task>/<episode>/step_table.json     step -> t_s and frame index
results/station2/2026-11-22/<task>/<episode>/frames/             (--debug) the JPEGs the model saw
results/station2/2026-11-22/<task>/<episode>/raw_response.json   (--debug) the batch output line
results/station2/2026-11-22/summary.csv                          task, episode, cycles, action, flags, cost
results/station2/2026-11-22/batches/<id>/job.json                batch name, input file, episodes, state, cost
```

A rerun skips episodes whose `<name>_vlm_result.json` has a parsed response; `--force` redoes them.
