"""隔离加载冻结合同：保留源文件SHA，不把历史目录留在全局搜索路径。"""

import importlib.util
import sys
from functools import cache
from pathlib import Path

H = Path(__file__).resolve().parent
DQ37 = H.parent / "发射台_前期右尾评测底座_DQ-37"
DQ35 = H.parent / "pump毕业币_数据留存_DQ-35"


@cache
def source_module(path):
    """按绝对来源加载到私有模块名，拒绝借用同名缓存。"""
    path = Path(path).resolve()
    name = "_wm2_source_" + path.parent.name + "_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


@cache
def contract_module(name):
    """只执行指定冻结合同；其临时路径和公用模块别名均在退出时还原。"""
    if name not in ("contract_filter", "contract_pairs"):
        raise ValueError("只允许加载两份冻结合同")
    original_path = sys.path[:]
    missing = object()
    original_modules = {k: sys.modules.get(k, missing) for k in ("weeks", "forward")}
    try:
        sys.modules["weeks"] = source_module(DQ37 / "weeks.py")
        if name == "contract_filter":
            sys.modules["forward"] = source_module(DQ37 / "forward.py")
        return source_module(H / (name + ".py"))
    finally:
        sys.path[:] = original_path
        for key, value in original_modules.items():
            if value is missing:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
