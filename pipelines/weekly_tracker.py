#!/usr/bin/env python3
"""weekly_tracker.py — 自动跟踪系统核心脚本"""

import sys, os, json, logging
from datetime import datetime, timezone, timedelta
import numpy as np

from _path_setup import ensure_ie_paths
ensure_ie_paths()
from env import DATA_ROOT, IE_SCRIPTS, IE_STRATEGIES, IE_PIPELINES, BH_CACHE, BH_REPORTS, TRACKING, SYSTEM, XHS_REPORT, XHS_SCORES, WX_ARTICLES


BH_DIR = str(DATA_ROOT / 'blackhorse-ai')  # from env
SRC_DIR = os.path.join(BH_DIR, 'src')
TRACKING_DIR = str(TRACKING)  # from env
PREDICTIONS_DIR = os.path.join(TRACKING_DIR, 'predictions')
SCRIPTS_DIR = str(IE_SCRIPTS)  # from env
for p in [SRC_DIR, SCRIPTS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

logging.basicConfig(level=logging.WARNING, format='%(levelname)s | %(message)s')
logger = logging.getLogger('tracker')

FOCUS_STOCKS = {
    "000725": {"name": "京东方A", "tier": "T1"},
    "688981": {"name": "中芯国际", "tier": "T2"},
    "688072": {"name": "拓荆科技", "tier": "T3"},
    "600584": {"name": "长电科技", "tier": "T2"},
    "688126": {"name": "沪硅产业", "tier": "T3"},
    "002371": {"name": "北方华创", "tier": "T2"},
    "688012": {"name": "中微公司", "tier": "T2"},
    "300433": {"name": "蓝思科技", "tier": "T3"},
    "002049": {"name": "紫光国微", "tier": "T1"},
    "300308": {"name": "中际旭创", "tier": "T3"},
}

def load_config():
    p = os.path.join(TRACKING_DIR, 'tracker_config.json')
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(os.path.join(TRACKING_DIR, 'tracker_config.json'), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def load_predictions():
    preds = []
    if os.path.exists(PREDICTIONS_DIR):
        for fn in sorted(os.listdir(PREDICTIONS_DIR)):
            if fn.endswith('.json'):
                with open(os.path.join(PREDICTIONS_DIR, fn), 'r', encoding='utf-8') as f:
                    p = json.load(f)
                    if not p.get('verified'):
                        preds.append(p)
    return preds

def save_prediction(pred):
    fp = os.path.join(PREDICTIONS_DIR, pred['id'] + '.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(pred, f, ensure_ascii=False, indent=2)
    logger.info(f'Pred saved: {pred["id"]}')

_seq = [1]
def next_seq():
    n = _seq[0]; _seq[0] += 1; return n

def fetch_data(code):
    try:
        from fetch_data import _get_kline_degrade
        df = _get_kline_degrade(code, days=250)
        if df is not None and not df.empty:
            return df, 'normal'
    except Exception as e:
        logger.warning(f"  ⚠️ 跳过: {e}")
        pass
    try:
        import akshare as ak
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date='20250801', adjust="qfq")
        if not df.empty:
            df.rename(columns={'日期':'date','开盘':'open','收盘':'close','最高':'high','最低':'low','成交量':'volume','成交额':'amount'}, inplace=True)
            return df, 'degraded'
    except Exception as e:
        logger.warning(f"  ⚠️ 跳过: {e}")
        pass
    return None, 'failed'

def score_stock(df):
    if df is None or df.empty:
        return None
    c = df['close'].values if 'close' in df.columns else df['\u6536\u76d8'].values
    if len(c) < 20:
        return None
    ma20 = np.mean(c[-20:])
    ma60 = np.mean(c[-60:]) if len(c) >= 60 else ma20
    cur = c[-1]
    ts = 95 if cur > ma20 > ma60 else (70 if cur > ma20 else 30)
    gain = round((cur / c[-20] - 1) * 100, 1) if len(c) >= 20 else None
    vol = np.std(np.diff(c) / c[:-1]) * np.sqrt(252) * 100
    vs = max(0, 100 - vol)
    return {'total': round(ts*0.269 + 50*0.222 + 50*0.20 + vs*0.086 + 50*0.057 + 0*0.05 + 50*0.116, 1), 'trend': ts, 'gain_20d': gain, 'vol': round(vol, 1), 'price': round(cur, 2), 'ma20': round(ma20, 2), 'ma60': round(ma60, 2) if len(c) >= 60 else None}

def run_scan():
    print('='*55); print(' Investment Tracker v1.0'); print(f' Time: {datetime.now().strftime("%Y-%m-%d %H:%M")}'); print('='*55)
    cfg = load_config()
    scan_id = datetime.now().strftime('%Y%m%d') + '-v1'
    run_at = datetime.now(timezone(timedelta(hours=8))).isoformat()
    past = load_predictions()
    print(f' Pending: {len(past)}')
    results = {}
    for code, info in FOCUS_STOCKS.items():
        print(f'  {code} {info["name"]} (Tier {info["tier"]})...', end=' ')
        df, q = fetch_data(code)
        if df is None:
            print('NO DATA'); continue
        f = score_stock(df)
        if f is None:
            print('NO SCORE'); continue
        print(f'score={f["total"]} gain={f["gain_20d"]}%')
        results[code] = {'name': info["name"], 'tier': info["tier"], 'factors': f, 'data_q': q}
        if info['tier'] in ('T1', 'T2'):
            pred = {'id': datetime.now().strftime('%Y%m%d') + f'-{next_seq():03d}', 'created_at': run_at, 'stock_code': code, 'stock_name': info['name'], 'thesis': f'Tier{info["tier"]} gain={f["gain_20d"]}%', 'expected_outcome': '1month: beats CSI300', 'timeframe': '1month', 'confidence': '60%', 'frameworks_used': ['safety', 'cycle'], 'key_assumptions': [], 'tier_at_creation': info['tier'], 'verified': False, 'verification': None}
            save_prediction(pred)
            print(f'    -> Pred {pred["id"]}')
    vc = 0
    for pred in past:
        try:
            cd = datetime.fromisoformat(pred['created_at'])
            if cd.tzinfo is None:
                cd = cd.replace(tzinfo=timezone(timedelta(hours=8)))
            if (datetime.now(timezone(timedelta(hours=8))) - cd).days >= 28:
                pred['verified'] = True; pred['verification'] = {'verified_at': run_at, 'outcome': 'pending_review'}
                with open(os.path.join(PREDICTIONS_DIR, pred['id'] + '.json'), 'w', encoding='utf-8') as f:
                    json.dump(pred, f, ensure_ascii=False, indent=2)
                vc += 1
        except Exception as e:
            logger.warning(f"  ⚠️ 跳过: {e}")
            pass
    print(f'\nSUMMARY: {len(results)} scanned, {_seq[0]-1} preds, {vc} verified')
    sr = {'scan_id': scan_id, 'run_at': run_at, 'results': results, 'summary': {'scanned': len(results), 'new_preds': _seq[0]-1, 'verified': vc}}
    sp = os.path.join(TRACKING_DIR, f'scan_{scan_id}.json')
    with open(sp, 'w', encoding='utf-8') as f:
        json.dump(sr, f, ensure_ascii=False, indent=2)
    cfg['last_scan'] = run_at
    save_config(cfg)
    print(f'Report: {sp}')

if __name__ == '__main__':
    run_scan()


# ── 报告集成（2026-05-27 新增）──

def generate_weekly_review(factors_ic: dict = None, adjustments: list = None) -> str:
    '''调用周复盘报告引擎生成 HTML 报告'''
    from strategies.weekly_review import generate_weekly_review as _gen
    return _gen(factors_ic=factors_ic, adjustments=adjustments)


def attach_to_pipeline():
    '''挂接到 daily_pipeline 每日流水线末尾生成日复盘'''
    try:
        from strategies.daily_review import generate_daily_review
        # 从最近的因子数据取 IC
        factors_ic = _load_recent_ic()
        path = generate_daily_review(factor_ics=factors_ic)
        print(f"  ✅ 日复盘已生成: {path}")
        return path
    except Exception as e:
        print(f"  ⚠️ 日复盘生成失败: {e}")
        return ""


def _load_recent_ic() -> dict:
    '''从 FactorTracker 加载最近因子 IC'''
    try:
        from strategies.factor_tracker import FactorTracker
        tracker = FactorTracker()
        perfs = tracker.get_all_performances()
        return {name: perf.rank_ic for name, perf in perfs.items() if perf}
    except Exception:
        return {}
    # 自动触发预测验证
    try:
        from evolution_engine import EvolutionEngine
        ee = EvolutionEngine()
        verified = ee.verify_outcome(datetime.now().strftime("%Y-%m-%d"))
        if verified > 0:
            logger.info(f"自动验证 {verified} 条预测")
            ee.update_weights()
    except Exception as e:
        logger.debug(f"自动验证跳过: {e}")
