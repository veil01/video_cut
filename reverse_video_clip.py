import subprocess
import os
import re

# 将 .vtt 文件转换为 .txt 文件
def convert_vtt_to_txt(vtt_file, txt_file):
    """
    从 .vtt 文件提取字幕内容并保存为 .txt 文件
    """
    with open(vtt_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 提取字幕内容（忽略时间戳和空行）
    subtitles = []
    for line in lines:
        # 跳过时间戳行和空行
        if '-->' in line or line.strip() == '' or line.startswith('WEBVTT'):
            continue
        subtitles.append(line.strip())

    # 保存为 .txt 文件
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(subtitles))


# 检测敏感词并记录时间区间
def detect_sensitive_words(vtt_file, sensitive_words_file, output_segment_file):
    """
    从 .vtt 文件中提取时间和字幕内容，检测敏感词，并记录需要删除的时间段
    """
    # 读取敏感词列表
    with open(sensitive_words_file, 'r', encoding='utf-8') as f:
        sensitive_words = [line.strip() for line in f.readlines() if line.strip()]  # 去掉空行

    # 初始化存储需要删除的时间段
    remove_intervals = []

    # 正则表达式匹配时间区间
    time_pattern = re.compile(r'(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})')

    # 读取 .vtt 文件并逐行处理
    with open(vtt_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_time = None
    current_text = []

    for line in lines:
        line = line.strip()

        # 检查是否是时间行
        if time_pattern.match(line):
            # 如果当前有字幕内容，检查敏感词
            if current_time and current_text:
                content = ' '.join(current_text)
                if any(word in content for word in sensitive_words):
                    remove_intervals.append(current_time)
                current_text = []  # 清空当前字幕内容

            # 更新当前时间区间
            match = time_pattern.match(line)
            current_time = (match.group(1), match.group(2))

        # 如果是字幕内容行，累积到当前字幕文本中
        elif line and not line.startswith('WEBVTT'):
            current_text.append(line)

    # 检查最后一段字幕
    if current_time and current_text:
        content = ' '.join(current_text)
        if any(word in content for word in sensitive_words):
            remove_intervals.append(current_time)

    # 将需要删除的时间段写入输出文件
    with open(output_segment_file, 'w', encoding='utf-8') as f:
        for start_time, end_time in remove_intervals:
            f.write(f"{start_time} {end_time}\n")

def extract_segments_with_ffmpeg(input_video, segments_file, output_video):
    import shutil

    # 创建一个临时目录存储中间片段
    temp_dir = "temp_segments"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    # 读取 segments 文件
    with open(segments_file, 'r') as file:
        lines = file.readlines()
        remove_intervals = []
        for line in lines:
            # 直接解析 "start_time end_time"
            times = line.strip().split()
            if len(times) == 2:
                start_time, end_time = times
                remove_intervals.append((start_time, end_time))

    # 确保时间段按开始时间排序
    remove_intervals = sorted(remove_intervals, key=lambda x: x[0])

    # 提取每个需要移除的片段并保存为独立文件
    segment_files = []
    for i, (start, end) in enumerate(remove_intervals):
        segment_file = os.path.join(temp_dir, f"remove_segment_{i}.mp4")
        command = [
            "ffmpeg",
            "-i", input_video,
            "-ss", start,
            "-to", end,
            "-c:v", "libx264",  # 重新编码视频为 H.264
            "-crf", "23",       # 设置质量（23 是默认值，越小越高质量）
            "-preset", "fast",  # 设置编码速度（fast 是推荐值）
            "-c:a", "aac",      # 重新编码音频为 AAC
            "-b:a", "192k",     # 设置音频比特率
            "-y", segment_file
        ]
        result = subprocess.run(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to extract segment {i}: {result.stderr}")
        segment_files.append(segment_file)

    # 创建一个文件列表供 ffmpeg concat 使用
    concat_list_file = os.path.join(temp_dir, "concat_list.txt")
    with open(concat_list_file, 'w') as f:
        for segment_file in segment_files:
            f.write(f"file '{os.path.abspath(segment_file)}'\n")

    # 使用 ffmpeg concat 拼接所有片段
    concat_command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_file,
        "-c:v", "libx264",  # 重新编码视频为 H.264
        "-crf", "23",       # 设置质量
        "-preset", "fast",  # 设置编码速度
        "-c:a", "aac",      # 重新编码音频为 AAC
        "-b:a", "192k",     # 设置音频比特率
        "-y", output_video
    ]
    result = subprocess.run(concat_command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to concatenate segments: {result.stderr}")

    # 清理临时文件
    for segment_file in segment_files:
        os.remove(segment_file)
    os.remove(concat_list_file)
    shutil.rmtree(temp_dir)



if __name__ == "__main__":
    # 输入文件路径
    input_video = 'input\HU_1.mp4'
    vtt_file = "vtt/HU_1.vtt"  # 替换为你的 .vtt 文件路径
    txt_file = "temp/output.txt"  # 转换后的 .txt 文件路径
    sensitive_words_file = "temp/sensitive_words.txt"  # 敏感词列表文件路径
    output_segment_file = "temp/segments_to_remove.txt"  # 输出需要删除的时间段文件路径
    output_video = "delete/edited_video.mp4"
    
    # 步骤 1: 将 .vtt 文件转换为 .txt 文件
    convert_vtt_to_txt(vtt_file, txt_file)
    print(f"已将 {vtt_file} 转换为 {txt_file}。")

    # 步骤 2: 检测敏感词并记录时间区间
    detect_sensitive_words(vtt_file, sensitive_words_file, output_segment_file)
    print(f"已将包含敏感词的时间段保存到 {output_segment_file}。")

    extract_segments_with_ffmpeg(input_video, output_segment_file, output_video)
