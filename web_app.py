# -*- coding: utf-8 -*-
"""East Asia Weather Monitor - Web Version (optimized)"""
import sys, os, re, datetime, json, hashlib, threading, time
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, render_template, request, Response, make_response

from weather_crawler import (
    NMCSource, JMASource, KMASource, CWASource, SynopSource, MetarSource,
    load_all_stations, ELEMENTS, ELEMENT_UNITS
)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400
STATIONS = load_all_stations()


class WeatherDataManager:
    def __init__(self):
        self.nmc = NMCSource(STATIONS["nmc"])
        self.jma = JMASource(STATIONS["jma"])
        self.kma = KMASource(STATIONS["kma"])
        self.cwa = CWASource(STATIONS["cwa"])
        self.synop = SynopSource(STATIONS["synop"])
        self.metar = MetarSource(STATIONS.get("metar", {}))
        self._cached_result = []
        self._cached_stats = []
        self._last_update = None
        self._total_stations = sum(len(v) for v in STATIONS.values()) + len(STATIONS.get("metar", {}))
        # 预序列化 JSON 缓存（每次 fetch 后更新一次，避免每个请求重复 jsonify）
        self._cached_data_payload = b'{"stations":[],"stats":[],"update_time":"No data yet"}'
        self._cached_data_etag = '"empty"'
        self._fetching = False
        self._fetch_lock = threading.Lock()

    def fetch_all(self):
        # 防止重复并发抓取
        with self._fetch_lock:
            if self._fetching:
                return self._cached_result
            self._fetching = True

        try:
            results = {}
            t0 = time.time()
            # 提高并发：50 个 worker 同时跑（IO 密集任务，主要瓶颈是网络）
            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = []
                for sid in self.nmc.station_info:
                    futures.append(executor.submit(self.nmc.fetch_single, sid))
                for jcode in self.jma.stations:
                    futures.append(executor.submit(self.jma.fetch_single, jcode))
                for kcode in self.kma.stations:
                    futures.append(executor.submit(self.kma.fetch_single, kcode))
                for ccode in self.cwa.stations:
                    futures.append(executor.submit(self.cwa.fetch_single, ccode))
                for scode in self.synop.stations:
                    futures.append(executor.submit(self.synop.fetch_single, scode))
                for mcode in self.metar.stations:
                    futures.append(executor.submit(self.metar.fetch_single, mcode))

                for fut in as_completed(futures):
                    try:
                        sid2, city, province, data, time_str = fut.result(timeout=30)
                        if data:
                            results[sid2] = {"city": city, "region": province, "data": data, "time": time_str or "N/A"}
                    except Exception:
                        pass

            elapsed = time.time() - t0
            stations_list = [{"station_id": k, **v} for k, v in results.items()]
            self._cached_result = stations_list
            self._cached_stats = self._compute_stats(stations_list)
            self._last_update = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 预序列化 JSON 字符串 + ETag，下次 /api/data 直接返回，零开销
            payload = json.dumps({
                "stations": stations_list,
                "stats": self._cached_stats,
                "update_time": self._last_update,
            }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._cached_data_payload = payload
            self._cached_data_etag = '"' + hashlib.md5(payload).hexdigest()[:16] + '"'

            print(f"[Fetch] {len(stations_list)} stations in {elapsed:.1f}s", flush=True)
            return stations_list
        finally:
            self._fetching = False

    @staticmethod
    def _parse_num(val):
        if val in (None, "", "N/A", "9999"):
            return None
        try:
            f = float(val)
            return None if f == 9999.0 else f
        except:
            pass
        try:
            nums = re.findall(r"-?\d+\.?\d*", str(val))
            return float(nums[0]) if nums else None
        except:
            return None

    @staticmethod
    def _parse_precip(val):
        if not val or val == "N/A":
            return None, None
        m = re.search(r"([\d.]+)\s*mm", str(val))
        if not m:
            try:
                return float(val), 1
            except:
                return None, None
        num = float(m.group(1))
        pm = re.search(r"\((\d+)h\)", str(val))
        return num, int(pm.group(1)) if pm else 1

    def _compute_stats(self, stations):
        stats, time_records = {}, {}
        now = datetime.datetime.now()
        for rec in stations:
            ts = rec.get("time", "")
            if not ts or ts == "N/A":
                continue
            try:
                rt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M")
                if (now - rt).total_seconds() > 21600:
                    continue
            except:
                continue
            reg = rec.get("region", "")
            if not reg:
                continue
            if reg not in stats:
                stats[reg] = {"max_temp": (None, None), "min_temp": (None, None),
                              "max_hum": (None, None), "min_hum": (None, None),
                              "max_precip": (None, None), "max_wind": (None, None)}
                time_records[reg] = []
            time_records[reg].append(ts)
            d = rec.get("data", {})
            t = self._parse_num(d.get("瞬时温度"))
            h = self._parse_num(d.get("相对湿度"))
            pv, _ = self._parse_precip(d.get("1小时降水"))
            w = self._parse_num(d.get("2分钟平均风速"))
            nm = rec.get("city", rec.get("station_id", ""))
            if t is not None:
                if stats[reg]["max_temp"][0] is None or t > stats[reg]["max_temp"][0]:
                    stats[reg]["max_temp"] = (t, nm)
                if stats[reg]["min_temp"][0] is None or t < stats[reg]["min_temp"][0]:
                    stats[reg]["min_temp"] = (t, nm)
            if h is not None:
                if stats[reg]["max_hum"][0] is None or h > stats[reg]["max_hum"][0]:
                    stats[reg]["max_hum"] = (h, nm)
                if stats[reg]["min_hum"][0] is None or h < stats[reg]["min_hum"][0]:
                    stats[reg]["min_hum"] = (h, nm)
            if pv is not None:
                if stats[reg]["max_precip"][0] is None or pv > stats[reg]["max_precip"][0]:
                    stats[reg]["max_precip"] = (pv, nm)
            if w is not None:
                if stats[reg]["max_wind"][0] is None or w > stats[reg]["max_wind"][0]:
                    stats[reg]["max_wind"] = (w, nm)
        result = []
        for reg, st in sorted(stats.items()):
            times = time_records.get(reg, [])
            ct = Counter(times).most_common(1)[0][0] if times else "N/A"
            fmt = lambda v, u: f"{v[0]}{u} ({v[1]})" if v[0] is not None else "N/A"
            result.append({"region": reg,
                           "max_temp": fmt(st["max_temp"], "C"),
                           "min_temp": fmt(st["min_temp"], "C"),
                           "max_hum": fmt(st["max_hum"], "%"),
                           "min_hum": fmt(st["min_hum"], "%"),
                           "max_precip": fmt(st["max_precip"], "mm"),
                           "max_wind": fmt(st["max_wind"], "m/s"),
                           "common_time": ct})
        return result


manager = WeatherDataManager()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    try:
        stations = manager.fetch_all()
        return jsonify({"success": True, "total": len(stations), "update_time": manager._last_update})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/data")
def api_data():
    # 直接返回预序列化的 bytes，比 jsonify 快 10 倍以上
    # ETag 支持浏览器条件请求（数据没变就返回 304）
    etag = manager._cached_data_etag
    if request.headers.get("If-None-Match") == etag:
        return Response(status=304)
    resp = make_response(manager._cached_data_payload)
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "private, max-age=10"
    return resp


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip().lower()
    if not q or not manager._cached_result:
        return jsonify({"stations": manager._cached_result})
    filtered = [s for s in manager._cached_result
                if q in str(s.get("station_id", "")).lower()
                or q in s.get("city", "").lower()
                or q in s.get("region", "").lower()]
    return jsonify({"stations": filtered})


@app.route("/api/status")
def api_status():
    """快速状态接口，页面初次加载用，避免拉取全量数据"""
    return jsonify({
        "total": len(manager._cached_result),
        "update_time": manager._last_update or "数据加载中…",
        "fetching": manager._fetching,
        "etag": manager._cached_data_etag,
    })


if __name__ == "__main__":
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()

    def scheduled_fetch():
        with app.app_context():
            try:
                manager.fetch_all()
                print(f"[AutoFetch] {manager._last_update}", flush=True)
            except Exception as e:
                print(f"[AutoFetch] Error: {e}", flush=True)

    scheduler.add_job(scheduled_fetch, "interval", minutes=30, id="weather_fetch")
    scheduler.start()
    print("Auto-fetch every 30 minutes started.", flush=True)

    # 首次抓取完全后台、不阻塞启动
    def delayed_first_fetch():
        time.sleep(1)
        scheduled_fetch()

    threading.Thread(target=delayed_first_fetch, daemon=True).start()

    print("=" * 50, flush=True)
    print("  East Asia Weather Monitor - Web Edition", flush=True)
    print("  URL: http://127.0.0.1:5000", flush=True)
    print("  Auto-fetch: every 30 minutes", flush=True)
    print("=" * 50, flush=True)

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)
