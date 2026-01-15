# Copyright (c) Opendatalab. All rights reserved.

"""
文档类型检测
"""


def detect_document_type(markdown_content: str) -> str:
    """
    检测文档类型
    
    Returns:
        str: 文档类型
            - "noiseRec" - 噪声检测
            - "emRec" - 电磁检测
            - "opStatus" - 工况信息
            - "settlementReport" - 结算报告
            - "designReview" - 设计评审
            - "feasibilityApprovalInvestment" - 可研批复投资估算
            - "feasibilityReviewInvestment" - 可研评审投资估算
            - "preliminaryApprovalInvestment" - 初设批复概算投资
            - "unknown" - 未知类型
    """
    # 检测表格类型（噪声、电磁）- 兼容旧名称
    if "污染源噪声检测原始记录表" in markdown_content:
        return "noiseRec"  # 也支持 noise_detection
    if "工频电场/磁场环境检测原始记录表" in markdown_content or "工频电场磁场环境检测原始记录表" in markdown_content:
        return "emRec"  # 也支持 electromagnetic_detection
    
    # 检测投资估算类型（新增3个类型）
    # 可研批复投资估算（包含建设规模相关字段）
    if ("可研批复" in markdown_content or "可行性研究报告的批复" in markdown_content) and \
       ("工程或费用名称" in markdown_content or "静态投资" in markdown_content):
        # 检查是否有建设规模相关列（可研批复特有）
        if "架空线" in markdown_content or "间隔" in markdown_content:
            return "feasibilityApprovalInvestment"
    
    # 可研评审投资估算
    if ("可研评审" in markdown_content or "可行性研究报告的评审意见" in markdown_content) and \
       ("工程或费用名称" in markdown_content or "静态投资" in markdown_content):
        return "feasibilityReviewInvestment"
    
    # 初设批复概算投资
    if ("初设批复" in markdown_content or "初步设计的批复" in markdown_content) and \
       ("工程名称" in markdown_content or "静态投资" in markdown_content):
        return "preliminaryApprovalInvestment"
    
    return "unknown"

