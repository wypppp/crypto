# Hydromancer 历史成交：AWS 设置步骤（给你操作）

> 依据：用户 10-02 裁决〇-2（[存档](../../3_审计/2026-10-02_总控第八轮与用户裁决_资格Hydromancer前向卡数据落袋.md)）：批准，单项上限 10 美元；专用 IAM 用户只读该存储桶；预算告警 10 美元并配自动停用；下载完成后删除密钥；密钥只放 `.env`，不入库。
> 数据：`s3://hydromancer-reservoir`（东京区 ap-northeast-1，requester-pays：数据免费，流量费由下载方付，东京区外网约 $0.114/GB）。先列目录看总大小，再下载 xyz 的成交（2025-10-13 起）。
> 下载脚本 [hydromancer_get.py](hydromancer_get.py) 自己按字节封顶（默认 40 GB，约 $4.6），因为 AWS 预算的费用数据有几个小时延迟，预算动作不能当成实时刹车。

## 1. 开账户

用你本人的身份开一个 AWS 账户（需要信用卡）。开好后用根用户登录一次，开启根用户的 MFA，之后日常不用根用户。

## 2. 建只读的 IAM 用户

IAM → 用户 → 创建用户，名字 `rt-hydromancer-readonly`，**不给控制台访问**。权限选“直接附加策略”→“创建内联策略”→ JSON，粘贴：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListReservoir",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::hydromancer-reservoir"
    },
    {
      "Sid": "ReadReservoir",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::hydromancer-reservoir/*"
    }
  ]
}
```

策略名 `rt-hydromancer-read`。这个用户除了读这个桶，什么也做不了。

## 3. 建访问密钥，写进 `.env`

用户 → 安全凭证 → 创建访问密钥 → 用途选“命令行界面（CLI）”。把两行加到工作区根目录的 `/home/ancillary/.env`（已在 .gitignore 里，不入库）：

```
AWS_ACCESS_KEY_ID=（你的 Access key）
AWS_SECRET_ACCESS_KEY=（你的 Secret access key）
```

执行模型只用正则按键名读取，不打印、不写出。

## 4. 预算告警与自动停用

**4.1 给预算动作用的角色**：IAM → 角色 → 创建角色 → “自定义信任策略”，粘贴：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "budgets.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

下一步添加内联权限策略（只允许给用户挂、摘策略）：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["iam:AttachUserPolicy", "iam:DetachUserPolicy"],
      "Resource": "*"
    }
  ]
}
```

角色名 `rt-budgets-action`。

**4.2 建预算**：Billing and Cost Management → Budgets → 创建预算 → “自定义” → “成本预算”，按月，金额 **$10**。告警：实际成本达 50%（$5）、100%（$10）各发一封邮件到你的邮箱。

**4.3 加动作**：在同一个预算里 → “附加操作”（Configure actions）：
- 触发：实际成本达到 **100%**；
- 动作类型：**应用 IAM 策略**；执行角色选 `rt-budgets-action`；
- 策略选 AWS 托管策略 **`AWSDenyAll`**；目标选用户 `rt-hydromancer-readonly`；
- 选“自动执行”（不需要人工批准）。

触发后这个用户的所有请求都会被拒绝，下载停止。

## 5. 做完告诉执行模型

在 `review.md` 写一句“AWS 已设好”即可。执行模型先列目录（几乎不花钱），把总大小与预计费用写给你；在上限以内就直接下载，超了先问你。

## 6. 下载完成后

执行模型会在回复里说明下载完成。然后你：
1. IAM → 用户 `rt-hydromancer-readonly` → 安全凭证 → 停用并删除访问密钥；
2. 从 `.env` 删掉那两行；
3. 预算可以留着（不收费），也可以删。
