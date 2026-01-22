#!/usr/bin/env python3
"""
PDF Converter API 测试脚本

测试新增的投资类型：
- fsApproval: 可研批复
- fsReview: 可研评审  
- pdApproval: 初设批复

以及现有类型：
- settlementReport: 结算报告
- designReview: 初设评审
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any

# API 配置
API_BASE_URL = "http://47.101.133.94:14213"

# 测试文件配置
TEST_DIR = Path(__file__).parent / "test"

# 测试用例：文件名 -> 文档类型
TEST_CASES = {
    # 新增投资类型
    # "2-（可研批复）晋电发展〔2017〕831号+国网山西省电力公司关于临汾古县、晋城周村220kV输变电等工程可行性研究报告的批复.pdf.pdf": "fsApproval",
    # "1-（可研评审）晋电经研规划〔2017〕187号(盖章)国网山西经研院关于山西晋城周村220kV输变电工程可行性研究报告的评审意见.pdf": "fsReview",
    # "5-（初设批复）晋电建设〔2019〕566号　国网山西省电力公司关于晋城周村220kV输变电工程初步设计的批复 .pdf": "pdApproval",
    # 现有类型
    # "9-（结算报告）山西晋城周村220kV输变电工程结算审计报告.pdf": "settlementReport",
    # "4-（初设评审）中电联电力建设技术经济咨询中心技经〔2019〕201号关于山西周村220kV输变电工程初步设计的评审意见.pdf": "designReview",
    # 决算报告
    "10-（决算报告）盖章页-山西晋城周村220kV输变电工程竣工决算审核报告（中瑞诚鉴字（2021）第002040号）.pdf": "finalAccount",
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


def upload_file(file_path: Path, document_type: str) -> Optional[str]:
    """上传文件并获取任务 ID"""
    print(f"\n  📤 上传文件: {file_path.name}")
    print(f"     类型: {document_type}")
    
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/pdf")}
            # 使用 data 发送表单参数，参数名是 type（不是 document_type）
            data = {"type": document_type}
            
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
    if expected_type in ["fsApproval", "fsReview", "pdApproval"]:
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


def test_single_file(file_path: Path, document_type: str) -> bool:
    """测试单个文件"""
    print_header(f"测试: {document_type}")
    print(f"  文件: {file_path.name}")
    
    # 1. 上传文件
    task_id = upload_file(file_path, document_type)
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
    for filename, document_type in TEST_CASES.items():
        file_path = TEST_DIR / filename
        
        if not file_path.exists():
            print_header(f"跳过: {document_type}")
            print_result(False, f"文件不存在: {filename}")
            skipped += 1
            continue
        
        total += 1
        
        try:
            if test_single_file(file_path, document_type):
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
    for filename, dtype in TEST_CASES.items():
        if dtype == document_type:
            file_path = TEST_DIR / filename
            if file_path.exists():
                test_single_file(file_path, document_type)
                return
            else:
                print_result(False, f"文件不存在: {filename}")
                return
    
    print_result(False, f"未找到类型 {document_type} 的测试文件")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 测试指定类型
        doc_type = sys.argv[1]
        if doc_type in ["--help", "-h"]:
            print("用法:")
            print("  python test_api.py          # 运行所有测试")
            print("  python test_api.py <type>   # 测试指定类型")
            print("\n可用类型:")
            for dtype in set(TEST_CASES.values()):
                print(f"  - {dtype}")
        else:
            test_single(doc_type)
    else:
        # 运行所有测试
        run_all_tests()
