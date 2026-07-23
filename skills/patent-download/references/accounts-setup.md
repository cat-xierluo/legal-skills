# 各平台账号获取与 ToS 说明

本工具支持 6 个下载通道。Google Patents 与 CNIPA 专利公布公告系统为**公开免登录**,直接可用;其余 4 个平台需要账号,**通过环境变量配置(见 `config/.env.example`),本仓库不存储任何账号密码**。

## ⚠️ 服务条款(ToS)合规提示

度衍、PatentStar、粤港澳、PSS 为商用或会员制平台。用账号自动登录、批量下载**可能违反其服务条款**。使用前请:

1. 阅读对应平台的用户协议与反爬声明
2. 确认你的账号权限是否允许自动化访问
3. 控制请求频率,避免对平台造成压力
4. 仅下载你有权获取的专利文档

**合规风险由使用者自行承担。** 若仅做常规检索,优先用 Google Patents(公开免登录,无 ToS 风险)。

## 各平台账号获取

### Google Patents（无需账号）⭐ 推荐
- 网址:https://patents.google.com
- 方式:公开免登录,通过 patent-downloader SDK 直连
- 配置:无需

### 度衍专利
- 网址:https://www.uyanip.com
- 注册:官网注册（手机号）
- 环境变量:`PATENT_UYANIP_USERNAME` / `PATENT_UYANIP_PASSWORD`
- 特点:有 PDF 下载按钮,无验证码

### 专利之星（PatentStar）
- 网址:https://cprs.patentstar.com.cn
- 注册:商用系统,需购买/开通账号
- 环境变量:`PATENT_PATENTSTAR_USERNAME` / `PATENT_PATENTSTAR_PASSWORD`
- 状态:API 接口已失效（Ret=206）,仅作兼容保留

### 粤港澳知识产权大数据平台（GPIC）
- 网址:https://search.gpic.gd.cn
- 注册:官网注册
- 环境变量:`PATENT_GPIC_USERNAME` / `PATENT_GPIC_PASSWORD`

### PSS 专利检索系统
- 网址:https://pss-system.cponline.cnipa.gov.cn
- 注册:国家知识产权局公共服务,需实名注册
- 环境变量:`PATENT_PSS_USERNAME` / `PATENT_PSS_PASSWORD`

### CNIPA 专利公布公告系统（无需账号）
- 网址:http://epub.cnipa.gov.cn
- 方式:公开免登录,但有验证码/反爬
- 配置:无需账号

## 配置流程

```bash
cp config/.env.example config/.env
# 编辑 config/.env,填入你注册的账号
python scripts/cli.py <平台> <专利号>
# 账号会自动从环境变量 / .env 加载
```
