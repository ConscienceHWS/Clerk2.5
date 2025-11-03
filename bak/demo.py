from vllm import LLM
from PIL import Image
from mineru_vl_utils import MinerUClient
from mineru_vl_utils import MinerULogitsProcessor  # if vllm>=0.10.1

# 降低 GPU 内存利用率到 0.7 或更低
llm = LLM(
    model="OpenDataLab/MinerU2.5-2509-1.2B",
    logits_processors=[MinerULogitsProcessor],  # if vllm>=0.10.1
    gpu_memory_utilization=0.85,  # 从 0.9 降低到 0.7
)

client = MinerUClient(
    backend="vllm-engine",
    vllm_llm=llm
)

image = Image.open("/mnt/win_d/Clerk2.5/3.pdf")
extracted_blocks = client.two_step_extract(image)
print(extracted_blocks)
