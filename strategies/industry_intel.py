"""产业咨询收集分析模块 — 行业动态采集 → 因子映射"""

import sys, json, logging, time, re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from threading import Lock

from config_loader import IE_SCRIPTS, CFG as CONFIG, report_dir
import os

from env import DATA_ROOT, IE_SCRIPTS, IE_STRATEGIES, IE_PIPELINES, BH_CACHE, BH_REPORTS, TRACKING, SYSTEM, XHS_REPORT, XHS_SCORES, WX_ARTICLES

# DSH path handled by config_loader

log = logging.getLogger("industry_intel")

# 行业主题 → 关键词映射（与HOT_TOPICS兼容）
# 每个主题有匹配的关键词列表和相关权重
INDUSTRY_TOPICS = {
    "AI大模型": {"keywords": ["AI", "LLM", "大模型", "GPT", "OpenAI", "Anthropic", "Claude",
                              "人工智能", "AGI", "多模态", "科大讯飞", "商汤", "三六零", "云从"], "weight": 0.15,
                "positive_words": ["突破", "发布", "融资", "增长", "开源", "合作"],
                "negative_words": ["裁员", "调查", "监管", "诉讼", "亏损", "事故"]},
    "半导体/芯片": {"keywords": ["芯片", "半导体", "英伟达", "台积电", "光刻", "先进封装",
                                "HBM", "DRAM", "NAND", "EUV"], "weight": 0.15,
                   "positive_words": ["量产", "扩产", "供不应求", "突破", "国产替代"],
                   "negative_words": ["制裁", "限购", "断供", "库存过剩", "降价"]},
    "新能源": {"keywords": ["新能源", "光伏", "锂电池", "储能", "电动车", "固态电池",
                            "钙钛矿", "氢能", "风电"], "weight": 0.12,
              "positive_words": ["装机量增长", "补贴", "产能提升", "出口增长"],
              "negative_words": ["产能过剩", "反倾销", "价格战", "退补"]},
    "机器人": {"keywords": ["机器人", "人形机器人", "灵巧手", "滚柱丝杠", "谐波减速器",
                            "机器视觉", "自动化"], "weight": 0.10,
              "positive_words": ["量产", "订单", "融资", "政策支持"],
              "negative_words": ["延迟", "召回", "技术瓶颈"]},
    "低空经济": {"keywords": ["低空", "eVTOL", "飞行汽车", "无人机", "空域管理",
                              "通航"], "weight": 0.08,
                "positive_words": ["政策", "试点", "牌照", "航线", "融资"],
                "negative_words": ["事故", "监管收紧", "推迟"]},
    "消费电子": {"keywords": ["消费电子", "手机", "PC", "可穿戴", "VR", "AR", "MR",
                              "折叠屏", "物联网"], "weight": 0.08,
                "positive_words": ["销量增长", "新品发布", "创新", "市场份额提升"],
                "negative_words": ["销量下滑", "库存积压", "砍单"]},
    "医药创新": {"keywords": ["创新药", "生物医药", "基因治疗", "ADC", "细胞治疗",
                              "CXO", "GLP-1", "医疗器械"], "weight": 0.10,
                "positive_words": ["获批", "临床", "突破", "授权", "出海"],
                "negative_words": ["集采", "临床失败", "专利失效", "监管"]},
    "军工": {"keywords": ["军工", "国防", "航天", "卫星", "导弹", "雷达", "电子对抗",
                          "C919", "大飞机"], "weight": 0.08,
            "positive_words": ["订单", "列装", "预算增长", "出口"],
            "negative_words": ["预算削减", "技术封锁"]},
    "金融": {"keywords": ["银行", "券商", "保险", "金融科技", "数字人民币", "量化",
                           "资管"], "weight": 0.07,
            "positive_words": ["降准", "降息", "宽松", "改革", "合并"],
            "negative_words": ["坏账", "处罚", "监管", "风险暴露"]},
    "消费": {"keywords": ["消费", "白酒", "食品饮料", "旅游", "免税", "零售",
                           "跨境电商", "预制菜"], "weight": 0.07,
            "positive_words": ["消费复苏", "涨价", "扩张", "品牌升级"],
            "negative_words": ["消费降级", "需求疲软", "库存高企"]},
}


class IndustryIntel:
    """产业咨询情报系统

    功能:
    - 从aihot API采集行业动态
    - 将新闻/资讯分类到行业主题
    - 计算行业情绪得分
    - 提供因子映射接口
    """

    def __init__(self, cache_ttl_hours: int = 6):
        self._cache_ttl = cache_ttl_hours
        self._cache: Dict[str, dict] = {}
        self._lock = Lock()
        self._data_dir = report_dir("industry")
        self._data_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 数据采集 ----------

    def fetch_aihot_news(self, hours: int = 24) -> List[dict]:
        """从aihot API获取最新AI/科技新闻"""
        import urllib.request
        from datetime import datetime, timezone

        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = f"https://aihot.virxact.com/api/public/items?mode=selected&since={since}&take=50"
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 aihot-skill/0.2.0"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            log.info(f"aihot: 获取 {len(items)} 条资讯")
            return items
        except Exception as e:
            log.warning(f"aihot API失败: {e}")
            return []

    # ---------- 主题分类 ----------

    def classify_news(self, items: List[dict]) -> Dict[str, List[dict]]:
        """将新闻条目分类到行业主题"""
        classified: Dict[str, List[dict]] = {}
        for item in items:
            title = (item.get("title", "") or "") + " " + (item.get("summary", "") or "")
            title_lower = title.lower()

            matched = False
            for topic, info in INDUSTRY_TOPICS.items():
                for kw in info["keywords"]:
                    if kw.lower() in title_lower:
                        if topic not in classified:
                            classified[topic] = []
                        classified[topic].append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "source": item.get("source", ""),
                            "published_at": item.get("publishedAt", ""),
                            "matched_kw": kw,
                        })
                        matched = True
                        break
            if not matched:
                if "未分类" not in classified:
                    classified["未分类"] = []
                classified["未分类"].append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                })
        return classified

    # ---------- 情绪分析 ----------

    def compute_sentiment(self, classified: Dict[str, List[dict]]) -> Dict[str, float]:
        """计算每个主题的情绪得分 [-1.0, 1.0]"""
        sentiments = {}
        for topic, items in classified.items():
            if topic == "未分类":
                continue
            info = INDUSTRY_TOPICS.get(topic, {})
            pos_words = info.get("positive_words", [])
            neg_words = info.get("negative_words", [])

            pos_count = 0
            neg_count = 0
            for item in items:
                text = f"{item.get('title', '')} {item.get('source', '')}"
                for pw in pos_words:
                    if pw in text:
                        pos_count += 1
                for nw in neg_words:
                    if nw in text:
                        neg_count += 1

            total = pos_count + neg_count
            if total > 0:
                sentiments[topic] = round((pos_count - neg_count) / total, 3)
            else:
                sentiments[topic] = 0.0

        return sentiments

    def compute_heat(self, classified: Dict[str, List[dict]]) -> Dict[str, float]:
        """计算每个主题的热度 [0.0, 1.0] — 基于资讯数量归一化"""
        if not classified:
            return {}
        total = sum(len(v) for v in classified.values())
        if total == 0:
            return {}
        return {topic: round(len(items) / total, 3) for topic, items in classified.items()}

    # ---------- 行业股票映射 ----------

    def get_relevant_stocks(self, topic: str) -> List[str]:
        """获取某个行业主题相关的股票代码列表（TODO: 待实现name_map反查）"""
        return []  # 目前由factor_sentiment通过名称匹配替代

    # ---------- 持久化 ----------

    def _cache_path(self) -> Path:
        return self._data_dir / "industry_state.json"

    def save_state(self, classified: dict, sentiments: dict, heat: dict):
        """保存当前行业状态"""
        state = {
            "updated_at": datetime.now().isoformat(),
            "classified": {k: v[:5] for k, v in classified.items()},  # 只保留前5条
            "sentiments": sentiments,
            "heat": heat,
        }
        with open(self._cache_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        log.info(f"行业状态已保存: {len(classified)} 个主题")

    def load_state(self) -> Optional[dict]:
        """加载行业状态"""
        path = self._cache_path()
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            age = (datetime.now() - datetime.fromisoformat(state.get("updated_at", "2000-01-01"))).total_seconds()
            if age > self._cache_ttl * 3600:
                return None
            return state
        except Exception:
            return None

    # ---------- 因子映射接口 ----------

    def get_sentiment_score(self, stock_name: str) -> float:
        """根据股票名称获取当前情绪得分 [0, 100]"""
        if not stock_name or not stock_name.strip():
            return 0.0
        name_lower = stock_name.lower()
        # 检查股票所属行业主题
        for topic, info in INDUSTRY_TOPICS.items():
            for kw in info["keywords"]:
                if kw.lower() in name_lower or name_lower in kw.lower():
                    # 获取该行业的情绪得分
                    state = self.load_state()
                    if state:
                        sentiment = state.get("sentiments", {}).get(topic, 0)
                        heat = state.get("heat", {}).get(topic, 0.5)
                        # 情绪分 [0, 100] = (sentiment * 0.5 + 0.5) * heat * 100
                        score = (sentiment * 0.5 + 0.5) * heat * 100
                        return round(min(score, 100), 1)
                    return info.get("weight", 10) * 5  # fallback
        return 0.0

    # ---------- 主循环 ----------

    def update(self) -> dict:
        """执行一次完整的行业情报更新"""
        log.info("=== 行业情报更新 ===")
        try:
            items = self.fetch_aihot_news(hours=24)
            classified = self.classify_news(items)
            sentiments = self.compute_sentiment(classified)
            heat = self.compute_heat(classified)

            self.save_state(classified, sentiments, heat)

            result = {
                "status": "ok",
                "total_news": len(items),
                "topics": len(classified),
                "top_sentiment": max(sentiments.items(), key=lambda x: x[1]) if sentiments else ("", 0),
                "top_heat": max(heat.items(), key=lambda x: x[1]) if heat else ("", 0),
            }
            log.info(f"更新完成: {result['total_news']}条新闻, {result['topics']}个主题")
            return result
        except Exception as e:
            log.error(f"行业情报更新失败: {e}")
            return {"status": "error", "message": str(e)}

    def summary(self) -> str:
        """输出行业状态摘要"""
        state = self.load_state()
        if not state:
            return "⚠️ 行业情报数据不可用（尚未更新或缓存过期）"

        lines = ["📊 行业情报摘要", "=" * 40]
        lines.append(f"更新: {state.get('updated_at', 'N/A')}")
        lines.append("")

        sentiments = state.get("sentiments", {})
        heat = state.get("heat", {})
        for topic, s in sorted(sentiments.items(), key=lambda x: abs(x[1]), reverse=True)[:10]:
            bar = "🟢" if s > 0.1 else ("🔴" if s < -0.1 else "⚪")
            h = heat.get(topic, 0)
            lines.append(f"{bar} {topic}: 情绪{s:+.2f} 热度{h:.0%}")

        return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ii = IndustryIntel()
    result = ii.update()
    print(f"\n更新结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    print(f"\n{ii.summary()}")

    # ---------- 多源舆情采集 ----------

    def fetch_xhs_sentiment(self, topic: str = "A股") -> Dict[str, float]:
        """从小红书舆情系统获取话题情绪分数"""
        # 读取 xhs-sentiment-monitoring 产出文件
        xhs_paths = [
            Path(os.environ.get("XHS_REPORT_PATH", str(XHS_REPORT))),
            XHS_SCORES,
        ]
        for p in xhs_paths:
            if p.exists():
                try:
                    import json
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f) if p.suffix == ".json" else {"raw": f.read()}
                    log.info(f"小红书舆情已加载: {p.name}")
                    return data if isinstance(data, dict) else {}
                except Exception as e:
                    log.debug(f"加载小红书舆情失败: {e}")
        return {}

    def fetch_cls_news(self, hours: int = 24) -> List[dict]:
        """从财联社获取实时财经快讯"""
        import urllib.request, json
        url = "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=8.5.5"
        payload = json.dumps({"category":"news","limit":50,"timestamp":int(datetime.now().timestamp())}).encode()
        try:
            req = urllib.request.Request(url, data=payload,
                headers={"User-Agent":"Mozilla/5.0","Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            items = data.get("data", data.get("items", data.get("roll_data", [])))
            if isinstance(items, list):
                log.info(f"财联社: 获取 {len(items)} 条快讯")
                return items
        except Exception as e:
            log.warning(f"财联社API失败: {e}")
        return []

    def fetch_wechat_articles(self, keyword: str = "") -> List[dict]:
        """读取微信公众号文章缓存（由 wechat-article-scraper 产出）"""
        wx_dir = WX_ARTICLES
        if not wx_dir.exists():
            return []
        articles = []
        for f in sorted(wx_dir.glob("*.md"))[-10:]:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    articles.append({"source": "wechat", "file": f.name, "content": fh.read()[:2000]})
            except Exception:
                continue
        log.info(f"公众号: 读取 {len(articles)} 篇文章")
        return articles

