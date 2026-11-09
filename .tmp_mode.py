
import os, sys
sys.path.insert(0, r"E:\novel-studio")
from studio import reverse

OLD = "---\n類型: 名詞表\n更新至: 第001章\n---\n\n# 名詞表\n\n| 名詞 | 類別 | 說明 | 注意 |\n|---|---|---|---|\n"
NEW = OLD + "| 周遠 | 人名 | 維修技師 | |\n| 晨星號 | 船艦 | 補給船 | |\n"
print("canon:", reverse._canon_rel("設定", "設定/名詞表.md"))
print("mode(default):", reverse._mode_for("設定", "設定/名詞表.md"))
print("mode(merge asked):", reverse._mode_for("設定", "設定/名詞表.md", "merge"))
print("mode(keep asked):", reverse._mode_for("設定", "設定/名詞表.md", "keep"))
print("char mode(default):", reverse._mode_for("設定", "設定/角色/周遠.md"))
