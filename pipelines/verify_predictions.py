#!/usr/bin/env python3
"""verify_predictions.py — 验证预测结果 vs 实际走势"""

import os, sys, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

# ====== sys.path setup (before env import) ======
_SCRIPT_DIR = Path(__file__).resolve().parent
_ROOT = str(_SCRIPT_DIR.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from _path_setup import ensure_ie_paths
ensure_ie_paths()
# ================================================

from env import DATA_ROOT, IE_SCRIPTS, IE_STRATEGIES, IE_PIPELINES, BH_CACHE, BH_REPORTS, TRACKING, SYSTEM, XHS_REPORT, XHS_SCORES, WX_ARTICLES


TRACKING = str(TRACKING)  # from env
PRED_DIR = os.path.join(TRACKING, 'predictions')
VERIFY_FILE = os.path.join(TRACKING, 'verification_log.json')

# 加入黑马管道
BH = str(IE_STRATEGIES)  # from env
DSH = str(IE_SCRIPTS)  # from env
for p in [BH, DSH]:
    if p not in sys.path: sys.path.insert(0, p)

def load_preds(only_unverified=True):
    preds = []
    if not os.path.exists(PRED_DIR): return preds
    for fn in sorted(os.listdir(PRED_DIR)):
        if fn.endswith('.json'):
            with open(os.path.join(PRED_DIR, fn), 'r', encoding='utf-8') as f:
                p = json.load(f)
                if not only_unverified or not p.get('verified'):
                    preds.append(p)
    return preds

def get_current_price(code):
    """获取最新价格"""
    try:
        from fetch_data import _get_kline_degrade
        df = _get_kline_degrade(code, days=30)
        if df is not None and not df.empty:
            c = df['收盘'].values if '收盘' in df.columns else df['close'].values
            return c[-1], c[0] if len(c) >= 2 else None
    except:
        pass
    return None, None

def verify_pred(pred):
    """验证单条预测：对比预期 vs 实际"""
    code = pred['stock_code']
    expected = pred.get('expected_outcome', '')
    current, start_price = get_current_price(code)
    if current is None:
        return None
    
    # 检查时间
    created = pred.get('created_at', '')
    if not created:
        return None
    
    try:
        cd = datetime.fromisoformat(created)
        if cd.tzinfo is None:
            cd = cd.replace(tzinfo=timezone(timedelta(hours=8)))
        days = (datetime.now(timezone(timedelta(hours=8))) - cd).days
    except:
        return None
    
    # 计算涨跌幅
    change = ((current / start_price) - 1) * 100 if start_price else 0
    
    # 判断结果 (简化版逻辑)
    outcome = 'pending'
    lesson = ''
    
    if 'beat' in expected or '超额收益' in expected or '补涨' in expected or '涨幅超过' in expected:
        # 需要比较板块，暂时用绝对值近似
        if change > 5:
            outcome = 'correct'
        elif change > -5:
            outcome = 'partial'
        else:
            outcome = 'wrong'
            lesson = '跌幅超出预期'
    elif '震荡' in expected or '高位' in expected or '波动' in expected:
        if -8 <= change <= 8:
            outcome = 'correct'
        elif change > 8:
            outcome = 'partial'
            lesson = '涨幅超过震荡预期'
        else:
            outcome = 'wrong'
            lesson = '跌幅超过震荡预期'
    elif '回调' in expected or '等回调' in expected:
        if change < -5:
            outcome = 'correct'
            lesson = '已出现回调，可关注买入机会'
        elif change > 5:
            outcome = 'wrong'
            lesson = '未出现回调反而上涨'
        else:
            outcome = 'partial'
    elif '催化剂' in expected or '消息面' in expected:
        if change > 10:
            outcome = 'correct'
        elif change > 0:
            outcome = 'partial'
        else:
            outcome = 'wrong'
    
    return {
        'pred_id': pred['id'],
        'stock': pred['stock_name'],
        'days_elapsed': days,
        'start_price': round(start_price, 2) if start_price else None,
        'current_price': round(current, 2),
        'change_pct': round(change, 1),
        'expected': expected[:80],
        'outcome': outcome,
        'lesson': lesson,
    }

def main():
    print('='*55)
    print('  Prediction Verification Engine')
    print('='*55)
    
    preds = load_preds()
    print(f'\n  Unverified predictions: {len(preds)}')
    
    results = []
    for p in preds:
        r = verify_pred(p)
        if r and r['days_elapsed'] >= 1:  # 只验证14天以上的
            results.append(r)
            print(f'  {p["id"]} {p["stock_name"]}: {r["change_pct"]:+.1f}% → {r["outcome"]}')
    
    if results:
        correct = sum(1 for r in results if r['outcome'] == 'correct')
        partial = sum(1 for r in results if r['outcome'] == 'partial')
        wrong = sum(1 for r in results if r['outcome'] == 'wrong')
        total = len(results)
        
        print(f'\n  Accuracy: {correct}/{total} correct ({correct/total*100:.0f}%)')
        print(f'  Partial: {partial}/{total} ({partial/total*100:.0f}%)')
        print(f'  Wrong: {wrong}/{total} ({wrong/total*100:.0f}%)')
        
        # 保存验证日志
        log = {'verified_at': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'results': results, 'summary': {'total': total, 'correct': correct, 'partial': partial, 'wrong': wrong}}
        with open(VERIFY_FILE, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        print(f'\n  Log: {VERIFY_FILE}')
    else:
        print('\n  No predictions ready for verification yet (need 14+ days)')
    
    print('='*55)

if __name__ == '__main__':
    main()
