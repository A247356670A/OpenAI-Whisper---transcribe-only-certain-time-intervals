def seconds_to_srt_time(seconds):
    """
    秒 -> SRT时间格式
    例如：
    123.456
    ->
    00:02:03,456
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))

    # 防止毫秒四舍五入到1000
    if milliseconds == 1000:
        milliseconds = 0
        secs += 1

    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def save_srt(subtitles, output_srt):
    subtitles.sort(key=lambda x: x["start"])

    with open(output_srt, "w", encoding="utf-8") as f:
        for idx, sub in enumerate(subtitles, start=1):
            f.write(f"{idx}\n")

            f.write(
                f"{seconds_to_srt_time(sub['start'])} --> "
                f"{seconds_to_srt_time(sub['end'])}\n"
            )

            f.write(sub["text"] + "\n\n")

    print(f"SRT saved to: {output_srt}")
    return output_srt


#
def transcribe(file_path,
               first_whisper_options,
               model,
               first_srt_file):
    subtitles = []

    try:

        print(f"Transcribing: {file_path}")

        result = model.transcribe(
            file_path,
            task="transcribe",
            verbose=True,
            **first_whisper_options
        )

        if "segments" in result and result["segments"]:

            for transcript_segment in result["segments"]:
                subtitles.append({
                    "start": transcript_segment["start"],
                    "end": transcript_segment["end"],
                    "text": transcript_segment["text"].strip()
                })

                print(
                    transcript_segment["start"],
                    "-->",
                    transcript_segment["end"],
                    transcript_segment["text"]
                )

        output_srt_path = save_srt(subtitles, first_srt_file)

        print(f"\n字幕已保存：{output_srt_path}")

        return output_srt_path

    except KeyboardInterrupt:

        print("\n\n检测到用户终止程序！")
        print("正在保存当前已识别字幕...")

        if subtitles:

            partial_file = first_srt_file.replace(
                ".srt",
                "_partial.srt"
            )

            save_srt(subtitles, partial_file)

            print(f"已保存部分字幕：{partial_file}")

        else:
            print("当前还没有可保存的字幕。")

        raise


def transcribe_segments(audio_segments,
                        second_whisper_options,
                        model,
                        second_srt_file):

    subtitles = []

    try:

        for i, audio_segment in enumerate(audio_segments):

            duration = audio_segment[1] - audio_segment[0]

            if duration < 0.5:
                print(
                    f"Skip segment {i}, duration={duration:.3f}s"
                )
                continue
            print(
                f"Segment {i} - second "
                f"{audio_segment[0]} to {audio_segment[1]}"
            )

            result = model.transcribe(
                audio_segment[2],
                task="transcribe",
                verbose=True,
                **second_whisper_options
            )

            if "segments" in result and result["segments"]:

                for transcript_segment in result["segments"]:

                    transcript_segment["start"] += audio_segment[0]
                    transcript_segment["end"] += audio_segment[0]

                    if transcript_segment["end"] > audio_segment[1]:
                        transcript_segment["end"] = audio_segment[1]

                    if transcript_segment["start"] < audio_segment[0]:
                        transcript_segment["start"] = audio_segment[0]

                    subtitles.append({
                        "start": transcript_segment["start"],
                        "end": transcript_segment["end"],
                        "text": transcript_segment["text"].strip()
                    })

                    print(
                        transcript_segment["start"],
                        "-->",
                        transcript_segment["end"],
                        transcript_segment["text"]
                    )

            print()

        # 正常结束
        output_srt_path = save_srt(subtitles, second_srt_file)
        return output_srt_path

    except KeyboardInterrupt:

        print("\n\n检测到用户终止程序！")
        print("正在保存当前已识别字幕...")

        partial_file = second_srt_file.replace(
            ".srt",
            "_partial.srt"
        )

        save_srt(subtitles, partial_file)

        print(
            f"已保存部分字幕：{partial_file}"
        )

        raise
