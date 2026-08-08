"""Build audio slices that remain after subtitle-covered intervals are excluded."""

from split_audio_by_intervals import split_audio_by_intervals


def exclude_segments_by_intervals(audio_array,
                                  time_intervals,
                                  excluded_time_intervals,
                                  sr):
    """Remove covered timeline ranges, then return the remaining audio slices.

    ``excluded_time_intervals`` normally comes from subtitle A.  The returned
    slices retain their original start/end timestamps for subtitle B.
    """

    # sort the excluded segments by start time
    excluded_time_intervals = \
        sorted(excluded_time_intervals, key=lambda x: x[0])

    print('Excluding intervals:\n ', excluded_time_intervals)

    # if there are exclusion time segments
    if excluded_time_intervals and len(excluded_time_intervals) > 0:

        # take each time segment
        for excluded_time_interval in excluded_time_intervals:

            # print('\n---\nProcessing exclusion: ', excluded_time_interval)

            # and check it against each of the time segments we selected for transcription
            for time_interval in time_intervals:

                # print('\n', time_interval)

                # if the exclusion is outside the current segment times
                if excluded_time_interval[1] <= time_interval[0] \
                        or excluded_time_interval[0] >= time_interval[1]:

                    # print('outside, ignoring')
                    continue

                # if the exclusion is exactly as the current segment times
                elif time_interval[0] == excluded_time_interval[0] \
                        and time_interval[1] == excluded_time_interval[1]:

                    # simply remove the whole segment
                    time_intervals.remove(time_interval)

                    # print('exact match, removing')

                else:

                    # if the exclusion start time is equal to the segment start time
                    if excluded_time_interval[0] == time_interval[0]:

                        # cut out the beginning of the segment
                        # by using the end time of the exclusion as its start
                        time_interval[0] = excluded_time_interval[1]

                        # print('cutting beginning, modified segment:', time_interval)

                    # if the exclusion end time is equal to the segment end time
                    elif excluded_time_interval[1] == time_interval[1]:

                        # cut out the end of the segment
                        # by using the start time of the exclusion as its end
                        time_interval[1] = excluded_time_interval[0]

                        # print('cutting end, modified segment:', time_interval)

                    # if the exclusion is in the middle of the segment
                    elif excluded_time_interval[0] > time_interval[0] \
                            and excluded_time_interval[1] < time_interval[1]:

                        # print('splitting in two')

                        # remove the segment from the list
                        time_intervals.remove(time_interval)

                        # but then split it into two segments
                        # first the segment until the exclusion
                        time_intervals.append([time_interval[0],
                                               excluded_time_interval[0]])

                        # then the segment from the exclusion
                        time_intervals.append([excluded_time_interval[1],
                                               time_interval[1]])

                        # print('splitting in two: ',
                        #  [time_interval[0], excluded_time_interval[0]],
                        #  [excluded_time_interval[1], time_interval[1]])

    # sort the selection by start time
    time_intervals = sorted(time_intervals, key=lambda x: x[0])

    # print('New selection for transcription: \n ', time_intervals)

    # now split the audio by the newly created intervals
    audio_segments, time_intervals = split_audio_by_intervals(audio_array,
                                                              time_intervals,
                                                              sr)

    return audio_segments, time_intervals
