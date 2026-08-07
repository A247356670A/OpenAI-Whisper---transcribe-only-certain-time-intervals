from SrtMerge import merge_srt, write_srt
from SrtToIntervals import extract_time_intervals
from exclude_segments_by_intervals import exclude_segments_by_intervals
from split_audio_by_intervals import split_audio_by_intervals
from transcribe import transcribe_segments, transcribe

import torch
import whisper
import librosa

# load whisper model
torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = whisper.load_model("large-v2")

# define whisper options:
second_whisper_options = {
    "language": "Japanese",
    "word_timestamps": True,
    "suppress_tokens": [],
    "condition_on_previous_text": False,
}
task = 'transcribe'
# upload the files
file_path = "/Users/junxianchen/四月一日/20260622_シーズン3きたああ！！初めてのロスカリファ！！！第1章「ある夢に遊ぶ者の告白」前半戦【Vtuber】.mp4"

# srt file from fist whisper
first_srt_file = "20260622_シーズン3きたああ！！初めてのロスカリファ！！！第1章「ある夢に遊ぶ者の告白」前半戦【Vtuber】.srt"

# srt file from second whisper
second_srt_file = "20260622_シーズン3きたああ！！初めてのロスカリファ！！！第1章「ある夢に遊ぶ者の告白」前半戦【Vtuber】_partB.srt"

print("Using file: ", file_path)

"""
Load audio using librosa

We're using librosa to load the audio as an array.
This is not necessary for the default Whisper pipeline, but we'll need it later to split the audio into the segments we want.
"""

# load audio file using librosa and get the audio_array
audio_array, sr = librosa.load(file_path, sr=16_000)
# there's just one audio segment, which is the full audio array
audio_segments = audio_array


"""
Do not transcribe certain segments (transcription 3)

#### First, define which time intervals you absolutely don't want to transcribe

Note: you do not need to do any of the previous transcriptions for this to work.
"""

# you can either use the full audio file ...
time_intervals = [[0, len(audio_array) / sr]]

# ... or time intervals as above
# time_intervals =  [[1, 6], [19, 27], [30, 32], [40.6, 53.12], [54, 60]]

print('Selected intervals for transcription:\n ', time_intervals)

# which time segments we do NOT want to transcribe?
# format is same as above:
#  [[segment1_start_time, segment1_end_time], [segment2_start_time, segment2_end_time], etc.]
# these times can be in an unordered fashion, as they will be sorted later


excluded_time_intervals = extract_time_intervals(
    first_srt_file,
    merge_gap=1.0
)

# call the exclude function to filter out the unwanted audio segments
audio_segments, time_intervals = \
    exclude_segments_by_intervals(audio_array,
                                  time_intervals,
                                  excluded_time_intervals,
                                  sr)

print('time intervals:\n {} \n'.format(time_intervals))
print('audio segments:\n ', audio_segments)

"""#### Now transcribe only the segments that haven't been excluded
Note: you do not need to do the first two transcriptions for this to work
"""

# transcribe each audio segment without the exclusions
transcribe_segments(audio_segments, second_whisper_options, model, second_srt_file)

merged = merge_srt(first_srt_file, second_srt_file, time_threshold=0.5)

merged_srt = first_srt_file.replace(
    ".srt",
    "_merged.srt"
)
write_srt(merged, merged_srt)

print("合并 + 去重完成:", merged_srt)

"""# Only transcribe certain segments (transcription 2)
#### But, first define which using their start and end times
"""

# which time intervals do we want to transcribe?
# anything in the audio not within these intervals will be ignored
# format is
# [
#    [segment1_start_time, segment1_end_time],
#    [segment2_start_time, segment2_end_time],
#    etc.
# ]
# these times can be placed in an unordered fashion,
# as they will be sorted later
# time_intervals = [[54, 60], [19, 27], [40.600, 53.120]]

# print('Selected intervals for transcription:\n {} \n'.format(time_intervals))

# call split function
# audio_segments, time_intervals = \
# split_audio_by_intervals(audio_array, time_intervals, sr)

# print('time intervals:\n {} \n'.format(time_intervals))
# print('audio segments:\n {} \n'.format(audio_segments))

"""#### Now transcribe only those segments

Note: for this to work you do not need to do the first transcription.
"""

# transcribe_segments(audio_segments, other_whisper_options)
