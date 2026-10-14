# 心田 Bot v48 系统接口与联调说明

本文件对应 xintian-bot-v48-interfaces.py。代码已完成本地数据库及模拟 Bot 检查；须在主机安装后才能称为上线，尚未验证生产网页或真实 Telegram 操作。

基础地址：https://member.xintian.com.my 。所有 Bot 接口必须带 `X-Xintian-Bot-Key`，密钥仅限可信 Bot 服务端。日期采用马来西亚时间。保留现有签到识别、AI问答及工作人员排除。

## 1. 体验订单核验

`POST /api/bot/trial-orders/check`，JSON：

```json
{"tg_user_id":"123456789","contact_user_id":"123456789","phone":"+60123456789","fb_name":"客户的Facebook名称"}
```

contact_user_id 必须来自 Telegram 本人联系卡，与发消息的 tg_user_id 相同；不能把任意客户输入的电话号码当作已验证联系卡。核对本人电话与 FB 名称，单笔已导入订单满 RM50，日期有效、未关联会员、未发奖励、未作体验申请。存在对应会员或名称别名时拒绝重复体验。

```json
{"ok":true,"eligible":true,"orders":[{"anchor_order":"订单号","amount":50.0,"purchase_date":"2026-10-14","fb_name":"客户的Facebook名称","phone":"+60123456789"}],"reason":""}
```

不符合资格仍返回 HTTP200：eligible=false、orders=[]、reason 给出原因。参数无效返回400。无电话号码或姓名不一致的订单交客服核验，不以同名自动认领。最早的合格订单排在第一位，最多返回五笔；查询不锁定订单，最终注册事务再次核验并防重复。RM50沿用现有系统 total_amount 字段；当前订单数据没有独立运费字段，不能宣称此字段已经扣除运费。

## 2. 体验注册生日

已确认最新代码支持 `POST /api/bot/registrations/trial` 的可选 `birthday`，格式 `YYYY-MM-DD`，写入 members.birthday，非年月份。更新保留此功能。

必填：tg_user_id、contact_user_id、phone、name、anchor_order；可选 fb_name、referrer_code、birthday。Bot订单核验与注册必须用同一联系人资料，建议name及fb_name按实际收集的FB名字提交。首次体验仍为 friend，生日不等于礼物资格；生日盲盒只限有效 paid/vip/elder，并沿用生日当天至七天后截止规则。

已注册重试由原注册事务核验本人及订单，不能重新领取体验或奖励。注册返回原有 ok/member_id/member_code/expiry_date/awarded_orders 等字段。不会改变生日盲盒审批、积分或兑换历史。

## 3. 会籍查询

保留 `GET /api/bot/member?tg_user_id=...`，member 内既有：membership_active、expiry_date、tier、member_code、birthday、余额。增加兼容同义字段 is_active、expire_date、level。无绑定404，重复绑定409；查询错误应保留待审/暂停动作，不能当成会籍无效。

## 4. 续费凭证

`POST /api/bot/renewal-applications`，multipart/form-data，与v48字段一致：

| 字段 | 内容 |
|---|---|
| request_id | 唯一请求编号，1–100字，英文数字及冒号、下划线、短横线；同一次重试保持相同编号 |
| tg_user_id | 已绑定会员的本人TG ID |
| amount | 正数，最多两位小数；这是客户申报金额，审核确认实收金额 |
| payment_date | YYYY-MM-DD，不晚于马来西亚今天 |
| transaction_ref | 银行/TNG交易编号；去首尾空白并大写，防重复提交 |
| file | 不超过5MB的JPG/PNG/WEBP/PDF凭证；与原凭证格式校验一致 |

返回：

```json
{"ok":true,"application_id":123,"receipt_id":123,"status":"pending"}
```

申请编号就是原后台「续费单据」编号，不另开一个审核页面。上传只建待审核记录，不收会费、不延长会籍。相同request_id与相同内容返回原申请并带 repeated=true；相同编号内容不同或已使用交易编号拒绝。

后台批准后调用原正式续费操作：登记付款、延长会籍、friend转paid；同一审核不能重复计费。审核结果与通知任务在同一数据库事务提交。批准通知包含新到期日，拒绝通知包含审核原因。通知走原 send-jobs，新增 kind=renewal，job_id=renewal:数字，chat_id为私人TG ID、text原样发送；start/result仍是原/send-jobs/start、/send-jobs/result。不添加群问题前缀。旧已审核单据不会补发通知。

## 5. 续费提醒五阶段

接口：

- `POST /api/bot/renewal-reminders/claim`，JSON `{}`。
- `POST /api/bot/renewal-reminders/{task_id}/start`，JSON `{"lease_token":"..."}`。
- `POST /api/bot/renewal-reminders/{task_id}/result`。

claim 返回 `{"ok":true,"task":null}` 表示无任务，关闭时另带 enabled=false。

```json
{"ok":true,"task":{"task_id":"12","lease_token":"...","lease_until":"2026-10-15 09:02:00","member_id":1,"tg_user_id":"123456789","expiry_date":"2026-10-22","stage":"T-7","text":"系统生成的提醒正文","due_date":"2026-10-15"}}
```

阶段：T-7、T-3、T0、T+3、T+7。注意到期当天为 **T0**。每天按本地日期精确匹配，只发当天阶段；停机错过的旧阶段不集中补发。按会员+到期日+阶段唯一防重。VIP、元老永久类别及工作人员不生成续费提醒。

start 成功：`{"ok":true,"send_allowed":true}`；会籍变化、过期任务或开关关闭：ok=false、send_allowed=false。启动前必须同时核验两个标志，不可重复start。

result：

```json
{"task_id":"12","lease_token":"...","status":"sent","telegram_message_id":"456","error":""}
```

status 可为 sent、failed、uncertain。成功必须带正整数 Telegram 消息编号。失败/不确定必须带error。领取未启动的租约两分钟后可重新领取；启动后五分钟无结果标记uncertain。失败和uncertain不会自动重发，需核对TG后处理；同一发送结果回报支持幂等重试。提醒不会进人工问题待办。

## 6. 群资格及任务

`GET /api/bot/group-eligibility?tg_user_id=...`：

```json
{"ok":true,"tg_user_id":"123456789","membership_active":false,"eligible":false,"protected_staff":false,"should_remove":true,"member":{"member_id":1,"name":"花友","tier":"paid","expiry_date":"2026-10-08","membership_active":false}}
```

工作人员 protected_staff=true、membership_active=true、should_remove=false，仅用于群保护，不改变其会员/游戏身份。未注册用户返回明确结果 member=null、eligible=false、should_remove=false；系统不自动移除未知群用户。绑定冲突409，必须暂停动作。

群任务：

- `POST /api/bot/group-tasks/claim`，JSON `{}`。
- `POST /api/bot/group-tasks/{task_id}/start`，JSON `{"lease_token":"..."}`。
- `POST /api/bot/group-tasks/{task_id}/result`。

claim：`{"ok":true,"task":{"task_id":"1","lease_token":"...","action":"remove","chat_id":"-1003922360963","tg_user_id":"123456789","member_id":1,"expiry_date":"2026-10-08"}}`，无任务task=null。

群ID读取现有公告群设置。自动移除限已登记会员，到期日已过七天且当前会籍无效；到期当天仍有效。start重新核验工作人员、TG绑定、到期日、会籍、群设置及开关。Bot真正移除前再查group-eligibility；必须明确ok=true且should_remove=true，接口故障不能继续移除。

remove使用ban后unban，允许续费后重新申请，不永久封禁。恢复任务action=restore，用unban(only_if_banned=true)，失败不能报成功。仅有已尝试移除记录的会员续费后产生恢复任务；包括结果不确定、可能仍被封禁的情况。解除封禁不会直接把人加入群，审核通知提示用户重新点Bot进群按钮。

result：`{"task_id":"1","lease_token":"...","status":"done","error":""}`；状态为done/skipped/failed/uncertain。部分移除操作失败或结果不确定应报uncertain，以免隐藏可能仍封禁的情况。任务与租约防重逻辑同提醒；执行失败不自动重复踢人。

## 7. 入群审核

沿用Bot通过Telegram API创建creates_join_request=true的邀请链接；本次不新增系统生成邀请链接接口。TG把chat_join_request事件发给Bot，非向系统拉取申请列表。更新限定只处理配置的会员群，并查group-eligibility；接口失败保留待审，明确有效才批准，明确无效才拒绝。管理员生成链接的身份查询失败时停止操作。

注册/绑定后按钮链接仍来自Bot的 GROUP_INVITE_URL。请Bot开发方确保它填的是管理员实际生成的「需审核邀请链接」，现有普通固定链接不会自动变成审核链接。此更新不撤销旧群链接。

## 8. 安装与启用

把 xintian-bot-v48-interfaces.py 文件完整保存到主机 `/opt/xintian/xintian-bot-v48-interfaces.py`，执行：

```bash
/opt/xintian/venv/bin/python /opt/xintian/xintian-bot-v48-interfaces.py
```

安装器校验上传代码版本，备份代码及SQLite，初始化新增表，检查完整系统路由，重启会员及Bot服务。若Bot已更新到另一版，会停止而不覆盖。安装失败撤回代码，新增表保留；完整数据库备份留在backups目录，不自动回滚正在使用的业务数据库。

初始系统开关文件 `/opt/xintian/data/bot-lifecycle.json` 的 reminders_enabled、group_tasks_enabled 都为false。确认体验核验及续费审核通知后，Bot开发方联调提醒和群资格；联调仅使用确定可移除的测试账户，普通花友不要作为移除测试对象。

检查当前开关及任务数量：

```bash
/opt/xintian/venv/bin/python /opt/xintian/xintian-bot-v48-interfaces.py --status
```

确认联调通过后启用系统端（与Bot端开关双重控制）：

```bash
/opt/xintian/venv/bin/python /opt/xintian/xintian-bot-v48-interfaces.py --enable-reminders
/opt/xintian/venv/bin/python /opt/xintian/xintian-bot-v48-interfaces.py --enable-group-tasks
```

Bot端仍需对应设置 XINTIAN_REMINDERS=1、XINTIAN_GROUP_TASKS=1并重启Bot。开关启用后Bot下一次轮询即会领取当天真实任务；系统本身无独立提醒计时器，依靠Bot轮询。

紧急暂停系统自动任务（不影响其他Bot功能）：

```bash
/opt/xintian/venv/bin/python /opt/xintian/xintian-bot-v48-interfaces.py --disable-automatic
```

## 已做检查及限制

本地SQLite实测：本人订单条件、五阶段日期、任务防重、并发领取、工作人员保护、续费审核幂等、通知失败时会费与会籍一并回滚、恢复任务、原send-jobs通知桥接、积分不变；模拟Bot会籍查询失败不移除；安装器备份与版本保护。运行依赖检查、完整FastAPI加载、systemd重启及真实Telegram收发须由主机安装/联调验证。

本版本未提供不确定任务的后台一键重试界面。failed/uncertain记录保留数据库，先核对实际结果，不能直接把记录改回queued重复执行。请反馈安装输出及联调结果，再判断是否可以开启自动任务。
