import paddle
import numpy as np
from PIL import Image
import cv2
import time
from typing import List, Tuple, Dict
import warnings
import os

class LightweightOCR:
    def __init__(self, use_light_model=True):
        """
        初始化轻量级OCR模型 - 适配PaddleOCR 3.3.1
        """
        self.use_light_model = use_light_model
        self.ocr_engine = None
        self.init_models()
    
    def init_models(self):
        """初始化模型 - 完全适配PaddleOCR 3.3.1"""
        try:
            from paddleocr import PaddleOCR
            
            print("使用PaddleOCR 3.3.1兼容参数...")
            
            # PaddleOCR 3.3.1 新参数格式
            ocr_args = {
                # 基本参数
                "lang": 'ch',  # 中文识别
                
                # 设备设置 - 新版本使用device参数替代use_gpu
                "device": 'cpu',  # 使用CPU
                
                # 性能优化参数
                "cpu_threads": 4,  # CPU线程数
                
                # 新版参数名
                "use_textline_orientation": False,  # 替代use_angle_cls
                "text_det_thresh": 0.3,  # 替代det_db_thresh
                "text_det_box_thresh": 0.5,  # 文本检测框阈值
                
                # 轻量级优化
                "use_space_char": False,  # 关闭空格识别
            }
            
            # 尝试启用MKLDNN加速（如果可用）
            try:
                ocr_args["enable_mkldnn"] = True
            except:
                print("MKLDNN不可用，使用普通CPU模式")
            
            # 初始化OCR引擎
            self.ocr_engine = PaddleOCR(**ocr_args)
            print("OCR模型初始化完成")
            
        except ImportError:
            print("请先安装: pip install paddlepaddle paddleocr")
            raise
        except Exception as e:
            print(f"模型初始化失败: {e}")
            # 尝试最简初始化
            self._init_minimal()
    
    def _init_minimal(self):
        """最简化初始化，确保基本功能可用"""
        try:
            from paddleocr import PaddleOCR
            print("尝试最简化初始化...")
            # 只传递最必要的参数
            self.ocr_engine = PaddleOCR(lang='ch', device='cpu')
            print("最简化初始化成功")
        except Exception as e:
            print(f"最简化初始化失败: {e}")
            self.ocr_engine = None
    
    def check_ocr_engine(self):
        """检查OCR引擎状态"""
        if self.ocr_engine is None:
            raise RuntimeError("OCR引擎未正确初始化")
        return True
    
    def preprocess_image(self, image_path: str) -> np.ndarray:
        """
        图像预处理优化
        """
        # 读取图像
        if isinstance(image_path, str):
            img = cv2.imread(image_path)
            if img is None:
                # 尝试用PIL读取
                try:
                    pil_img = Image.open(image_path)
                    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                except:
                    raise ValueError(f"无法读取图像: {image_path}")
        else:
            img = image_path
        
        if img is None:
            raise ValueError("无法读取图像")
        
        # 调整图像尺寸，提高处理速度但保持可读性
        h, w = img.shape[:2]
        max_size = 1600  # 限制最大尺寸
        
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
        return img
    
    def detect_text_regions(self, image: np.ndarray) -> List:
        """检测文本区域"""
        if not self.check_ocr_engine():
            return self.fallback_text_detection(image)
        
        try:
            # PaddleOCR 3.3.1 的OCR调用方式
            result = self.ocr_engine.ocr(image)
            
            # 解析新版输出格式
            if result and len(result) > 0:
                return self._parse_new_format(result[0])
            return []
            
        except Exception as e:
            print(f"PaddleOCR检测失败: {e}")
            return self.fallback_text_detection(image)
    
    def _parse_new_format(self, ocr_result):
        """解析PaddleOCR 3.3.1的输出格式"""
        text_regions = []
        
        if ocr_result is None:
            return text_regions
            
        for line in ocr_result:
            if line and len(line) >= 2:
                # 新版格式: [[坐标点], (文本, 置信度)]
                bbox = line[0]  # 坐标点列表
                text_info = line[1]  # (文本, 置信度)
                
                if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                    text, confidence = text_info[0], text_info[1]
                    text_regions.append([bbox, (text, confidence)])
        
        return text_regions
    
    def fallback_text_detection(self, image: np.ndarray) -> List:
        """
        备用文本检测方法
        """
        print("使用备用文本检测方法...")
        
        # 确保图像是灰度图
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # 二值化
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 形态学操作
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # 查找轮廓
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        text_regions = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            min_area = (image.shape[0] * image.shape[1]) * 0.0005
            if w * h > min_area and w > 10 and h > 10:
                text_regions.append([[[x, y], [x+w, y], [x+w, y+h], [x, y+h]], ('', 0.5)])
        
        return text_regions
    
    def recognize_text(self, image_path: str, confidence_threshold: float = 0.5) -> Dict:
        """
        主识别函数 - 适配PaddleOCR 3.3.1
        """
        start_time = time.time()
        
        try:
            # 预处理
            processed_img = self.preprocess_image(image_path)
            
            # 文本检测
            detection_start = time.time()
            text_regions = self.detect_text_regions(processed_img)
            detection_time = time.time() - detection_start
            
            results = {
                'text_blocks': [],
                'full_text': '',
                'stats': {
                    'total_regions': len(text_regions),
                    'detection_time': detection_time,
                    'total_time': 0
                }
            }
            
            recognized_texts = []
            
            # 处理识别结果
            for i, region in enumerate(text_regions):
                try:
                    if len(region) >= 2:
                        bbox = region[0]
                        
                        if isinstance(region[1], tuple) and len(region[1]) == 2:
                            text, confidence = region[1]
                        else:
                            text = str(region[1]) if region[1] is not None else ""
                            confidence = 0.5
                        
                        if confidence >= confidence_threshold and text.strip():
                            results['text_blocks'].append({
                                'bbox': bbox,
                                'text': text,
                                'confidence': confidence
                            })
                            recognized_texts.append(text)
                except Exception as e:
                    print(f"处理区域 {i} 时出错: {e}")
                    continue
            
            results['full_text'] = '\n'.join(recognized_texts)
            results['stats']['total_time'] = time.time() - start_time
            
            return results
            
        except Exception as e:
            print(f"OCR识别过程中出错: {e}")
            return {
                'text_blocks': [],
                'full_text': '',
                'stats': {
                    'total_regions': 0,
                    'detection_time': 0,
                    'total_time': time.time() - start_time,
                    'error': str(e)
                }
            }
    
    def simple_ocr(self, image_path: str) -> str:
        """简化版OCR接口"""
        try:
            result = self.recognize_text(image_path)
            return result['full_text']
        except Exception as e:
            print(f"OCR识别失败: {e}")
            return ""
    
    def batch_recognize(self, image_paths: List[str], batch_size: int = 1) -> List[Dict]:
        """批量识别"""
        results = []
        for i, path in enumerate(image_paths):
            print(f"处理图片 {i+1}/{len(image_paths)}: {path}")
            try:
                result = self.recognize_text(path)
                results.append(result)
            except Exception as e:
                print(f"处理图片 {path} 时出错: {e}")
                results.append({'error': str(e), 'text_blocks': [], 'full_text': ''})
            
            if batch_size > 1 and (i + 1) % batch_size == 0:
                time.sleep(0.1)
        
        return results

def optimize_for_cpu():
    """CPU优化设置"""
    paddle.set_device('cpu')
    os.environ['OMP_NUM_THREADS'] = '4'
    os.environ['MKL_NUM_THREADS'] = '4'
    print("CPU优化设置完成")

def check_paddleocr_version():
    """检查PaddleOCR版本"""
    try:
        import paddleocr
        print(f"PaddleOCR版本: {getattr(paddleocr, '__version__', '未知')}")
    except:
        print("无法获取PaddleOCR版本信息")

def create_sample_image():
    """创建示例测试图片"""
    from PIL import Image, ImageDraw, ImageFont
    
    img = Image.new('RGB', (400, 200), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    
    try:
        # 尝试使用中文字体
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except:
        try:
            font = ImageFont.truetype("Arial.ttf", 20)
        except:
            font = ImageFont.load_default()
    
    d.text((50, 50), "Hello PaddleOCR 3.3.1", fill=(0, 0, 0), font=font)
    d.text((50, 100), "测试中文识别效果", fill=(0, 0, 0), font=font)
    d.text((50, 140), "Text Recognition", fill=(0, 0, 0), font=font)
    
    img.save("sample_text.jpg")
    print("已创建示例图片: sample_text.jpg")

def test_ocr_functionality():
    """测试OCR功能"""
    optimize_for_cpu()
    check_paddleocr_version()
    
    # 创建测试图片
    if not os.path.exists("sample_text.jpg"):
        create_sample_image()
    
    # 初始化OCR
    print("初始化OCR引擎...")
    ocr = LightweightOCR()
    
    # 测试识别
    image_path = "sample_text.jpg"
    print(f"测试图片: {image_path}")
    
    try:
        result = ocr.recognize_text(image_path)
        
        print("\n=== OCR识别结果 ===")
        print(f"识别到的文本区域数: {result['stats']['total_regions']}")
        print(f"检测耗时: {result['stats']['detection_time']:.3f}秒")
        print(f"总耗时: {result['stats']['total_time']:.3f}秒")
        
        if result['full_text']:
            print(f"\n识别到的全文:\n{result['full_text']}")
        else:
            print("\n未识别到文本")
        
        if result['text_blocks']:
            print(f"\n详细信息:")
            for i, block in enumerate(result['text_blocks']):
                print(f"区域 {i+1}: '{block['text']}' (置信度: {block['confidence']:.3f})")
        else:
            print("未找到可信的文本区域")
            
    except Exception as e:
        print(f"测试过程中出错: {e}")

def debug_ocr_initialization():
    """调试OCR初始化"""
    print("=== OCR初始化调试 ===")
    
    try:
        from paddleocr import PaddleOCR
        
        # 测试最简初始化
        print("1. 测试最简初始化...")
        ocr_simple = PaddleOCR(lang='ch', device='cpu')
        print("   最简初始化成功")
        
        # 测试完整参数
        print("2. 测试完整参数初始化...")
        ocr_full = PaddleOCR(
            lang='ch',
            device='cpu',
            cpu_threads=4,
            use_textline_orientation=False,
            text_det_thresh=0.3,
            text_det_box_thresh=0.5,
            use_space_char=False
        )
        print("   完整参数初始化成功")
        
        return True
    except Exception as e:
        print(f"初始化调试失败: {e}")
        return False

if __name__ == "__main__":
    # 先调试初始化
    if debug_ocr_initialization():
        print("\n初始化调试通过，开始功能测试...")
        test_ocr_functionality()
    else:
        print("初始化调试失败，请检查安装")