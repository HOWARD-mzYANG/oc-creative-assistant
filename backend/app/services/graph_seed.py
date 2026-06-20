"""图谱默认数据定义。

本模块属于服务层初始化配置，负责提供默认项目和首次打开时展示的示例图谱。
它不访问数据库，也不处理 HTTP 请求或向量索引同步。
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas import EdgePayload, NodePayload, PositionPayload


_DEFAULT_OC_JSON = r"""
{
  "format": "oc",
  "version": 1,
  "project": {
    "name": "霍格沃茨：最后围城",
    "description": "一个以霍格沃茨最终围城为背景的戏剧化测试故事。黑暗势力进攻城堡时，哈利、赫敏、德拉科和守卫者们必须决定，是用武力、牺牲、信任，还是禁忌魔法来保护学校。故事聚焦于古老护盾的崩裂、危险的天文塔密道，以及守护霍格沃茨所要付出的情感代价。"
  },
  "nodes": [
    {
      "id": "char-draft-1780894131147-1",
      "node_type": "character",
      "title": "哈利·波特",
      "content": "哈利·波特是霍格沃茨的年轻巫师。在这个测试故事中，他站在最终围城的中心。他想保护学校和朋友，却担心胜利可能需要有人献出自己最幸福的记忆，以强化古老护盾。",
      "meta": {
        "text": "角色",
        "tags": [
          "角色"
        ],
        "status": "draft",
        "sortOrder": 0,
        "fields": {}
      },
      "position_x": 260,
      "position_y": 40,
      "sort_order": 0
    },
    {
      "id": "plot-draft-1780894228405-1",
      "node_type": "plot",
      "title": "护盾开始崩落",
      "content": "恐惧在霍格沃茨内部蔓延时，古老护盾上浮现出银色裂纹。赫敏意识到，护盾变弱不只是因为敌人的攻击，也因为守卫者们开始彼此猜疑。",
      "meta": {
        "text": "情节",
        "tags": [
          "情节"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 574.2315508696063,
      "position_y": -117.8156434069039,
      "sort_order": 0
    },
    {
      "id": "world-draft-1780894208212-2",
      "node_type": "worldbuilding",
      "title": "天文塔密道",
      "content": "天文塔密道是位于天文塔下方的一条隐藏通道。它最初被设计为紧急撤离路线，但在最终围城中变成了一件双刃的战术资源。如果它可信且安全，就能帮助学生远离危险；如果它被敌人利用，就可能让敌人突破城堡内层，或追踪撤离队伍。德拉科向哈利和赫敏揭露这条密道，迫使守卫者判断他的警告是否真诚，也迫使他们思考昔日敌人之间是否仍可能存在信任。",
      "meta": {
        "text": "世界观",
        "tags": [
          "世界观"
        ],
        "status": "draft",
        "sortOrder": 1
      },
      "position_x": 0,
      "position_y": 0,
      "sort_order": 0
    },
    {
      "id": "char-draft-1780894159667-2",
      "node_type": "character",
      "title": "赫敏·格兰杰",
      "content": "赫敏·格兰杰是哈利的亲密朋友，也是围城期间的主要策略制定者。她发现环绕霍格沃茨的古老护盾不仅由防御咒语维持，也由守卫者自愿献出的个人记忆提供力量。",
      "meta": {
        "text": "角色",
        "tags": [
          "角色"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 480,
      "position_y": 40,
      "sort_order": 1
    },
    {
      "id": "plot-draft-1780894408716-1",
      "node_type": "plot",
      "title": "德拉科揭露密道",
      "content": "德拉科带着关于天文塔下密道的警告接近哈利和赫敏。他透露，这条密道已经不再是安全的撤离路线。伏地魔的追随者已经在通道中留下追踪咒，任何进入其中的人都会暴露礼堂撤离队伍的位置。\n\n德拉科并没有要求守卫者使用这条密道。相反，他催促他们在敌人借它追踪学生之前封住入口。这让他的角色从“提供逃生路线”转变为“阻止隐蔽突破”。\n\n赫敏意识到，德拉科的信息之所以有价值，不是因为它打开了一条路，而是因为它帮助守卫者避开陷阱。哈利必须在敌人激活追踪咒之前，决定是否相信德拉科的警告。",
      "meta": {
        "text": "情节",
        "tags": [
          "情节"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 734.0237394405855,
      "position_y": 188.1203416224279,
      "sort_order": 1
    },
    {
      "id": "83d522abc7e64a258bceb56329845501",
      "node_type": "worldbuilding",
      "title": "霍格沃茨城堡（围城舞台）",
      "content": "霍格沃茨城堡是最终围城的核心战场。遭到攻击时，它不再只是一所学校，而是由魔法、记忆、隐藏路线和人与人之间的信任共同构成的多层防御堡垒。它能否幸存，不只取决于城墙和咒语，也取决于守卫者能否在恐惧、欺骗和正面进攻中保持团结。",
      "meta": {
        "text": "AI 建议",
        "tags": [
          "AI 建议"
        ],
        "status": "synced",
        "sortOrder": 0
      },
      "position_x": 120,
      "position_y": 120,
      "sort_order": 1
    },
    {
      "id": "char-draft-1780894179760-3",
      "node_type": "character",
      "title": "德拉科·马尔福",
      "content": "德拉科·马尔福知道天文塔下方有一条隐藏通道。这条通道可能让敌人进入霍格沃茨，但德拉科也有机会把它告诉哈利，从而改变战局。",
      "meta": {
        "text": "角色",
        "tags": [
          "角色"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 700,
      "position_y": 40,
      "sort_order": 2
    },
    {
      "id": "plot-draft-1780894432449-2",
      "node_type": "plot",
      "title": "记忆献祭之争",
      "content": "古老护盾继续变弱时，哈利提出献出自己关于友情的最幸福记忆。他认为，与其眼看霍格沃茨沦陷，不如承受一次痛苦的牺牲。一些守卫者因为急需解决办法而支持他。\n\n赫敏反对这个决定。她认为，如果哈利献出那段帮助他信任他人的记忆，守卫者也许能保住城堡，却会失去让抵抗具有意义的情感纽带。麦格也警告说，指挥者不能允许一个学生独自承担整场战斗的道德代价。\n\n这场争论让守卫者分裂。护盾急需力量，但没有人能就牺牲、信任和策略的优先级达成一致。",
      "meta": {
        "text": "情节",
        "tags": [
          "情节"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 425.22666423113617,
      "position_y": 289.0150388419254,
      "sort_order": 2
    },
    {
      "id": "002d03da411c445bae8c225f5e5a6da4",
      "node_type": "worldbuilding",
      "title": "战场结构",
      "content": "",
      "meta": {
        "text": "AI 建议",
        "tags": [
          "AI 建议"
        ],
        "status": "synced",
        "sortOrder": 0
      },
      "position_x": 120,
      "position_y": 120,
      "sort_order": 2
    },
    {
      "id": "char-draft-1780894321663-4",
      "node_type": "character",
      "title": "麦格教授",
      "content": "麦格教授在最终围城中指挥城堡的有序防御。她负责保护学生、协调教师，并守住正门足够长的时间，让撤离计划得以执行。\n\n与哈利不同，麦格必须从整个战场的角度思考。她不能只凭个人忠诚做决定。她最害怕的是情绪化决策会让年幼学生暴露在危险中。\n\n麦格尊重哈利的勇气，但也明白没有协调的勇气可能变成鲁莽。城堡陷落之前，她需要赫敏的策略、哈利的决心和德拉科的信息真正协同起来。",
      "meta": {
        "text": "角色",
        "tags": [
          "角色"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 40,
      "position_y": 200,
      "sort_order": 3
    },
    {
      "id": "plot-draft-1780894467462-4",
      "node_type": "plot",
      "title": "天文塔密道前的抉择",
      "content": "哈利、赫敏、德拉科和一小队守卫者抵达天文塔密道入口。密道要求有人说出誓言才会开启。德拉科必须说出自己打算保护谁，同时清楚虚假的誓言会把他们困在地下。\n\n德拉科犹豫了，因为他知道许多守卫者仍然怀疑他。哈利必须决定是否公开信任他。赫敏在一旁仔细观察，因为她明白这个时刻可能会影响古老护盾本身：如果守卫者之间的信任被修复，护盾也许不需要哈利的记忆就能增强。\n\n只有当德拉科说出自己要保护被困在礼堂中的学生时，密道才打开。这证明他的意图是真诚的，却也暴露出敌人已经从通道另一端逼近。",
      "meta": {
        "text": "情节",
        "tags": [
          "情节"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 857.2025969602732,
      "position_y": 457.34182973433155,
      "sort_order": 3
    },
    {
      "id": "world-draft-1780911210385-1",
      "node_type": "worldbuilding",
      "title": "古老护盾",
      "content": "古老护盾是在最终围城期间环绕霍格沃茨的古老防护魔法。它能阻挡黑魔法直接进入城堡范围，但强度取决于守卫者之间的情感团结。当恐惧、猜疑或绝望在学生和教师之间扩散时，护盾上就会出现银色裂纹。赫敏发现，护盾不只是防御咒语，也反映着守卫者是否仍然相信彼此。",
      "meta": {
        "text": "世界观",
        "tags": [
          "世界观"
        ],
        "status": "draft",
        "parentId": "83d522abc7e64a258bceb56329845501",
        "sortOrder": 0
      },
      "position_x": 0,
      "position_y": 0,
      "sort_order": 3
    },
    {
      "id": "char-draft-1780894543399-5",
      "node_type": "character",
      "title": "伏地魔",
      "content": "伏地魔在霍格沃茨最终围城中率领黑暗势力。他的目标不只是摧毁城堡的实体防御，也要打碎守卫者之间的情感团结。他明白古老护盾会因猜疑、恐惧和绝望而削弱，所以他同时攻击霍格沃茨的城墙和城内人们的士气。\n\n伏地魔相信爱、记忆和忠诚都是可以利用的弱点。他命令追随者散布假消息、威胁被俘学生，并迫使守卫者面对道德上几乎不可能承受的选择。他想让哈利相信牺牲是拯救他人的唯一方式，因为这种信念会把哈利从朋友身边孤立出去。\n\n他的主要战场策略是心理围城。他并不只是想进入霍格沃茨；他想让守卫者在失去彼此信任后，亲手为他打开道路。",
      "meta": {
        "text": "角色",
        "tags": [
          "角色"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 260,
      "position_y": 200,
      "sort_order": 4
    },
    {
      "id": "plot-draft-1780894630727-1",
      "node_type": "plot",
      "title": "围城开始",
      "content": "当伏地魔的军队包围霍格沃茨并攻击外层防线时，最终围城正式开始。贝拉特里克斯率领第一波攻势，目标是魔法雕像、防护屏障和一切可见的抵抗象征。\n\n起初，古老护盾仍然支撑着。然而伏地魔的策略并不只是用黑魔法击破护盾。他还向城堡中传递消息，声称守卫者已经被内部背叛，以此散播恐惧。\n\n这场开场攻击建立了两个战场：城堡外的实体围攻，以及城堡内的心理围攻。",
      "meta": {
        "text": "情节",
        "tags": [
          "情节"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 246.4574637352742,
      "position_y": -218.21014349179498,
      "sort_order": 4
    },
    {
      "id": "world-draft-1780911237009-2",
      "node_type": "worldbuilding",
      "title": "记忆献祭",
      "content": "记忆献祭是一种危险仪式，能把守卫者最幸福的记忆转化为魔法力量，从而恢复古老护盾的一部分。这个仪式有效但不可逆：献出记忆的人失去的不只是事件本身，还有附着在记忆上的情感温度。哈利考虑使用它，因为他相信一次个人牺牲也许能拯救城堡；赫敏则担心，失去友情记忆会削弱护盾真正需要的信任。",
      "meta": {
        "text": "世界观",
        "tags": [
          "世界观"
        ],
        "status": "draft",
        "parentId": "83d522abc7e64a258bceb56329845501",
        "sortOrder": 1
      },
      "position_x": 0,
      "position_y": 0,
      "sort_order": 4
    },
    {
      "id": "char-draft-1780894558600-6",
      "node_type": "character",
      "title": "贝拉特里克斯·莱斯特兰奇",
      "content": "贝拉特里克斯·莱斯特兰奇是伏地魔麾下最激进的战场指挥官。她领导对外层围城防线的正面攻击，并用暴力景象在守卫者之间散播恐慌。\n\n与专注于心理崩溃的伏地魔不同，贝拉特里克斯相信恐惧必须可见且直接。她同时攻击魔法雕像、防御屏障和学生士气。她的攻势旨在让守卫者觉得抵抗毫无意义。\n\n贝拉特里克斯也成为赫敏的个人威胁。她看出赫敏是防御体系背后的策略核心，并试图逼迫她仓促决策。她的出现让这场战斗从战术冲突变成了情感冲突。",
      "meta": {
        "text": "角色",
        "tags": [
          "角色"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 480,
      "position_y": 200,
      "sort_order": 5
    },
    {
      "id": "plot-draft-1780894655049-2",
      "node_type": "plot",
      "title": "发现斯内普的笔记",
      "content": "赫敏发现了一组加密笔记，可能是西弗勒斯·斯内普留下的。笔记中描述古老护盾并不只是回应个人牺牲，而是回应昔日敌人之间重新建立的信任。\n\n一些守卫者拒绝相信这些笔记，因为他们不信任斯内普。另一些人则认为，笔记中的信息与他们观察到的情况吻合：猜疑蔓延时，护盾最容易变弱。\n\n这些笔记带来一种新的可能性。如果德拉科真心选择保护学生，他的誓言也许能比哈利的记忆献祭更安全地强化护盾。",
      "meta": {
        "text": "情节",
        "tags": [
          "情节"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 171.33814107237288,
      "position_y": 26.375504933693037,
      "sort_order": 5
    },
    {
      "id": "world-draft-1780911277525-3",
      "node_type": "worldbuilding",
      "title": "围城防线",
      "content": "围城防线是战斗期间围绕霍格沃茨形成的多层防御。外层防线由被施法的雕像、屏障和资深守卫者维持；中层防线由教师、结界和移动路障保护；内层防线环绕礼堂，保护年幼学生。贝拉特里克斯攻破外层防线后，守卫者被迫向内收缩，使之后关于护盾、密道和哈利牺牲的每一个决定都变得更加紧迫。",
      "meta": {
        "text": "世界观",
        "tags": [
          "世界观"
        ],
        "status": "draft",
        "parentId": "002d03da411c445bae8c225f5e5a6da4",
        "sortOrder": 0
      },
      "position_x": 0,
      "position_y": 0,
      "sort_order": 5
    },
    {
      "id": "char-draft-1780894573094-7",
      "node_type": "character",
      "title": "卢修斯·马尔福",
      "content": "卢修斯·马尔福在围城中像一件政治与心理武器。他知道德拉科可能会向哈利揭露天文塔密道，于是试图用家族忠诚、恐惧和羞耻阻止德拉科。\n\n卢修斯不像贝拉特里克斯那样直接指挥战场，但他懂得如何通过名声和义务给人施压。他试图说服德拉科：即使他帮助守卫者，守卫者也永远不会真正接纳他。\n\n卢修斯的存在加剧了德拉科的信任困境。如果德拉科听从父亲，天文塔密道可能变成敌人进入霍格沃茨的路线；如果他拒绝父亲，就必须公开选择守卫者，而不是自己的家族。",
      "meta": {
        "text": "角色",
        "tags": [
          "角色"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 700,
      "position_y": 200,
      "sort_order": 6
    },
    {
      "id": "plot-draft-1780894683414-3",
      "node_type": "plot",
      "title": "贝拉特里克斯攻破外层防线",
      "content": "贝拉特里克斯加强了对外层围城防线的攻击。她的部队摧毁了数座魔法雕像，迫使守卫者退向中层防线。肉眼可见的崩溃在城堡内的学生之间制造了恐慌。\n\n麦格命令教师和年长学生稳定中层防线。即便增援外层防御在战术上有用，她也拒绝抛弃礼堂中的年幼学生。\n\n这一事件增加了所有后续决策的压力。守卫者已经没有太多时间继续争论护盾、密道和德拉科的忠诚。",
      "meta": {
        "text": "情节",
        "tags": [
          "情节"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 635.7768198736337,
      "position_y": 1035.140051805151,
      "sort_order": 6
    },
    {
      "id": "world-draft-1780911302972-4",
      "node_type": "worldbuilding",
      "title": "礼堂内层防御",
      "content": "礼堂内层防御是霍格沃茨内部最后的保护区域。随着战斗逼近城堡核心，它庇护年幼学生、受伤的守卫者和撤离队伍。麦格指挥这条防线，因为放弃它就等于牺牲学校中最脆弱的人。礼堂成为围城的道德中心：每一个战略决策都必须以是否保护聚集在那里的人为判断标准。",
      "meta": {
        "text": "世界观",
        "tags": [
          "世界观"
        ],
        "status": "draft",
        "parentId": "002d03da411c445bae8c225f5e5a6da4",
        "sortOrder": 1
      },
      "position_x": 0,
      "position_y": 0,
      "sort_order": 6
    },
    {
      "id": "char-draft-1780894592022-8",
      "node_type": "character",
      "title": "西弗勒斯·斯内普",
      "content": "西弗勒斯·斯内普在守卫者的信息网络中是一个暧昧的人物。一些守卫者相信他在围城开始前留下了关于古老护盾的秘密笔记，另一些人则怀疑这些笔记可能是陷阱。\n\n笔记暗示，古老护盾原本就不该通过某一个人的牺牲来恢复。相反，当昔日敌人选择保护同一群人时，它的回应最强。如果这些信息可信，就能把德拉科在天文塔密道前的誓言和护盾恢复联系起来。\n\n斯内普的作用间接却关键。他并不作为战场指挥官出现，但围绕他笔记的不确定性迫使守卫者决定：真相是否可能来自一个他们并不完全信任的人。",
      "meta": {
        "text": "角色",
        "tags": [
          "角色"
        ],
        "status": "draft",
        "sortOrder": 0,
        "fields": {}
      },
      "position_x": 40,
      "position_y": 360,
      "sort_order": 7
    },
    {
      "id": "plot-draft-1780894712655-4",
      "node_type": "plot",
      "title": "伏地魔利用裂痕",
      "content": "伏地魔意识到德拉科的誓言强化了古老护盾，于是改变策略。他不再直接攻击护盾，而是散布一种说法：德拉科打开密道只是为了把敌人引进来。\n\n守卫者被迫决定是否公开为德拉科辩护。如果他们犹豫，重新出现的猜疑可能再次削弱护盾。如果他们站在德拉科一边，就必须承担相信一个家族仍效忠伏地魔的人的风险。\n\n这一刻考验着护盾的真正意义。它不再只是关于记忆或魔法，而是关于守卫者能否在攻击之下仍然选择信任。",
      "meta": {
        "text": "情节",
        "tags": [
          "情节"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 993.548292077676,
      "position_y": 715.7094495092341,
      "sort_order": 7
    },
    {
      "id": "plot-draft-1780894744502-5",
      "node_type": "plot",
      "title": "礼堂最终防线",
      "content": "当内层围城防线遭到攻击时，战斗抵达礼堂。麦格协调守卫者，赫敏保护撤离路线，哈利则面对一个选择：是牺牲自己的记忆，还是相信刚刚形成、仍然脆弱的团结。\n\n德拉科的信息帮助年幼学生经由天文塔密道撤离，但伏地魔的部队试图从另一端进入。贝拉特里克斯攻击守卫者阵线，迫使赫敏离开密道。\n\n最终防线把所有冲突汇聚在一起：哈利的牺牲、赫敏的策略、德拉科的忠诚、麦格的指挥、伏地魔的心理围城，以及古老护盾对信任的依赖。",
      "meta": {
        "text": "情节",
        "tags": [
          "情节"
        ],
        "status": "draft",
        "sortOrder": 0
      },
      "position_x": 1164.7518772122514,
      "position_y": 1237.2137469243823,
      "sort_order": 8
    }
  ],
  "edges": [
    {
      "source": "plot-draft-1780894228405-1",
      "target": "plot-draft-1780894432449-2",
      "label": "导致",
      "relation_type": "causes",
      "edge_type": "bezier",
      "sort_order": 0
    },
    {
      "source": "world-draft-1780911210385-1",
      "target": "83d522abc7e64a258bceb56329845501",
      "label": "归属于",
      "relation_type": "belongs_to",
      "edge_type": "bezier",
      "sort_order": 0
    },
    {
      "source": "plot-draft-1780894408716-1",
      "target": "plot-draft-1780894467462-4",
      "label": "导致",
      "relation_type": "causes",
      "edge_type": "bezier",
      "sort_order": 1
    },
    {
      "source": "world-draft-1780911237009-2",
      "target": "83d522abc7e64a258bceb56329845501",
      "label": "归属于",
      "relation_type": "belongs_to",
      "edge_type": "bezier",
      "sort_order": 1
    },
    {
      "source": "plot-draft-1780894467462-4",
      "target": "plot-draft-1780894712655-4",
      "label": "发展为",
      "relation_type": "develops_into",
      "edge_type": "bezier",
      "sort_order": 2
    },
    {
      "source": "world-draft-1780911277525-3",
      "target": "002d03da411c445bae8c225f5e5a6da4",
      "label": "归属于",
      "relation_type": "belongs_to",
      "edge_type": "bezier",
      "sort_order": 2
    },
    {
      "source": "plot-draft-1780894630727-1",
      "target": "plot-draft-1780894228405-1",
      "label": "导致",
      "relation_type": "causes",
      "edge_type": "bezier",
      "sort_order": 3
    },
    {
      "source": "world-draft-1780911302972-4",
      "target": "002d03da411c445bae8c225f5e5a6da4",
      "label": "归属于",
      "relation_type": "belongs_to",
      "edge_type": "bezier",
      "sort_order": 3
    },
    {
      "source": "plot-draft-1780894683414-3",
      "target": "plot-draft-1780894744502-5",
      "label": "防线破裂迫使最终决战",
      "relation_type": "causes",
      "edge_type": "bezier",
      "sort_order": 7
    },
    {
      "source": "plot-draft-1780894712655-4",
      "target": "plot-draft-1780894744502-5",
      "label": "通向最终决战",
      "relation_type": "causes",
      "edge_type": "bezier",
      "sort_order": 8
    },
    {
      "source": "plot-draft-1780894432449-2",
      "target": "plot-draft-1780894467462-4",
      "label": "冲突于",
      "relation_type": "conflicts_with",
      "edge_type": "bezier",
      "sort_order": 10
    },
    {
      "source": "plot-draft-1780894655049-2",
      "target": "plot-draft-1780894228405-1",
      "label": "揭示护盾秘密",
      "relation_type": "references",
      "edge_type": "bezier",
      "sort_order": 13
    }
  ]
}
"""

_DEFAULT_OC: dict[str, Any] = json.loads(_DEFAULT_OC_JSON)
_DEFAULT_PROJECT = _DEFAULT_OC["project"]

DEFAULT_PROJECT_ID = "default-project"
DEFAULT_PROJECT_NAME = str(_DEFAULT_PROJECT["name"])
DEFAULT_PROJECT_DESCRIPTION = str(_DEFAULT_PROJECT.get("description") or "")

_TYPE_LABEL_BY_NODE_TYPE = {
    "character": "角色",
    "plot": "情节",
    "worldbuilding": "世界观",
}


def _coerce_tags(meta: dict[str, Any]) -> list[str]:
    """从默认快照 meta 中安全提取字符串标签列表。"""
    tags = meta.get("tags", [])
    if not isinstance(tags, list):
        return []
    return [tag for tag in tags if isinstance(tag, str)]


def _coerce_sort_order(meta: dict[str, Any]) -> int:
    """从默认快照 meta 中读取同级排序值，非法时回退为 0。"""
    value = meta.get("sortOrder", 0)
    return value if isinstance(value, int) else 0


def _node_from_snapshot(raw: dict[str, Any]) -> NodePayload:
    """把默认项目快照中的节点字典转换为 API 节点 payload。"""
    node_type = str(raw.get("node_type") or "plot")
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    parent_id = meta.get("parentId")

    return NodePayload(
        id=str(raw["id"]),
        type=node_type,
        nodeType=node_type,
        title=str(raw.get("title") or "未命名"),
        content=str(raw.get("content") or ""),
        meta=str(meta.get("text") or ""),
        typeLabel=_TYPE_LABEL_BY_NODE_TYPE.get(node_type, node_type.title()),
        tags=_coerce_tags(meta),
        status=str(meta.get("status") or "draft"),
        parentId=parent_id if isinstance(parent_id, str) and parent_id else None,
        sortOrder=_coerce_sort_order(meta),
        position=PositionPayload(
            x=float(raw.get("position_x") or 0.0),
            y=float(raw.get("position_y") or 0.0),
        ),
    )


def _edge_from_snapshot(index: int, raw: dict[str, Any]) -> EdgePayload:
    """把默认项目快照中的边字典转换为 API 边 payload。"""
    return EdgePayload(
        id=f"edge-default-{index:02d}",
        source=str(raw["source"]),
        target=str(raw["target"]),
        label=str(raw.get("label") or "相关"),
        relationType=str(raw.get("relation_type") or "relates_to"),
        type=str(raw.get("edge_type") or "bezier"),
    )


DEFAULT_NODES = [_node_from_snapshot(raw) for raw in _DEFAULT_OC["nodes"]]
DEFAULT_EDGES = [
    _edge_from_snapshot(index, raw)
    for index, raw in enumerate(_DEFAULT_OC["edges"])
]
