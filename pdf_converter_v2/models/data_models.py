# Copyright (c) Opendatalab. All rights reserved.

"""
数据模型定义
"""

from typing import List


class WeatherData:
    """气象数据模型"""
    def __init__(self):
        self.monitorAt: str = ""
        self.weather: str = ""
        self.temp: str = ""
        self.humidity: str = ""
        self.windSpeed: str = ""
        self.windDirection: str = ""
        self._auto_filled_weather: bool = False
    
    def to_dict(self):
        return {
            "monitorAt": self.monitorAt,
            "weather": self.weather,
            "temp": self.temp,
            "humidity": self.humidity,
            "windSpeed": self.windSpeed,
            "windDirection": self.windDirection
        }


class NoiseData:
    """噪声数据模型"""
    def __init__(self):
        self.code: str = ""
        self.address: str = ""
        self.source: str = ""
        self.dayMonitorAt: str = ""
        self.dayMonitorValue: str = ""
        self.dayMonitorBackgroundValue: str = ""
        self.nightMonitorAt: str = ""
        self.nightMonitorValue: str = ""
        self.nightMonitorBackgroundValue: str = ""
        self.remark: str = ""
    
    def to_dict(self):
        return {
            "code": self.code,
            "address": self.address,
            "source": self.source,
            "dayMonitorAt": self.dayMonitorAt,
            "dayMonitorValue": self.dayMonitorValue,
            "dayMonitorBackgroundValue": self.dayMonitorBackgroundValue,
            "nightMonitorAt": self.nightMonitorAt,
            "nightMonitorValue": self.nightMonitorValue,
            "nightMonitorBackgroundValue": self.nightMonitorBackgroundValue,
            "remark": self.remark
        }


class OperationalCondition:
    """工况信息数据模型（旧格式）"""
    def __init__(self):
        self.monitorAt: str = ""  # 检测时间
        self.project: str = ""  # 项目名称
        self.name: str = ""  # 名称，如1#主变
        self.voltage: str = ""  # 电压范围
        self.current: str = ""  # 电流范围
        self.activePower: str = ""  # 有功功率
        self.reactivePower: str = ""  # 无功功率
    
    def to_dict(self):
        return {
            "monitorAt": self.monitorAt,
            "project": self.project,
            "name": self.name,
            "voltage": self.voltage,
            "current": self.current,
            "activePower": self.activePower,
            "reactivePower": self.reactivePower
        }


class OperationalConditionV2:
    """工况信息数据模型（新格式：表1检测工况）"""
    def __init__(self):
        self.monitorAt: str = ""  # 检测时间
        self.project: str = ""  # 项目名称
        self.name: str = ""  # 名称，如500kV 江黄Ⅰ线
        self.maxVoltage: str = ""  # 电压最大值
        self.minVoltage: str = ""  # 电压最小值
        self.maxCurrent: str = ""  # 电流最大值
        self.minCurrent: str = ""  # 电流最小值
        self.maxActivePower: str = ""  # 有功功率最大值
        self.minActivePower: str = ""  # 有功功率最小值
        self.maxReactivePower: str = ""  # 无功功率最大值
        self.minReactivePower: str = ""  # 无功功率最小值
    
    def to_dict(self):
        return {
            "monitorAt": self.monitorAt,
            "project": self.project,
            "name": self.name,
            "maxVoltage": self.maxVoltage,
            "minVoltage": self.minVoltage,
            "maxCurrent": self.maxCurrent,
            "minCurrent": self.minCurrent,
            "maxActivePower": self.maxActivePower,
            "minActivePower": self.minActivePower,
            "maxReactivePower": self.maxReactivePower,
            "minReactivePower": self.minReactivePower
        }


class NoiseDetectionRecord:
    """噪声检测记录数据模型"""
    def __init__(self):
        self.project: str = ""
        self.standardReferences: str = ""
        self.soundLevelMeterMode: str = ""
        self.soundCalibratorMode: str = ""
        self.calibrationValueBefore: str = ""
        self.calibrationValueAfter: str = ""
        self.weather: List[WeatherData] = []
        self.noise: List[NoiseData] = []
        self.operationalConditions: List[OperationalCondition] = []
    
    def to_dict(self):
        return {
            "project": self.project,
            "standardReferences": self.standardReferences,
            "soundLevelMeterMode": self.soundLevelMeterMode,
            "soundCalibratorMode": self.soundCalibratorMode,
            "calibrationValueBefore": self.calibrationValueBefore,
            "calibrationValueAfter": self.calibrationValueAfter,
            "weather": [w.to_dict() for w in self.weather],
            "noise": [n.to_dict() for n in self.noise],
            "operationalConditions": [oc.to_dict() for oc in self.operationalConditions]
        }


class ElectromagneticWeatherData:
    """电磁检测气象数据模型"""
    def __init__(self):
        self.weather: str = ""
        self.temp: str = ""
        self.humidity: str = ""
        self.windSpeed: str = ""
        self.windDirection: str = ""
    
    def to_dict(self):
        return {
            "weather": self.weather,
            "temp": self.temp,
            "humidity": self.humidity,
            "windSpeed": self.windSpeed,
            "windDirection": self.windDirection
        }


class ElectromagneticData:
    """电磁数据模型"""
    def __init__(self):
        self.code: str = ""
        self.address: str = ""
        self.height: str = ""
        self.monitorAt: str = ""
        self.powerFrequencyEFieldStrength1: str = ""
        self.powerFrequencyEFieldStrength2: str = ""
        self.powerFrequencyEFieldStrength3: str = ""
        self.powerFrequencyEFieldStrength4: str = ""
        self.powerFrequencyEFieldStrength5: str = ""
        self.avgPowerFrequencyEFieldStrength: str = ""
        self.powerFrequencyMagneticDensity1: str = ""
        self.powerFrequencyMagneticDensity2: str = ""
        self.powerFrequencyMagneticDensity3: str = ""
        self.powerFrequencyMagneticDensity4: str = ""
        self.powerFrequencyMagneticDensity5: str = ""
        self.avgPowerFrequencyMagneticDensity: str = ""
    
    def to_dict(self):
        return {
            "code": self.code,
            "address": self.address,
            "height": self.height,
            "monitorAt": self.monitorAt,
            "powerFrequencyEFieldStrength1": self.powerFrequencyEFieldStrength1,
            "powerFrequencyEFieldStrength2": self.powerFrequencyEFieldStrength2,
            "powerFrequencyEFieldStrength3": self.powerFrequencyEFieldStrength3,
            "powerFrequencyEFieldStrength4": self.powerFrequencyEFieldStrength4,
            "powerFrequencyEFieldStrength5": self.powerFrequencyEFieldStrength5,
            "avgPowerFrequencyEFieldStrength": self.avgPowerFrequencyEFieldStrength,
            "powerFrequencyMagneticDensity1": self.powerFrequencyMagneticDensity1,
            "powerFrequencyMagneticDensity2": self.powerFrequencyMagneticDensity2,
            "powerFrequencyMagneticDensity3": self.powerFrequencyMagneticDensity3,
            "powerFrequencyMagneticDensity4": self.powerFrequencyMagneticDensity4,
            "powerFrequencyMagneticDensity5": self.powerFrequencyMagneticDensity5,
            "avgPowerFrequencyMagneticDensity": self.avgPowerFrequencyMagneticDensity
        }


class ElectromagneticDetectionRecord:
    """电磁检测记录数据模型"""
    def __init__(self):
        self.project: str = ""
        self.standardReferences: str = ""
        self.deviceName: str = ""
        self.deviceMode: str = ""
        self.deviceCode: str = ""
        self.monitorHeight: str = ""
        self.weather: ElectromagneticWeatherData = ElectromagneticWeatherData()
        self.electricMagnetic: List[ElectromagneticData] = []
    
    def to_dict(self):
        return {
            "project": self.project,
            "standardReferences": self.standardReferences,
            "deviceName": self.deviceName,
            "deviceMode": self.deviceMode,
            "deviceCode": self.deviceCode,
            "monitorHeight": self.monitorHeight,
            "weather": self.weather.to_dict(),
            "electricMagnetic": [em.to_dict() for em in self.electricMagnetic]
        }


class InvestmentItem:
    """投资项目数据模型"""
    def __init__(self):
        self.no: str = ""  # 序号
        self.name: str = ""  # 工程或费用名称
        self.level: str = ""  # 明细等级
        self.constructionScaleOverheadLine: str = ""  # 建设规模-架空线（仅可研批复）
        self.constructionScaleBay: str = ""  # 建设规模-间隔（仅可研批复）
        self.constructionScaleSubstation: str = ""  # 建设规模-变电（仅可研批复）
        self.constructionScaleOpticalCable: str = ""  # 建设规模-光缆（仅可研批复）
        self.staticInvestment: str = ""  # 静态投资（元）
        self.dynamicInvestment: str = ""  # 动态投资（元）
    
    def to_dict(self, include_construction_scale: bool = False):
        """
        转换为字典
        
        Args:
            include_construction_scale: 是否包含建设规模字段（可研批复需要）
        """
        result = {
            "No": self.no,
            "name": self.name,
            "Level": self.level,
            "staticInvestment": self.staticInvestment,
            "dynamicInvestment": self.dynamicInvestment
        }
        
        # 如果需要建设规模字段，添加到输出（用于可研批复）
        if include_construction_scale:
            result["constructionScaleOverheadLine"] = self.constructionScaleOverheadLine
            result["constructionScaleBay"] = self.constructionScaleBay
            result["constructionScaleSubstation"] = self.constructionScaleSubstation
            result["constructionScaleOpticalCable"] = self.constructionScaleOpticalCable
        
        return result


class FeasibilityApprovalInvestment:
    """可研批复投资估算数据模型
    
    返回结构与 designReview 保持一致，包含建设规模字段
    三层嵌套结构：
    - Level 0: 顶层大类（如"山西晋城周村220千伏输变电工程"）
    - Level 1: 二级分类（如"变电工程"、"线路工程"），有自己的 items
    - Level 2: 具体项目（如"周村220千伏变电站新建工程"）
    """
    def __init__(self):
        self.items: List[InvestmentItem] = []
    
    def to_dict(self):
        """转换为嵌套结构，与 designReview 保持一致
        
        Level="1" 的项目作为顶层大类（Level: 0）
        Level="2" 的项目作为二级分类（Level: 1），有自己的 items
        Level="3" 的项目作为具体项目（Level: 2），放入二级分类的 items
        Level="0" 的项目（合计）跳过
        """
        if not self.items:
            return []
        
        result = []
        current_top_category = None  # Level 0 顶层大类
        current_sub_category = None  # Level 1 二级分类
        
        for item in self.items:
            if item.level == "1":
                # 顶层大类（如"山西晋城周村220千伏输变电工程"）
                # 保存之前的二级分类和顶层大类
                if current_sub_category is not None and current_top_category is not None:
                    current_top_category["items"].append(current_sub_category)
                    current_sub_category = None
                if current_top_category is not None:
                    result.append(current_top_category)
                
                current_top_category = {
                    "name": item.name,
                    "Level": 0,
                    "constructionScaleSubstation": item.constructionScaleSubstation or "",
                    "constructionScaleBay": item.constructionScaleBay or "",
                    "constructionScaleOverheadLine": item.constructionScaleOverheadLine or "",
                    "constructionScaleOpticalCable": item.constructionScaleOpticalCable or "",
                    "staticInvestment": self._parse_number(item.staticInvestment),
                    "dynamicInvestment": self._parse_number(item.dynamicInvestment),
                    "items": []
                }
            elif item.level == "2" and current_top_category is not None:
                # 二级分类（如"变电工程"、"线路工程"）
                # 保存之前的二级分类
                if current_sub_category is not None:
                    current_top_category["items"].append(current_sub_category)
                
                current_sub_category = {
                    "No": self._parse_no(item.no),
                    "name": item.name,
                    "Level": 1,
                    "constructionScaleSubstation": item.constructionScaleSubstation or "",
                    "constructionScaleBay": item.constructionScaleBay or "",
                    "constructionScaleOverheadLine": item.constructionScaleOverheadLine or "",
                    "constructionScaleOpticalCable": item.constructionScaleOpticalCable or "",
                    "staticInvestment": self._parse_number(item.staticInvestment),
                    "dynamicInvestment": self._parse_number(item.dynamicInvestment),
                    "items": []
                }
            elif item.level == "3" and current_sub_category is not None:
                # 具体项目（如"周村220千伏变电站新建工程"）
                current_sub_category["items"].append({
                    "No": self._parse_no(item.no),
                    "name": item.name,
                    "Level": 2,
                    "constructionScaleSubstation": item.constructionScaleSubstation or "",
                    "constructionScaleBay": item.constructionScaleBay or "",
                    "constructionScaleOverheadLine": item.constructionScaleOverheadLine or "",
                    "constructionScaleOpticalCable": item.constructionScaleOpticalCable or "",
                    "staticInvestment": self._parse_number(item.staticInvestment),
                    "dynamicInvestment": self._parse_number(item.dynamicInvestment),
                })
            elif item.level == "0":
                # 合计行 - 跳过
                if current_sub_category is not None and current_top_category is not None:
                    current_top_category["items"].append(current_sub_category)
                    current_sub_category = None
                if current_top_category is not None:
                    result.append(current_top_category)
                    current_top_category = None
        
        # 添加最后的分类
        if current_sub_category is not None and current_top_category is not None:
            current_top_category["items"].append(current_sub_category)
        if current_top_category is not None:
            result.append(current_top_category)
        
        return result
    
    @staticmethod
    def _parse_number(value: str) -> float:
        if not value or not value.strip():
            return 0.0
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    
    @staticmethod
    def _parse_no(value: str) -> int:
        if not value or not value.strip():
            return 0
        try:
            return int(value.strip())
        except ValueError:
            return 0


class FeasibilityReviewInvestment:
    """可研评审投资估算数据模型
    
    返回结构与 designReview 保持一致，不包含建设规模字段
    三层嵌套结构：
    - Level 0: 顶层大类
    - Level 1: 二级分类，有自己的 items
    - Level 2: 具体项目
    """
    def __init__(self):
        self.items: List[InvestmentItem] = []
    
    def to_dict(self):
        """转换为嵌套结构，与 designReview 保持一致
        
        Level="1" 的项目作为顶层大类（Level: 0）
        Level="2" 的项目作为二级分类（Level: 1），有自己的 items
        Level="3" 的项目作为具体项目（Level: 2），放入二级分类的 items
        Level="0" 的项目（合计）跳过
        """
        if not self.items:
            return []
        
        result = []
        current_top_category = None
        current_sub_category = None
        
        for item in self.items:
            if item.level == "1":
                # 顶层大类
                if current_sub_category is not None and current_top_category is not None:
                    current_top_category["items"].append(current_sub_category)
                    current_sub_category = None
                if current_top_category is not None:
                    result.append(current_top_category)
                
                current_top_category = {
                    "name": item.name,
                    "Level": 0,
                    "staticInvestment": self._parse_number(item.staticInvestment),
                    "dynamicInvestment": self._parse_number(item.dynamicInvestment),
                    "items": []
                }
            elif item.level == "2" and current_top_category is not None:
                # 二级分类
                if current_sub_category is not None:
                    current_top_category["items"].append(current_sub_category)
                
                current_sub_category = {
                    "No": self._parse_no(item.no),
                    "name": item.name,
                    "Level": 1,
                    "staticInvestment": self._parse_number(item.staticInvestment),
                    "dynamicInvestment": self._parse_number(item.dynamicInvestment),
                    "items": []
                }
            elif item.level == "3" and current_sub_category is not None:
                # 具体项目
                current_sub_category["items"].append({
                    "No": self._parse_no(item.no),
                    "name": item.name,
                    "Level": 2,
                    "staticInvestment": self._parse_number(item.staticInvestment),
                    "dynamicInvestment": self._parse_number(item.dynamicInvestment),
                })
            elif item.level == "0":
                # 合计行 - 跳过
                if current_sub_category is not None and current_top_category is not None:
                    current_top_category["items"].append(current_sub_category)
                    current_sub_category = None
                if current_top_category is not None:
                    result.append(current_top_category)
                    current_top_category = None
        
        # 添加最后的分类
        if current_sub_category is not None and current_top_category is not None:
            current_top_category["items"].append(current_sub_category)
        if current_top_category is not None:
            result.append(current_top_category)
        
        return result
    
    @staticmethod
    def _parse_number(value: str) -> float:
        if not value or not value.strip():
            return 0.0
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    
    @staticmethod
    def _parse_no(value: str) -> int:
        if not value or not value.strip():
            return 0
        try:
            return int(value.strip())
        except ValueError:
            return 0


class PreliminaryApprovalInvestment:
    """初设批复概算投资数据模型
    
    返回结构与 designReview 保持一致：
    [{
        "name": str,  # 大类名称（如"变电工程"、"线路工程"）
        "Level": 0,   # 大类层级
        "staticInvestment": float,  # 静态投资总计
        "dynamicInvestment": float,  # 动态投资总计
        "items": [  # 子项列表
            {
                "No": int,  # 序号
                "name": str,  # 工程名称
                "Level": 1,  # 子项层级
                "staticInvestment": float,  # 静态投资
                "dynamicInvestment": float,  # 动态投资
            },
            ...
        ]
    }, ...]
    """
    def __init__(self):
        self.items: List[InvestmentItem] = []
    
    def to_dict(self):
        """转换为嵌套结构，与 designReview 保持一致
        
        Level="1" 的项目作为大类（变电工程、线路工程等）
        Level="2" 的项目作为子项
        Level="0" 的项目（合计）跳过，不包含在输出中
        """
        if not self.items:
            return []
        
        result = []
        current_category = None
        
        for item in self.items:
            if item.level == "1":
                # 大类项目 - 创建新的类别
                if current_category is not None:
                    result.append(current_category)
                
                current_category = {
                    "name": item.name,
                    "Level": 0,
                    "staticInvestment": self._parse_number(item.staticInvestment),
                    "dynamicInvestment": self._parse_number(item.dynamicInvestment),
                    "items": []
                }
            elif item.level == "2" and current_category is not None:
                # 子项目 - 添加到当前类别的 items 中
                current_category["items"].append({
                    "No": self._parse_no(item.no),
                    "name": item.name,
                    "Level": 1,
                    "staticInvestment": self._parse_number(item.staticInvestment),
                    "dynamicInvestment": self._parse_number(item.dynamicInvestment),
                })
            elif item.level == "0":
                # 合计行 - 跳过，不包含在输出中
                # 先保存当前类别
                if current_category is not None:
                    result.append(current_category)
                    current_category = None
        
        # 添加最后一个类别
        if current_category is not None:
            result.append(current_category)
        
        return result
    
    @staticmethod
    def _parse_number(value: str) -> float:
        """将字符串数字转换为浮点数"""
        if not value or not value.strip():
            return 0.0
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    
    @staticmethod
    def _parse_no(value: str) -> int:
        """将序号转换为整数"""
        if not value or not value.strip():
            return 0
        try:
            return int(value.strip())
        except ValueError:
            return 0

