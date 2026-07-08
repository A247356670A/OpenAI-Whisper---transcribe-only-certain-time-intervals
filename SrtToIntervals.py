import re

def srt_time_to_seconds(time_str):
    """
    将 SRT 时间格式 HH:MM:SS,mmm 转换为秒(float)
    """
    h, m, s_ms = time_str.split(":")
    s, ms = s_ms.split(",")

    return (
        int(h) * 3600 +
        int(m) * 60 +
        int(s) +
        int(ms) / 1000
    )


def merge_intervals(intervals, max_gap=1.0):
    """
    合并相邻时间段。

    如果：
        下一个开始时间 - 当前结束时间 <= max_gap
    则认为属于同一个时间段。

    Parameters
    ----------
    intervals : list
        [[start, end], ...]

    max_gap : float
        最大允许间隔（秒）

    Returns
    -------
    list
        合并后的时间段
    """

    if not intervals:
        return []

    merged = [intervals[0]]

    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]

        if start - last_end <= max_gap:
            # 合并，更新时间段结束时间
            merged[-1][1] = max(last_end, end)
        else:
            merged.append([start, end])

    return merged


def extract_time_intervals(srt_file, merge_gap=1.0):
    """
    提取 SRT 时间段，并自动合并相邻时间段。

    返回：
        [
            [start1, end1],
            [start2, end2],
            ...
        ]
    """

    pattern = re.compile(
        r'(\d{2}:\d{2}:\d{2},\d{3})\s-->\s(\d{2}:\d{2}:\d{2},\d{3})'
    )

    time_intervals = []

    with open(srt_file, "r", encoding="utf-8") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                start = srt_time_to_seconds(match.group(1))
                end = srt_time_to_seconds(match.group(2))
                time_intervals.append([start, end])

    # 按开始时间排序（保险起见）
    time_intervals.sort(key=lambda x: x[0])

    # 自动合并
    return merge_intervals(time_intervals, merge_gap)


# ==========================
# Example
# ==========================
#
# srt_file = "20260623_ドラキナちゃん最高！！目移りが止まらない第1章「ある夢に遊ぶ者の告白」中編【Vtuber】_LLM_zh.srt"
#
# time_intervals = extract_time_intervals(
#     srt_file,
#     merge_gap=1.0
# )
#
# print(time_intervals)