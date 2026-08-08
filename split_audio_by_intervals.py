"""Convert timeline intervals into audio arrays while preserving time offsets."""


def split_audio_by_intervals(audio_array, time_intervals=None, sr=16_000):
    """Return ``[start, end, samples]`` slices for the requested time ranges."""
    MIN_DURATION = 0.5  # 秒

    # ``None`` explicitly requests the full recording; an empty list means
    # every interval was excluded and must therefore produce no B segments.
    if time_intervals is None:
        time_intervals = [[0, len(audio_array) / sr]]

    # Sort and drop tiny fragments that Whisper cannot transcribe reliably.
    time_intervals = sorted(time_intervals, key=lambda x: x[0])
    time_intervals = [
        interval
        for interval in time_intervals
        if interval[1] - interval[0] >= MIN_DURATION
    ]
    # reset the audio segments list
    audio_segments = []

    # if there are time segments
    if time_intervals is not None and time_intervals and len(time_intervals) > 0:

        # take each time segment
        for time_interval in time_intervals:
            # calculate duration based on start and end times!!

            # and add it to an audio segments list
            # the format is [start_time, end_time, audio_array]
            audio_segment = [time_interval[0],
                             time_interval[1],
                             audio_array[int(time_interval[0] * sr):
                                         int(time_interval[1] * sr)]
                             ]

            audio_segments.append(audio_segment)

    return audio_segments, time_intervals
