#!/usr/bin/env python3
"""review.py - 代码审查工具（双通道）
  结构化检查: python review.py src <file>       (确定性, 0.2s)
  Agent互审:  python review.py agent <file>     (子agent, 独立上下文)
  ARCH审查:   python review.py arch <doc.md>    (子agent审查设计文档)
  
  结构化检查 = 语法 + 导入 + 边界模式
  Agent互审   = delegate_task派生子Hermes实例做LLM审查
"""

import os, sys, json, py_compile, re

DIR = os.path.dirname(os.path.abspath(__file__))

def struct_check(fp):
    """确定性结构化检查"""
    results = []
    if not os.path.exists(fp): return [("FAIL", "Not found: %s" % fp)]
    with open(fp, "r", encoding="utf-8") as f: content = f.read()
    if fp.endswith(".py"):
        try:
            py_compile.compile(fp, doraise=True)
            results.append(("OK", "Syntax OK"))
        except py_compile.PyCompileError as e:
            return [("FAIL", "Syntax: %s" % str(e).split("\n")[0][:120])]
    for line in content.split("\n"):
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            parts = s.split()
            if len(parts) >= 2:
                mod = parts[1].split(".")[0]
                try: __import__(mod)
                except: results.append(("WARN", "Import? %s" % mod))
    if "except:" in content and "pass" in content:
        results.append(("WARN", "Bare except:pass"))
    return results

def print_results(name, results):
    status = "FAIL" if any(r[0]=="FAIL" for r in results) else "OK"
    print("%-30s [%s]" % (name, status))
    for s, m in results:
        print("  %-6s %s" % (s, m[:120]))
    return status

def review_src(fp):
    if not fp: return
    results = struct_check(fp)
    print_results(os.path.basename(fp), results)

def review_agent(fp):
    """使用delegate_task派生子agent审查（由调用方执行，本函数仅为占位说明）"""
    print("\n  Agent REVIEW: 由调用方通过delegate_task执行")
    print("  在Hermes会话中调用: delegate_task(goal='REVIEW this code...')")
    print("  -> 子agent独立会话, 独立上下文, 审查结果返回父会话")

def review_arch(fp):
    """ARCH文档审查说明"""
    print("\n  ARCH REVIEW: 由调用方通过delegate_task执行")
    print("  在Hermes会话中调用: delegate_task(goal='REVIEW this ARCH design...')")
    print("  -> 子agent审查设计文档, 输出APPROVED/FAIL+问题清单")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python review.py src <file>    # 结构化检查")
        print("  python review.py agent <file>  # Agent互审(需Hermes调用)")
        print("  python review.py arch <doc>    # ARCH审查(需Hermes调用)")
        sys.exit(1)
    mode, target = sys.argv[1], sys.argv[2]
    if mode == "src": review_src(target)
    elif mode == "agent": review_agent(target)
    elif mode == "arch": review_arch(target)
    else: print("Unknown mode: %s" % mode)
