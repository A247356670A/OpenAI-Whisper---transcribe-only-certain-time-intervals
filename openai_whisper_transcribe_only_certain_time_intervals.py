# -*- coding: utf-8 -*-
"""OpenAI Whisper - transcribe only certain time intervals.ipynb
Original file is located at
    https://colab.research.google.com/drive/17cTsmfVJmpDDMURGcu8hUu1zHNAYbfa5

# OpenAI Whisper with time intervals

This allows you to make transcriptions on certain time intervals or even exclude certain time intervals from the transcriptions by getting the audio as an array and filtering stuff out before passing it to whisper.

Written by [Octavian Mot](https://github.com/octimot/)

!apt install ffmpeg

pip install git+https://github.com/openai/whisper.git
pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu116
pip install ffmpeg-python
pip install librosa
!nvidia-smi 
"""

from SrtToIntervals import extract_time_intervals
from exclude_segments_by_intervals import exclude_segments_by_intervals
from split_audio_by_intervals import split_audio_by_intervals
from transcribe_segments import transcribe_segments

import torch
import whisper
import librosa

# load whisper model
torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = whisper.load_model("large-v2")

# define whisper options:
other_whisper_options = {
    "language": "Japanese",
    "word_timestamps": True,
    "suppress_tokens": [],
    "condition_on_previous_text": False,
}
task = 'transcribe'
# upload the files
audio_file_path = "20260623_ドラキナちゃん最高！！目移りが止まらない第1章「ある夢に遊ぶ者の告白」中編【Vtuber】.mp4"

srt_file = "20260623_ドラキナちゃん最高！！目移りが止まらない第1章「ある夢に遊ぶ者の告白」中編【Vtuber】_LLM_zh.srt"

print("Using audio file:", audio_file_path)

"""# Load audio using librosa

We're using librosa to load the audio as an array.
This is not necessary for the default Whisper pipeline, but we'll need it later to split the audio into the segments we want.
"""

# load audio file using librosa and get the audio_array
audio_array, sr = librosa.load(audio_file_path, sr=16_000)
# there's just one audio segment, which is the full audio array
audio_segments = audio_array

"""# Transcribe full audio with Whisper (transcription 1)

Just to see all the transcriptions segments as you'd expect from a normal Whisper transcription, and then use them for visual comparison.
"""

# transcribe the audio
# results = model.transcribe(audio_segments, task=task, verbose=True, **other_whisper_options)

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

"""# Do not transcribe certain segments (transcription 3)

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
    srt_file,
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
transcribe_segments(audio_segments, other_whisper_options, model)
