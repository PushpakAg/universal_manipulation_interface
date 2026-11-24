# Repetition VLM on station2 / 2026-11-22: findings

Gemini 3.8 Flash counting task cycles (repetitions) in the head-camera MP4s of
`s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/station2/2026-11-22/` (112 episodes: task01 15, task02 26,
task03 21, task04 9, task06 41). All runs on 2026-11-24. 260 model answers, total cost **$8.39**.

Data behind every number below: `vlm_runs_by_episode.csv` (one row per answer), `vlm_runs_summary.csv` (per run and
task), `video_token_counts.csv`, `vlm_findings.csv`. Rebuild with `python make_report_csv.py`.

## 1. Summary

**No setting change had a consistent effect.** Changing the prompt, the image resolution, the reasoning level, the frame
rate or the input format (images vs video) moved the cycle counts up on some episodes and down on others. More importantly,
**sending the identical request twice gave counts as different as any setting change** (for example 11 cycles, then 0).
The differences between settings in this report are therefore mostly run-to-run noise, not effects of the settings.

What is consistent:

- Wire and cable tasks (task01 to task03) are understood and counted stably (task02: 3 cycles in 26/26 episodes).
- The output format was followed every time: 260/260 answers were valid JSON in the required schema, none was cut off
  (max output 24,548 tokens against a 65,536 cap).
- When a run does find cycles, their times agree with other runs that found cycles.

What is not:

- task06 (very small LEDs) and, to a lesser degree, task04 (hex key) vary from run to run.
- A count of 0 is usually a miss: it comes with an invented explanation (calibration, idle operator, gripper in a vise)
  while another run of the same episode finds cycles at consistent times.

## 2. Runs

| Run | Input | Prompt set | fps | Media resolution | Reasoning | Episodes | Cost |
|---|---|---|---|---|---|---|---|
| R1 | images (JPEG, 768 px) | final_prompts 1.0 | 3 | low | model default | all 112 | $2.65 |
| R2 | images | final_prompts 1.0 | 1 | medium | medium | task04 + task06 (50) | $1.21 |
| R3 | images | final_prompts 1.0 | 10 | low | medium | task04 + task06 (50) | $2.80 |
| R4 | video (head MP4, Files API) | final_video_prompts 1.0 | 10 | low / medium / high | medium | task06/14, task06/38, live API | $0.44 |
| R5 | images and video | old vs v1.1 (small objects, follow the UMI grippers) | 3 | images low, video high | medium | 7 episodes; v1.1 sent twice | $1.30 |

Note on design: R2 changed frame rate, resolution and reasoning at the same time, and R3 changed frame rate and
reasoning relative to R1, so R1 to R3 cannot attribute a change to one setting. R4 and R5 change one thing at a time.

## 3. Inconsistency by type of change

### 3.1 Frame rate (R1 3 fps, R2 1 fps, R3 10 fps; images)

| task06, 41 episodes | R1 3 fps low | R2 1 fps medium | R3 10 fps low |
|---|---|---|---|
| total cycles | 61 | 83 | 13 |
| median cycles | 0 | 1 | 0 |
| episodes with 0 | 25 | 19 | 34 |
| action names an LED | 18 | 27 | 12 |
| distinct action phrasings | 36 | 28 | 37 |

- Same count in two runs: R1/R2 15 of 41, R1/R3 23, R2/R3 17. Almost all of this agreement is on **0**: the runs agree
  on a non-zero count for only **1 to 2 of 41** episodes.
- Episode level swings: task06/08 0 / 14 / 0, task06/38 10 / 9 / 0, task06/19 5 / 0 / 0, task06/16 0 / 6 / 0.
- task04 (9 episodes, R1/R2/R3): 00: 0/3/18, 03: 5/0/0, 05: 0/5/0, 07: 2/5/2, 08: 0/3/3; only 01 and 06 agree in all three.
- 10 fps was the worst on average, but the direction is not reliable per episode (R3 gave task04/00 18 cycles where R1
  gave 0).

### 3.2 Resolution (R4, video 10 fps, one request per resolution)

| Episode (earlier image counts) | low | medium | high |
|---|---|---|---|
| task06/38 (10, 9) | 0 | **6** | 0 |
| task06/14 (5, 4) | **6** | 0 | 0 |

- Low and medium were billed **the same input tokens** (54,592 and 21,319), so medium probably is not applied to video at
  all, yet the answers flipped between them. The difference is run-to-run noise, not resolution.
- High resolution (3.3 times the tokens) found no cycles in either episode, but was the only video setting that named the
  object an LED; low and medium called it "pin", "safety pin" or "pushpin".
- With images, R2 (medium) recognised LEDs most often (27/41), but R2 also changed frame rate and reasoning.

### 3.3 Reasoning (R1 default vs R5 images old prompts medium; same prompts, 3 fps, low resolution)

| Episode | R1 default reasoning | R5 medium reasoning | thinking tokens (R1 / R5) |
|---|---|---|---|
| task01/00 | 5 | 4 | 7,333 / 7,191 |
| task02/00 | 3 | 3 | 1,845 / 2,068 |
| task06/08 | 0 | 0 | 5,350 / 5,663 |
| task06/14 | 5 | 3 | 4,494 / 8,741 |
| task06/22 | 4 | 7 | 10,470 / 12,534 |
| task06/32 | 4 | **12** | 6,697 / 8,099 |
| task06/38 | **10** | **0** | 7,344 / 4,149 |

- The input is the same JPEG grid in both, only the reasoning level differs. Counts moved both ways (task06/32 up 8,
  task06/38 down 10).
- Medium reasoning did not use consistently more thinking tokens than the default (task06/38: 4,149 vs 7,344).
- Thinking tokens per answer stayed in the same range in every run (median 4,700 to 11,000) whether the request had 66
  frames or 620, so the model does not spend more reasoning on longer or denser inputs.

### 3.4 Prompt (R5: final_prompts 1.0 vs v1.1, same input)

v1.1 adds: the objects are tiny, hands are usually not visible, follow each UMI gripper and its finger state, re-check
before answering 0, name setup activities only when clearly seen. The output format and schema are unchanged.

| Episode | images old | images v1.1 (r1 / r2) | video old | video v1.1 (r1 / r2) |
|---|---|---|---|---|
| task01/00 (control) | 4 | 3 / 5 | 5 | 5 / 5 |
| task02/00 (control) | 3 | 3 / 4 | 3 | 3 / **6** |
| task06/08 | 0 | 0 / 0 | 0 | **12** / 0 |
| task06/14 | 3 | 5 / 5 | 5 | 8 / 6 |
| task06/22 | 7 | 6 / 11 | 3 | 9 / **16** |
| task06/32 | **12** | **0 / 0** | 3 | 11 / 0 |
| task06/38 | 0 | 10 / 18 | 0 | 11 / 0 |

- On video, v1.1 raised the task06 median from 3 to 8.5 and named LEDs more often (the old video prompt called them
  "connector", "white module" or found "no manipulation").
- On images, v1.1 lost task06/32 in both repeats (12 with the old prompt, then "test gripper in air", "calibrate
  gripper").
- v1.1 can over-segment: task02/00 went 3 to 6 once, task06/22 gave 16 cycles of 1 to 2 s each.
- Zero answers still occur with v1.1 (video 3 of 10, images 4 of 10).

### 3.5 Input format (images vs video, R5, same prompt version and 3 fps)

- Old prompts: task06 median 3 for both, but on different episodes (task06/32: images 12, video 3; task06/14: images 3,
  video 5).
- v1.1: video found more cycles on task06 (median 8.5 vs 5) but also gave the largest single swings (12 then 0).
- Video is 2 to 4 times cheaper per frame (about 69 tokens per frame at low or medium, 259 at high; images 266 at low,
  540 at medium). A full 112-episode batch at 3 fps high costs about $2.40 (input and output) vs $5 to $11 for 10 fps images.
- Video timestamps are coarser (the model reads time to about 1 s), but cycle times from video matched image runs where
  both found cycles.

### 3.6 Same request, sent twice (R5 r1 vs r2)

| Episode | images v1.1 | video v1.1 |
|---|---|---|
| task01/00 | 3 / 5 | 5 / 5 |
| task02/00 | 3 / 4 | 3 / 6 |
| task06/08 | 0 / 0 | 12 / 0 |
| task06/14 | 5 / 5 | 8 / 6 |
| task06/22 | 6 / 11 | 9 / 16 |
| task06/32 | 0 / 0 | 11 / 0 |
| task06/38 | 10 / 18 | 11 / 0 |

This is the baseline noise: identical requests at temperature 0 differ by up to 12 cycles. Every difference in
sections 3.1 to 3.5 is within this range, so none of them can be called an effect of the setting from one run.

## 4. What the counts do agree on

When cycles are found, their times line up across runs, prompts and input formats:

- task06/38: R1 (10 cycles), R5 images v1.1 r1 (10) and R5 video v1.1 r1 (11) mark cycles at the same seconds from 3 to 60 s.
- task06/32: R5 images old (12) and video v1.1 r1 (11) align cycle by cycle from 5 to 41 s.
- task06/08: R5 video v1.1 r1 found 12, R2 found 14; four other runs said 0.

So a non-zero answer confirmed by a second run is credible, and most zero answers on task06 are misses.

## 5. Other observations

- **Task understanding.** task01 to task03: always wire or cable into a tray. task04: split between "remove", "insert"
  and "calibrate" hex key in every run, which suggests the task04 cycle itself is ambiguous. task06: 28 to 37 different
  action phrasings per run; when the LED is not recognised the count is usually 0 (R1: generic "component" 12 of 17 zero,
  "calibrate / scan" 4 of 4 zero).
- **Request size.** A 125 MB request (task04/00, 1,531 images at 10 fps, 768 px) was rejected with HTTP 400 and failed
  its whole batch. At 512 px (67 MB) it was accepted. Video input avoids this limit.
- **Output tokens.** No answer reached the output cap; the automatic retry at low reasoning never triggered.

## 6. Likely causes (hypotheses, not tested)

1. **Perception of tiny objects.** Answers fail when the LED is not recognised; the gripper motion is visible but the
   model does not treat it as a cycle without seeing the object.
2. **Fixed reasoning budget.** Thinking tokens do not grow with the number of frames, so long or dense inputs (10 fps,
   600+ frames) get less reasoning per frame.
3. **Model non-determinism.** Temperature 0 does not make Gemini answers repeatable for long multimodal inputs.

## 7. Recommendations

1. **Measure repeatability before comparing settings.** Run each episode 2 to 3 times; treat a setting as better only if
   it wins across repeats.
2. **Retry zero answers** (same request, up to 3 times), and **vote**: take cycles that appear at the same times in at
   least 2 runs.
3. **Configuration to test next:** video input, final_video_prompts v1.1 plus a minimum cycle length (about 1.5 to 2 s)
   and a "do not split one pick-and-place" rule, 3 fps, media resolution high, medium reasoning, batch. Three runs of all
   112 episodes cost about $7 (prices double after 2026-12-31).
4. **Give the task.** Fill `given_task` per task folder (for example "pick an LED and place it into the container") so
   the model does not have to identify the object before counting. Define the task04 cycle (remove, insert or both).
5. **Ground truth.** Hand-count task06 episodes 05, 08, 16, 19, 20, 38, 39 and task04 00, 03, 05; without it the runs
   can only be compared with each other.

## 8. Costs

| Run | Answers | Cost |
|---|---|---|
| R1 | 112 | $2.65 |
| R2 | 50 | $1.21 |
| R3 | 50 | $2.80 |
| R4 | 6 (live, double price) | $0.44 |
| R5 | 42 | $1.30 |
| **Total** | **260** | **$8.39** |

Batch prices: $0.375 per M input and $1.875 per M output tokens (introductory, until 2026-12-31; live API is double).
Token counting (`countTokens`) is free.

## 9. Caveats

- R1 and R2 step tables were replaced by later runs; their cycle times are derived from the frame rate (exact for these
  sampling grids), and the 3 to 30 s duration flag is not recomputed for them.
- R1 to R3 change several settings at once (see section 2).
- R4 and R5 use few episodes (2 and 7) and at most two repeats; they show that differences exist, not their size.
- No ground truth was available: "correct" means agreement between runs, not verified counts.
