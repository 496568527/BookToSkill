# 冒险岛怀旧服 自动挂机

基于「截图识别 + 模拟按键」的简单挂机脚本，不读写游戏内存。

> ⚠️ 大多数服务器（包括私服/怀旧服）禁止使用挂机脚本，可能封号。请自行承担风险，最好先用小号测试。

## 功能
- 自动左右巡逻 + 攻击 + 捡物
- 根据血条/蓝条比例自动喝药
- 定时释放 BUFF
- 通过小地图黄点定位自己，在设定的左右边界之间巡逻（识别不到时按时间掉头）
- 卡住检测（小地图位置长时间不变 → 跳跃并掉头）
- 小地图出现其他玩家（红点）自动暂停并蜂鸣；HP 归零自动停止；最长挂机时间
- 游戏窗口不在前台时自动暂停按键

## 安装（Windows，Python 3.10+）
```bash
pip install -r requirements.txt
```
**必须以管理员身份运行命令行**，否则按键发不进游戏。游戏建议用窗口模式。

## 使用步骤
1. 修改 `config.json` 里的 `keys` 和 `buffs`，对应你自己的键位：
   - `attack` 攻击技能键，`jump` 跳跃，`pickup` 捡东西
   - `hp_potion` / `mp_potion` 红药、蓝药所在快捷栏键
   - 按键名：`ctrl` `alt` `shift` `insert` `home` `pageup` `delete` `end` `pagedown` `a`~`z` `f1` 等
2. **满血满蓝时**运行校准，自动找出血条/蓝条位置：
   ```bash
   python calibrate.py
   ```
   打开生成的 `calibrate_debug.png`，检查黄框(血)、青框(蓝)、紫框(小地图)、红圈(你自己)是否对准。
3. 分别站到要巡逻平台的最左端、最右端各运行一次 `calibrate.py`，把输出的 `x` 填到 `patrol.left_x` / `patrol.right_x`。
4. 启动：
   ```bash
   python bot.py
   ```
   切到游戏，按 **F9** 开始/暂停，**F12** 退出。

## 主要参数
| 参数 | 说明 |
|---|---|
| `potion.hp_threshold` / `mp_threshold` | 低于此比例喝药（0.5 = 50%） |
| `buffs[].interval` | BUFF 释放间隔（秒） |
| `patrol.attacks_per_step` | 每走一步攻击几次 |
| `patrol.walk_seconds` | 每步走多久 |
| `patrol.jump_attack` | 走路时是否跳 |
| `patrol.use_minimap` | false = 只按 `turn_seconds` 定时掉头 |
| `safety.pause_when_player_nearby` | 有人来就暂停 |
| `debug` | true 时打印每次识别到的 HP/MP/位置 |

## 限制
- 只在一个平台上左右巡逻，不会爬绳子/换层。挑一个怪多的平坦平台挂。
- 没有处理测谎仪等验证，出现时请手动处理。
- 坐标基于窗口客户区；改了分辨率要重新运行 `calibrate.py`。
