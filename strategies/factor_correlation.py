"""因子正交化追踪器 — 因子相关矩阵 + 共线性检测"""

import sys, logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import pandas as pd
import numpy as np

from config_loader import report_dir
log = logging.getLogger("factor_corr")

FACTOR_NAMES = ["trend", "volume", "volatility", "capital", "fundamental", "sentiment", "alpha191"]


def compute_factor_correlation(factor_scores: Dict[str, List[float]]) -> pd.DataFrame:
    """计算因子得分间的相关矩阵"""
    df = pd.DataFrame(factor_scores)
    return df.corr()


def detect_collinearity(corr_matrix: pd.DataFrame, threshold: float = 0.7) -> List[tuple]:
    """检测高度相关的因子对"""
    pairs = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i+1, len(corr_matrix.columns)):
            val = abs(corr_matrix.iloc[i, j])
            if val > threshold:
                pairs.append((corr_matrix.columns[i], corr_matrix.columns[j], round(val, 3)))
    return pairs


def save_correlation_report(factor_scores: Dict[str, List[float]]):
    """保存因子相关分析报告"""
    corr = compute_factor_correlation(factor_scores)
    collinear = detect_collinearity(corr)
    
    report = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "samples": len(next(iter(factor_scores.values()))) if factor_scores else 0,
        "collinear_pairs": [{"f1": p[0], "f2": p[1], "correlation": p[2]} for p in collinear],
        "correlation_matrix": corr.to_dict(),
    }
    
    path = report_dir("factors") / f"factor_correlation_{datetime.now().strftime('%Y%m%d')}.json"
    with open(path, "w", encoding="utf-8") as f:
        import json
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"因子相关报告已保存: {path}")
    
    if collinear:
        log.warning(f"检测到 {len(collinear)} 对共线因子: {collinear}")
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test with random data
    np.random.seed(42)
    scores = {f: list(np.random.randn(100)) for f in FACTOR_NAMES}
    report = save_correlation_report(scores)
    print(f"相关矩阵:\n{compute_factor_correlation(scores).round(3)}")
