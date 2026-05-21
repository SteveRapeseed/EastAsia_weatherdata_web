# -*- coding: utf-8 -*-
"""Crawler core module - Optimized"""
import re, datetime, math, json, os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ELEMENTS = ["瞬时温度", "相对湿度", "1小时降水", "2分钟平均风向", "2分钟平均风速"]
ELEMENT_UNITS = {"瞬时温度": "°C", "相对湿度": "%", "1小时降水": "mm", "2分钟平均风向": "", "2分钟平均风速": "m/s"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_WORKERS = 20
REQUEST_TIMEOUT = 8

def create_session():
    session = requests.Session()
    session.verify = False
    # 关键：禁用 trust_env，避免读取系统/Shell 代理配置（如 HTTP_PROXY/HTTPS_PROXY）
    # 否则当代理软件未运行时，每次请求都会先尝试连接代理 -> FileNotFoundError -> 失败重试
    session.trust_env = False
    session.proxies = {}
    retries = Retry(total=1, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    return session

def load_all_stations(data_dir=None):
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__), "stations")
    result = {}
    for name in ["nmc", "jma", "kma", "cwa", "synop", "metar"]:
        path = os.path.join(data_dir, f"{name}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                result[name] = json.load(f)
        else:
            result[name] = {}
    return result




class NMCSource:
    def __init__(self, station_info):
        self.station_info = station_info

    def fetch_single(self, station_id):  # 去掉 session 参数
        info = self.station_info.get(station_id)
        if not info:
            return station_id, station_id, '', {}, ''
        scode = info['scode']
        city = info['city']
        province = info['province']
        url = f'https://www.nmc.cn/f/rest/real/{scode}'
        try:
            session = create_session()
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            session.close()
            if resp.status_code != 200:
                return station_id, city, province, {}, ''
            json_data = resp.json()
        except Exception:
            return station_id, city, province, {}, ''

        real = json_data.get('real', json_data)
        weather = real.get('weather', {}) if isinstance(real, dict) else {}
        wind = real.get('wind', {}) if isinstance(real, dict) else {}
        publish_time = real.get('publish_time', '')

        temp = weather.get('temperature')
        humidity = weather.get('humidity')
        rain = weather.get('rain')
        wind_direct = wind.get('direct')
        wind_speed = wind.get('speed')

        humidity = str(int(humidity)) if humidity is not None and humidity != '' and humidity != 9999 else (
            '9999' if humidity == 9999 else humidity)
        if str(wind_direct) == '9999' and str(wind_speed) != '9999':
            wind_direct = '无持续风向'

        data = {
            '瞬时温度': temp,
            '相对湿度': humidity,
            '1小时降水': rain,
            # 不再返回 '地面气压'，保持与 ELEMENTS 一致
            '2分钟平均风向': wind_direct,
            '2分钟平均风速': wind_speed,
        }
        for k in data:
            val = data[k]
            if k == '1小时降水':
                # 降水：None/空 = 该站无降水数据（设为0.0），9999 = 无数据源（N/A）
                if val is None or val == '' or val == 0 or val == '0':
                    data[k] = '0.0'
                elif val == '9999' or val == 9999:
                    data[k] = 'N/A'
                else:
                    data[k] = str(val)
            else:
                data[k] = str(val) if val is not None and val != '' else 'N/A'
        return station_id, city, province, data, publish_time

# ================== 日本数据源 (JMA) ==================
# ================== 日本数据源 (JMA) — 增强回溯 ==================
import datetime
import time

# ================== 日本数据源 (JMA) — 最终修正版 ==================
import datetime


class JMASource:
    def __init__(self, stations):
        self.stations = stations

    WIND_DIR_MAP = {
        0: '静穏', 1: 'NNE', 2: 'NE', 3: 'ENE',
        4: 'E', 5: 'ESE', 6: 'SE', 7: 'SSE',
        8: 'S', 9: 'SSW', 10: 'SW', 11: 'WSW',
        12: 'W', 13: 'WNW', 14: 'NW', 15: 'NNW',
        16: 'N',
    }

    def _make_session(self):
        return create_session()

    def fetch_single(self, station_code):
        info = self.stations.get(station_code)
        if not info:
            return station_code, station_code, '', {}, ''
        name = info['name']
        region = info['region']

        jst = datetime.timezone(datetime.timedelta(hours=9))
        now_jst = datetime.datetime.now(jst)
        block_hour = (now_jst.hour // 3) * 3
        date_str = now_jst.strftime('%Y%m%d')

        urls_to_try = []
        urls_to_try.append((
            f'https://www.jma.go.jp/bosai/amedas/data/point/{station_code}/{date_str}_{block_hour:02d}.json',
            'current'
        ))
        prev = now_jst - datetime.timedelta(hours=3)
        prev_block_hour = (prev.hour // 3) * 3
        prev_date_str = prev.strftime('%Y%m%d')
        urls_to_try.append((
            f'https://www.jma.go.jp/bosai/amedas/data/point/{station_code}/{prev_date_str}_{prev_block_hour:02d}.json',
            'previous'
        ))

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.jma.go.jp/bosai/amedas/',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }

        best_ts = None
        best_data = None
        session = self._make_session()
        try:
            for url, blk_type in urls_to_try:
                try:
                    resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data:
                            latest_ts = max(data.keys())
                            if best_ts is None or latest_ts > best_ts:
                                best_ts = latest_ts
                                best_data = data
                except Exception:
                    continue
        finally:
            session.close()

        if best_ts and best_data:
            return self._parse_response(station_code, name, region, best_data, best_ts)
        else:
            return station_code, name, region, {}, ''

    def _parse_response(self, station_code, name, region, data, latest_ts):
        try:
            obs = data[latest_ts]

            temp = obs.get('temp', [None])[0]
            humidity = obs.get('humidity', [None])[0]
            pressure = obs.get('pressure', [None])[0]
            precip = obs.get('precipitation1h', [None])[0]
            wind_dir_code = obs.get('windDirection', [None])[0]
            wind_speed = obs.get('wind', [None])[0]

            wind_dir_str = self.WIND_DIR_MAP.get(wind_dir_code, str(wind_dir_code)) if wind_dir_code is not None else 'N/A'

            weather_data = {
                '瞬时温度': str(temp) if temp is not None else 'N/A',
                '相对湿度': str(humidity) if humidity is not None else 'N/A',
                '1小时降水': str(precip) if precip is not None else 'N/A',
                '地面气压': str(pressure) if pressure is not None else 'N/A',
                '2分钟平均风向': wind_dir_str,
                '2分钟平均风速': str(wind_speed) if wind_speed is not None else 'N/A',
            }

            # JST → CST
            jst_tz = datetime.timezone(datetime.timedelta(hours=9))
            cst_tz = datetime.timezone(datetime.timedelta(hours=8))
            dt_jst = datetime.datetime.strptime(latest_ts, '%Y%m%d%H%M%S').replace(tzinfo=jst_tz)
            dt_cst = dt_jst.astimezone(cst_tz)
            time_str = dt_cst.strftime('%Y-%m-%d %H:%M')

            return station_code, name, region, weather_data, time_str
        except Exception:
            return station_code, name, region, {}, ''
# ================== 韩国数据源 (KMA) ==================
# ================== 韩国数据源 (KMA) — 修正版 ==================


class KMASource:
    def __init__(self, stations):
        self.stations = stations

    def _make_url(self, station_code):
        """构造 KMA AWS 分钟数据 URL"""
        kst = datetime.timezone(datetime.timedelta(hours=9))
        now = datetime.datetime.now(kst)
        time_str = now.strftime('%Y%m%d%H%M')
        return f'https://www.weather.go.kr/cgi-bin/aws/nph-aws_txt_min_cal_test?{time_str}&0&MINDB_01M&{station_code}&a&M'

    def fetch_single(self, station_code):
        info = self.stations.get(station_code)
        if not info:
            return station_code, station_code, '', {}, ''
        name = info['name']
        region = info['region']

        url = self._make_url(station_code)
        headers = {
            'Referer': 'https://www.weather.go.kr/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        session = create_session()
        try:
            resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return station_code, name, region, {}, ''

            soup = BeautifulSoup(resp.content, 'html.parser')
            # 遍历所有行，寻找有效数据行（第一列为 HH:MM 格式，且温度列不为空）
            rows = soup.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 16:               # 新表头共 16 列
                    continue
                # 时间列必须匹配 HH:MM
                time_cell = cells[0].text.strip()
                if not re.match(r'^\d{2}:\d{2}$', time_cell):
                    continue
                # 温度列（索引 7）有效时才是数据行
                temp_val = cells[7].text.strip()
                if temp_val == '.' or temp_val == '':
                    continue

                # 按新的列索引提取要素
                precip_60m = cells[2].text.strip()   # 강수60M (1小时降水)
                wind_dir = cells[12].text.strip()    # 풍향10M 方向 (英文缩写)
                wind_speed = cells[13].text.strip()  # 풍속10M (风速 m/s)
                humidity = cells[14].text.strip()    # 습도% (湿度)
                time_str = time_cell

                def clean(v):
                    return 'N/A' if v in ('.', '', None) else v

                weather_data = {
                    '瞬时温度': clean(temp_val),
                    '相对湿度': clean(humidity),
                    '1小时降水': clean(precip_60m),
                    '2分钟平均风向': clean(wind_dir),
                    '2分钟平均风速': clean(wind_speed),
                }

                # 时间转换：KST → CST (UTC+8)
                try:
                    kst_tz = datetime.timezone(datetime.timedelta(hours=9))
                    cst_tz = datetime.timezone(datetime.timedelta(hours=8))
                    hour, minute = map(int, time_str.split(':'))
                    now_kst = datetime.datetime.now(kst_tz)
                    dt_kst = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if dt_kst > now_kst:
                        dt_kst -= datetime.timedelta(days=1)
                    dt_cst = dt_kst.astimezone(cst_tz)
                    cst_time = dt_cst.strftime('%Y-%m-%d %H:%M')
                except Exception:
                    cst_time = 'N/A'

                return station_code, name, region, weather_data, cst_time

            return station_code, name, region, {}, ''
        except Exception:
            return station_code, name, region, {}, ''
        finally:
            session.close()


import re
import datetime
from bs4 import BeautifulSoup, NavigableString, Tag


import re
import datetime
from bs4 import BeautifulSoup, NavigableString, Tag

# # class CWASource:
#     """台湾省地区气象局 (CWA) 数据源 - 最终稳定版"""
#     def __init__(self, stations):
#         self.stations = stations
#
#     def _clean(self, val):
#         if val in (None, '', '.', '-'):
#             return 'N/A'
#         return str(val)
#
#     def _extract_humidity(self, text):
#         """从湿度/能见度混合文本中提取湿度值"""
#         if not text:
#             return None
#         # 1. >3048 → 48
#         if text.startswith('>') and len(text) >= 4:
#             digits = re.sub(r'\D', '', text)
#             if len(digits) >= 2:
#                 return digits[-2:]
#         # 2. 11-1579 → 79
#         if '-' in text:
#             parts = text.split('-')
#             if len(parts) >= 2:
#                 digits = re.sub(r'\D', '', parts[-1])
#                 if len(digits) >= 2:
#                     return digits[-2:]
#         # 3. 無觀測59 → 59
#         if '無觀測' in text:
#             digits = re.sub(r'\D', '', text)
#             if len(digits) >= 2:
#                 return digits[-2:]
#         return None
#
#     def fetch_single(self, session, station_code):
#         info = self.stations.get(station_code)
#         if not info:
#             return station_code, station_code, '', {}, ''
#         name = info['name']
#         region = info['region']
#
#         url = f'https://www.cwa.gov.tw/V8/C/W/Observe/MOD/24hr/{station_code}.html'
#         headers = {
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
#             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
#             'Referer': 'https://www.cwa.gov.tw/',
#             'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
#         }
#
#         try:
#             # 请确保 CWA_PROXY 已定义，如：CWA_PROXY = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
#             resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT, proxies=CWA_PROXY)
#             if resp.status_code != 200:
#                 return station_code, name, region, {}, ''
#
#             soup = BeautifulSoup(resp.content, 'html.parser')
#
#             # 1. 定位第一条温度 span（代表最新观测）
#             temp_span = soup.find('span', class_='tem-C is-active')
#             if not temp_span:
#                 return station_code, name, region, {}, ''
#
#             # 2. 找到本条记录的日期（MM/DD格式），它位于温度 span 之前
#             date_node = temp_span.find_previous(string=re.compile(r'^\d{2}/\d{2}$'))
#             if not date_node:
#                 return station_code, name, region, {}, ''
#             date_str = date_node.strip()
#
#             # 3. 从日期节点开始，顺序收集兄弟节点，直到下一个日期为止
#             elements = []
#             sibling = date_node.next_sibling
#             while sibling:
#                 if isinstance(sibling, NavigableString) and re.match(r'^\d{2}/\d{2}$', sibling.strip()):
#                     break
#                 if isinstance(sibling, Tag) and sibling.name == 'span':
#                     elements.append(sibling)
#                 elif isinstance(sibling, NavigableString):
#                     text = sibling.strip()
#                     if text:
#                         elements.append(text)
#                 sibling = sibling.next_sibling
#
#             # 4. 按顺序提取时间、风向、风速、湿度文本
#             time_str = None
#             wind_dir = None
#             wind_speed = None
#             humidity_text = None
#
#             time_found = False
#             dir_found = False
#             speed_found = False
#
#             for elem in elements:
#                 # 时间：第一个 HH:MM 文本
#                 if isinstance(elem, str) and re.match(r'^\d{2}:\d{2}$', elem):
#                     if not time_found:
#                         time_str = elem
#                         time_found = True
#                         continue
#                 # span 元素
#                 if isinstance(elem, Tag):
#                     classes = elem.get('class', [])
#                     # 风向：class 包含 'wind' 但不包含 'wind_2'
#                     if 'wind' in classes and 'wind_2' not in classes:
#                         if not dir_found:
#                             wind_dir = elem.text.strip()
#                             dir_found = True
#                     # 风速：第一个 wind_2 is-active
#                     elif 'wind_2' in classes and 'is-active' in classes:
#                         if not speed_found:
#                             wind_speed = elem.text.strip()
#                             speed_found = True
#                 # 湿度文本：风速找到后，第一个包含 > 或 - 或 無觀測 的文本
#                 if speed_found and isinstance(elem, str) and ('>' in elem or '-' in elem or '無觀測' in elem):
#                     humidity_text = elem
#                     break
#
#             # 备用：若上述循环未找到湿度文本，再遍历一次所有后续纯文本
#             if not humidity_text:
#                 for sibling in date_node.next_siblings:
#                     if isinstance(sibling, NavigableString):
#                         txt = sibling.strip()
#                         if txt and ('>' in txt or '-' in txt or '無觀測' in txt):
#                             humidity_text = txt
#                             break
#
#             humidity = self._extract_humidity(humidity_text)
#
#             # 5. 组装数据
#             weather_data = {
#                 '瞬时温度': self._clean(temp_span.text.strip()),
#                 '相对湿度': self._clean(humidity),
#                 '1小时降水': '0.0',
#                 '2分钟平均风向': self._clean(wind_dir),
#                 '2分钟平均风速': self._clean(wind_speed),
#             }
#
#             # 6. 时间格式化（UTC+8）
#             full_time = f"{date_str} {time_str}" if time_str else date_str
#             time_match = re.search(r'(\d{2})/(\d{2})\s+(\d{2}):(\d{2})', full_time)
#             if time_match:
#                 month, day, hour, minute = map(int, time_match.groups())
#                 now = datetime.datetime.now()
#                 dt = datetime.datetime(now.year, month, day, hour, minute)
#                 display_time = dt.strftime('%Y-%m-%d %H:%M')
#             else:
#                 display_time = 'N/A'
#
#             return station_code, name, region, weather_data, display_time
#
#         except Exception:
#             return station_code, name, region, {}, ''
import datetime
import requests


class CWASource:
    """台湾省地区气象局 (CWA) 官方 API 数据源（含1小时降水）"""

    API_KEY = ''
    MAIN_API_URL = 'https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001'
    RAIN_API_URL = 'https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001'

    # 完整站号映射（原始站号 → API 站号）
    STATION_ID_MAP = {
        '46691': '466910', '46692': '466920', '46694': '466940',
        '46695': '466950', '46688': '466881', '46690': '466900',
        'C2A65': 'C2A650', '46705': '467050', 'C2C48': 'C2C480',
        'C0D66': 'C0D660', '46757': '467571', '46728': '467280',
        'C0E75': 'C0E750', '46749': '467490', '46727': '467270',
        '46755': '467550', '46765': '467650', 'C0H89': 'C0H890',
        'C0I39': 'C0I390', 'C0I46': 'C0I460', 'C0I36': 'C0I360',
        '46729': '467290', 'C0K40': 'C0K400', '46748': '467480',
        '46753': '467530', 'C0M68': 'C0M680', '46741': '467410',
        '46742': '467420', '46744': '467441', '46810': '468100',
        '46902': '469020', '46759': '467590', 'C2R17': 'C2R170',
        'C0R69': 'C0R690', '46708': '467080', 'C0U77': 'C0U770',
        'C0UA5': 'C0UA50', '46699': '466990', 'C0T96': 'C0T960',
        '46754': '467540', '46761': '467610', '46762': '467620',
        '46766': '467660', '46730': '467300', '46735': '467350',
        '46711': '467110', '46799': '467990', '46693': '466930',
        'C2H95': 'C2H950', 'C2H9J': 'C2H9J0', 'C2H9K': 'C2H9K0',
        'C2H9F': 'C2H9F0'
    }
    # 风向角度 → 16 方位
    WIND_DIR_MAP = {
        0: 'N', 22.5: 'NNE', 45: 'NE', 67.5: 'ENE',
        90: 'E', 112.5: 'ESE', 135: 'SE', 157.5: 'SSE',
        180: 'S', 202.5: 'SSW', 225: 'SW', 247.5: 'WSW',
        270: 'W', 292.5: 'WNW', 315: 'NW', 337.5: 'NNW',
        360: 'N',
    }

    def __init__(self, stations):
        self.stations = stations

    def _clean(self, val):
        """清洗无效值：-99 或空值转为 N/A"""
        if val in (None, '', '.', '-', '-99', -99, '-99.0'):
            return 'N/A'
        return str(val)

    def _angle_to_direction(self, angle_str):
        """风向角度 → 16方位文字"""
        try:
            angle = float(angle_str)
            if angle < 0:
                return 'N/A'
            angle = angle % 360
            closest = min(self.WIND_DIR_MAP.keys(), key=lambda x: abs(x - angle))
            return self.WIND_DIR_MAP[closest]
        except (ValueError, TypeError):
            return 'N/A'

    def _fetch_main(self, session, api_station_id):
        params = {
            'Authorization': self.API_KEY,
            'StationId': api_station_id,
            'WeatherElement': 'AirTemperature,RelativeHumidity,WindDirection,WindSpeed',
            'GeoInfo': '',
        }
        try:
            resp = session.get(self.MAIN_API_URL, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return None
            data = resp.json()
            stations = data.get('records', {}).get('Station', [])
            if not stations:
                return None
            latest = stations[0]
            elements = latest.get('WeatherElement', {})
            obs_time = latest.get('ObsTime', {}).get('DateTime', '')
            return elements, obs_time
        except:
            return None

    def _fetch_rain(self, session, api_station_id):
        params = {
            'Authorization': self.API_KEY,
            'StationId': api_station_id,
            'RainfallElement': 'Past1hr',
            'GeoInfo': '',
        }
        try:
            resp = session.get(self.RAIN_API_URL, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return 'N/A'
            data = resp.json()
            stations = data.get('records', {}).get('Station', [])
            if not stations:
                return 'N/A'
            latest = stations[0]
            rain = latest.get('RainfallElement', {}).get('Past1hr', {}).get('Precipitation', 'N/A')
            return self._clean(rain)
        except:
            return 'N/A'

    def fetch_single(self, station_code):
        info = self.stations.get(station_code)
        if not info:
            return station_code, station_code, '', {}, ''
        name = info['name']
        region = info['region']

        api_station_id = self.STATION_ID_MAP.get(station_code)
        if not api_station_id:
            return station_code, name, region, {}, ''

        session = create_session()
        try:
            main_result = self._fetch_main(session, api_station_id)
            if not main_result:
                return station_code, name, region, {}, ''
            elements, obs_time = main_result

            precip = self._fetch_rain(session, api_station_id)

            temp = elements.get('AirTemperature')
            humidity = elements.get('RelativeHumidity')
            wind_dir = elements.get('WindDirection')
            wind_speed = elements.get('WindSpeed')

            weather_data = {
                '瞬时温度': self._clean(temp),
                '相对湿度': self._clean(humidity),
                '1小时降水': precip,
                '2分钟平均风向': self._angle_to_direction(wind_dir),
                '2分钟平均风速': self._clean(wind_speed),
            }

            display_time = 'N/A'
            if obs_time:
                try:
                    dt = datetime.datetime.fromisoformat(obs_time)
                    display_time = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    pass

            return station_code, name, region, weather_data, display_time
        finally:
            session.close()


import re
import math
from bs4 import BeautifulSoup


class SynopSource:
    """OGIMET SYNOP 数据源（朝鲜、越南、蒙古国）—— 终极稳定版"""

    OGIMET_URL = 'https://www.ogimet.com/cgi-bin/decomet'

    def __init__(self, stations):
        self.stations = stations

    def _calc_rh(self, t, td):
        """Magnus 公式计算相对湿度 (%)，支持负露点"""
        try:
            t = float(t)
            td = float(td)
            a, b = 17.27, 237.7
            es_t = math.exp((a * t) / (b + t))
            es_td = math.exp((a * td) / (b + td))
            return str(round((es_td / es_t) * 100))
        except:
            return 'N/A'

    def _extract_temp_dew(self, text):
        """提取气温或露点数值（含负号）"""
        match = re.search(r'(-?[\d.]+)\s*C', text)
        return match.group(1) if match else None

    def _wind_angle_to_dir(self, angle_str):
        """风向角度区间 → 16 方位"""
        try:
            nums = re.findall(r'\d+', angle_str)
            if nums:
                mid = (int(nums[0]) + int(nums[-1])) // 2
            else:
                return 'N/A'
            dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
                    'S','SSW','SW','WSW','W','WNW','NW','NNW']
            idx = round(mid / 22.5) % 16
            return dirs[idx]
        except:
            return 'N/A'

    def _parse_wind_speed(self, text):
        """提取风速数值 (m/s) —— 增强版"""
        # 匹配 "7 m/s" 或 "3 m/s (10.8 Km/h, 5.8 Kt)" 等格式
        match = re.search(r'([\d.]+)\s*m/s', text)
        if match:
            return match.group(1)
        # 如果失败，尝试匹配任意数字
        match = re.search(r'([\d.]+)', text)
        return match.group(1) if match else 'N/A'

    def _extract_precip(self, soup):
        """提取降水量及持续时间，格式：x.xmm (xxh) 或 x.xmm"""
        amount = None
        hours = None
        for td in soup.find_all('td'):
            text = td.get_text()
            if 'Amount of precipitation' in text:
                i_tag = td.find('i')
                if i_tag:
                    match = re.search(r'([\d.]+)', i_tag.text)
                    if match:
                        amount = match.group(1)
            if 'Duration of period' in text:
                match = re.search(r'(\d+)\s+hours', text)
                if match:
                    hours = int(match.group(1))
        if amount:
            if hours:
                return f"{amount}mm ({hours}h)"
            else:
                return f"{amount}mm"
        return '0.0mm'  # 默认值，格式统一

    def _parse_all_tables(self, soup):
        tables = soup.find_all('table', bgcolor="#FFFFFF")
        data = {}
        time_str = None

        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if not cells:
                    continue
                # 处理单列情况（时间表格）
                if len(cells) == 1:
                    desc_cell = cells[0]
                    desc_text = desc_cell.get_text()
                    if 'Date/hour of observation' in desc_text:
                        i_tag = desc_cell.find('i')
                        if i_tag:
                            time_str = i_tag.text.strip()
                    continue  # 跳过后续逻辑

                # 处理双列情况
                desc_cell = cells[1] if len(cells) > 1 else None
                if not desc_cell:
                    continue
                desc_text = desc_cell.get_text()

                if 'Date/hour of observation' in desc_text:
                    i_tag = desc_cell.find('i')
                    if i_tag:
                        time_str = i_tag.text.strip()
                elif 'Temperature' in desc_text and 'Dew point' not in desc_text:
                    i_tag = desc_cell.find('i')
                    if i_tag:
                        t = self._extract_temp_dew(i_tag.text)
                        if t:
                            data['temp'] = t
                elif 'Dew point temperature' in desc_text:
                    i_tag = desc_cell.find('i')
                    if i_tag:
                        td = self._extract_temp_dew(i_tag.text)
                        if td:
                            data['dew'] = td
                elif 'True direction' in desc_text:
                    i_tag = desc_cell.find('i')
                    if i_tag:
                        data['wind_dir_angle'] = i_tag.text.strip()
                elif 'Wind speed' in desc_text:
                    i_tag = desc_cell.find('i')
                    if i_tag:
                        data['wind_speed_text'] = i_tag.text.strip()

        return data, time_str

    def _make_url(self, station, dt):
        return (f'{self.OGIMET_URL}?ind={station}&ano={dt.year}&mes={dt.month:02d}'
                f'&day={dt.day:02d}&hora={dt.hour:02d}&min=00&single=yes&lang=en')

    def fetch_single(self, station_code):
        info = self.stations.get(station_code)
        if not info:
            return station_code, station_code, '', {}, ''
        name, region = info['name'], info['region']

        session = create_session()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                   'Accept': 'text/html,application/xhtml+xml'}
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            hour = (now.hour // 3) * 3
            dt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if dt > now:
                dt -= datetime.timedelta(hours=3)  # 跳过未来时间点

            for _ in range(3):  # 最多尝试 3 个时次
                resp = session.get(self._make_url(station_code, dt), headers=headers, timeout=10)  # 专用超时 10 秒
                dt -= datetime.timedelta(hours=3)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.content, 'html.parser')
                if not soup.find('table', bgcolor="#AF4444"):
                    continue
                # ... 后续解析与原来一致

                parsed_data, time_str = self._parse_all_tables(soup)
                if 'temp' not in parsed_data:
                    continue

                temp = parsed_data['temp']
                dew = parsed_data.get('dew')
                humidity = self._calc_rh(temp, dew) if dew else 'N/A'

                wind_dir = 'N/A'
                if 'wind_dir_angle' in parsed_data:
                    wind_dir = self._wind_angle_to_dir(parsed_data['wind_dir_angle'])

                wind_speed = 'N/A'
                if 'wind_speed_text' in parsed_data:
                    wind_speed = self._parse_wind_speed(parsed_data['wind_speed_text'])

                precip = self._extract_precip(soup)

                display_time = 'N/A'
                if time_str:
                    try:
                        d = datetime.datetime.strptime(time_str, '%m/%d/%Y at %H:%M UTC')
                        d_utc = d.replace(tzinfo=datetime.timezone.utc)
                        d_cst = d_utc.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                        display_time = d_cst.strftime('%Y-%m-%d %H:%M')
                    except:
                        pass

                weather_data = {
                    '瞬时温度': temp,
                    '相对湿度': humidity,
                    '1小时降水': precip,
                    '2分钟平均风向': wind_dir,
                    '2分钟平均风速': wind_speed,
                }
                return station_code, name, region, weather_data, display_time

            return station_code, name, region, {}, ''
        finally:
            session.close()

import re
import math
from bs4 import BeautifulSoup


class MetarSource:
    """METAR 数据源（通过 OGIMET 获取原始报文并解析）"""

    OGIMET_URL = 'https://www.ogimet.com/display_metars2.php'

    def __init__(self, stations):
        self.stations = stations

    def _calc_rh(self, t, td):
        """Magnus 公式计算相对湿度 (%)，支持负露点"""
        try:
            t = float(t)
            td = float(td)
            a, b = 17.27, 237.7
            es_t = math.exp((a * t) / (b + t))
            es_td = math.exp((a * td) / (b + td))
            return str(round((es_td / es_t) * 100))
        except:
            return 'N/A'

    def _wind_dir_to_16(self, degrees):
        """风向角度 -> 16方位"""
        dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
                'S','SSW','SW','WSW','W','WNW','NW','NNW']
        idx = round(degrees / 22.5) % 16
        return dirs[idx]

    def _parse_metar(self, metar_str):
        """解析单条 METAR 报文，返回要素字典和观测时间"""
        # 1. 提取时间戳
        time_match = re.search(r'(\d{2})(\d{2})(\d{2})Z', metar_str)
        if time_match:
            day, hour, minute = map(int, time_match.groups())
            # 月份年份从页面获取，这里先留空，由调用者补充
            obs_time = f"{day:02d} {hour:02d}:{minute:02d} UTC"
        else:
            obs_time = None

        # 2. 提取温度/露点 (TT/Td 或 TT/MTd)
        temp_match = re.search(r'\b(M?\d{2})/(M?\d{2})\b', metar_str)
        temp = dew = None
        if temp_match:
            temp_str = temp_match.group(1).replace('M', '-')
            dew_str = temp_match.group(2).replace('M', '-')
            try:
                temp = int(temp_str)
                dew = int(dew_str)
            except:
                pass

        # 3. 提取风向风速 (dddssGssMPS 或 VRBssMPS)
        # 先匹配 12006G15MPS 格式
        wind_match = re.search(r'(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?MPS', metar_str)
        wind_dir_deg = wind_speed = None
        if wind_match:
            wind_dir_str = wind_match.group(1)
            wind_speed = int(wind_match.group(2))
            if wind_dir_str == 'VRB':
                wind_dir_deg = None   # 风向不定
            else:
                wind_dir_deg = int(wind_dir_str)

        return obs_time, temp, dew, wind_dir_deg, wind_speed

    def _make_url(self, station_code):
        """构造 OGIMET METAR 请求 URL（获取最近24小时）"""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        # 请求最近24小时的数据
        dt_end = now_utc
        dt_start = now_utc - datetime.timedelta(hours=24)
        url = (f'{self.OGIMET_URL}?lang=en&lugar={station_code}&tipo=ALL&ord=REV'
               f'&nil=SI&fmt=html&ano={dt_start.year}&mes={dt_start.month:02d}&day={dt_start.day:02d}'
               f'&hora={dt_start.hour:02d}&anof={dt_end.year}&mesf={dt_end.month:02d}'
               f'&dayf={dt_end.day:02d}&horaf={dt_end.hour:02d}&minf={dt_end.minute:02d}&send=send')
        return url

    def fetch_single(self, station_code):
        info = self.stations.get(station_code)
        if not info:
            return station_code, station_code, '', {}, ''
        name, region = info['name'], info['region']

        session = create_session()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            resp = session.get(self._make_url(station_code), headers=headers, timeout=15)
            if resp.status_code != 200:
                return station_code, name, region, {}, ''

            soup = BeautifulSoup(resp.content, 'html.parser')
            # 查找所有包含 "METAR" 的 <pre> 标签，取第一条有效报文
            metar_pre = None
            for pre in soup.find_all('pre'):
                text = pre.text.strip()
                if re.match(r'METAR\s+' + station_code, text):
                    if 'NIL' not in text.upper():  # 跳过 NIL 报文
                        metar_pre = pre
                        break
            if not metar_pre:
                return station_code, name, region, {}, ''

            metar_text = metar_pre.text.strip()

            # metar_text = metar_pre.text.strip()
            obs_time, temp, dew, wind_dir_deg, wind_speed = self._parse_metar(metar_text)

            if temp is None:
                return station_code, name, region, {}, ''

            # 计算湿度
            humidity = self._calc_rh(temp, dew) if dew is not None else 'N/A'
            # 风向转换
            wind_dir = self._wind_dir_to_16(wind_dir_deg) if wind_dir_deg is not None else ('VRB' if wind_dir_deg is None else 'N/A')

            weather_data = {
                '瞬时温度': str(temp),
                '相对湿度': humidity,
                '1小时降水': 'N/A',    # METAR 无降水
                '2分钟平均风向': wind_dir,
                '2分钟平均风速': str(wind_speed) if wind_speed else 'N/A',
            }

            # 时间转换 (UTC -> CST)
            display_time = 'N/A'
            if obs_time:
                try:
                    # 从 obs_time 提取 day, hour, minute
                    parts = obs_time.split(' ')
                    day = int(parts[0])
                    hour, minute = map(int, parts[1].split(':')[:2])
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    # 以当前月为基准，构造日期（安全方法：用1号+天数偏移）
                    first_day = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    dt_utc = first_day + datetime.timedelta(days=day - 1)
                    dt_utc = dt_utc.replace(hour=hour, minute=minute)
                    # 如果构造的时间在未来，则回退一天（可能是上个月）
                    if dt_utc > now_utc:
                        dt_utc -= datetime.timedelta(days=1)
                    # 转换为北京时间
                    dt_cst = dt_utc.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                    display_time = dt_cst.strftime('%Y-%m-%d %H:%M')
                except Exception:
                    pass

            return station_code, name, region, weather_data, display_time
        except Exception:
            return station_code, name, region, {}, ''
        finally:
            session.close()
# ================== 工作线程 ==================
