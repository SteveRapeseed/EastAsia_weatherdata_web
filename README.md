# 东亚气象监控平台 — East Asia Weather Monitor

东亚地区多源气象数据实时监控 Web 平台。每 30 分钟自动从 **中国中央气象台 (NMC)**、**日本气象厅 (JMA)**、**韩国气象厅 (KMA)**、**台湾中央气象署 (CWA)**、**国际 SYNOP 报** 以及 **全球 METAR 航空报** 抓取各站瞬时天气数据，以可视化图表与数据表格呈现。

## 数据来源

| 来源 | 内容 | 站点数 |
|------|------|--------|
| [NMC 中国中央气象台](https://www.nmc.cn) | 国内 2400+ 站点实时观测 | ~2493 |
| SYNOP 国际交换报文 | 东亚各国约定站 | ~145 |
| CWA 台湾中央气象署 | 台湾地区站 | ~67 |
| JMA 日本气象厅 | 日本站 | ~32 |
| KMA 韩国气象厅 | 韩国站 | ~23 |
| METAR 航空天气报 (OGIMET) | 东亚主要机场 | ~9 |

> 总站点数：约 2765 个。

## 功能特性

- **多源并发爬取** — 50 线程 ThreadPoolExecutor 并发请求，总抓取约 70 秒完成
- **自动定时更新** — APScheduler 每 30 分钟后台刷新所有站点数据
- **可视化图表** — 基于 Chart.js（本地加载）的温度概览与风速分布图
- **数据查询** — 按站点/城市/地区搜索、筛选、排序
- **地区极值统计** — 每个地区展示最高/最低温度、湿度、极大风速、最大降水
- **性能优化** — 后端预序列化 JSON + ETag 条件请求，前端自动轮询等待数据
- **跨平台运行** — Windows / Linux / macOS 均可

## 技术栈

- **后端** — Python Flask (threaded)，APScheduler
- **爬虫** — requests + BeautifulSoup，多线程并发
- **前端** — 原生 HTML/CSS/JavaScript，Chart.js
- **部署** — gunicorn / waitress / Flask 内置均可

## 快速启动

### 环境要求

- Python ≥ 3.8
- pip

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
python web_app.py
```

浏览器打开 [http://127.0.0.1:5000](http://127.0.0.1:5000)

首次启动约需 1~2 分钟完成初始抓取，页面会自动等待数据就绪后渲染。

### 生产部署

```bash
# gunicorn（Linux/Mac）
gunicorn -w 4 -b 0.0.0.0:5000 web_app:app --timeout 120

# waitress（Windows 可选 / Linux 也可用）
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
│   ├── nmc.json
│   ├── jma.json
│   ├── kma.json
│   ├── cwa.json
│   ├── synop.json
│   └── metar.json
├── templates/
│   └── index.html             # 前端页面模板
└── static/
    └── chart.umd.min.js       # Chart.js（本地）
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端页面 |
| `/api/data` | GET | 全量站点数据（支持 ETag 304） |
| `/api/status` | GET | 轻量状态（总站数、更新时间、正在抓取标志） |
| `/api/fetch` | POST | 手动触发立即抓取 |
| `/api/search?q=关键词` | GET | 搜索过滤站点 |

## 自定义站点

各 `stations/*.json` 文件为站点字典，格式为 `"站点ID": {"city": "城市名", "province": "所属地区"}`。如需增减站点，直接编辑对应 JSON 文件即可，无需改代码。

## TODO

- [ ] 对比过去 N 次数据的趋势曲线
- [ ] 站点地图标记
- [ ] 导出 CSV
- [ ] 数据下载 / 历史存档

## License

MIT


## CWA（台湾中央气象署）API Key 注册

本程序使用台湾中央气象署开放数据 API 获取台湾地区气象站数据，需要申请 API Key。

**申请步骤：**

1. 打开 [https://opendata.cwa.gov.tw/](https://opendata.cwa.gov.tw/)（台湾中央气象署开放数据平台）
2. 点击右上角「注册」，注册一个账号（免费）
3. 登录后进入「会员中心」→「API 金钥管理」
4. 点击「建立金钥」，选择「授权 O-A0003-001」和「O-A0002-001」数据集
5. 复制生成的 API Key 字符串

**配置到项目中：**

打开 weather_crawler.py，找到第 477 行：

\\python
API_KEY = ''  # 将你的 Key 填在引号内
\
将你申请的 API Key 填入引号中即可。如果不配置，台湾地区站点数据将无法获取，其他地区不受影响。
