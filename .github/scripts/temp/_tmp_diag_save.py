"""临时诊断：在临时目录副本上验证 load→add→save→load 读写闭环是否生效。"""
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # temp → scripts → .github → 仓库根
sys.path.insert(0, str(REPO / ".github/scripts"))

from lib.kb.storage import load_kb_json, save_kb_json  # noqa: E402

SRC = REPO / ".github/data/model-info"
tmp = Path(tempfile.mkdtemp(prefix="ysm_diag_"))
# 复制 character 到临时目录（kb_path 指向 tmp 目录）
dst_kb = tmp / "model-info"
shutil.copytree(SRC, dst_kb)

data = load_kb_json(dst_kb)
before = len(data.get("roles") or [])
print(f"加载角色数: {before}")

# 1) 添加一个测试角色
data.setdefault("roles", []).append(
    {"work": "OC", "zh": ["诊断临时角色"], "en": ["diag-temp-role"]})
save_kb_json(dst_kb, data)

data2 = load_kb_json(dst_kb)
after = len(data2.get("roles") or [])
found = [r for r in data2.get("roles") or []
         if "诊断临时角色" in (r.get("zh") or [])]
print(f"添加后角色数: {after}（+{after - before}）")
print(f"新角色可读回: {bool(found)} | {found[:1]}")

# 2) 删除测试角色
data3 = load_kb_json(dst_kb)
data3["roles"] = [r for r in data3.get("roles") or []
                  if "诊断临时角色" not in (r.get("zh") or [])]
save_kb_json(dst_kb, data3)
data4 = load_kb_json(dst_kb)
left = [r for r in data4.get("roles") or []
        if "诊断临时角色" in (r.get("zh") or [])]
print(f"删除后残留: {len(left)} | 角色总数: {len(data4.get('roles') or [])}")

# 3) 检查 OC.json 是否每角色一行（序列化格式）
oc = (dst_kb / "character" / "OC.json").read_text(encoding="utf-8")
print("OC.json roles 分行:", "\n    {" in oc)

shutil.rmtree(tmp, ignore_errors=True)
print("临时目录已清理")
