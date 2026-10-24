#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小說正文檢查工具（台灣繁體中文）

檢查項目：
  1. 簡體字                      → 必須修
  2. 標點（西式引號、半形標點、刪節號、破折號） → 必須修（可用 --fix-punct 自動修）
  3. 中國大陸用語                 → 建議修／提醒
  4. 工程詞外洩（第X章、伏筆、章綱……） → 建議修
  5. AI 味信號（套詞、句式、章尾預告）   → 提醒；同一章堆疊過多時升為建議修
  6. 字數統計

用法：
  python3 check_text.py 正文/第001章_退婚.md
  python3 check_text.py 正文/                     # 檢查整個資料夾
  python3 check_text.py 正文/第001章_退婚.md --fix-punct   # 自動修正標點
  python3 check_text.py 正文/第001章_退婚.md --json
  python3 check_text.py 正文/第001章_退婚.md --count       # 只算字數

白名單：
  書目錄（正文/ 的上一層）放一個 `.去AI味白名單` 檔，一行一個原文片段，
  `#` 開頭為註解。含有白名單片段的行，跳過用語與 AI 味檢查（簡體字與標點照查）。

只用 Python 標準函式庫，Python 3.8 以上。
結束代碼：0 = 沒有必須修的問題；1 = 有必須修的問題；2 = 參數或檔案錯誤。
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# 簡體專用字（由 OpenCC STCharacters 字典產生：轉繁後候選字不包含自己、且不在 Big5 字集中的字）
# ---------------------------------------------------------------------------
SIMPLIFIED_ONLY = set("㐷㐽㑇㑈㑔㑩㓆㓥㓰㔉㖊㖞㘎㚯㛀㛟㛠㛣㛤㛿㟆㟜㟥㡎㤘㤽㥪㧏㧐㧑㧟㧰㨫㭎㭏㭣㭤㭴㱩㱮㲿㳔㳕㳠㳡㳢㳽㴋㶉㶶㶽㺍㻅㻏㻘䀥䁖䂵䃅䅉䅟䅪䇲䉤䌶䌷䌸䌹䌺䌻䌼䌽䌾䌿䍀䍁䍠䎬䏝䑽䓓䓕䓖䓨䗖䘛䘞䙊䙌䙓䜣䜤䜥䜧䜩䝙䞌䞍䞎䞐䟢䢀䢁䢂䥺䥽䥾䥿䦀䦁䦂䦃䦅䦆䦶䦷䩄䭪䯃䯄䯅䲝䲞䲟䲠䲡䲢䲣䴓䴔䴕䴖䴗䴘䴙䶮专业丛东丝丢两严丧个临为丽举义乌乐乔习乡书买乱争亏亚产亩亲亵亸亿仅从仑仓仪们众会伛伞伟传伡伣伤伥伦伧伪伫佥侠侣侥侦侧侨侩侪侬侭俣俦俨俩俪俫俭债倾偬偻偾偿傤傥傧储傩兑兖兰关兴兹养兽冁内冈册写军农冯冲决况冻净凉减凑凛凤凫凭凯击凿刍刘则刚创删别刬刭刹刽刾刿剀剂剐剑剥剧劝办务劢动励劲劳势勋勚匀匦匮区医华协单卖卢卤卧卫却卺厅历厉压厌厍厐厕厢厣厦厨厩厮县叁参叆叇双发变叙叠号叹叽吓吕吗启吴呐呒呓呕呖呗员呙呛呜咏咙咛咝咤响哑哒哓哔哕哗哙哜哝哟唛唝唠唡唢唤啧啬啭啮啯啰啴啸喷喽喾嗫嗳嘘嘤嘱噜嚣团园囱围囵国图圆圹场块坚坛坜坝坞坟坠垄垅垆垒垦垩垫垭垯垱垲垴埘埙埚堑堕塆墙壮声壳壶壸处备够头夹夺奁奂奋奖奥妆妇妈妩妪妫姗姹娄娅娆娇娈娱娲娴婳婴婵婶媪媭嫒嫔嫱嬷孙学孪宝实宠审宪宫宽宾寝对寻导寿将尔尘尝尧尴尽层屃屉届属屡屦屿岁岂岖岗岘岚岛岽岿峃峄峡峣峤峥峦崂崃崄崭嵘嵚嵝巅巩巯币帅师帏帐帜带帧帮帱帻帼幂庆庐庑库应庙庞废庼廪开弃弑张弥弪弯弹强归当录彟彦彨彻径徕忆忧忾态怂怃怄怅怆总怼怿恋恳恶恸恹恺恻恼恽悦悫悬悭悮悯惧惨惩惫惬惭惮惯愠愤愦慑慭懑懒懔戆戋戏戗战戬戯户执扩扪扫扬抚抛抟抠抡抢护报担拟拢拣拥拦拧拨择挚挛挜挝挞挟挠挡挢挣挤挥挦捝捞损捡换捣掳掴掷掸掺掼揽揾揿搀搁搂搄搅携摄摅摆摇摈摊撄撑撵撷撸撺擜擞攒敌敚敛敩数斋斓斩断无旧时旷旸昙昼昽显晋晓晔晕晖暂暅暧术杀杂权条来杨杩枞枢枣枥枧枨枪枫枭柠柽栀栅标栈栉栊栋栌栎栏树样栾桠桡桢档桤桥桦桧桨桩桪梦梼梾梿检棁棂椁椝椟椠椢椤椫椭椮楼榄榅榇榈榉榝槚槛槟槠横樯樱橥橱橹橼檩欢欤欧歼殁殇残殒殓殚殡殴毁毂毕毙毡毵毶氇氢氩氲汇汉汤汹沟没沣沤沥沦沧沨沩沪泪泶泷泸泺泻泼泽泾浃浅浆浇浈浉浊测浍济浏浐浑浒浓浔浕涚涛涝涞涟涠涡涢涣涤润涧涨涩渊渌渍渎渐渑渔渖渗温湾湿溁溃溅溆溇滗滚滞滟滠满滢滤滥滦滨滩滪潆潇潋潍潜潴澛澜濑濒灏灭灯灵灾灿炀炉炜炝点炼炽烁烂烃烛烟烦烧烨烩烫烬热焕焖焘煴爱爷牍牦牵牺犊状犷犸犹狈狝狞独狭狮狯狰狱狲猃猎猕猡猪猫猬献獭玑玙玚玛玮环现玱玺珐珑珰珲琎琏琐琼瑶瑷瑸璎瓒瓯电画畅畴疖疗疟疠疡疬疭疮疯疱疴痈痉痖痨痪痫瘅瘆瘗瘘瘪瘫瘾瘿癞癣癫皑皱皲盏盐监盖盗盘眍眦眬睁睐睑瞆瞒瞩矫矶矾矿砀码砖砗砚砜砺砻砾础硁硕硖硗硙硚硵硷碍碛碜碱礼祃祎祢祯祷祸禀禄禅秃秆积称秽秾稆税稣稳穑穞穷窃窍窎窑窜窝窥窦窭竖竞笃笋笔笕笺笼笾筚筛筜筝筹筼签筿简箓箦箧箨箩箪箫篑篓篮篯簖籁籴类籼粜粝粤粪粮糁糇糍紧絷緼縆纟纠纡红纣纤纥约级纨纩纪纫纬纭纮纯纰纱纲纳纴纵纶纷纸纹纺纻纼纽纾线绀绁绂练组绅细织终绉绊绋绌绍绎经绐绑绒结绔绕绖绗绘给绚绛络绝绞统绠绡绢绣绤绥绦继绨绩绪绫绬续绮绯绰绱绲绳维绵绶绷绸绹绺绻综绽绾绿缀缁缂缃缄缅缆缇缈缉缊缋缌缍缎缏缐缑缒缓缔缕编缗缘缙缚缛缜缝缞缟缠缡缢缣缤缥缦缧缨缩缪缫缬缭缮缯缰缱缲缳缴缵罂罗罚罢罴羁羟翘翙翚耢耧耸耻聂聋职聍联聩聪肃肠肤肾肿胀胁胆胧胨胪胫胶脉脍脏脐脑脓脔脚脱脶脸腘腭腻腼腽腾膑臜舆舣舰舱舻艰艳艺节芈芗芜芦苁苇苈苋苌苍苎苏茎茏茑茔茕荆荙荚荛荜荝荞荟荠荡荣荤荥荦荧荨荩荪荫荬荭荮药莅莱莲莳莴莶获莸莹莺莼萚萝萤营萦萧萨葱蒀蒇蒉蒋蒌蓝蓟蓠蓣蓥蓦蔷蔹蔺蔼蕰蕲蕴薮藓藴蘖虏虑虚虬虽虾虿蚀蚁蚂蚃蚬蛊蛎蛏蛮蛰蛱蛲蛳蛴蜕蜗蝇蝈蝉蝼蝾螀螨蟏衅衔补衬衮袄袅袆袜袭袯装裆裈裢裣裤裥褛褴襕见观觃规觅视觇览觉觊觋觌觍觎觏觐觑觞觯訚詟誉誊讠计订讣认讥讦讧讨让讪讫讬训议讯记讱讲讳讴讵讶讷许讹论讻讼讽设访诀证诂诃评诅识诇诈诉诊诋诌词诎诏诐译诒诓诔试诖诗诘诙诚诛诜话诞诟诠诡询诣诤该详诧诨诩诪诫诬语诮误诰诱诲诳说诵诶请诸诹诺读诼诽课诿谀谁谂调谄谅谆谇谈谉谊谋谌谍谎谏谐谑谒谓谔谕谖谗谘谙谚谛谜谝谞谟谠谡谢谣谤谥谦谧谨谩谪谫谬谭谮谯谰谱谲谳谴谵谶豮贝贞负贠贡财责贤败账货质贩贪贫贬购贮贯贰贱贲贳贴贵贶贷贸费贺贻贼贽贾贿赀赁赂赃资赅赆赇赈赉赊赋赌赍赎赏赐赑赒赓赔赕赖赗赘赙赚赛赜赝赞赟赠赡赢赣赪赵趋趱趸跃跄跞践跶跷跸跹跻踌踪踬踯蹑蹒蹰蹿躏躜躯輼车轧轨轩轪轫转轭轮软轰轱轲轳轴轵轶轷轸轹轺轻轼载轾轿辀辁辂较辄辅辆辇辈辉辊辋辌辍辎辏辐辑辒输辔辕辖辗辘辙辚辞辩辫边辽达迁过迈运还这进远违连迟迩迳迹选逊递逦逻遗遥邓邝邬邮邹邺邻郏郐郑郓郦郧郸酂酝酦酱酽酾酿醖释鉴銮錾钅钆钇针钉钊钋钌钍钎钏钐钑钒钓钔钕钖钗钘钙钚钛钜钝钞钟钠钡钢钣钤钥钦钧钨钩钪钫钬钭钮钯钰钱钲钳钴钵钶钷钸钹钺钻钼钽钾钿铀铁铂铃铄铅铆铇铈铉铊铋铌铍铎铏铐铑铒铓铔铕铖铗铘铙铚铛铜铝铞铟铠铡铢铣铤铥铦铧铨铩铪铫铬铭铮铯铰铱铲铳铴铵银铷铸铹铺铻铼铽链铿销锁锂锃锄锅锆锇锈锉锊锋锌锍锎锏锐锑锒锓锔锕锖锗锘错锚锛锜锝锞锟锠锡锢锣锤锥锦锧锨锩锪锫锬锭键锯锰锱锲锳锴锵锶锷锸锹锺锻锼锽锾锿镀镁镂镃镄镅镆镇镈镉镊镋镌镍镎镏镐镑镒镓镔镕镖镗镘镙镚镛镜镝镞镟镠镡镢镣镤镥镦镧镨镩镪镫镬镭镮镯镰镱镲镳镴镵镶长门闩闪闫闬闭问闯闰闱闲闳间闵闶闷闸闹闺闻闼闽闾闿阀阁阂阃阄阅阆阇阈阉阊阋阌阍阎阏阐阑阒阓阔阕阖阗阘阙阚阛队阳阴阵阶际陆陇陈陉陕陦陧陨险随隐隶隽难雏雠雳雾霁霡霭靓靔静靥鞑鞒鞯鞲韦韧韨韩韪韫韬韵页顶顷顸项顺须顼顽顾顿颀颁颂颃预颅领颇颈颉颊颋颌颍颎颏颐频颒颓颔颕颖颗题颙颚颛颜额颞颟颠颡颢颣颤颥颦颧风飏飐飑飒飓飔飕飖飗飘飙飚飞飨餍饣饤饥饦饧饨饩饪饫饬饭饮饯饰饱饲饳饴饵饶饷饸饹饺饻饼饽饾饿馀馁馂馃馄馅馆馇馈馉馊馋馌馍馎馏馐馑馒馓馔馕马驭驮驯驰驱驲驳驴驵驶驷驸驹驺驻驼驽驾驿骀骁骂骃骄骅骆骇骈骉骊骋验骍骎骏骐骑骒骓骔骕骖骗骘骙骚骛骜骝骞骟骠骡骢骣骤骥骦骧髅髋髌鬓鬶魇魉鱼鱽鱾鱿鲀鲁鲂鲃鲄鲅鲆鲇鲈鲉鲊鲋鲌鲍鲎鲏鲐鲑鲒鲓鲔鲕鲖鲗鲘鲙鲚鲛鲜鲝鲞鲟鲠鲡鲢鲣鲤鲥鲦鲧鲨鲩鲪鲫鲬鲭鲮鲯鲰鲱鲲鲳鲴鲵鲶鲷鲸鲹鲺鲻鲼鲽鲾鲿鳀鳁鳂鳃鳄鳅鳆鳇鳈鳉鳊鳋鳌鳍鳎鳏鳐鳑鳒鳓鳔鳕鳖鳗鳘鳙鳚鳛鳜鳝鳞鳟鳠鳡鳢鳣鳤鸟鸠鸡鸢鸣鸤鸥鸦鸧鸨鸩鸪鸫鸬鸭鸮鸯鸰鸱鸲鸳鸴鸵鸶鸷鸸鸹鸺鸻鸼鸽鸾鸿鹀鹁鹂鹃鹄鹅鹆鹇鹈鹉鹊鹋鹌鹍鹎鹏鹐鹑鹒鹓鹔鹕鹖鹗鹘鹙鹚鹛鹜鹝鹞鹟鹠鹡鹢鹣鹤鹥鹦鹧鹨鹩鹪鹫鹬鹭鹮鹯鹰鹱鹲鹳鹴鹾麦麸麹麺麽黄黉黡黩黪黾鼋鼌鼍鼹齐齑齿龀龁龂龃龄龅龆龇龈龉龊龋龌龙龚龛龟鿎鿏鿒鿔与么优体儿吨听圣坏复宁岭并庄异忏怀怜惊扑扰晒机构气洁洒洼灶痒离篱网肮茧蚕触赶昵羡泞")

# 一簡對多繁的常見誤字：(正規表示式, 建議, 等級)
SUSPECT_CHARS = [
    (r"着", "著（「着」多為簡體或轉換殘留）", "必須修"),
    (r"(?:由|至|對|關|等|屬|終|基|處|過|善|敢|急|免|甘|勇|樂|位)于|于是", "於", "必須修"),
    (r"[這那哪家屋心手眼城村夜夢店房院懷嘴腦肚骨子]里", "裡（指內部時）", "必須修"),
    (r"(?<![皇太王天影歌母])后(?![羿土妃宮])", "後（皇后、后土等除外）", "提醒"),
    (r"頭发|发現|出发|发生|发展|理发", "發／髮", "必須修"),
    (r"(?<![若干相])干(?:淨|燥|杯|脆|活|嘛)|(?:餅|晒|曬|烘)干", "乾／幹", "必須修"),
]

# ---------------------------------------------------------------------------
# 中國大陸用語：(用語, 建議, 等級)  等級：建議修 / 提醒
# ---------------------------------------------------------------------------
MAINLAND_TERMS = [
    ("視頻", "影片", "建議修"),
    ("屏幕", "螢幕", "建議修"),
    ("質量", "品質（物理學質量除外）", "建議修"),
    ("信息", "訊息／資訊", "建議修"),
    ("網絡", "網路", "建議修"),
    ("軟件", "軟體", "建議修"),
    ("硬件", "硬體", "建議修"),
    ("鼠標", "滑鼠", "建議修"),
    ("打印", "列印", "建議修"),
    ("短信", "簡訊", "建議修"),
    ("激光", "雷射", "建議修"),
    ("博客", "部落格", "建議修"),
    ("點贊", "按讚", "建議修"),
    ("點讚", "按讚", "建議修"),
    ("二維碼", "QR Code", "建議修"),
    ("充電寶", "行動電源", "建議修"),
    ("內存", "記憶體", "建議修"),
    ("默認", "預設", "建議修"),
    ("鏈接", "連結", "建議修"),
    ("代碼", "程式碼", "建議修"),
    ("人工智能", "人工智慧", "建議修"),
    ("智能", "智慧", "建議修"),
    ("出租車", "計程車", "建議修"),
    ("的士", "計程車", "建議修"),
    ("公交車", "公車", "建議修"),
    ("公交", "公車", "建議修"),
    ("自行車", "腳踏車", "建議修"),
    ("航站樓", "航廈", "建議修"),
    ("方便面", "泡麵", "建議修"),
    ("方便麵", "泡麵", "建議修"),
    ("酸奶", "優格／優酪乳", "建議修"),
    ("薯片", "洋芋片", "建議修"),
    ("冰激凌", "冰淇淋", "建議修"),
    ("西紅柿", "番茄", "建議修"),
    ("盒飯", "便當", "建議修"),
    ("快餐", "速食", "建議修"),
    ("外賣", "外送", "建議修"),
    ("塑料", "塑膠", "建議修"),
    ("集裝箱", "貨櫃", "建議修"),
    ("衛生間", "廁所／洗手間", "建議修"),
    ("小區", "社區", "建議修"),
    ("服務員", "服務生", "建議修"),
    ("立馬", "馬上／立刻", "建議修"),
    ("靠譜", "可靠", "建議修"),
    ("給力", "很強／很棒", "建議修"),
    ("忽悠", "唬弄／哄騙", "建議修"),
    ("嘚瑟", "得意／臭屁", "建議修"),
    ("早上好", "早安", "建議修"),
    ("打車", "叫車／搭計程車", "建議修"),
    ("地鐵", "捷運（台灣）；他國城市可用地鐵", "提醒"),
    ("摩托車", "機車", "提醒"),
    ("土豆", "馬鈴薯（台灣的土豆是花生）", "提醒"),
    ("數據", "資料（統計數字可用數據）", "提醒"),
    ("項目", "專案（條列項目可用）", "提醒"),
    ("渠道", "管道", "提醒"),
    ("領導", "主管／長官（動詞可用）", "提醒"),
    ("工資", "薪水", "提醒"),
    ("空調", "冷氣", "提醒"),
    ("哥們", "兄弟", "提醒"),
    ("咋", "怎麼（方言角色可留）", "提醒"),
    ("甭", "不用", "提醒"),
    ("牛逼", "厲害", "提醒"),
    ("水平", "水準（指程度時）", "提醒"),
]

# ---------------------------------------------------------------------------
# AI 味信號：(類別, 正規表示式)
# ---------------------------------------------------------------------------
AI_SIGNALS = [
    ("否定翻轉", r"不是[^，。！？「」\n]{1,15}，(?:而|只|就)?是"),
    ("萬用狀語", r"帶著(?:一絲|一抹|幾分|些許)"),
    ("萬用狀語", r"聲音不大，卻"),
    ("萬用狀語", r"(?:語氣|聲音)(?:平靜無波|毫無波瀾|聽不出情緒)"),
    ("解釋結論", r"(?:終於|這才)(?:明白|意識到|懂了)"),
    ("解釋結論", r"這意味著|之所以[^。]{1,30}是因為|正是因為|由此可見"),
    ("預告昇華", r"命運的(?:齒輪|安排)|殊不知|他不知道的是|她不知道的是|多年以後|冥冥之中"),
    ("預告昇華", r"從這一刻(?:起|開始)|才剛剛開始|注定(?:無人入眠|不平靜)|翻開(?:了)?(?:嶄)?新的一頁"),
    ("意義膨脹", r"意義深遠|前途無量|未來可期|一切都(?:變了|將改變)"),
    ("點破潛台詞", r"恰到好處|恰如其分|誰都看得出"),
    ("告知心理", r"(?:他|她|我)(?:感到|意識到)(?:一陣|一絲|一股)?"),
    ("告知心理", r"散發著一股|顯得有些"),
    ("弱化裝飾", r"微微|淡淡|緩緩|一絲|一抹|些許|微不可察|幾不可聞"),
    ("通用表情", r"嘴角(?:勾起|微揚|上揚|一勾)|眼中閃過|眼底閃過|眉頭微皺|瞳孔(?:一縮|微縮|驟縮|收縮)|指節泛白|深吸一口氣"),
    ("通用心理", r"心頭一(?:震|顫|緊)|心中一(?:動|凜|驚)|心下了然|心中暗道|不由得|湧起一股"),
    ("空泛定性", r"不容置疑|不容置喙|毫無疑問|顯而易見|前所未有|生人勿近"),
    ("萬用比喻", r"(?:彷彿|仿佛|猶如|宛如|宛若)[^。，]{1,20}一般|如潮水般|像潮水一樣|淬了毒|如沐春風"),
    ("自動過渡", r"映入眼簾|此時此刻|不由自主|話鋒一轉|取而代之的是"),
    ("公文腔", r"與此同時|事實上|綜上所述|進一步|從而|基於此"),
    ("對白標記", r"沉聲(?:道|說)|淡淡地(?:說|道)|冷冷地(?:說|道)"),
]

# 同一類別在一章中出現幾次以上，升為「建議修」
CATEGORY_LIMIT = {
    "弱化裝飾": 8, "通用表情": 4, "通用心理": 4, "萬用狀語": 3, "否定翻轉": 3,
    "解釋結論": 3, "告知心理": 5, "萬用比喻": 3, "自動過渡": 3, "公文腔": 3,
    "對白標記": 4, "空泛定性": 3, "點破潛台詞": 2, "意義膨脹": 2, "預告昇華": 2,
}
# 同一字串在一章中重複幾次以上，提醒
PHRASE_REPEAT = 3

ENGINEERING_WORDS = r"第[一二三四五六七八九十百千零〇\d]+章|上一章|下一章|本章|伏筆|章綱|細綱|大綱|讀者"

CJK = r"[㐀-鿿豈-﫿]"
HALF_PUNCT = {",": "，", "?": "？", "!": "！", ":": "：", ";": "；"}


def load_whitelist(book_root):
    items = []
    if not book_root:
        return items
    path = os.path.join(book_root, ".去AI味白名單")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.strip() and not line.lstrip().startswith("#"):
                    items.append(line.strip())
    return items


def guess_book_root(path):
    p = os.path.abspath(path)
    d = p if os.path.isdir(p) else os.path.dirname(p)
    # 正文/ 的上一層
    while True:
        if os.path.basename(d) == "正文":
            return os.path.dirname(d)
        if os.path.isfile(os.path.join(d, "CLAUDE.md")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def strip_frontmatter(lines):
    """回傳 (起始行索引) 讓 YAML frontmatter 不參與檢查。"""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i + 1
    return 0


def count_chars(text):
    body = re.sub(r"^#.*$", "", text, flags=re.M)          # 去標題行
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)     # 去註解
    cjk = len(re.findall(CJK, body))
    no_space = len(re.sub(r"\s", "", body))
    return cjk, no_space


def fix_punct(text):
    n = 0

    def sub(pattern, repl, s, flags=0):
        nonlocal n
        s2, k = re.subn(pattern, repl, s, flags=flags)
        n += k
        return s2

    # 西式引號 → 「」『』
    text = sub("“", "「", text)
    text = sub("”", "」", text)
    text = sub("‘", "『", text)
    text = sub("’", "』", text)
    # 刪節號
    text = sub(r"(?<!…)…(?!…)", "……", text)
    text = sub(r"\.{3,}|。{3,}", "……", text)
    # 破折號：CJK 間單個 — 或 --
    text = sub(r"(?<=" + CJK + r")(?:—|--)(?=" + CJK + r"|「|」)", "——", text)
    # 半形標點緊鄰 CJK
    for h, fwd in HALF_PUNCT.items():
        text = sub(r"(?<=" + CJK + r")" + re.escape(h), fwd, text)
        text = sub(re.escape(h) + r"(?=" + CJK + r")", fwd, text)
    text = sub(r"(?<=" + CJK + r")\.(?=\s|$|" + CJK + r"|」)", "。", text, flags=re.M)
    text = sub(r"(?<=" + CJK + r")\(", "（", text)
    text = sub(r"\((?=" + CJK + r")", "（", text)
    text = sub(r"(?<=" + CJK + r")\)", "）", text)
    return text, n


def check_file(path, whitelist):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    start = strip_frontmatter(lines)
    findings = []
    cat_counter = Counter()
    cat_lines = defaultdict(list)
    phrase_counter = Counter()

    def add(level, kind, lineno, snippet, hint):
        findings.append({"等級": level, "類型": kind, "行": lineno,
                         "片段": snippet, "建議": hint})

    title_seen = False
    for idx in range(start, len(lines)):
        line = lines[idx]
        lineno = idx + 1
        if not line.strip():
            continue
        is_title = line.lstrip().startswith("#")
        whitelisted = any(w in line for w in whitelist)

        # 1. 簡體字
        simp = sorted({c for c in line if c in SIMPLIFIED_ONLY})
        if simp:
            add("必須修", "簡體字", lineno, "".join(simp), "改為繁體（注意一簡對多繁，依意思選字）")
        for pat, tw, level in SUSPECT_CHARS:
            for m in re.finditer(pat, line):
                add(level, "疑似誤字", lineno, m.group(0), "應為：" + tw)

        # 2. 標點
        if re.search("[“”‘’]", line):
            add("必須修", "標點", lineno, "西式引號", "改為「」『』（--fix-punct 可自動修）")
        for m in re.finditer(r"(?:" + CJK + r")[,?!:;]|[,?!:;](?:" + CJK + r")", line):
            add("必須修", "標點", lineno, m.group(0), "中文句子用全形標點（--fix-punct 可自動修）")
            break
        if re.search(r"\.{3,}|。{3,}|(?<!…)…(?!…)", line):
            add("必須修", "標點", lineno, "刪節號", "刪節號用「……」（--fix-punct 可自動修）")
        if re.search(r"(?<=" + CJK + r")(?:—(?!—)|--)", line) and "——" not in line:
            add("必須修", "標點", lineno, "破折號", "破折號用「——」（--fix-punct 可自動修）")

        if is_title:
            title_seen = True
            continue
        if whitelisted:
            continue

        # 3. 大陸用語
        for term, tw, level in MAINLAND_TERMS:
            if term in line:
                add(level, "大陸用語", lineno, term, "台灣用語：" + tw)

        # 4. 工程詞
        for m in re.finditer(ENGINEERING_WORDS, line):
            add("建議修", "工程詞", lineno, m.group(0),
                "正文不應出現寫作用詞；若故事內確實存在（例如角色在讀書）可忽略")

        # 5. AI 味信號
        for cat, pat in AI_SIGNALS:
            for m in re.finditer(pat, line):
                cat_counter[cat] += 1
                cat_lines[cat].append(lineno)
                phrase_counter[m.group(0)] += 1

    # AI 味彙整
    for cat, cnt in cat_counter.items():
        limit = CATEGORY_LIMIT.get(cat, 3)
        level = "建議修" if cnt >= limit else "提醒"
        add(level, "AI味：" + cat, cat_lines[cat][0],
            "共 %d 次，出現在第 %s 行" % (cnt, "、".join(str(x) for x in cat_lines[cat][:10])),
            "回到上下文判斷；同類堆疊時改成具體動作、物件或刪除（參考 ai-signals.md）")
    for phrase, cnt in phrase_counter.items():
        if cnt >= PHRASE_REPEAT and len(phrase) >= 2:
            add("建議修", "重複套詞", 0, "「%s」×%d" % (phrase, cnt), "同一章重複太多次，保留最有力的一處")

    # 章尾：最後一段
    body_lines = [(i + 1, l) for i, l in enumerate(lines[start:], start=start)
                  if l.strip() and not l.lstrip().startswith("#") and not l.strip().startswith("<!--")]
    if body_lines:
        last_no, last = body_lines[-1]
        if re.search(r"命運|注定|從這一刻|才剛剛開始|不知道的是|殊不知|新的一頁|一切都變了|終於明白", last) \
                and not any(w in last for w in whitelist):
            add("建議修", "章尾昇華", last_no, last.strip()[:40],
                "章尾停在具體的畫面、動作或對白上，不寫感悟或預告")

    cjk, no_space = count_chars("\n".join(lines[start:]))
    order = {"必須修": 0, "建議修": 1, "提醒": 2}
    findings.sort(key=lambda x: (order[x["等級"]], x["行"]))
    return {"檔案": path, "中文字數": cjk, "總字數（不含空白）": no_space, "問題": findings}


def collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.endswith((".md", ".txt")):
                    files.append(os.path.join(p, name))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print("找不到：%s" % p, file=sys.stderr)
            sys.exit(2)
    return files


def print_report(res):
    print("=" * 60)
    print("%s" % res["檔案"])
    print("中文字數：%d　總字數（不含空白）：%d" % (res["中文字數"], res["總字數（不含空白）"]))
    if not res["問題"]:
        print("沒有發現問題。")
        return
    groups = defaultdict(list)
    for f in res["問題"]:
        groups[f["等級"]].append(f)
    for level in ("必須修", "建議修", "提醒"):
        if not groups[level]:
            continue
        print("\n【%s】%d 項" % (level, len(groups[level])))
        for f in groups[level]:
            where = ("第 %d 行" % f["行"]) if f["行"] else "全章"
            print("  - %s｜%s｜%s → %s" % (where, f["類型"], f["片段"], f["建議"]))


def main():
    ap = argparse.ArgumentParser(description="小說正文檢查（台灣繁體中文）")
    ap.add_argument("paths", nargs="+", help="章節檔案或資料夾")
    ap.add_argument("--fix-punct", action="store_true", help="自動修正標點（直接改寫檔案）")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--count", action="store_true", help="只輸出字數")
    ap.add_argument("--book-root", help="書目錄（預設自動尋找 正文/ 的上一層）")
    args = ap.parse_args()

    files = collect(args.paths)
    if not files:
        print("沒有可檢查的 .md 或 .txt 檔案", file=sys.stderr)
        sys.exit(2)

    if args.count:
        for p in files:
            with open(p, encoding="utf-8") as f:
                lines = f.read().split("\n")
            cjk, ns = count_chars("\n".join(lines[strip_frontmatter(lines):]))
            print("%s\t中文字數 %d\t總字數 %d" % (p, cjk, ns))
        return

    if args.fix_punct:
        for p in files:
            with open(p, encoding="utf-8") as f:
                text = f.read()
            new, n = fix_punct(text)
            if n:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(new)
            print("%s：修正標點 %d 處" % (p, n))

    book_root = args.book_root or guess_book_root(files[0])
    whitelist = load_whitelist(book_root)
    results = [check_file(p, whitelist) for p in files]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print_report(r)
        must = sum(1 for r in results for f in r["問題"] if f["等級"] == "必須修")
        print("\n" + "=" * 60)
        print("合計：必須修 %d 項。%s" % (must, "請先修正必須修的項目。" if must else ""))

    if any(f["等級"] == "必須修" for r in results for f in r["問題"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
