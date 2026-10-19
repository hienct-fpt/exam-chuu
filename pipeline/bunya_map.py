"""Map every source's own topic tags (pipeline/tags/*.json) onto one shared, medium-grained 分野 taxonomy per
subject, so practice sets / weak-topic detection / the dashboard pool 四谷大塚 組み分け items together with the
school past papers (kyoritsu / shinagawa / chuo / sakaehigashi) and min-san.

build.py writes the shared 分野 as the item's `topic` and keeps the original label as `topic_detail`.

算数: みんなの算数オンライン (min-san)'s fixed 12 leaf 分野 (pipeline/minsan.py CATS), so min-san items (already
  tagged with these) join the same pool:
    文章題 : 和と差, 割合と比, 数の性質, 速さ, 規則性, 場合の数, 論理・推理
    図形   : 平面図形, 立体図形
    計算   : 計算, 逆算, 単位換算
  School labels were grounded via min-san's own tag->topic majority (pipeline/out/minsan/items.json); a few with
  no min-san precedent are a domain-knowledge best guess (marked). 組み分け 領域 (正答率一覧) map 1:1.
理科: 15 単元-level 分野 (力・てこ・ばね … 実験・観察・資料).
社会: 地理 8 / 歴史 6 / 公民 4 + 時事.
国語: 漢字 / 語句・文法 / 読解 / 記述 / 作文. The school tags can't tell 物語 from 説明文 (kyoritsu tags
  whole passages as 読解) nor 語句 from 文法 (kyoritsu "語句・文法"), so those stay merged to keep one pool.

"文章題" (算数 fallback label on a few 大問 whose items carry their own tags) is intentionally unmapped (None):
it is not a 分野, and bunya_for() callers fall back to the original label.
"""
from __future__ import annotations

# --- 算数 -------------------------------------------------------------------------------------------------
BUNYA_MAP: dict[str, str | None] = {
    # direct 1:1 with a min-san leaf category
    "数の性質": "数の性質",
    "計算": "計算",
    "規則性": "規則性",
    "場合の数": "場合の数",
    "割合と比": "割合と比",
    "速さ": "速さ",
    "論理・推理": "論理・推理",
    "単位換算": "単位換算",
    "立体図形": "立体図形",
    "逆算": "逆算",
    # 四谷大塚 組み分け 領域 (結果.pdf 正答率一覧)
    "数に関する問題": "数の性質",
    "和や差の問題": "和と差",
    "割合や比の問題": "割合と比",
    "速さの問題": "速さ",
    "規則性の問題": "規則性",
    "場合の数の問題": "場合の数",
    "調べる問題": "論理・推理",
    "平面図形の問題": "平面図形",
    "立体図形の問題": "立体図形",
    # grounded via min-san's own tag->topic majority (see docstring)
    "割合・食塩水": "割合と比",
    "平均": "和と差",
    "文章題-平均": "和と差",
    "仕事算": "割合と比",
    "売買損益": "割合と比",
    "流水算": "速さ",
    "速さ・旅人算": "速さ",
    "速さと比": "速さ",
    "速さとグラフ": "速さ",
    "通過算": "速さ",
    "時計算": "速さ",
    "植木算": "規則性",
    "文章題-植木算": "規則性",
    "暦・周期": "規則性",
    "虫食い算": "論理・推理",
    "集合": "和と差",
    "文章題-集合": "和と差",
    "つるかめ算": "和と差",
    "過不足算": "和と差",
    "文章題-消去算": "和と差",
    "和差算・分配": "和と差",
    "ニュートン算": "割合と比",
    "比例・ばね": "割合と比",
    "約束記号": "逆算",
    "計算-部分分数": "計算",
    "平面図形-面積": "平面図形",
    "平面図形-相似・比": "平面図形",
    "平面図形-角度": "平面図形",
    "平面図形-円周": "平面図形",
    "平面図形-長さ": "平面図形",
    "角度": "平面図形",
    "図形の移動": "平面図形",
    "図形の移動・回転": "平面図形",
    "縮尺・面積": "平面図形",
    "立体の体積": "立体図形",
    "立体図形-回転体": "立体図形",
    "立体-展開図": "立体図形",
    "立体-切断": "立体図形",
    # no min-san precedent found for the exact concept -> best domain-knowledge guess
    "点の移動とグラフ": "平面図形",
    "水量変化とグラフ": "立体図形",  # 水そう(立体)の水位グラフ, distinct from the simple L/mL "単位換算" tag
    "立体-水量": "立体図形",
    "位置・方角": "平面図形",
    "概数": "数の性質",
    # intentionally unmapped: generic fallback label, not a min-san leaf category
    "文章題": None,
}

# --- 理科 -------------------------------------------------------------------------------------------------
FORCE, MOTION, LIGHT, ELEC, HEAT = "力・てこ・ばね", "運動・ふりこ", "光・音", "電気・磁石", "熱・状態変化"
SOLN, GAS = "水溶液・溶解度", "気体・燃焼"
PLANT, BODY, ECO = "植物", "動物・人体", "生物と環境"
SKY, WEATHER, EARTH = "天体", "気象", "大地・地層"
LAB, MIXED = "実験・観察・資料", "総合"

SCIENCE_MAP: dict[str, str] = {
    # 組み分け
    "支点が端にあるてこ": FORCE, "重さのある太さが一様なてこ": FORCE, "重さのある太さが一様でないてこ": FORCE,
    "棒の重さと重心": FORCE, "滑車": FORCE, "輪軸": FORCE,
    "ふり子の運動": MOTION, "斜面での球の運動": MOTION, "運動の速さと向き": MOTION, "等速直線運動と速さの計算": MOTION,
    "熱の移動と温度変化": HEAT, "水や空気のあたたまり方": HEAT, "金属のあたたまり方とぼう張、収縮": HEAT,
    "水のすがたの変化": HEAT, "物の３つのすがた": HEAT,
    "よう解度": SOLN, "水よう液のこさ": SOLN, "水溶液の中和": SOLN, "中和の計算": SOLN,
    "液性による水溶液の分類": SOLN, "電解質と非電解質": SOLN,
    "いろいろな気体": GAS, "酸素の発生と性質": GAS, "二酸化炭素の発生と性質": GAS,
    "いろいろな花": PLANT, "花のつくり": PLANT, "花のはたらき": PLANT, "くきのつくりとはたらき": PLANT,
    "葉のつくりとはたらき": PLANT, "光合成": PLANT, "光合成と呼吸": PLANT, "双子葉類と単子葉類": PLANT,
    "植物の成長と日光": PLANT, "季節と植物": PLANT,
    "消化と消化器官": BODY, "栄養素とそのはたらき": BODY, "季節とこん虫": BODY, "季節と動物": BODY,
    "自然界のつり合い": ECO,
    "星座": SKY, "星座早見": SKY, "星の運動": SKY, "月の満ち欠け": SKY, "月の出入りと動き": SKY,
    "月といろいろな現象": SKY, "地球のようす": SKY, "地球上の位置": SKY,
    "季節と天気": WEATHER, "気団と前線": WEATHER, "気温と地温": WEATHER, "大地のあたたまり方": WEATHER,
    "しつ度": WEATHER, "雲、雨": WEATHER, "風向、風速、風力": WEATHER,
    "地球の歴史": EARTH,
    # 学校
    "物理-てこ": FORCE, "物理-てこ・はかり": FORCE, "物理-ばね・滑車": FORCE, "物理-かっ車・輪じく": FORCE,
    "物理-浮力": FORCE, "実験操作・ばね": FORCE,
    "物理-ふりこ": MOTION, "物理-慣性力": MOTION,
    "物理-光": LIGHT, "物理-光とレンズ": LIGHT, "物理-音": LIGHT, "物理-波の性質": LIGHT,
    "物理-磁石": ELEC, "物理-電気回路": ELEC, "物理-電流・回路": ELEC, "物理-電流と発熱": ELEC,
    "物理-電流と豆電球": ELEC,
    "物理-熱と膨張": HEAT, "化学-状態変化": HEAT, "実験操作・温度グラフ": HEAT, "実験操作・状態変化グラフ": HEAT,
    "化学-水溶液": SOLN, "化学-水溶液(食塩水・ろ過)": SOLN, "化学-溶解度": SOLN, "化学-中和": SOLN,
    "化学-酸とアルカリ": SOLN, "化学-水和物": SOLN,
    "化学-気体の性質": GAS, "化学-気体の発生": GAS, "化学-気体発生計算": GAS, "実験操作・気体発生グラフ": GAS,
    "化学-燃焼(ロウソク)": GAS, "化学-酸化(鉄・カイロ)": GAS, "化学-物質の成り立ち・原子": GAS,
    "生物-植物": PLANT, "生物-植物(発芽)": PLANT, "生物-植物(花芽・光周性)": PLANT, "生物-植物・森林": PLANT,
    "生物-人体": BODY, "生物-人体(消化)": BODY, "生物-人体(発生)": BODY, "生物-体温調節": BODY,
    "生物-呼吸": BODY, "生物-呼吸・循環": BODY, "生物-メダカ": BODY, "生物-昆虫": BODY, "生物-生殖": BODY,
    "生物-環境・生態": ECO, "生物-生態(なわばり)": ECO, "生物-生態系・食物連鎖": ECO, "生物-外来種": ECO,
    "生物-植物と環境(火山島)": ECO,
    "地学-天体": SKY, "地学-天体(冬の星座)": SKY, "地学-天体(太陽・月・星の動き)": SKY, "地学-天体(星座)": SKY,
    "地学-天体(月食)": SKY, "地学-天体(金星)": SKY, "地学-太陽の動き": SKY, "地学-星の動き": SKY,
    "地学-月の満ち欠け": SKY, "地学-月の見え方": SKY,
    "地学-気象": WEATHER,
    "地学-地層": EARTH, "地学-地層・化石": EARTH, "地学-地震": EARTH, "地学-流れる水": EARTH,
    "実験操作-けんび鏡": LAB, "実験操作・顕微鏡": LAB, "実験計画": LAB, "資料の読み取り": LAB,
    "総合-ばね・てこ・小問": MIXED, "総合-光の性質・植物のはたらき": MIXED, "総合-実験器具・火山": MIXED,
    "総合-気象・水溶液の濃度": MIXED, "総合-状態変化・侵食": MIXED,
}

# --- 社会 -------------------------------------------------------------------------------------------------
LAND, AGRI, IND, TRADE = "地理-国土・地形・地図", "地理-農林水産業", "地理-工業・資源・エネルギー", "地理-貿易・交通・情報"
POP, REGION, WORLD, STATS = "地理-人口・都市", "地理-日本の各地方", "地理-世界・環境問題", "資料読み取り・記述"
ANCIENT, MEDIEVAL, EARLYMOD = "歴史-原始・古代", "歴史-中世", "歴史-近世"
MODERN, CONTEMP, THEME = "歴史-近代", "歴史-現代", "歴史-テーマ史"
CONST, POLITICS, ECON, INTL, NEWS = "公民-憲法・人権", "公民-政治のしくみ", "公民-経済・財政", "公民-国際", "時事問題"

SOCIAL_MAP: dict[str, str] = {
    # 組み分け
    "日本の位置と面積": LAND, "地図の高さと縮尺": LAND, "方位と地図記号": LAND,
    "漁業の種類と漁法": AGRI, "日本の水産業とおもな漁港": AGRI, "水産業の今とこれから": AGRI,
    "日本の工業の特色": IND, "日本の工業地帯": IND, "日本の工業地域": IND, "日本の重化学工業": IND,
    "日本の軽工業": IND, "日本の伝統工業": IND, "日本の地下資源": IND, "日本の電力": IND,
    "日本の輸入と輸出": TRADE, "日本のおもな貿易港": TRADE, "貿易で使われるお金": TRADE,
    "国内とのつながり": TRADE, "海外とのつながり": TRADE, "情報化社会": TRADE,
    "日本の人口とその問題点": POP, "日本のおもな都市": POP,
    **{f"{r}地方の{k}": REGION for r in ("北海道", "東北", "関東", "中部", "近畿", "中国、四国", "九州")
       for k in ("自然", "産業", "特色")},
    "世界のすがた": WORLD, "地球の環境問題": WORLD, "環境問題への取り組み": WORLD,
    "統計の読みとり": STATS,
    "縄文時代": ANCIENT, "弥生時代": ANCIENT,
    **{f"{era}の{k}": ANCIENT for era in ("古墳、飛鳥時代", "奈良時代", "平安時代") for k in ("政治", "外交", "文化")},
    # 学校
    "地理-日本(地図)": LAND, "地理-地形": LAND, "地理-地形と自然・世界の山": LAND, "地理-海と島・日本の国土": LAND,
    "地理-農業": AGRI, "地理-畜産": AGRI, "地理-産業(畜産)": AGRI, "地理-水産業": AGRI, "地理-農産物と都道府県": AGRI,
    "地理-工業": IND, "地理-伝統工業": IND, "地理-伝統産業": IND, "地理-資源・エネルギー": IND,
    "地理-貿易": TRADE, "地理-交通": TRADE,
    "地理-人口": POP, "地理-総合(村落・都市)": POP,
    "地理-日本": REGION, "地理-日本(中部)": REGION, "地理-日本(北海道)": REGION, "地理-日本(山梨)": REGION,
    "地理-日本(熊本)": REGION, "地理-地名と各地の産業": REGION, "地理-地域文化": REGION,
    "地理-観光と産業": REGION, "地理-総合(自然・産業)": REGION,
    "地理・歴史(九州)": REGION, "地理・歴史(千葉)": REGION,
    "地理-世界": WORLD, "地理-時差": WORLD,
    "地理-統計": STATS,
    "歴史-古代": ANCIENT,
    "歴史-中世": MEDIEVAL, "歴史-中世~近世(武士)": MEDIEVAL,
    "歴史-近世": EARLYMOD, "歴史-近世・時事": EARLYMOD,
    "歴史-近代": MODERN, "歴史-近現代": MODERN, "歴史・公民(近現代)": MODERN,
    "歴史-現代": CONTEMP,
    "歴史-通史": THEME, "歴史-通史(京都)": THEME, "歴史-通史(曜日と歴史)": THEME, "歴史-通史(菓子と食文化)": THEME,
    "歴史-総合": THEME, "歴史-総合(子どもと歴史)": THEME, "歴史-外国との交流(通史)": THEME,
    "歴史-技術と交流(通史)": THEME, "歴史-服装の歴史(通史)": THEME,
    "公民-憲法": CONST, "公民-人権": CONST, "公民-基本的人権・法律": CONST, "公民-憲法と労働": CONST,
    "公民-憲法・政治のしくみ": CONST,
    "公民-政治": POLITICS, "公民-政治(三権分立)": POLITICS, "公民-政治(多数決)": POLITICS,
    "公民-国会・内閣": POLITICS, "公民-選挙": POLITICS, "公民-選挙・地方自治": POLITICS,
    "公民-選挙・国際": POLITICS, "公民-地方自治": POLITICS, "公民-法律・行政": POLITICS,
    "公民-物価と経済": ECON, "公民-財政・税": ECON, "公民-働き方と社会保障": ECON,
    "公民-国際": INTL, "公民-国際連合・国際情勢": INTL,
    "公民-時事": NEWS, "時事問題": NEWS,
}

# --- 国語 -------------------------------------------------------------------------------------------------
KANJI, GOKU, READ, WRITE, ESSAY = "漢字", "語句・文法", "読解", "記述", "作文"

JAPANESE_MAP: dict[str, str] = {
    # 組み分け
    "漢字の書き取り": KANJI,
    "単語の学習": GOKU, "三字の熟語": GOKU, "四字の熟語": GOKU, "同訓異字": GOKU, "同音異義語": GOKU,
    "和語": GOKU, "対義語": GOKU, "類義語": GOKU, "慣用句": GOKU, "ことわざ": GOKU, "敬語": GOKU, "手紙文": GOKU,
    "人物の気持ち": READ, "人物の性格": READ, "場面": READ, "文脈": READ, "段落": READ, "理由": READ,
    "経験と感想": READ, "表現": READ, "要旨": READ, "話題と要点": READ, "意見と根拠": READ,
    "指示語": READ, "接続語": READ,  # asked inside the 読解 大問, not as 文法 drills
    "記述問題": WRITE,
    # 学校
    "漢字": KANJI, "漢字・語彙": KANJI,
    "語句・文法": GOKU, "語句・選択": GOKU,
    "読解": READ, "小説": READ, "論説文": READ, "選択": READ,  # chuo: 選択肢 questions on the 読解 passages
    "記述": WRITE,
    "作文": ESSAY,
}

MAPS: dict[str, dict[str, str | None]] = {
    "math": BUNYA_MAP, "science": SCIENCE_MAP, "social": SOCIAL_MAP, "japanese": JAPANESE_MAP,
}


def bunya_for(topic: str | None, subject: str = "math") -> str | None:
    """Shared 分野 for a source's own topic tag, or None if unmapped/untagged."""
    if not topic:
        return None
    return MAPS.get(subject, {}).get(topic)


def unified_topic(topic: str | None, subject: str) -> str | None:
    """Topic used for practice / analytics: the shared 分野, falling back to the original label."""
    return bunya_for(topic, subject) or topic
