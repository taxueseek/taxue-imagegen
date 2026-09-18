#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_regressions.py — 回归测试入口（断言本体按被测域拆在 scripts/tests/）。

2026-09-18：单文件长到 1,304 行后按域拆成五个模块（preflight / fill_meta /
postcheck / dewm / 文档门禁）。拆分是纯搬运：断言逐字未改，只把 main() 的
手工调用清单改成「各域模块声明 TESTS，这里按序聚合」。

拆分时顺手修了两件事：
  1. test_preflight_quote_declaration（坑 5）此前定义了但 main() 漏接线，
     是一个**从未跑过**的回归测试——现已入列；
  2. 新增 test_skill_verify_consistency（父 SKILL.md §5 ↔ verify 子技能
     判定口径的一致性，见 tests/test_docs_gates.py 的 docstring）。

用法（契约不变，run_tests.sh 第 [4/8] 步与 CI 只认退出码）：
  python3 scripts/test_regressions.py      # 退出码 0=全过，1=有失败
  bash scripts/run_tests.sh                # 集成进总套件
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tests"))

import _harness  # noqa: E402
import test_dewm  # noqa: E402
import test_docs_gates  # noqa: E402
import test_fill_meta  # noqa: E402
import test_postcheck  # noqa: E402
import test_preflight  # noqa: E402

# 运行顺序 = 被测链路：出稿 → 验收 → 去水印 → 文档门禁
MODULES = (test_preflight, test_fill_meta, test_postcheck, test_dewm, test_docs_gates)


def main():
    print("== taxue-imagegen regression tests ==")
    for mod in MODULES:
        for fn in mod.TESTS:
            print(f"\n[{fn.__name__}]")
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                # 2026-09-18：只打 repr(e) 会让「归因到哪个函数」失真——异常可能来自
                # 被测函数之外的调用链（如 _harness），此时必须看堆栈才能定位。
                traceback.print_exc()
                _harness.check(f"{fn.__name__} 执行异常", False, repr(e))

    failed = [r for r in _harness._results if not r[0]]
    print(f"\n== summary: {len(_harness._results) - len(failed)}/{len(_harness._results)} passed ==")
    for _, label, why in failed:
        print(f"  FAIL {label}  <- {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
