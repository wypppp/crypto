"""冻结过滤契约的隔离入口；只修导入环境，语义与源文件不变。"""

from frozen_contract_imports import contract_module

_contract = contract_module("contract_filter")


def __getattr__(name):
    return getattr(_contract, name)
