#!/usr/bin/env python3
# Copyright (c) Opendatalab. All rights reserved.

"""
FastAPI版本测试脚本
用于测试API服务是否正常工作
"""

import requests
import time
import sys
from pathlib import Path

API_BASE_URL = "http://192.168.2.3:8000"


def test_health_check():
    """测试健康检查"""
    print("测试健康检查...")
    response = requests.get(f"{API_BASE_URL}/health")
    assert response.status_code == 200
    print(f"✓ 健康检查通过: {response.json()}")
    return True


def test_convert_file(file_path: str):
    """测试文件转换"""
    print(f"\n测试文件转换: {file_path}")
    
    if not Path(file_path).exists():
        print(f"✗ 文件不存在: {file_path}")
        return False
    
    # 上传文件
    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {
            "output_json": True,
            "use_split": False,
            "max_pages": 8
        }
        print("上传文件...")
        response = requests.post(f"{API_BASE_URL}/convert", files=files, data=data)
        
        if response.status_code != 200:
            print(f"✗ 上传失败: {response.status_code} - {response.text}")
            return False
        
        result = response.json()
        task_id = result["task_id"]
        print(f"✓ 任务已创建: {task_id}")
    
    # 轮询任务状态
    print("等待任务完成...")
    max_wait_time = 300  # 最多等待5分钟
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        response = requests.get(f"{API_BASE_URL}/task/{task_id}")
        if response.status_code != 200:
            print(f"✗ 查询任务状态失败: {response.status_code}")
            return False
        
        status = response.json()
        print(f"  状态: {status['status']} - {status['message']}")
        
        if status["status"] == "completed":
            print("✓ 转换完成!")
            
            # 下载Markdown文件
            if status.get("markdown_file"):
                print("下载Markdown文件...")
                md_response = requests.get(f"{API_BASE_URL}/download/{task_id}/markdown")
                if md_response.status_code == 200:
                    output_md = f"output_{task_id}.md"
                    with open(output_md, "wb") as f:
                        f.write(md_response.content)
                    print(f"✓ Markdown文件已保存: {output_md}")
            
            # 下载JSON文件
            if status.get("json_file"):
                print("下载JSON文件...")
                json_response = requests.get(f"{API_BASE_URL}/download/{task_id}/json")
                if json_response.status_code == 200:
                    output_json = f"output_{task_id}.json"
                    with open(output_json, "wb") as f:
                        f.write(json_response.content)
                    print(f"✓ JSON文件已保存: {output_json}")
                    print(f"  文档类型: {status.get('document_type', 'unknown')}")
            
            # 清理任务
            print("清理任务...")
            delete_response = requests.delete(f"{API_BASE_URL}/task/{task_id}")
            if delete_response.status_code == 200:
                print("✓ 任务已清理")
            
            return True
        
        elif status["status"] == "failed":
            print(f"✗ 转换失败: {status.get('error', '未知错误')}")
            return False
        
        time.sleep(2)  # 等待2秒后再次查询
    
    print(f"✗ 超时: 等待超过 {max_wait_time} 秒")
    return False


def main():
    """主函数"""
    print("=" * 50)
    print("PDF转换工具 API 测试")
    print("=" * 50)
    
    # 测试健康检查
    try:
        test_health_check()
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到API服务")
        print("请确保API服务已启动: python pdf_converter/api_server.py")
        sys.exit(1)
    except Exception as e:
        print(f"✗ 健康检查失败: {e}")
        sys.exit(1)
    
    # 测试文件转换（如果提供了文件路径）
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        try:
            success = test_convert_file(file_path)
            if success:
                print("\n✓ 所有测试通过!")
                sys.exit(0)
            else:
                print("\n✗ 测试失败")
                sys.exit(1)
        except Exception as e:
            print(f"\n✗ 测试出错: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        print("\n提示: 要测试文件转换，请提供文件路径:")
        print(f"  python {sys.argv[0]} <file_path>")


if __name__ == '__main__':
    main()

