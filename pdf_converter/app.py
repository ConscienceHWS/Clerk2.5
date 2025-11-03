# Copyright (c) Opendatalab. All rights reserved.

import os
import json
from loguru import logger


if __name__ == '__main__':
    os.environ['MINERU_MODEL_SOURCE'] = "local"
    try:
        with open('/root/mineru.json', 'r+') as file:
            config = json.load(file)
            
            delimiters = {
                'display': {'left': '\\[', 'right': '\\]'},
                'inline': {'left': '\\(', 'right': '\\)'}
            }
            
            config['latex-delimiter-config'] = delimiters
            
            if os.getenv('apikey'):
                config['llm-aided-config']['title_aided']['api_key'] = os.getenv('apikey')
                config['llm-aided-config']['title_aided']['enable'] = True
                config['llm-aided-config']['title_aided']['model'] = "qwen3-next-80b-a3b-instruct"
            
            file.seek(0)  # 将文件指针移回文件开始位置
            file.truncate()  # 截断文件，清除原有内容
            json.dump(config, file, indent=4)  # 写入新内容
    except Exception as e:
        logger.exception(e)
    os.system('mineru-gradio --enable-vllm-engine true --server-name 0.0.0.0 --enable-api true --max-convert-pages 20 --latex-delimiters-type b --gpu-memory-utilization 0.9')