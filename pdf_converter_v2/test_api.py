#!/usr/bin/env python3
"""
PDF Converter API 测试脚本

测试新增的投资类型：
- fsApproval: 可研批复
- fsReview: 可研评审  
- pdApproval: 初设批复
- safetyFsApproval: 安评可研批复

以及现有类型：
- settlementReport: 结算报告
- designReview: 初设评审
"""

import os
import sys
import json
import time
import base64
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List

# API 配置
API_BASE_URL = "http://47.101.133.94:14213"

# 测试文件配置
TEST_DIR = Path(__file__).parent / "test"

# 测试用例：文件名 -> (文档类型, 是否去水印, 是否只保留表格附件)
# 格式: 
#   "文件名": ("类型", 去水印, 只保留表格) - 完整格式
#   "文件名": ("类型", 去水印) - 兼容格式，只保留表格默认True
#   "文件名": "类型" - 旧格式，去水印False，只保留表格True
TEST_CASES = {
    # 新增投资类型
    "鄂电司发展〔2024〕124号　国网湖北省电力有限公司关于襄阳连云220千伏输变电工程可行性研究报告的批复.pdf": ("safetyFsApproval", True,False),  # 需要去水印 + 只保留表格附件
    # "2-（可研批复）晋电发展〔2017〕831号+国网山西省电力公司关于临汾古县、晋城周村220kV输变电等工程可行性研究报告的批复.pdf.pdf": "fsApproval",
    # "1-（可研评审）晋电经研规划〔2017〕187号(盖章)国网山西经研院关于山西晋城周村220kV输变电工程可行性研究报告的评审意见.pdf": "fsReview",
    # "5-（初设批复）晋电建设〔2019〕566号　国网山西省电力公司关于晋城周村220kV输变电工程初步设计的批复 .pdf": "pdApproval",
    # 现有类型
    # "9-（结算报告）山西晋城周村220kV输变电工程结算审计报告.pdf": "settlementReport",
    # "4-（初设评审）中电联电力建设技术经济咨询中心技经〔2019〕201号关于山西周村220kV输变电工程初步设计的评审意见.pdf": "designReview",
    # 决算报告
    # "10-（决算报告）盖章页-山西晋城周村220kV输变电工程竣工决算审核报告（中瑞诚鉴字（2021）第002040号）.pdf": "finalAccount",
}


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def print_result(success: bool, message: str):
    """打印结果"""
    status = "✅ 成功" if success else "❌ 失败"
    print(f"  {status}: {message}")


def check_health() -> bool:
    """检查 API 健康状态"""
    print_header("检查 API 健康状态")
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=10)
        if response.status_code == 200:
            print_result(True, f"API 正常运行 - {response.json()}")
            return True
        else:
            print_result(False, f"状态码: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_result(False, f"连接失败: {e}")
        return False


def upload_file(file_path: Path, document_type: str, remove_watermark: bool = False, table_only: bool = True) -> Optional[str]:
    """上传文件并获取任务 ID
    
    Args:
        file_path: 文件路径
        document_type: 文档类型
        remove_watermark: 是否去水印
        table_only: 是否只保留表格附件
    """
    print(f"\n  📤 上传文件: {file_path.name}")
    print(f"     类型: {document_type}")
    if remove_watermark:
        print(f"     去水印: 是")
    if table_only:
        print(f"     只保留表格: 是")
    
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/pdf")}
            # 使用 data 发送表单参数，参数名是 type（不是 document_type）
            data = {"type": document_type}
            
            # 添加去水印参数
            if remove_watermark:
                data["remove_watermark"] = "true"
                data["watermark_light_threshold"] = "200"
                data["watermark_saturation_threshold"] = "30"
            
            # 添加只保留表格参数
            data["table_only"] = "true" if table_only else "false"
            
            response = requests.post(
                f"{API_BASE_URL}/convert",
                files=files,
                data=data,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                task_id = result.get("task_id")
                print(f"     任务 ID: {task_id}")
                return task_id
            else:
                print_result(False, f"上传失败: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        print_result(False, f"上传异常: {e}")
        return None


def poll_task_status(task_id: str, max_wait: int = 300) -> Optional[Dict[str, Any]]:
    """轮询任务状态"""
    print(f"  ⏳ 等待任务完成...")
    
    start_time = time.time()
    poll_interval = 5  # 轮询间隔（秒）
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(f"{API_BASE_URL}/task/{task_id}", timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                status = result.get("status")
                
                if status == "completed":
                    elapsed = time.time() - start_time
                    print(f"     完成! 耗时: {elapsed:.1f}s")
                    return result
                elif status == "failed":
                    error = result.get("error", "未知错误")
                    print_result(False, f"任务失败: {error}")
                    return None
                else:
                    # 仍在处理中
                    elapsed = time.time() - start_time
                    print(f"     处理中... ({elapsed:.0f}s)", end="\r")
            else:
                print_result(False, f"查询状态失败: {response.status_code}")
                return None
                
        except Exception as e:
            print_result(False, f"查询异常: {e}")
            return None
        
        time.sleep(poll_interval)
    
    print_result(False, f"超时: 超过 {max_wait} 秒")
    return None


def get_json_result(task_id: str) -> Optional[Dict[str, Any]]:
    """获取 JSON 结果"""
    try:
        response = requests.get(f"{API_BASE_URL}/task/{task_id}/json", timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            print_result(False, f"获取 JSON 失败: {response.status_code}")
            return None
    except Exception as e:
        print_result(False, f"获取 JSON 异常: {e}")
        return None


def validate_result(result: Dict[str, Any], expected_type: str) -> bool:
    """验证结果"""
    document_type = result.get("document_type")
    data = result.get("data")
    
    # 检查文档类型
    if document_type != expected_type:
        print_result(False, f"文档类型不匹配: 期望 {expected_type}, 实际 {document_type}")
        return False
    
    # 检查数据是否为空
    if not data:
        print_result(False, "数据为空")
        return False
    
    # 对于投资类型，检查嵌套结构
    if expected_type in ["fsApproval", "fsReview", "pdApproval", "safetyFsApproval"]:
        if not isinstance(data, list):
            print_result(False, f"数据格式错误: 期望 list, 实际 {type(data).__name__}")
            return False
        
        if len(data) == 0:
            print_result(False, "投资数据列表为空")
            return False
        
        # 检查第一项的结构
        first_item = data[0]
        required_fields = ["name", "Level", "staticInvestment", "dynamicInvestment", "items"]
        missing_fields = [f for f in required_fields if f not in first_item]
        
        if missing_fields:
            print_result(False, f"缺少字段: {missing_fields}")
            return False
        
        print_result(True, f"解析到 {len(data)} 个大类")
        
        # 打印摘要
        for item in data:
            name = item.get("name", "")
            static = item.get("staticInvestment", 0)
            dynamic = item.get("dynamicInvestment", 0)
            sub_items = len(item.get("items", []))
            print(f"       - {name}: 静态={static}, 动态={dynamic}, 子项={sub_items}")
    
    # 对于结算报告
    elif expected_type == "settlementReport":
        if isinstance(data, list):
            print_result(True, f"解析到 {len(data)} 条记录")
        else:
            print_result(True, f"解析完成")
    
    # 对于初设评审
    elif expected_type == "designReview":
        if isinstance(data, list):
            print_result(True, f"解析到 {len(data)} 条记录")
        else:
            print_result(True, f"解析完成")
    
    return True


def test_single_file(file_path: Path, document_type: str, remove_watermark: bool = False, table_only: bool = True) -> bool:
    """测试单个文件
    
    Args:
        file_path: 文件路径
        document_type: 文档类型
        remove_watermark: 是否去水印
        table_only: 是否只保留表格附件
    """
    print_header(f"测试: {document_type}")
    print(f"  文件: {file_path.name}")
    if remove_watermark:
        print(f"  去水印: 是")
    if table_only:
        print(f"  只保留表格: 是")
    
    # 1. 上传文件
    task_id = upload_file(file_path, document_type, remove_watermark, table_only)
    if not task_id:
        return False
    
    # 2. 等待任务完成
    task_result = poll_task_status(task_id)
    if not task_result:
        return False
    
    # 3. 获取 JSON 结果
    json_result = get_json_result(task_id)
    if not json_result:
        return False
    
    # 4. 验证结果
    is_valid = validate_result(json_result, document_type)
    
    # 5. 保存结果到文件
    output_dir = Path(__file__).parent / "test_results"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{document_type}_result.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(json_result, f, ensure_ascii=False, indent=2)
    print(f"  💾 结果已保存: {output_file}")
    
    return is_valid


def run_all_tests():
    """运行所有测试"""
    print_header("PDF Converter API 测试")
    print(f"  API 地址: {API_BASE_URL}")
    print(f"  测试目录: {TEST_DIR}")
    
    # 检查测试目录
    if not TEST_DIR.exists():
        print_result(False, f"测试目录不存在: {TEST_DIR}")
        return
    
    # 检查 API 健康状态
    if not check_health():
        print("\n❌ API 不可用，终止测试")
        return
    
    # 统计结果
    total = 0
    passed = 0
    failed = 0
    skipped = 0
    
    # 运行每个测试用例
    for filename, config in TEST_CASES.items():
        # 解析配置格式
        if isinstance(config, tuple):
            if len(config) >= 3:
                document_type, remove_watermark, table_only = config[:3]
            elif len(config) == 2:
                document_type, remove_watermark = config
                table_only = True  # 默认只保留表格
            else:
                document_type = config[0]
                remove_watermark = False
                table_only = True
        else:
            document_type = config
            remove_watermark = False
            table_only = True
        
        file_path = TEST_DIR / filename
        
        if not file_path.exists():
            print_header(f"跳过: {document_type}")
            print_result(False, f"文件不存在: {filename}")
            skipped += 1
            continue
        
        total += 1
        
        try:
            if test_single_file(file_path, document_type, remove_watermark, table_only):
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print_result(False, f"测试异常: {e}")
            failed += 1
    
    # 打印总结
    print_header("测试总结")
    print(f"  总计: {total}")
    print(f"  ✅ 通过: {passed}")
    print(f"  ❌ 失败: {failed}")
    print(f"  ⏭️  跳过: {skipped}")
    
    if failed == 0 and skipped == 0:
        print("\n🎉 所有测试通过!")
    elif failed > 0:
        print(f"\n⚠️  有 {failed} 个测试失败")


def test_single(document_type: str):
    """测试单个类型"""
    print_header(f"单项测试: {document_type}")
    
    # 检查 API
    if not check_health():
        print("\n❌ API 不可用")
        return
    
    # 查找对应的文件
    for filename, config in TEST_CASES.items():
        # 解析配置格式
        if isinstance(config, tuple):
            if len(config) >= 3:
                dtype, remove_watermark, table_only = config[:3]
            elif len(config) == 2:
                dtype, remove_watermark = config
                table_only = True
            else:
                dtype = config[0]
                remove_watermark = False
                table_only = True
        else:
            dtype = config
            remove_watermark = False
            table_only = True
        
        if dtype == document_type:
            file_path = TEST_DIR / filename
            if file_path.exists():
                test_single_file(file_path, document_type, remove_watermark, table_only)
                return
            else:
                print_result(False, f"文件不存在: {filename}")
                return
    
    print_result(False, f"未找到类型 {document_type} 的测试文件")


def test_ocr(
    image_path: Optional[str] = None,
    remove_watermark: bool = False,
    light_threshold: int = 200,
    saturation_threshold: int = 30,
    crop_header_footer: bool = False,
    header_ratio: float = 0.05,
    footer_ratio: float = 0.05,
    auto_detect_header_footer: bool = False
) -> bool:
    """
    测试 OCR 接口
    
    Args:
        image_path: 图片路径或包含base64数据的txt文件路径，默认使用 test/image.png
                   支持格式：
                   - 图片文件：.png, .jpg, .jpeg
                   - txt文件：包含base64编码的图片数据（可带data:image/xxx;base64,前缀）
        remove_watermark: 是否去除水印
        light_threshold: 水印亮度阈值（0-255），默认200
        saturation_threshold: 水印饱和度阈值（0-255），默认30
        crop_header_footer: 是否裁剪页眉页脚
        header_ratio: 页眉裁剪比例（0-1），默认0.05
        footer_ratio: 页脚裁剪比例（0-1），默认0.05
        auto_detect_header_footer: 是否自动检测页眉页脚边界
    
    Returns:
        是否测试成功
    """
    print_header("测试 OCR 接口")
    
    # 检查 API
    if not check_health():
        print("\n❌ API 不可用")
        return False
    
    # 确定图片路径
    if image_path is None:
        image_path = TEST_DIR / "image.png"
    else:
        image_path = Path(image_path)
    
    print(f"  📷 文件路径: {image_path}")
    
    if not image_path.exists():
        print_result(False, f"文件不存在: {image_path}")
        return False
    
    suffix = image_path.suffix.lower()
    
    # 判断是 txt 文件还是图片文件
    if suffix == ".txt":
        # 从 txt 文件读取 base64 数据
        print(f"  📄 文件类型: txt (base64 数据)")
        try:
            with open(image_path, "r", encoding="utf-8") as f:
                image_base64 = f.read().strip()
            
            # 解析 data URI，提取格式和 base64 数据
            if image_base64.startswith("data:"):
                # 格式: data:image/png;base64,xxxxx
                if "," in image_base64:
                    header, image_base64 = image_base64.split(",", 1)
                    # 从 header 中提取图片格式
                    if "image/png" in header:
                        image_format = "png"
                    elif "image/jpeg" in header or "image/jpg" in header:
                        image_format = "jpeg"
                    else:
                        image_format = "png"  # 默认
                    print(f"  🖼️  图片格式 (从data URI解析): {image_format}")
                else:
                    image_format = "png"
                    print(f"  🖼️  图片格式 (默认): {image_format}")
            else:
                image_format = "png"
                print(f"  🖼️  图片格式 (默认): {image_format}")
            
            print(f"  🔤 Base64长度: {len(image_base64)} 字符")
            
        except Exception as e:
            print_result(False, f"读取txt文件失败: {e}")
            return False
    else:
        # 读取图片文件并转为 base64
        print(f"  📄 文件类型: 图片文件")
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")
            print(f"  📦 图片大小: {len(image_data)} bytes")
            print(f"  🔤 Base64长度: {len(image_base64)} 字符")
        except Exception as e:
            print_result(False, f"读取图片失败: {e}")
            return False
        
        # 确定图片格式
        format_map = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}
        image_format = format_map.get(suffix, "png")
        print(f"  🖼️  图片格式: {image_format}")
    
    # 调用 OCR 接口
    print(f"\n  📤 调用 OCR 接口...")
    # 构建请求参数
    request_data = {
        "image_base64": image_base64,
        "image_format": image_format
    }
    
    if crop_header_footer:
        request_data["crop_header_footer"] = True
        if auto_detect_header_footer:
            request_data["auto_detect_header_footer"] = True
            print(f"  ✂️  裁剪页眉页脚: 自动检测模式")
        else:
            request_data["header_ratio"] = header_ratio
            request_data["footer_ratio"] = footer_ratio
            print(f"  ✂️  裁剪页眉页脚: 是 (顶部={header_ratio*100:.0f}%, 底部={footer_ratio*100:.0f}%)")
    
    if remove_watermark:
        request_data["remove_watermark"] = True
        request_data["watermark_light_threshold"] = light_threshold
        request_data["watermark_saturation_threshold"] = saturation_threshold
        print(f"  🔧 去水印: 是 (亮度阈值={light_threshold}, 饱和度阈值={saturation_threshold})")
    
    try:
        start_time = time.time()
        response = requests.post(
            f"{API_BASE_URL}/ocr",
            json=request_data,
            timeout=120
        )
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            print_result(True, f"OCR 识别成功 (耗时: {elapsed:.2f}s)")
            
            # 显示识别结果（支持两种返回格式）
            # 格式1: {"texts": [...], "gpu_info": {...}}
            # 格式2: {"code": 0, "data": {"texts": [...]}, "gpu_info": {...}}
            if "data" in result and isinstance(result.get("data"), dict):
                texts: List[str] = result.get("data", {}).get("texts", [])
            else:
                texts: List[str] = result.get("texts", [])
            gpu_info = result.get("gpu_info", {})
            
            print(f"\n  📝 识别结果 ({len(texts)} 个文本块):")
            for i, text in enumerate(texts[:10]):  # 最多显示前10个
                # 截断长文本
                display_text = text[:50] + "..." if len(text) > 50 else text
                print(f"       [{i+1}] {display_text}")
            
            if len(texts) > 10:
                print(f"       ... 还有 {len(texts) - 10} 个文本块")
            
            # 显示 GPU 信息
            if gpu_info:
                print(f"\n  💻 GPU 监控信息:")
                gpu_util = gpu_info.get('gpu_utilization', gpu_info.get('gpu_util_avg', 'N/A'))
                if isinstance(gpu_util, float):
                    gpu_util = f"{gpu_util:.1f}"
                print(f"       GPU利用率: {gpu_util}%")
                
                mem_used = gpu_info.get('gpu_memory_used_max', gpu_info.get('memory_used_max', 'N/A'))
                if isinstance(mem_used, (int, float)):
                    mem_used = f"{mem_used / (1024**2):.0f}"  # 转为 MB
                print(f"       显存使用峰值: {mem_used} MB")
                
                gpu_name = gpu_info.get('gpu_name', 'N/A')
                print(f"       GPU型号: {gpu_name}")
            
            # 保存完整结果
            output_dir = Path(__file__).parent / "test_results"
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / "ocr_result.json"
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n  💾 结果已保存: {output_file}")
            
            return True
        else:
            print_result(False, f"OCR 失败: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print_result(False, "OCR 请求超时")
        return False
    except Exception as e:
        print_result(False, f"OCR 异常: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 测试指定类型
        doc_type = sys.argv[1]
        if doc_type in ["--help", "-h"]:
            print("用法:")
            print("  python test_api.py          # 运行所有测试")
            print("  python test_api.py <type>   # 测试指定类型")
            print("  python test_api.py ocr      # 测试 OCR 接口")
            print("  python test_api.py ocr <image_path>  # 测试 OCR（指定图片或txt）")
            print("  python test_api.py ocr <image_path> --nowm  # 测试 OCR 并去水印")
            print("  python test_api.py ocr <image_path> --crop  # 测试 OCR 并裁剪页眉页脚")
            print("  python test_api.py ocr <image_path> --nowm --crop  # 同时去水印和裁剪")
            print("\n可用类型:")
            for dtype in set(TEST_CASES.values()):
                print(f"  - {dtype}")
            print("  - ocr  (OCR 图片识别)")
            print("\nOCR 去水印参数:")
            print("  --nowm         启用去水印")
            print("  --light=N      亮度阈值（0-255，默认200）")
            print("  --sat=N        饱和度阈值（0-255，默认30）")
            print("\nOCR 裁剪页眉页脚参数:")
            print("  --crop         启用裁剪页眉页脚（固定比例模式）")
            print("  --crop-auto    启用裁剪页眉页脚（自动检测模式）")
            print("  --header=N     页眉裁剪比例（0-1，默认0.05表示5%）")
            print("  --footer=N     页脚裁剪比例（0-1，默认0.05表示5%）")
        elif doc_type == "ocr":
            # 解析 OCR 参数
            image_path = None
            remove_watermark = False
            light_threshold = 200
            saturation_threshold = 30
            crop_header_footer = False
            header_ratio = 0.05
            footer_ratio = 0.05
            auto_detect_header_footer = False
            
            for arg in sys.argv[2:]:
                if arg == "--nowm":
                    remove_watermark = True
                elif arg == "--crop":
                    crop_header_footer = True
                elif arg == "--crop-auto":
                    crop_header_footer = True
                    auto_detect_header_footer = True
                elif arg.startswith("--light="):
                    try:
                        light_threshold = int(arg.split("=")[1])
                    except ValueError:
                        print(f"警告: 无效的亮度阈值 {arg}，使用默认值 200")
                elif arg.startswith("--sat="):
                    try:
                        saturation_threshold = int(arg.split("=")[1])
                    except ValueError:
                        print(f"警告: 无效的饱和度阈值 {arg}，使用默认值 30")
                elif arg.startswith("--header="):
                    try:
                        header_ratio = float(arg.split("=")[1])
                    except ValueError:
                        print(f"警告: 无效的页眉比例 {arg}，使用默认值 0.05")
                elif arg.startswith("--footer="):
                    try:
                        footer_ratio = float(arg.split("=")[1])
                    except ValueError:
                        print(f"警告: 无效的页脚比例 {arg}，使用默认值 0.05")
                elif not arg.startswith("--"):
                    image_path = arg
            
            test_ocr(
                image_path, 
                remove_watermark, 
                light_threshold, 
                saturation_threshold,
                crop_header_footer,
                header_ratio,
                footer_ratio,
                auto_detect_header_footer
            )
        else:
            test_single(doc_type)
    else:
        # 运行所有测试
        run_all_tests()
