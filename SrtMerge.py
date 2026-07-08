import re


# =========================
# 时间转换
# =========================

def srt_time_to_seconds(t):
    h, m, s_ms = t.split(":")
    s, ms = s_ms.split(",")
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000


def seconds_to_srt_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


# =========================
# 解析 SRT
# =========================

def parse_srt(file_path):
    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2},\d{3})\s-->\s(\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\Z)",
        re.S
    )

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    subs = []
    for m in pattern.finditer(content):
        start = srt_time_to_seconds(m.group(1))
        end = srt_time_to_seconds(m.group(2))
        text = m.group(3).strip().replace("\n", " ")

        subs.append([start, end, text])

    return subs


# =========================
# 核心：智能去重
# =========================

def is_duplicate(a, b, time_threshold=0.5):
    """
    判断两个字幕是否重复

    条件：
    1. 时间非常接近
    2. 文本相同
    """
    start_a, end_a, text_a = a
    start_b, end_b, text_b = b

    time_close = abs(start_a - start_b) <= time_threshold and abs(end_a - end_b) <= time_threshold
    text_same = text_a == text_b

    return time_close and text_same


def merge_srt(old_srt, new_srt, time_threshold=0.5):
    old_subs = parse_srt(old_srt)
    new_subs = parse_srt(new_srt)

    all_subs = old_subs + new_subs
    all_subs.sort(key=lambda x: x[0])

    merged = []

    for sub in all_subs:
        duplicated = False

        for i in range(len(merged)):
            if is_duplicate(sub, merged[i], time_threshold):
                # 保留更长的那个（更完整）
                merged[i][0] = min(merged[i][0], sub[0])
                merged[i][1] = max(merged[i][1], sub[1])

                # 文本相同就跳过
                duplicated = True
                break

        if not duplicated:
            merged.append(sub)

    return merged


# =========================
# 写入 SRT
# =========================

def write_srt(subs, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(subs, 1):
            f.write(f"{i}\n")
            f.write(f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}\n")
            f.write(f"{text}\n\n")


# =========================
# 使用
# =========================

# old_srt = "/Users/junxianchen/四月一日/20260623_ドラキナちゃん最高！！目移りが止まらない第1章「ある夢に遊ぶ者の告白」中編【Vtuber】.srt"
# new_srt = "/Users/junxianchen/四月一日/20260623_ドラキナちゃん最高！！目移りが止まらない第1章「ある夢に遊ぶ者の告白」中編【Vtuber】_partB.srt"
# output_srt = "/Users/junxianchen/四月一日/20260623_ドラキナちゃん最高！！目移りが止まらない第1章「ある夢に遊ぶ者の告白」中編【Vtuber】_merged.srt"

# merged = merge_srt(old_srt, new_srt, time_threshold=0.5)
# write_srt(merged, output_srt)
#
# print("合并 + 去重完成:", output_srt)