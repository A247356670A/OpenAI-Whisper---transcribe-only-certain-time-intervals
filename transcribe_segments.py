def transcribe_segments(audio_segments, other_whisper_options, model):
    '''
    Transcribes only the passed audio segments
    and offsets the transcription segments start and end times

    '''

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

                print(transcript_segment['start'], ' --> ',
                      transcript_segment['end'], '\n', transcript_segment['text'])

        print("\n")
