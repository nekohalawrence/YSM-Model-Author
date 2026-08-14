# -*- coding: utf-8 -*-
"""
kb_tool.py --merge 的跳过记录与提示排版测试。

覆盖：
  1) 用户对重复条目对输入 'n'（跳过）后，merge_skips.json 持久化该对；
     再次运行 --merge 时不再询问（自动跳过）。
  2) 提示排版：Game 全称显示在上层；中文名与英文名按索引逐项对齐。
  3) 已合并/删除的条目对会被清理（prune），不影响后续运行。
"""
import builtins
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')

REPO = pathlib.Path(__file__).resolve().parents[2]
KB_TOOL = REPO / ".github" / "scripts" / "naming" / "kb_tool.py"

_spec = importlib.util.spec_from_file_location("kb_tool", str(KB_TOOL))
kb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kb)

WORKS = {
    "BA": {"cn": ["碧蓝档案"], "en": ["Blue Archive"]},
    "HSR": {"cn": ["崩坏：星穹铁道"], "en": ["Honkai Star Rail"]},
}

# 两对子串重叠（cn/en 无完全相等，不会进阶段 1 自动合并）
ROLES_BA = [
    {"work": "BA", "cn": ["槌永日和"], "en": ["tsuchinaga-hiyori"], "source": "manual"},
    {"work": "BA", "cn": ["空崎日奈", "日奈"],
     "en": ["new_sorasaki-hina", "sorasaki-hina", "hina"], "source": "manual"},
]
ROLES_HSR = [
    {"work": "HSR", "cn": ["三月七"], "en": ["march7th"], "source": "manual"},
    {"work": "HSR", "cn": ["三月"], "en": ["march"], "source": "manual"},
]


def make_kb(tmp: pathlib.Path) -> None:
    (tmp / "character").mkdir(parents=True)
    (tmp / "character" / "BA.json").write_text(json.dumps(ROLES_BA, ensure_ascii=False), encoding="utf-8")
    (tmp / "character" / "HSR.json").write_text(json.dumps(ROLES_HSR, ensure_ascii=False), encoding="utf-8")
    (tmp / "works.json").write_text(json.dumps(WORKS, ensure_ascii=False), encoding="utf-8")


def run_merge_with_inputs(tmp: pathlib.Path, inputs: list[str]) -> list[str]:
    """运行 run_merge，按 inputs 依次应答（耗尽后抛 KeyboardInterrupt=Ctrl+C），返回打印行。"""
    captured: list[str] = []
    orig_print = builtins.print

    def cap_print(*args, **kwargs):
        captured.append(" ".join(str(a) for a in args))
        orig_print(*args, **kwargs)

    answers = iter(inputs)
    orig_input = builtins.input

    def fake_input(prompt):
        try:
            return next(answers)
        except StopIteration:
            raise KeyboardInterrupt()

    builtins.print = cap_print
    builtins.input = fake_input
    try:
        kb.run_merge(tmp)
    finally:
        builtins.print = orig_print
        builtins.input = orig_input
    return captured


def test_format_pair_lines() -> tuple[bool, str]:
    """Game 全称在上层；每个条目一行（cn/en 各自逗号连接），无空 cn 行。"""
    lines = kb.format_pair_lines(ROLES_BA[0], ROLES_BA[1], WORKS).splitlines()
    ok = lines[0] == "Game: 碧蓝档案 (BA)"
    ok = ok and len(lines) == 3  # Game + 两个条目各一行
    ok = ok and "槌永日和" in lines[1] and "tsuchinaga-hiyori" in lines[1]
    ok = ok and "空崎日奈, 日奈" in lines[2] and "new_sorasaki-hina, sorasaki-hina, hina" in lines[2]
    ok = ok and not any(ln.strip().startswith("|") for ln in lines[1:])  # 无空 cn 行
    return ok, " | ".join(l.strip() for l in lines)


def test_skip_persisted(tmp: pathlib.Path) -> tuple[bool, str]:
    """第一次：两对都输 n -> merge_skips.json 记录两对。"""
    run_merge_with_inputs(tmp, ["n", "n"])
    skips = kb.load_merge_skips(tmp)
    ba_key = kb.pair_skip_key(ROLES_BA[0], ROLES_BA[1])
    hsr_key = kb.pair_skip_key(ROLES_HSR[0], ROLES_HSR[1])
    return (ba_key in skips and hsr_key in skips,
            f"skips={len(skips)} 含 BA={ba_key in skips} HSR={hsr_key in skips}")


def test_skip_prevents_reask(tmp: pathlib.Path) -> tuple[bool, str]:
    """第二次运行：两对均被记录，不再出现任何询问（ask 不被调用）。"""
    asked: list[str] = []
    orig_input = builtins.input

    def fake_input(prompt):
        asked.append(prompt)
        raise KeyboardInterrupt()

    builtins.input = fake_input
    try:
        kb.run_merge(tmp)  # 不应询问；即使被中断也优雅退出
    finally:
        builtins.input = orig_input
    return len(asked) == 0, f"ask 调用次数 = {len(asked)}"


def test_prune_invalid_skips() -> tuple[bool, str]:
    """条目被合并/删除后，对应 skip 记录被清理。"""
    valid = f"{kb.role_key(ROLES_BA[0])} ↔ {kb.role_key(ROLES_BA[1])}"
    skips = [valid, "BA|已删除|deleted ↔ BA|幽灵|ghost"]
    pruned = kb.prune_merge_skips(skips, [ROLES_BA[0], ROLES_BA[1]])
    return pruned == [valid], f"pruned={pruned}"





def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="kb_skip_"))
    try:
        make_kb(tmp)
        checks = [
            ("format_pair_lines: Game 全称 + cn/en 对齐", *test_format_pair_lines()),
            ("第一次 n 后 merge_skips 持久化", *test_skip_persisted(tmp)),
            ("第二次运行不再询问", *test_skip_prevents_reask(tmp)),
            ("失效 skip 记录被清理", *test_prune_invalid_skips()),
        ]
        all_ok = True
        for i, (name, passed, detail) in enumerate(checks, 1):
            print(f"检查 {i}: {'PASS' if passed else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
            all_ok = all_ok and passed
        print("merge 跳过记录测试:", "全部通过" if all_ok else "存在失败")
        return 0 if all_ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
