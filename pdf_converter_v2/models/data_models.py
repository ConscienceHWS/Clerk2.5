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
    
    def to_dict(self):
        return {
            "weather": self.weather,
            "temp": self.temp,
            "humidity": self.humidity,
            "windSpeed": self.windSpeed
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

