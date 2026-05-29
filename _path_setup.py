"""
_path_setup.py -- investment-engine 统一导入入口

所有子模块通过此文件注册到 sys.path，替代散落各处的 sys.path.insert。
用途：在模块顶部调用 ensure_ie_paths() 后即可直接 import 同项目其他模块。

用法：
    from _path_setup import ensure_ie_paths
    ensure_ie_paths()

设计原则：
    - env.py 是依赖图叶子节点（不导入任何项目内部模块）
    - _path_setup.py 仅做路径注册，不做模块初始化
    - 幂等：多次调用只注册一次
"""

import sys, os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ADDED = False

# 所有子模块目录（注册到 sys.path 供直接 import）
_SUBDIRS = [
    "scripts",
    "strategies",
    "pipelines",
    "tracking",
    "system",
]


def ensure_ie_paths():
    """将 investment-engine 下所有子模块目录加入 sys.path（幂等）"""
    global _ADDED
    if _ADDED:
        return
    for subdir in _SUBDIRS:
        p = str(_HERE / subdir)
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)
    # 根目录本身也加入（方便 import env.py 等）
    root = str(_HERE)
    if root not in sys.path:
        sys.path.insert(0, root)
    _ADDED = True


def ensure_strategies_path():
    """仅注册 strategies/ 目录（轻量版，用于不需要其他子模块的场景）"""
    p = str(_HERE / "strategies")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.append(p)


def ensure_pipelines_path():
    """仅注册 pipelines/ 目录"""
    p = str(_HERE / "pipelines")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.append(p)

# 向后兼容别名
ensure_dsh_paths = ensure_ie_paths


# 版本信息
__version__ = "1.0.0"
__ie_root__ = str(_HERE)
