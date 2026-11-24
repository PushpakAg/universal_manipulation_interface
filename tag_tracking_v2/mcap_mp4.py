
#!/usr/bin/env python3

"""
Process UMI MCAP recordings into three synchronised MP4 videos.

Input:
    MCAP containing three Foxglove CompressedVideo topics.

Output:
    camera0.mp4
    camera1.mp4
    camera2.mp4
    sync_manifest.csv
    sync_report.json

Synchronisation:
    - Uses embedded camera capture timestamps.
    - Finds common temporal overlap.
    - Builds a shared constant-FPS timeline.
    - Selects nearest source frame for each camera.
    - Enforces a configurable maximum timestamp error.
"""

import argparse
import av
import base64
import bisect
import csv
import json
import math
import cv2
import numpy as np

from pathlib import Path
from collections import defaultdict
from tempfile import TemporaryDirectory
from statistics import median


TOPICS = {
    "/cameras/camera0/video": "camera0",
    "/cameras/camera1/video": "camera1",
    "/cameras/camera2/video": "camera2",
}


def timestamp_to_ns(timestamp):
    """Convert Foxglove sec/nsec timestamp to nanoseconds."""
    return (
        int(timestamp["sec"]) * 1_000_000_000
        + int(timestamp["nsec"])
    )


def decode_mcap(mcap_path, temp_dir):
    """
    Read MCAP and decode individual compressed video frames.

    Each CompressedVideo message is expected to contain
    exactly one independently decodable video frame.
    """

    from mcap.reader import make_reader

    streams = defaultdict(list)
    codecs = {}

    print("\n[1/4] Reading MCAP and decoding camera streams...")

    with open(mcap_path, "rb") as f:
        reader = make_reader(f)

        for schema, channel, message in reader.iter_messages(
            topics=list(TOPICS.keys())
        ):

            topic = channel.topic
            camera = TOPICS[topic]

            if channel.message_encoding != "json":
                raise RuntimeError(
                    f"{topic}: Expected JSON message encoding, "
                    f"got {channel.message_encoding}"
                )

            payload = json.loads(message.data.decode("utf-8"))

            capture_ns = timestamp_to_ns(payload["timestamp"])

            video_format = payload["format"].lower()

            if video_format not in ("h264", "h265", "vp9", "av1"):
                raise RuntimeError(
                    f"Unsupported video format: {video_format}"
                )

            if camera in codecs and codecs[camera] != video_format:
                raise RuntimeError(
                    f"Codec changed within {camera}"
                )

            codecs[camera] = video_format

            compressed = base64.b64decode(payload["data"])

            if camera not in streams:
                streams[camera] = []

            if camera not in getattr(decode_mcap, "_decoders", {}):
                pass

            # Maintain one decoder context per camera.
            if not hasattr(decode_mcap, "_decoders"):
                decode_mcap._decoders = {}

            decoders = decode_mcap._decoders

            if camera not in decoders:
                decoders[camera] = av.CodecContext.create(
                    {"h265": "hevc", "h264": "h264"}.get(
                        video_format.lower(), video_format
                    ),
                    "r",
                )

            decoder = decoders[camera]

            packet = av.Packet(compressed)
            frames = decoder.decode(packet)

            if len(frames) != 1:
                raise RuntimeError(
                    f"{camera}: Expected exactly one decoded frame "
                    f"for message at {capture_ns}, got {len(frames)}. "
                    "Check codec packet structure and decoder support."
                )

            frame = frames[0].to_ndarray(format="bgr24")

            source_index = len(streams[camera])

            frame_path = (
                Path(temp_dir)
                / f"{camera}_{source_index:06d}.jpg"
            )

            success = cv2.imwrite(
                str(frame_path),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 95]
            )

            if not success:
                raise RuntimeError(
                    f"Could not save temporary frame: {frame_path}"
                )

            streams[camera].append({
                "timestamp_ns": capture_ns,
                "frame_index": source_index,
                "frame_path": str(frame_path),
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
                "log_time": int(message.log_time),
                "publish_time": int(message.publish_time),
            })

    # Reset decoder contexts for subsequent calls.
    decode_mcap._decoders = {}

    for camera, records in streams.items():
        records.sort(key=lambda x: x["timestamp_ns"])

        if not records:
            raise RuntimeError(f"No frames found for {camera}")

        timestamps = [r["timestamp_ns"] for r in records]

        if len(set(timestamps)) != len(timestamps):
            raise RuntimeError(
                f"{camera}: Duplicate capture timestamps detected. "
                "Resolve duplicates before synchronisation."
            )

        if any(
            b <= a for a, b in zip(timestamps, timestamps[1:])
        ):
            raise RuntimeError(
                f"{camera}: Non-monotonic timestamps."
            )

        print(
            f"{camera}: {len(records)} frames | "
            f"{codecs[camera]} | "
            f"{records[0]['width']}x{records[0]['height']}"
        )

    missing = set(TOPICS.values()) - set(streams.keys())

    if missing:
        raise RuntimeError(f"Missing camera streams: {missing}")

    return streams, codecs


def nearest_frame(records, target_ns):
    """Find the nearest source frame to a target timestamp."""

    timestamps = [r["timestamp_ns"] for r in records]

    pos = bisect.bisect_left(timestamps, target_ns)

    candidates = []

    if pos > 0:
        candidates.append(pos - 1)

    if pos < len(timestamps):
        candidates.append(pos)

    idx = min(
        candidates,
        key=lambda i: abs(timestamps[i] - target_ns)
    )

    record = records[idx]

    error_ms = abs(
        record["timestamp_ns"] - target_ns
    ) / 1_000_000

    return record, error_ms


def build_timeline(streams, fps, tolerance_ms):
    """Create a shared timeline across all three cameras."""

    print("\n[2/4] Building common synchronisation timeline...")

    start_ns = max(
        records[0]["timestamp_ns"]
        for records in streams.values()
    )

    end_ns = min(
        records[-1]["timestamp_ns"]
        for records in streams.values()
    )

    if start_ns >= end_ns:
        raise RuntimeError(
            "No overlapping time interval across camera streams."
        )

    duration = (end_ns - start_ns) / 1e9

    frame_count = math.floor(duration * fps) + 1

    timeline = []

    for i in range(frame_count):

        target_ns = start_ns + round(i * 1e9 / fps)

        selected = {}
        errors = {}

        for camera, records in streams.items():

            record, error_ms = nearest_frame(
                records, target_ns
            )

            selected[camera] = record
            errors[camera] = error_ms

        max_error = max(errors.values())

        if max_error > tolerance_ms:
            raise RuntimeError(
                f"Synchronisation tolerance exceeded at output "
                f"frame {i}: {max_error:.3f} ms > "
                f"{tolerance_ms:.3f} ms. "
                "Increase tolerance or investigate source timestamps."
            )

        timeline.append({
            "output_index": i,
            "target_ns": target_ns,
            "selected": selected,
            "errors": errors,
        })

    print(f"Common start: {start_ns}")
    print(f"Common end:   {end_ns}")
    print(f"Duration:     {duration:.3f} seconds")
    print(f"Output FPS:   {fps}")
    print(f"Output frames:{frame_count}")

    return timeline, start_ns, end_ns


def write_outputs(timeline, streams, output_dir, fps):
    """Write three synchronised MP4s and a frame-level manifest."""

    print("\n[3/4] Writing synchronised videos...")

    output_dir.mkdir(parents=True, exist_ok=True)

    writers = {}
    sizes = {}
    manifest_path = output_dir / "sync_manifest.csv"

    cameras = list(streams.keys())

    try:
        for camera in cameras:

            first_frame = cv2.imread(
                streams[camera][0]["frame_path"]
            )

            if first_frame is None:
                raise RuntimeError(
                    f"Cannot read initial frame for {camera}"
                )

            height, width = first_frame.shape[:2]

            output_path = output_dir / f"{camera}.mp4"

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

            writer = cv2.VideoWriter(
                str(output_path),
                fourcc,
                fps,
                (width, height)
            )

            if not writer.isOpened():
                raise RuntimeError(
                    f"Could not open video writer: {output_path}"
                )

            writers[camera] = writer
            sizes[camera] = (width, height)

        with open(manifest_path, "w", newline="") as csvfile:

            fieldnames = [
                "output_index",
                "target_timestamp_ns",
            ]

            for camera in cameras:
                fieldnames.extend([
                    f"{camera}_source_frame",
                    f"{camera}_source_timestamp_ns",
                    f"{camera}_error_ms",
                ])

            csv_writer = csv.DictWriter(
                csvfile,
                fieldnames=fieldnames
            )

            csv_writer.writeheader()

            for item in timeline:

                row = {
                    "output_index": item["output_index"],
                    "target_timestamp_ns": item["target_ns"],
                }

                for camera in cameras:

                    record = item["selected"][camera]

                    frame = cv2.imread(
                        record["frame_path"]
                    )

                    if frame is None:
                        raise RuntimeError(
                            f"Could not read {record['frame_path']}"
                        )

                    expected_size = sizes[camera]

                    if (
                        frame.shape[1] != expected_size[0]
                        or frame.shape[0] != expected_size[1]
                    ):
                        raise RuntimeError(
                            f"{camera}: Resolution changed during recording."
                        )

                    writers[camera].write(frame)

                    row[f"{camera}_source_frame"] = (
                        record["frame_index"]
                    )

                    row[f"{camera}_source_timestamp_ns"] = (
                        record["timestamp_ns"]
                    )

                    row[f"{camera}_error_ms"] = round(
                        item["errors"][camera], 4
                    )

                csv_writer.writerow(row)

    finally:
        for writer in writers.values():
            writer.release()

    print("Videos and manifest written.")


def write_report(
    streams,
    codecs,
    timeline,
    start_ns,
    end_ns,
    output_dir,
    fps
):
    """Generate a processing and synchronisation quality report."""

    report = {
        "input_streams": {},
        "synchronisation": {
            "method": "embedded_capture_timestamp_nearest_frame",
            "start_timestamp_ns": start_ns,
            "end_timestamp_ns": end_ns,
            "duration_seconds": (end_ns - start_ns) / 1e9,
            "output_fps": fps,
            "output_frame_count": len(timeline),
        }
    }

    for camera, records in streams.items():

        intervals = [
            (b["timestamp_ns"] - a["timestamp_ns"]) / 1e6
            for a, b in zip(records, records[1:])
        ]

        errors = [
            item["errors"][camera]
            for item in timeline
        ]

        report["input_streams"][camera] = {
            "source_frame_count": len(records),
            "codec": codecs[camera],
            "median_source_interval_ms": median(intervals),
            "median_source_fps": (
                1000 / median(intervals) if intervals else None
            ),
            "first_timestamp_ns": records[0]["timestamp_ns"],
            "last_timestamp_ns": records[-1]["timestamp_ns"],
            "median_alignment_error_ms": median(errors),
            "max_alignment_error_ms": max(errors),
        }

    with open(
        output_dir / "sync_report.json",
        "w"
    ) as f:
        json.dump(report, f, indent=4)

    print("\n[4/4] Processing report generated.")


def main():

    parser = argparse.ArgumentParser(
        description="Synchronise three UMI MCAP camera streams."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Input MCAP file."
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Output directory."
    )

    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="Common output FPS. Default: 30."
    )

    parser.add_argument(
        "--tolerance-ms",
        type=float,
        default=12.0,
        help="Maximum allowed source-frame timestamp error."
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    if args.fps <= 0 or args.tolerance_ms < 0:
        raise ValueError("FPS must be positive and tolerance non-negative.")

    output_dir = (
        Path(args.output)
        if args.output
        else input_path.parent / (
            input_path.stem + "_processed"
        )
    )

    print("=" * 60)
    print("UMI MCAP THREE-CAMERA SYNCHRONISATION")
    print("=" * 60)

    with TemporaryDirectory(prefix="umi_mcap_") as temp_dir:

        streams, codecs = decode_mcap(
            input_path,
            temp_dir
        )

        timeline, start_ns, end_ns = build_timeline(
            streams,
            args.fps,
            args.tolerance_ms
        )

        write_outputs(
            timeline,
            streams,
            output_dir,
            args.fps
        )

        write_report(
            streams,
            codecs,
            timeline,
            start_ns,
            end_ns,
            output_dir,
            args.fps
        )

    print("\nSUCCESS")
    print(f"Output directory: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
