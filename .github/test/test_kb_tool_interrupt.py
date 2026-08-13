# -*- coding: utf-8 -*-
"""
kb_tool.py 交互中断（KeyboardInterrupt）处理测试。

背景：用户在 --merge / --add / --alias / --del / --suggest 的交互确认环节按
Ctrl+C 时，ask() 未捕获 KeyboardInterrupt，脚本直接抛 traceback 崩溃。

修复后 ask() 把 KeyboardInterrupt 视同 'q'（退出），各命令保存已完成部分并
优雅返回；顶层 __main__ 另有兜底。本测试验证：
  1) ask() 在 input 抛 KeyboardInterrupt 时返回 'q'
  2) run_merge 在确认环节被中断时优雅返回、不抛异常（auto/manual 已合并部分保存）
"""
import builtins
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')

REPO = pathlib.Path(__file__).resolve().parents[2]      # .github/test -> 仓库根
SCRIPTS = REPO / ".github" / "scripts"
KB_TOOL = SCRIPTS / "naming" / "kb_tool.py"

# 加载 kb_tool 模块（其顶层会把 .github/scripts 加入 sys.path 以导入 lib/）
_spec = importlib.util.spec_from_file_location("kb_tool", str(KB_TOOL))
kb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kb)


def test_ask_returns_q_on_keyboard_interrupt() -> bool:
    """input 抛 KeyboardInterrupt -> ask() 返回 'q'（而非崩溃）。"""
    orig_input = builtins.input

    def raiser(prompt):
        raise KeyboardInterrupt()

    builtins.input = raiser
    try:
        result = kb.ask("测试提示: ")
    finally:
        builtins.input = orig_input
    return result == 'q'


def test_run_merge_survives_interrupt() -> tuple[bool, str]:
    """run_merge 阶段 2 确认时 Ctrl+C -> 优雅退出；先前的合并被保存。"""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="kb_test_"))
    try:
        (tmp / "roles").mkdir(parents=True)
        roles = [
            {"work": "BA", "cn": ["阿米娅"], "en": ["amiya"], "source": "manual"},
            {"work": "BA", "cn": ["阿米"], "en": ["a"], "source": "manual"},        # 子串重叠对 1
            {"work": "HSR", "cn": ["姬子"], "en": ["himeko"], "source": "manual"},
            {"work": "HSR", "cn": ["姬"], "en": ["h"], "source": "manual"},          # 子串重叠对 2
        ]
        (tmp / "roles" / "BA.json").write_text(
            json.dumps([r for r in roles if r["work"] == "BA"], ensure_ascii=False), encoding="utf-8")
        (tmp / "roles" / "HSR.json").write_text(
            json.dumps([r for r in roles if r["work"] == "HSR"], ensure_ascii=False), encoding="utf-8")
        (tmp / "works.json").write_text("{}", encoding="utf-8")

        # 第一对确认 'y' 合并；第二对确认时抛 KeyboardInterrupt（模拟 Ctrl+C）
        answers = iter(["y"])
        orig_input = builtins.input

        def fake_input(prompt):
            try:
                return next(answers)
            except StopIteration:
                raise KeyboardInterrupt()

        builtins.input = fake_input
        try:
            kb.run_merge(tmp)  # 不应抛异常
        finally:
            builtins.input = orig_input

        data = kb.load_kb_json(tmp)
        merged = data.get("roles") or []
        # 阶段 2 合并了一对（4 -> 3），中断后剩余对未处理但无异常
        return len(merged) == 3, f"合并后角色数 = {len(merged)}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    checks = [
        ("ask() Ctrl+C -> 'q'", test_ask_returns_q_on_keyboard_interrupt()),
        ("run_merge 中断优雅退出且保存已合并", *test_run_merge_survives_interrupt()[0:1]),
    ]
    ok, msg = test_run_merge_survives_interrupt()
    checks.append(("run_merge 合并结果正确", ok, msg))

    all_ok = True
    for i, check in enumerate(checks, 1):
        name = check[0]
        passed = check[1]
        detail = check[2] if len(check) > 2 else ""
        print(f"检查 {i}: {'PASS' if passed else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
        all_ok = all_ok and passed
    print("kb_tool 中断处理测试:", "全部通过" if all_ok else "存在失败")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
