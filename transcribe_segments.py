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


def transcribe_segments(audio_segments, other_whisper_options, model, output_srt):
    '''
    Transcribes only the passed audio segments
    and offsets the transcription segments start and end times

    '''

    subtitles = []

    # transcribe each audio segment
    for i, audio_segment in enumerate(audio_segments):

        print("Segment {} - second {} to {}"
              .format(i, audio_segment[0], audio_segment[1]))

        # run whisper transcribe on the audio segment
        result = model.transcribe(audio_segment[2],
                                  task='transcribe',
                                  verbose=False,
                                  **other_whisper_options)

        print("\nResults with offsets:")
        # now process the result and add the original start time offset
        # to each transcript segment start and end times

        # if there are segments in the result
        if 'segments' in result and result['segments']:

            # take each segment and add the offset to the start and end time
            for transcript_segment in result['segments']:
                transcript_segment['start'] += audio_segment[0]
                transcript_segment['end'] += audio_segment[0]

                # avoid end time being larger than the interval end time
                # - there seems to be an issue in the whisper model:
                #   https://github.com/openai/whisper/discussions/357
                if transcript_segment['end'] > audio_segment[1]:
                    transcript_segment['end'] = audio_segment[1]

                # also avoid start time being smaller than the interval start time
                if transcript_segment['start'] < audio_segment[0]:
                    transcript_segment['start'] = audio_segment[0]

                subtitles.append({
                    "start": transcript_segment["start"],
                    "end": transcript_segment["end"],
                    "text": transcript_segment["text"].strip()
                })
                print(transcript_segment['start'], ' --> ',
                      transcript_segment['end'], '\n', transcript_segment['text'])

        print("\n")

    # ==========================
    # 写 SRT
    # ==========================

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