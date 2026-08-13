"""仓库与数据路径的统一定位；.github/data 按语义目录组织（与脚本解耦）。

数据目录规范（脚本不得按自身名字建子目录）：
  templates/  网站/README 等模板文件
  knowledge/  命名知识库（works.json / aliases.json / roles/）
  meta/       各脚本共享的元数据（models_meta.json / platform_map.json 等）
  schemas/    数据契约（JSON Schema，由 lib/validate.py 校验）
"""
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent  # .github/scripts


def find_workspace_root() -> Path:
    """智能定位仓库根目录：优先 cwd 含 Models/，再回退到脚本位置推断。"""
    cwd = Path.cwd()
    if (cwd / 'Models').is_dir():
        return cwd
    if SCRIPT_DIR.name == 'scripts' and SCRIPT_DIR.parent.name == '.github':
        candidate = SCRIPT_DIR.parents[1]
        if (candidate / 'Models').is_dir():
            return candidate
    return cwd


WORKSPACE_ROOT = find_workspace_root()
DATA_DIR = WORKSPACE_ROOT / '.github' / 'data'
TEMPLATES_DIR = DATA_DIR / 'templates'
KNOWLEDGE_DIR = DATA_DIR / 'knowledge'
META_DIR = DATA_DIR / 'meta'
SCHEMAS_DIR = DATA_DIR / 'schemas'

# 语义目录名 -> 实际路径
_CATEGORY_DIRS = {
    'templates': TEMPLATES_DIR,
    'knowledge': KNOWLEDGE_DIR,
    'meta': META_DIR,
    'schemas': SCHEMAS_DIR,
}


def data_path(category: str, *parts: str) -> Path:
    """返回语义目录下的数据路径，如 data_path('meta', 'models_meta.json')。"""
    return _CATEGORY_DIRS[category].joinpath(*parts)


def get_safe_relpath(path: Path) -> str:
    """安全获取相对路径，若不在根目录下则返回原路径。"""
    try:
        return str(path.relative_to(WORKSPACE_ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path, default=None):
    """读取 JSON；文件缺失或损坏时返回 default。"""
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    """写 JSON（UTF-8、ensure_ascii=False、末尾换行），自动创建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_text_utf8(path: Path) -> str:
    """读取文本，忽略解码错误；IO 失败返回空串。"""
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return ''
