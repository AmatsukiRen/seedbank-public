# 协议与实现导航

这里说明产品库中的现行查阅入口。`spec/` 保留生命包与协议的格式演进编号，这些编号不等同于应用版本 0.0.1。早期研发记录中的验收过程与本机材料没有整体迁入产品库；原有引用已改为下列公开可读入口。实际执行结果统一见[验收记录](acceptance.md)，不从历史设计说明推定当前已经通过。

## Memory

记忆来源、更正、遗忘与派生检索从 [cognition 规范](../spec/cognition.md)和[生命包格式](../spec/life-pack.md)查阅。来源过滤与交流范围是读取时的约束；缓存与索引不取代原始档案。

实现入口：[memory_state.py](../tools/seed/seedbank/memory_state.py)、[memory_sources.py](../tools/seed/seedbank/memory_sources.py)、[cognition.py](../tools/seed/seedbank/cognition.py)。主人、其他人物与群聊的交流范围见 [channel 规范](../spec/channel.md)及 [disclosure.py](../tools/seed/seedbank/disclosure.py)。

## Media

图片与声音的接收记录、保存及解释见[感知规范](../spec/senses.md)、[生命包格式](../spec/life-pack.md)和 [media_intake.py](../tools/seed/seedbank/media_intake.py)。同一摄入请求的重放不等于向外部平台重复发送回复。失败恢复与原件保持独立；真实素材不作为仓库示例数据。

## Agency

目标、计划、行动结果与来源见[成长规范](../spec/development.md)及[自主活动规范](../spec/agency.md)。提议、执行尝试、成功回执、用户反馈和当前完成条件分别记录；模型自述不是成功执行或因果学习的证据。

实现入口：[development.py](../tools/seed/seedbank/development.py)、[agency.py](../tools/seed/seedbank/agency.py)、[learning.py](../tools/seed/seedbank/learning.py)。可迁移经验仍受任务条件、来源和隐私限制；真实长期效果另行观察。

## Relationships

关系、提醒与纪念事项分别见 [bonds](../spec/bonds.md)、[friends](../spec/friends.md)、[hands](../spec/hands.md)、[memorial](../spec/memorial.md) 和 [clock](../spec/clock.md)。日期更正保留来源；提醒到期与离线时长不等同于生命结束。

## Inner

内在记录、自我叙事与连续性见 [inner](../spec/inner.md)和 [persona](../spec/persona.md)。记录的生成来源与失败状态应区分；没有当时证据的旧记录不能后来补称为自主产生。当前出生、记忆和选择的连续性也不代表已经证明意识。

## Storage

存储结构及兼容约定见[生命包格式](../spec/life-pack.md)，恢复与备份实现见 [backup.py](../tools/seed/seedbank/backup.py)和 [requests.py](../tools/seed/seedbank/requests.py)。测试须创建独立人工包，不能对日常个体执行恢复演练或并行写入。

## Providers

模型配置与可选 Codex 入口见[模型服务](model-services.md)、[brain 规范](../spec/brain.md)和[开始使用](getting-started.md)。服务预设不是全部型号完成实测的承诺，也不会提供维护者的账号。

## Development

开发、打包和离线回归见[开发说明](development.md)；载体扩展与手动本地插件分别见[扩展说明](extensions.md)、[插件指南](plugins.md)。UI 内选择角色、模型连接和出生身份是不同操作。
