
<div align="center">

# 东亚气象监控平台

### East Asia Weather Monitor

🌐 **www.eaweathe.com**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-green?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Stars](https://img.shields.io/github/stars/SteveRapeseed/EastAsia_weatherdata_web?style=social)](https://github.com/SteveRapeseed/EastAsia_weatherdata_web)

</div>

## ⚖️ 重要声明

1. **非商业性质**：本项目为气象爱好者个人搭建的**非商业、非盈利性质**学习交流平台，不投放广告，不提供付费服务。
2. **使用限制**：项目展示的实时气象信息，仅供爱好者**个人学习、交流参考**，**严禁**任何个人或机构将其用于商业经营、二次转载分发或衍生制作盈利产品。
3. **数据时效性与准确性**：项目数据仅为技术试验性展示，**不保证数据的时效性、准确性与完整性**。任何关键决策请以[中国气象局](https://www.cma.gov.cn)或[中央气象台](https://www.nmc.cn)等官方渠道发布的信息为准。
4. **代码用途**：本仓库代码仅供学习交流，使用者需**自行承担**运行代码带来的一切后果，包括但不限于数据合规风险。请严格遵守国家法律法规和源网站的使用条款。

<br>

<p align="center">
  <strong>东亚地区多源气象数据实时监控 Web 平台</strong><br>
  每 30 分钟自动抓取中国、日本、韩国、台湾、SYNOP、METAR 等气象站数据<br>
  以可视化图表与数据表格呈现
</p>

<br>

[功能特性](#功能特性) •
[技术栈](#技术栈) •
[快速开始](#快速开始) •
[项目结构](#项目结构) •
[API 参考](#api-参考) •
[贡献](#贡献) •
[许可证](#许可证)

</div>

## 功能特性

- **多源并发爬取** — 50 线程 ThreadPoolExecutor 并发请求，约 70 秒完成 2765+ 站点抓取
- **自动定时更新** — APScheduler 东八区每 0 分 / 30 分定点刷新
- **可视化图表** — Chart.js 温度概览与风速分布图，支持均值 / 最高 / 最低切换
- **数据查询** — 按站点、城市、地区多维度搜索、筛选、排序
- **地区极值统计** — 每地区最高 / 最低温度、湿度、极大风速、最大降水
- **快速手动刷新** — 点击立即刷新仅抓取 NMC + JMA + KMA，数据即到即渲染
- **高性能 API** — 后端预序列化 JSON + ETag 条件请求 + 前端自动轮询
- **跨平台运行** — Windows / Linux / macOS 均可

### 数据来源

| 来源 | 内容 | 站点数 |
|------|------|--------|
| [NMC 中国中央气象台](https://www.nmc.cn) | 国内实时观测 | ~2493 |
| SYNOP 国际交换报文 | 东亚各国约定站 | ~145 |
| CWA 台湾中央气象署 | 台湾地区站 | ~67 |
| JMA 日本气象厅 | 日本站 | ~32 |
| KMA 韩国气象厅 | 韩国站 | ~23 |
| METAR 航空天气报 (OGIMET) | 东亚主要机场 | ~9 |

> 总站点数：约 2765 个。

### 技术栈

- **后端框架** — [Flask](https://flask.palletsprojects.com/)（threaded 多线程模式）
- **任务调度** — [APScheduler](https://apscheduler.readthedocs.io/)（CronTrigger）
- **爬虫** — [requests](https://requests.readthedocs.io/) + [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)，多线程并发
- **前端** — 原生 HTML / CSS / JavaScript，[Chart.js](https://www.chartjs.org/) 图表
- **部署** — gunicorn / waitress / Flask 内置均可

## 快速开始

### 环境要求

- Python ≥ 3.8
- pip（Python 包管理器）

### 安装

1. **克隆仓库**

```bash
git clone https://github.com/SteveRapeseed/EastAsia_weatherdata_web.git
cd EastAsia_weatherdata_web
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **配置 CWA API Key（可选）**

> 如果不需要台湾地区数据可跳过此步。

前往 [台湾中央气象署开放数据平台](https://opendata.cwa.gov.tw/) 注册账号 → 创建 API Key（授权 O-A0003-001 和 O-A0002-001 数据集）→ 填入 `weather_crawler.py` 第 477 行：

```python
API_KEY = '你的API_KEY'
```

4. **启动服务**

```bash
python web_app.py
```

浏览器打开 [http://127.0.0.1:5000](http://127.0.0.1:5000)

> 首次启动约需 1~2 分钟完成初始抓取，页面会自动等待数据就绪后渲染。

### 生产部署

```bash
# gunicorn（Linux / macOS）
gunicorn -w 4 -b 0.0.0.0:5000 web_app:app --timeout 120

# waitress（Windows / Linux）
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 --threads=16 web_app:app
```

## 项目结构

```
EastAsia_weatherdata_web/
├── web_app.py                 # Flask 应用入口与 API 路由
├── weather_crawler.py         # 各数据源爬虫类
├── requirements.txt           # Python 依赖
├── README.md                  # 本文件
├── stations/                  # 站点配置文件（JSON）
│   ├── nmc.json               # NMC 中国站配置
│   ├── jma.json               # JMA 日本站配置
│   ├── kma.json               # KMA 韩国站配置
│   ├── cwa.json               # CWA 台湾站配置
│   ├── synop.json             # SYNOP 国际站配置
│   └── metar.json             # METAR 机场站配置
├── templates/
│   └── index.html             # 前端页面模板
└── static/
    └── chart.umd.min.js       # Chart.js（本地加载）
```

## API 参考

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端主页面 |
| `/api/data` | GET | 全量站点数据（支持 ETag 304 条件请求） |
| `/api/status` | GET | 轻量状态：总站数、更新时间、抓取状态、ETag |
| `/api/fetch` | POST | 手动触发抓取（NMC + JMA + KMA 快速模式） |
| `/api/search?q=关键词` | GET | 按站点 ID / 城市 / 地区搜索过滤 |

## 贡献

欢迎贡献代码、报告问题或提出新功能！

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/AmazingFeature`
3. 提交改动：`git commit -m 'Add some AmazingFeature'`
4. 推送到分支：`git push origin feature/AmazingFeature`
5. 发起 Pull Request

## 许可证

根据 MIT 许可证分发。详见 `LICENSE` 文件。

## 联系我们

SteveRapeseed — [GitHub](https://github.com/SteveRapeseed)

项目链接：<https://github.com/SteveRapeseed/EastAsia_weatherdata_web>

## 致谢

- [中国中央气象台 (NMC)](https://www.nmc.cn)
- [台湾中央气象署开放数据平台](https://opendata.cwa.gov.tw)
- [日本气象厅 (JMA)](https://www.jma.go.jp)
- [韩国气象厅 (KMA)](https://www.weather.go.kr)
- [OGIMET METAR 数据](https://www.ogimet.com)
- [Chart.js](https://www.chartjs.org)
- [Best-README-Template](https://github.com/othneildrew/Best-README-Template)

<p align="right">
  <a href="#顶部">返回顶部 ↑</a>
</p>
