#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF转换API测试脚本
测试上传文件、轮询状态、获取结果等功能，并生成测试报告
"""

import os
import sys
import time
import json
import requests
import statistics
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 测试配置
API_BASE_URL = "http://47.100.220.144:4214"
TEST_RUNS_PER_FILE = 3  # 每个文件测试次数
POLL_INTERVAL = 2  # 轮询间隔（秒）
MAX_POLL_ATTEMPTS = 300  # 最大轮询次数（300次 * 2秒 = 10分钟超时）
SUPPORTED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg'}

# 文档类型映射（根据文件名推断）
FILE_TYPE_MAP = {
    '噪声': 'noiseRec',
    '电磁': 'emRec',
    '工况': 'opStatus',
}


@dataclass
class TestResult:
    """单次测试结果"""
    file_name: str
    run_number: int
    task_id: Optional[str] = None
    upload_time: Optional[float] = None
    upload_status_code: Optional[int] = None
    upload_error: Optional[str] = None
    total_time: Optional[float] = None
    poll_count: int = 0
    final_status: Optional[str] = None
    json_response: Optional[Dict] = None
    json_file_path: Optional[str] = None  # 保存的JSON文件路径
    error_message: Optional[str] = None
    success: bool = False


@dataclass
class ConcurrentTestResult:
    """并发测试结果"""
    file_name: str
    file_path: str
    task_id: Optional[str] = None
    upload_time: Optional[float] = None
    upload_status_code: Optional[int] = None
    total_time: Optional[float] = None
    poll_count: int = 0
    final_status: Optional[str] = None
    json_response: Optional[Dict] = None
    json_file_path: Optional[str] = None
    error_message: Optional[str] = None
    success: bool = False
    # 对比数据
    avg_sequential_time: float = 0.0  # 之前单次测试的平均耗时
    time_difference: float = 0.0  # 并发耗时与平均耗时的差值
    time_difference_percent: float = 0.0  # 耗时差异百分比
    result_similarity: float = 0.0  # 与之前结果的一致性（0-1）


@dataclass
class FileTestSummary:
    """单个文件的测试汇总"""
    file_name: str
    file_path: str
    file_type: Optional[str] = None
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    avg_upload_time: float = 0.0
    avg_total_time: float = 0.0
    min_total_time: float = 0.0
    max_total_time: float = 0.0
    time_stability: float = 0.0  # 时间稳定度（1 - 变异系数，值越大越稳定）
    result_consistency: float = 0.0  # 结果一致性（JSON结构一致性，0-1）
    results: List[TestResult] = None
    concurrent_result: Optional[ConcurrentTestResult] = None  # 并发测试结果
    
    def __post_init__(self):
        if self.results is None:
            self.results = []


class APITester:
    """API测试器"""
    
    def __init__(self, api_base_url: str, pdf_dir: str, runs_per_file: int = TEST_RUNS_PER_FILE, output_dir: Optional[str] = None):
        self.api_base_url = api_base_url.rstrip('/')
        self.pdf_dir = Path(pdf_dir)
        self.runs_per_file = runs_per_file
        self.test_results: List[FileTestSummary] = []
        self.session = requests.Session()
        self.session.timeout = 30
        
        # 设置输出目录（用于保存JSON结果）
        if output_dir is None:
            self.output_dir = project_root / "test" / "json_results"
        else:
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def infer_file_type(self, file_name: str) -> Optional[str]:
        """根据文件名推断文档类型"""
        for keyword, file_type in FILE_TYPE_MAP.items():
            if keyword in file_name:
                return file_type
        return None
    
    def upload_file(self, file_path: Path, file_type: Optional[str] = None) -> Dict:
        """上传文件并返回响应"""
        url = f"{self.api_base_url}/convert"
        
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, self._get_content_type(file_path))}
            data = {}
            if file_type:
                data['type'] = file_type
            
            response = self.session.post(url, files=files, data=data)
            return {
                'status_code': response.status_code,
                'response': response.json() if response.status_code == 200 else None,
                'error': None if response.status_code == 200 else response.text
            }
    
    def _get_content_type(self, file_path: Path) -> str:
        """根据文件扩展名获取Content-Type"""
        ext = file_path.suffix.lower()
        content_types = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
        }
        return content_types.get(ext, 'application/octet-stream')
    
    def poll_task_status(self, task_id: str) -> Dict:
        """轮询任务状态直到完成"""
        url = f"{self.api_base_url}/task/{task_id}/json"
        
        poll_count = 0
        while poll_count < MAX_POLL_ATTEMPTS:
            try:
                response = self.session.get(url)
                if response.status_code == 200:
                    # 任务完成，返回JSON数据
                    return {
                        'status': 'completed',
                        'json_data': response.json(),
                        'poll_count': poll_count + 1
                    }
                elif response.status_code == 400:
                    # 任务还在处理中或失败
                    error_data = response.json()
                    if '任务尚未完成' in error_data.get('detail', ''):
                        # 还在处理中，继续轮询
                        poll_count += 1
                        time.sleep(POLL_INTERVAL)
                        continue
                    else:
                        # 任务失败
                        return {
                            'status': 'failed',
                            'error': error_data.get('detail', '未知错误'),
                            'poll_count': poll_count + 1
                        }
                else:
                    return {
                        'status': 'error',
                        'error': f'HTTP {response.status_code}: {response.text}',
                        'poll_count': poll_count + 1
                    }
            except requests.exceptions.RequestException as e:
                return {
                    'status': 'error',
                    'error': str(e),
                    'poll_count': poll_count + 1
                }
        
        # 超时
        return {
            'status': 'timeout',
            'error': f'轮询超时（超过{MAX_POLL_ATTEMPTS * POLL_INTERVAL}秒）',
            'poll_count': poll_count
        }
    
    def test_file(self, file_path: Path, run_number: int, file_type: Optional[str] = None) -> TestResult:
        """测试单个文件的一次运行"""
        result = TestResult(
            file_name=file_path.name,
            run_number=run_number
        )
        
        print(f"  [运行 {run_number}] 开始测试 {file_path.name}...")
        
        # 步骤1: 上传文件
        upload_start = time.time()
        try:
            upload_result = self.upload_file(file_path, file_type)
            result.upload_time = time.time() - upload_start
            result.upload_status_code = upload_result['status_code']
            
            if upload_result['status_code'] != 200:
                result.error_message = f"上传失败: {upload_result['error']}"
                result.upload_error = upload_result['error']
                print(f"    ❌ 上传失败: {result.error_message}")
                return result
            
            task_id = upload_result['response']['task_id']
            result.task_id = task_id
            print(f"    ✓ 上传成功，task_id: {task_id} (耗时: {result.upload_time:.2f}s)")
            
        except Exception as e:
            result.upload_time = time.time() - upload_start
            result.error_message = f"上传异常: {str(e)}"
            print(f"    ❌ 上传异常: {result.error_message}")
            return result
        
        # 步骤2: 轮询状态
        poll_start = time.time()
        poll_result = self.poll_task_status(task_id)
        result.poll_count = poll_result['poll_count']
        result.total_time = time.time() - upload_start  # 总时间包括上传和轮询
        
        if poll_result['status'] == 'completed':
            result.final_status = 'completed'
            result.json_response = poll_result['json_data']
            result.success = True
            
            # 保存JSON结果到文件
            try:
                json_file_path = self._save_json_result(file_path, run_number, result.json_response, result.task_id)
                result.json_file_path = str(json_file_path)
                print(f"    ✓ 任务完成 (总耗时: {result.total_time:.2f}s, 轮询次数: {result.poll_count})")
                print(f"    ✓ JSON已保存: {json_file_path.name}")
            except Exception as e:
                print(f"    ⚠️  任务完成但保存JSON失败: {str(e)}")
        else:
            result.final_status = poll_result['status']
            result.error_message = poll_result.get('error', '未知错误')
            print(f"    ❌ 任务失败: {result.error_message} (总耗时: {result.total_time:.2f}s)")
        
        return result
    
    def _save_json_result(self, file_path: Path, run_number: int, json_data: Dict, task_id: str) -> Path:
        """保存JSON结果到文件"""
        # 生成文件名: 原文件名_运行次数_taskid前8位.json
        file_stem = file_path.stem
        task_id_short = task_id[:8] if task_id else "unknown"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_filename = f"{file_stem}_run{run_number}_{task_id_short}_{timestamp}.json"
        json_file_path = self.output_dir / json_filename
        
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        return json_file_path
    
    def _calculate_time_stability(self, times: List[float]) -> float:
        """计算时间稳定度（1 - 变异系数，值越大越稳定）"""
        if len(times) < 2:
            return 1.0 if len(times) == 1 else 0.0
        
        try:
            mean = statistics.mean(times)
            if mean == 0:
                return 0.0
            stdev = statistics.stdev(times)
            cv = stdev / mean  # 变异系数
            stability = max(0.0, min(1.0, 1.0 - cv))  # 转换为稳定度，范围0-1
            return stability
        except Exception:
            return 0.0
    
    def _calculate_result_consistency(self, json_responses: List[Dict]) -> float:
        """计算结果一致性（JSON结构一致性，0-1）"""
        if len(json_responses) < 2:
            return 1.0 if len(json_responses) == 1 else 0.0
        
        try:
            # 提取所有JSON的键结构
            def get_keys_structure(obj, prefix=""):
                """递归获取所有键的路径"""
                keys = set()
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        full_key = f"{prefix}.{key}" if prefix else key
                        keys.add(full_key)
                        if isinstance(value, (dict, list)):
                            keys.update(get_keys_structure(value, full_key))
                elif isinstance(obj, list) and len(obj) > 0:
                    # 对于列表，检查第一个元素的键结构
                    keys.update(get_keys_structure(obj[0], prefix))
                return keys
            
            structures = [get_keys_structure(j) for j in json_responses]
            
            if not structures:
                return 0.0
            
            # 计算所有结构的交集和并集
            common_keys = set.intersection(*structures) if structures else set()
            all_keys = set.union(*structures) if structures else set()
            
            if not all_keys:
                return 0.0
            
            # 一致性 = 共同键数 / 所有键数
            consistency = len(common_keys) / len(all_keys)
            return consistency
        except Exception:
            return 0.0
    
    def test_all_files(self):
        """测试所有文件"""
        # 获取所有支持的文件
        test_files = []
        for ext in SUPPORTED_EXTENSIONS:
            test_files.extend(self.pdf_dir.glob(f'*{ext}'))
            test_files.extend(self.pdf_dir.glob(f'*{ext.upper()}'))
        
        if not test_files:
            print(f"❌ 在 {self.pdf_dir} 目录下未找到可测试的文件")
            return
        
        print(f"找到 {len(test_files)} 个文件，每个文件测试 {self.runs_per_file} 次")
        print("=" * 80)
        
        for file_path in sorted(test_files):
            print(f"\n📄 测试文件: {file_path.name}")
            print("-" * 80)
            
            # 推断文件类型
            file_type = self.infer_file_type(file_path.name)
            if file_type:
                print(f"  推断文档类型: {file_type}")
            
            # 创建文件测试汇总
            file_summary = FileTestSummary(
                file_name=file_path.name,
                file_path=str(file_path),
                file_type=file_type
            )
            
            # 对每个文件测试多次
            for run_num in range(1, self.runs_per_file + 1):
                result = self.test_file(file_path, run_num, file_type)
                file_summary.results.append(result)
                file_summary.total_runs += 1
                
                if result.success:
                    file_summary.successful_runs += 1
                else:
                    file_summary.failed_runs += 1
                
                # 每次测试之间稍作延迟
                if run_num < self.runs_per_file:
                    time.sleep(1)
            
            # 计算统计信息
            successful_times = [r.total_time for r in file_summary.results if r.success and r.total_time]
            if successful_times:
                file_summary.avg_total_time = sum(successful_times) / len(successful_times)
                file_summary.min_total_time = min(successful_times)
                file_summary.max_total_time = max(successful_times)
                # 计算时间稳定度
                file_summary.time_stability = self._calculate_time_stability(successful_times)
            
            upload_times = [r.upload_time for r in file_summary.results if r.upload_time]
            if upload_times:
                file_summary.avg_upload_time = sum(upload_times) / len(upload_times)
            
            # 计算结果一致性
            successful_json_responses = [r.json_response for r in file_summary.results 
                                        if r.success and r.json_response is not None]
            if len(successful_json_responses) >= 2:
                file_summary.result_consistency = self._calculate_result_consistency(successful_json_responses)
            elif len(successful_json_responses) == 1:
                file_summary.result_consistency = 1.0  # 只有一次成功，认为完全一致
            
            self.test_results.append(file_summary)
            
            # 打印文件测试汇总
            print(f"\n  文件测试汇总:")
            print(f"    成功: {file_summary.successful_runs}/{file_summary.total_runs}")
            print(f"    平均耗时: {file_summary.avg_total_time:.2f}s")
            print(f"    最快: {file_summary.min_total_time:.2f}s")
            print(f"    最慢: {file_summary.max_total_time:.2f}s")
            print(f"    时间稳定度: {file_summary.time_stability:.2%}")
            print(f"    结果一致性: {file_summary.result_consistency:.2%}")
    
    def _test_file_concurrent(self, file_path: Path, file_type: Optional[str], file_summary: FileTestSummary) -> ConcurrentTestResult:
        """并发测试单个文件（内部方法，用于线程池）"""
        result = ConcurrentTestResult(
            file_name=file_path.name,
            file_path=str(file_path)
        )
        
        upload_start = time.time()
        try:
            upload_result = self.upload_file(file_path, file_type)
            result.upload_time = time.time() - upload_start
            result.upload_status_code = upload_result.get('status_code')
            
            if upload_result['status_code'] != 200:
                result.error_message = f"上传失败: {upload_result.get('error', '未知错误')}"
                return result
            
            task_id = upload_result['response']['task_id']
            result.task_id = task_id
            
            # 轮询状态
            poll_result = self.poll_task_status(task_id)
            result.poll_count = poll_result['poll_count']
            result.total_time = time.time() - upload_start
            
            if poll_result['status'] == 'completed':
                result.final_status = 'completed'
                result.json_response = poll_result['json_data']
                result.success = True
                
                # 保存JSON结果
                try:
                    json_file_path = self._save_json_result(file_path, 0, result.json_response, result.task_id)
                    result.json_file_path = str(json_file_path)
                except Exception:
                    pass
            else:
                result.final_status = poll_result['status']
                result.error_message = poll_result.get('error', '未知错误')
                
        except Exception as e:
            result.total_time = time.time() - upload_start
            result.error_message = f"测试异常: {str(e)}"
        
        return result
    
    def _compare_with_sequential(self, concurrent_result: ConcurrentTestResult, file_summary: FileTestSummary):
        """对比并发测试结果与单次测试结果"""
        # 对比耗时
        if concurrent_result.success and concurrent_result.total_time and file_summary.avg_total_time > 0:
            concurrent_result.avg_sequential_time = file_summary.avg_total_time
            concurrent_result.time_difference = concurrent_result.total_time - file_summary.avg_total_time
            concurrent_result.time_difference_percent = (concurrent_result.time_difference / file_summary.avg_total_time) * 100
        
        # 对比结果内容
        if concurrent_result.success and concurrent_result.json_response:
            # 与之前所有成功的JSON结果对比
            successful_json_responses = [r.json_response for r in file_summary.results 
                                        if r.success and r.json_response is not None]
            if successful_json_responses:
                # 计算与之前结果的平均一致性
                similarities = []
                for prev_json in successful_json_responses:
                    similarity = self._calculate_json_similarity(concurrent_result.json_response, prev_json)
                    similarities.append(similarity)
                concurrent_result.result_similarity = sum(similarities) / len(similarities) if similarities else 0.0
            else:
                concurrent_result.result_similarity = 1.0  # 没有之前的结果，认为完全一致
    
    def _calculate_json_similarity(self, json1: Dict, json2: Dict) -> float:
        """计算两个JSON的相似度（0-1）"""
        try:
            def get_keys_structure(obj, prefix=""):
                """递归获取所有键的路径"""
                keys = set()
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        full_key = f"{prefix}.{key}" if prefix else key
                        keys.add(full_key)
                        if isinstance(value, (dict, list)):
                            keys.update(get_keys_structure(value, full_key))
                elif isinstance(obj, list) and len(obj) > 0:
                    keys.update(get_keys_structure(obj[0], prefix))
                return keys
            
            keys1 = get_keys_structure(json1)
            keys2 = get_keys_structure(json2)
            
            if not keys1 and not keys2:
                return 1.0
            if not keys1 or not keys2:
                return 0.0
            
            common_keys = keys1.intersection(keys2)
            all_keys = keys1.union(keys2)
            
            return len(common_keys) / len(all_keys) if all_keys else 0.0
        except Exception:
            return 0.0
    
    def test_concurrent(self):
        """并发测试所有文件"""
        if not self.test_results:
            print("⚠️  没有测试结果，跳过并发测试")
            return
        
        print(f"\n{'=' * 80}")
        print("🚀 开始并发测试所有文件")
        print(f"{'=' * 80}\n")
        
        # 准备测试任务
        test_tasks = []
        for file_summary in self.test_results:
            file_path = Path(file_summary.file_path)
            if file_path.exists():
                test_tasks.append((file_path, file_summary.file_type, file_summary))
        
        if not test_tasks:
            print("❌ 没有可测试的文件")
            return
        
        print(f"准备并发测试 {len(test_tasks)} 个文件...\n")
        
        # 并发执行测试
        concurrent_start = time.time()
        results_dict = {}  # file_path -> (result, file_summary)
        
        with ThreadPoolExecutor(max_workers=len(test_tasks)) as executor:
            # 提交所有任务
            future_to_file = {
                executor.submit(self._test_file_concurrent, file_path, file_type, file_summary): 
                (file_path, file_summary)
                for file_path, file_type, file_summary in test_tasks
            }
            
            # 收集结果
            completed = 0
            for future in as_completed(future_to_file):
                file_path, file_summary = future_to_file[future]
                completed += 1
                try:
                    result = future.result()
                    results_dict[file_path] = (result, file_summary)
                    
                    if result.success:
                        print(f"  [{completed}/{len(test_tasks)}] ✅ {file_path.name} - 完成 (耗时: {result.total_time:.2f}s)")
                    else:
                        print(f"  [{completed}/{len(test_tasks)}] ❌ {file_path.name} - 失败: {result.error_message}")
                except Exception as e:
                    print(f"  [{completed}/{len(test_tasks)}] ❌ {file_path.name} - 异常: {str(e)}")
                    result = ConcurrentTestResult(
                        file_name=file_path.name,
                        file_path=str(file_path),
                        error_message=f"测试异常: {str(e)}"
                    )
                    results_dict[file_path] = (result, file_summary)
        
        concurrent_total_time = time.time() - concurrent_start
        
        # 对比分析并保存结果
        print(f"\n并发测试总耗时: {concurrent_total_time:.2f}秒")
        print("开始对比分析...\n")
        
        for file_path, (result, file_summary) in results_dict.items():
            self._compare_with_sequential(result, file_summary)
            file_summary.concurrent_result = result
            
            # 打印对比结果
            if result.success:
                print(f"📊 {file_path.name}:")
                print(f"   并发耗时: {result.total_time:.2f}s")
                print(f"   平均单次耗时: {result.avg_sequential_time:.2f}s")
                if result.time_difference_percent != 0:
                    diff_str = f"{result.time_difference_percent:+.1f}%"
                    print(f"   耗时差异: {diff_str}")
                print(f"   结果相似度: {result.result_similarity:.2%}")
            else:
                print(f"❌ {file_path.name}: {result.error_message}")
        
        print(f"\n{'=' * 80}")
        print("✅ 并发测试完成")
        print(f"{'=' * 80}\n")
    
    def generate_report(self, output_file: Optional[str] = None):
        """生成测试报告"""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = project_root / "test" / f"test_report_{timestamp}.md"
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 计算总体统计
        total_files = len(self.test_results)
        total_runs = sum(f.total_runs for f in self.test_results)
        total_successful = sum(f.successful_runs for f in self.test_results)
        total_failed = sum(f.failed_runs for f in self.test_results)
        success_rate = (total_successful / total_runs * 100) if total_runs > 0 else 0
        
        all_times = []
        for file_summary in self.test_results:
            all_times.extend([r.total_time for r in file_summary.results if r.success and r.total_time])
        
        avg_time = sum(all_times) / len(all_times) if all_times else 0
        min_time = min(all_times) if all_times else 0
        max_time = max(all_times) if all_times else 0
        
        # 计算总体稳定度
        all_time_stabilities = [f.time_stability for f in self.test_results if f.time_stability > 0]
        avg_time_stability = sum(all_time_stabilities) / len(all_time_stabilities) if all_time_stabilities else 0.0
        
        all_result_consistencies = [f.result_consistency for f in self.test_results if f.result_consistency > 0]
        avg_result_consistency = sum(all_result_consistencies) / len(all_result_consistencies) if all_result_consistencies else 0.0
        
        # 生成Markdown报告
        report_lines = [
            "# PDF转换API测试报告",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**API地址**: {self.api_base_url}",
            f"**测试目录**: {self.pdf_dir}",
            f"**每个文件测试次数**: {self.runs_per_file}",
            f"**JSON结果保存目录**: {self.output_dir}",
            "",
            "## 总体统计",
            "",
            f"- 测试文件数: {total_files}",
            f"- 总测试次数: {total_runs}",
            f"- 成功次数: {total_successful}",
            f"- 失败次数: {total_failed}",
            f"- 成功率: {success_rate:.2f}%",
            f"- 平均耗时: {avg_time:.2f}秒",
            f"- 最快耗时: {min_time:.2f}秒",
            f"- 最慢耗时: {max_time:.2f}秒",
            f"- 平均时间稳定度: {avg_time_stability:.2%}",
            f"- 平均结果一致性: {avg_result_consistency:.2%}",
            "",
            "## 详细测试结果",
            "",
        ]
        
        # 每个文件的详细结果
        for file_summary in self.test_results:
            report_lines.extend([
                f"### {file_summary.file_name}",
                "",
                f"- **文件路径**: `{file_summary.file_path}`",
                f"- **文档类型**: {file_summary.file_type or '自动推断'}",
                f"- **测试次数**: {file_summary.total_runs}",
                f"- **成功次数**: {file_summary.successful_runs}",
                f"- **失败次数**: {file_summary.failed_runs}",
                f"- **平均耗时**: {file_summary.avg_total_time:.2f}秒",
                f"- **最快耗时**: {file_summary.min_total_time:.2f}秒",
                f"- **最慢耗时**: {file_summary.max_total_time:.2f}秒",
                f"- **时间稳定度**: {file_summary.time_stability:.2%}",
                f"- **结果一致性**: {file_summary.result_consistency:.2%}",
                "",
                "#### 每次运行详情",
                "",
                "| 运行 | 任务ID | 上传耗时(s) | 总耗时(s) | 轮询次数 | 状态 | JSON文件 | 错误信息 |",
                "|------|--------|-------------|-----------|----------|------|----------|----------|",
            ])
            
            for result in file_summary.results:
                task_id_short = result.task_id[:8] + "..." if result.task_id else "N/A"
                upload_time_str = f"{result.upload_time:.2f}" if result.upload_time else "N/A"
                total_time_str = f"{result.total_time:.2f}" if result.total_time else "N/A"
                status_emoji = "✅" if result.success else "❌"
                status_text = result.final_status or "unknown"
                
                # JSON文件路径
                if result.json_file_path:
                    json_file_name = Path(result.json_file_path).name
                    json_file_link = f"[{json_file_name}]({result.json_file_path})"
                else:
                    json_file_link = "-"
                
                error_text = result.error_message or "-"
                if len(error_text) > 50:
                    error_text = error_text[:47] + "..."
                
                report_lines.append(
                    f"| {result.run_number} | {task_id_short} | {upload_time_str} | "
                    f"{total_time_str} | {result.poll_count} | {status_emoji} {status_text} | {json_file_link} | {error_text} |"
                )
            
            # 添加并发测试对比
            if file_summary.concurrent_result:
                concurrent_result = file_summary.concurrent_result
                report_lines.extend([
                    "",
                    "#### 并发测试对比",
                    "",
                ])
                
                if concurrent_result.success:
                    report_lines.extend([
                        f"- **并发测试耗时**: {concurrent_result.total_time:.2f}秒",
                        f"- **平均单次测试耗时**: {concurrent_result.avg_sequential_time:.2f}秒",
                        f"- **耗时差异**: {concurrent_result.time_difference:+.2f}秒 ({concurrent_result.time_difference_percent:+.1f}%)",
                        f"- **结果相似度**: {concurrent_result.result_similarity:.2%}",
                    ])
                    if concurrent_result.json_file_path:
                        json_file_name = Path(concurrent_result.json_file_path).name
                        json_file_link = f"[{json_file_name}]({concurrent_result.json_file_path})"
                        report_lines.append(f"- **并发测试JSON文件**: {json_file_link}")
                else:
                    report_lines.append(f"- **并发测试状态**: ❌ 失败 - {concurrent_result.error_message or '未知错误'}")
                
                report_lines.append("")
            
            report_lines.append("")
        
        # 并发测试汇总
        concurrent_results = [f.concurrent_result for f in self.test_results if f.concurrent_result]
        if concurrent_results:
            concurrent_successful = [r for r in concurrent_results if r.success]
            concurrent_failed = [r for r in concurrent_results if not r.success]
            
            report_lines.extend([
                "## 并发测试汇总",
                "",
                f"- **并发测试文件数**: {len(concurrent_results)}",
                f"- **并发测试成功数**: {len(concurrent_successful)}",
                f"- **并发测试失败数**: {len(concurrent_failed)}",
            ])
            
            if concurrent_successful:
                concurrent_times = [r.total_time for r in concurrent_successful if r.total_time]
                sequential_times = [r.avg_sequential_time for r in concurrent_successful if r.avg_sequential_time > 0]
                similarities = [r.result_similarity for r in concurrent_successful if r.result_similarity > 0]
                
                if concurrent_times:
                    total_concurrent_time = sum(concurrent_times)
                    total_sequential_time = sum(sequential_times) if sequential_times else 0
                    avg_concurrent_time = sum(concurrent_times) / len(concurrent_times)
                    avg_sequential_time = sum(sequential_times) / len(sequential_times) if sequential_times else 0
                    avg_similarity = sum(similarities) / len(similarities) if similarities else 0
                    
                    report_lines.extend([
                        "",
                        f"- **并发测试总耗时**: {total_concurrent_time:.2f}秒",
                        f"- **单次测试总耗时（估算）**: {total_sequential_time:.2f}秒",
                        f"- **平均并发耗时**: {avg_concurrent_time:.2f}秒",
                        f"- **平均单次耗时**: {avg_sequential_time:.2f}秒",
                        f"- **平均结果相似度**: {avg_similarity:.2%}",
                    ])
                    
                    if total_sequential_time > 0:
                        time_saved = total_sequential_time - total_concurrent_time
                        time_saved_percent = (time_saved / total_sequential_time) * 100
                        report_lines.extend([
                            f"- **时间节省**: {time_saved:.2f}秒 ({time_saved_percent:.1f}%)",
                        ])
            
            report_lines.extend([
                "",
                "### 并发测试详细对比",
                "",
                "| 文件名 | 并发耗时(s) | 平均单次耗时(s) | 耗时差异 | 结果相似度 | 状态 |",
                "|--------|-------------|----------------|----------|------------|------|",
            ])
            
            for file_summary in self.test_results:
                if file_summary.concurrent_result:
                    cr = file_summary.concurrent_result
                    if cr.success:
                        time_diff_str = f"{cr.time_difference:+.2f}s ({cr.time_difference_percent:+.1f}%)"
                        similarity_str = f"{cr.result_similarity:.2%}"
                        status_emoji = "✅"
                    else:
                        time_diff_str = "-"
                        similarity_str = "-"
                        status_emoji = "❌"
                    
                    concurrent_time_str = f"{cr.total_time:.2f}" if cr.total_time else "N/A"
                    sequential_time_str = f"{cr.avg_sequential_time:.2f}" if cr.avg_sequential_time > 0 else "N/A"
                    error_text = cr.error_message or "-"
                    if len(error_text) > 30:
                        error_text = error_text[:27] + "..."
                    
                    report_lines.append(
                        f"| {file_summary.file_name} | {concurrent_time_str} | {sequential_time_str} | "
                        f"{time_diff_str} | {similarity_str} | {status_emoji} {error_text} |"
                    )
            
            report_lines.append("")
        
        # 错误汇总
        error_summary = defaultdict(int)
        for file_summary in self.test_results:
            for result in file_summary.results:
                if not result.success and result.error_message:
                    error_summary[result.error_message] += 1
        
        if error_summary:
            report_lines.extend([
                "## 错误汇总",
                "",
                "| 错误信息 | 出现次数 |",
                "|----------|----------|",
            ])
            for error, count in sorted(error_summary.items(), key=lambda x: x[1], reverse=True):
                report_lines.append(f"| {error} | {count} |")
            report_lines.append("")
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        
        print(f"\n{'=' * 80}")
        print(f"✅ 测试报告已生成: {output_path}")
        print(f"{'=' * 80}")
        
        return output_path


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PDF转换API测试脚本')
    parser.add_argument('--api-url', default=API_BASE_URL, help=f'API基础URL (默认: {API_BASE_URL})')
    parser.add_argument('--pdf-dir', default=str(project_root / "test" / 'pdf'), help='PDF文件目录')
    parser.add_argument('--runs', type=int, default=TEST_RUNS_PER_FILE, help=f'每个文件测试次数 (默认: {TEST_RUNS_PER_FILE})')
    parser.add_argument('--output', help='测试报告输出文件路径')
    parser.add_argument('--json-dir', help='JSON结果保存目录 (默认: test/json_results)')
    
    args = parser.parse_args()
    
    # 创建测试器
    tester = APITester(args.api_url, args.pdf_dir, runs_per_file=args.runs, output_dir=args.json_dir)
    
    # 执行测试
    try:
        tester.test_all_files()
        
        # 所有单次测试完成后，进行并发测试
        if tester.test_results:
            tester.test_concurrent()
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 生成报告
    if tester.test_results:
        tester.generate_report(args.output)
    else:
        print("\n⚠️  没有测试结果，跳过报告生成")


if __name__ == '__main__':
    main()

