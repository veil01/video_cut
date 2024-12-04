import re
import ffmpeg
from datetime import timedelta
from transformers import AutoModelForCausalLM, AutoTokenizer
import requests



def read_transcript(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    
    pattern = r'\[(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\](.*)'
    matches = re.findall(pattern, content)
    
    timestamps_and_text = [(start, end, text.strip()) for start, end, text in matches]
    return timestamps_and_text




def judging(transcripts):

    model_name = "Qwen/Qwen2.5-1.5B"

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype="auto",
        device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    
    prompt_body = f'transcripts:{transcripts}'
    # prompt_head = "判断下面的transcribe的字幕内容里是否存在推销产品、感谢直播间刷的礼物等内容。如果符合，输出它们所在的时间，没有就不用回复任何东西。"
    prompt_head ='你看一下下面的transcripts中是否存在high quality、high level、单独的G,如果有，输出它们出现的时间。如果存在多个，中间以逗号隔开。'
    prompt = prompt_head + prompt_body
    

    messages = [
        {"role": "system", "content": "你的名字叫做千问，是一个转录文件的辨别助手，你的工作就是对一段文字进行甄别和判断，判断它是否符合条件。你无需回复除了我要求你的其它任何文字，包括自我介绍，问候语，开场词等。"}
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False
    )
    model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=512
    )
    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]

    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

    return response

def extract_times_and_texts(transcript):
    times_and_texts = []
    pattern = r'\[(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\]\s*(.*)'
    
    with open(transcript, 'r', encoding='utf-8') as file:
        lines = file.readlines()  # 读取所有行
        for line in lines:
            match = re.match(pattern, line)
            if match:
                timestamp = match.group(1)  # 开始时间
                text = match.group(3).strip()  # 提取文本
                if any(keyword in text for keyword in ['high quality', 'high-level', 'G']):
                    times_and_texts.append((timestamp, text))
    print(times_and_texts)
    return times_and_texts



def send_to_qwen(transcripts):

    
    url = "http://localhost:5055/generate"  # 替换为实际的 API 地址
    payload = {"prompt": "".join(transcripts)}
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("\nQwen 回复:", response.json().get("response"))
    else:
        print("发送失败")
        
        
def time_str_to_seconds(time_str):
    try:
        # 分割时间字符串
        parts = time_str.split(':')
        
        # 根据部分数量处理小时、分钟和秒
        if len(parts) == 3:  # 格式为 HH:MM:SS
            hours, minutes, seconds = parts
        elif len(parts) == 2:  # 格式为 MM:SS
            hours = '0'
            minutes, seconds = parts
        elif len(parts) == 1:  # 格式为 SS
            return float(parts[0])  # 直接返回秒数
        else:
            raise ValueError("Invalid time format")

        # 将小时和分钟转换为整数，秒数转换为浮点数
        total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return total_seconds
    except ValueError as e:
        print(f"Error parsing time string '{time_str}': {e}")
        return None  # 或者抛出异常，取决于你的需求


    


def clip_video(input_file, output_file, remove_regions):
    try:
        probe_result = ffmpeg.probe(input_file)
        input_duration = float(probe_result['format']['duration'])
    except ffmpeg.Error as e:
        print(f"Error probing video: {e}")
        return

    remove_clips = []

    for start, end, _ in remove_regions:
        start_sec = time_str_to_seconds(start)
        end_sec = time_str_to_seconds(end)
        
        # 检查转换结果是否为 None
        if start_sec is None or end_sec is None:
            print(f"Invalid time string: start='{start}', end='{end}'")
            continue
        
        # 确保开始时间小于结束时间，并且都在视频时长内
        if start_sec < end_sec and start_sec < input_duration and end_sec <= input_duration:
            remove_clips.append((start_sec, end_sec))
        else:
            print(f"Invalid time range: start={start_sec}, end={end_sec}")

    if not remove_clips:
        print("No valid regions to remove.")
        return

    input_stream = ffmpeg.input(input_file)

    clips = []
    for start, end in remove_clips:
        duration = end - start
        if duration > 0:  # 确保持续时间为正
            clips.append(input_stream.video.trim(start=start, duration=duration))
        else:
            print(f"Invalid duration for clip: start={start}, end={end}")

    if not clips:
        print("No valid clips to process.")
        return

    final_clip = clips[0]
    for clip in clips[1:]:
        final_clip = final_clip.overlay(clip, enable='between(t,{},{})'.format(remove_clips[-1][1], input_duration))

    final_clip = final_clip.setpts('PTS-STARTPTS')
    final_clip.output(output_file).run()



# 示例用法
input_transcript = 'Body Language 2.txt'
input_video = 'Body Language 2.mp4'
output_video = f'output/output_{input_video}.mp4'


times_and_texts = extract_times_and_texts(input_transcript)
remove_regions = [(time[:10], time[11:], text) for time, text in times_and_texts]
clip_video(input_video, output_video, remove_regions)

# 顺序：
# 1.建立一个空列表filter_time，用于收集符合条件的语句时间。
# 2.使用AI对每三行的内容进行判断，看是否符合条件。符合的将被传入进filter_time。传入的应只有开始时间，结束时间。
# 3.对在filter_time中的时间进行读取，