# -*- coding: utf-8 -*-
"""East Asia Weather Monitor - Web Version"""
import sys, os, re, datetime, json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, render_template, request
from apscheduler.schedulers.background import BackgroundScheduler

from weather_crawler import (
    NMCSource, JMASource, KMASource, CWASource, SynopSource,
    load_all_stations, ELEMENTS, ELEMENT_UNITS
)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
STATIONS = load_all_stations()

class WeatherDataManager:
    def __init__(self):
        self.nmc = NMCSource(STATIONS["nmc"])
        self.jma = JMASource(STATIONS["jma"])
        self.kma = KMASource(STATIONS["kma"])
        self.cwa = CWASource(STATIONS["cwa"])
        self.synop = SynopSource(STATIONS["synop"])
        self._cached_result = []
        self._cached_stats = []
        self._last_update = None
        self._total_stations = sum(len(v) for v in STATIONS.values())

    def fetch_all(self):
        results = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for sid in self.nmc.station_info:
                futures.append(("NMC", executor.submit(self.nmc.fetch_single, sid)))
            for jcode in self.jma.stations:
                futures.append(("JMA", executor.submit(self.jma.fetch_single, jcode)))
            for kcode in self.kma.stations:
                futures.append(("KMA", executor.submit(self.kma.fetch_single, kcode)))
            for ccode in self.cwa.stations:
                futures.append(("CWA", executor.submit(self.cwa.fetch_single, ccode)))
            for scode in self.synop.stations:
                futures.append(("SYNOP", executor.submit(self.synop.fetch_single, scode)))
            for src, fut in futures:
                try:
                    sid2, city, province, data, time_str = fut.result()
                    results[sid2] = {"city": city, "region": province, "data": data, "time": time_str or "N/A"}
                except Exception:
                    pass
        stations_list = [{"station_id": k, **v} for k, v in results.items()]
        self._cached_result = stations_list
        self._cached_stats = self._compute_stats(stations_list)
        self._last_update = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return stations_list

    @staticmethod
    def _parse_num(val):
        if val in (None, "", "N/A", "9999"):
            return None
        try:
            f = float(val)
            return None if f == 9999.0 else f
        except: pass
        try:
            nums = re.findall(r"-?\d+\.?\d*", str(val))
            return float(nums[0]) if nums else None
        except: return None

    @staticmethod
    def _parse_precip(val):
        if not val or val == "N/A": return None, None
        m = re.search(r"([\d.]+)\s*mm", str(val))
        if not m: return None, None
        num = float(m.group(1))
        pm = re.search(r"\((\d+)h\)", str(val))
        return num, int(pm.group(1)) if pm else 1

    def _compute_stats(self, stations):
        stats, time_records = {}, {}
        now = datetime.datetime.now()
        for rec in stations:
            ts = rec.get("time", "")
            if not ts or ts == "N/A": continue
            try:
                rt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M")
                if (now - rt).total_seconds() > 21600: continue
            except: continue
            reg = rec.get("region", "")
            if not reg: continue
            if reg not in stats:
                stats[reg] = {"max_temp": (None,None),"min_temp": (None,None),"max_hum": (None,None),"min_hum": (None,None),"max_precip": (None,None),"max_wind": (None,None)}
                time_records[reg] = []
            time_records[reg].append(ts)
            t = self._parse_num(rec.get("data",{}).get("瞬时温度"))
            h = self._parse_num(rec.get("data",{}).get("相对湿度"))
            pv,_ = self._parse_precip(rec.get("data",{}).get("1小时降水"))
            w = self._parse_num(rec.get("data",{}).get("2分钟平均风速"))
            nm = rec.get("city", rec.get("station_id",""))
            if t is not None:
                if stats[reg]["max_temp"][0] is None or t > stats[reg]["max_temp"][0]: stats[reg]["max_temp"] = (t, nm)
                if stats[reg]["min_temp"][0] is None or t < stats[reg]["min_temp"][0]: stats[reg]["min_temp"] = (t, nm)
            if h is not None:
                if stats[reg]["max_hum"][0] is None or h > stats[reg]["max_hum"][0]: stats[reg]["max_hum"] = (h, nm)
                if stats[reg]["min_hum"][0] is None or h < stats[reg]["min_hum"][0]: stats[reg]["min_hum"] = (h, nm)
            if pv is not None:
                if stats[reg]["max_precip"][0] is None or pv > stats[reg]["max_precip"][0]: stats[reg]["max_precip"] = (pv, nm)
            if w is not None:
                if stats[reg]["max_wind"][0] is None or w > stats[reg]["max_wind"][0]: stats[reg]["max_wind"] = (w, nm)
        result = []
        for reg, st in sorted(stats.items()):
            times = time_records.get(reg, [])
            ct = Counter(times).most_common(1)[0][0] if times else "N/A"
            fmt = lambda v, u: f"{v[0]}{u} ({v[1]})" if v[0] is not None else "N/A"
            result.append({"region": reg, "max_temp": fmt(st["max_temp"],"C"), "min_temp": fmt(st["min_temp"],"C"),
                "max_hum": fmt(st["max_hum"],"%"), "min_hum": fmt(st["min_hum"],"%"),
                "max_precip": fmt(st["max_precip"],"mm"), "max_wind": fmt(st["max_wind"],"m/s"), "common_time": ct})
        return result

manager = WeatherDataManager()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    try:
        stations = manager.fetch_all()
        return jsonify({"success": True, "stations": stations, "stats": manager._cached_stats,
            "total": len(stations), "update_time": manager._last_update})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/data")
def api_data():
    return jsonify({"stations": manager._cached_result, "stats": manager._cached_stats,
        "update_time": manager._last_update or "No data yet"})

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip().lower()
    if not q or not manager._cached_result:
        return jsonify({"stations": manager._cached_result})
    filtered = [s for s in manager._cached_result
        if q in str(s.get("station_id","")).lower() or q in s.get("city","").lower() or q in s.get("region","").lower()]
    return jsonify({"stations": filtered})

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    
    def scheduled_fetch():
        with app.app_context():
            try:
                manager.fetch_all()
                print(f"[AutoFetch] Data updated at {manager._last_update}")
            except Exception as e:
                print(f"[AutoFetch] Error: {e}")
    
    scheduler.add_job(scheduled_fetch, "interval", minutes=30, id="weather_fetch")
    scheduler.start()
    print("Auto-fetch every 30 minutes started.")
    
    print("Fetching initial data...")
    scheduled_fetch()
    
    print("=" * 50)
    print("  East Asia Weather Monitor - Web Edition")
    print("  URL: http://127.0.0.1:5000")
    print("  Auto-fetch: every 30 minutes")
    print("  Ctrl+C to stop")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5000)
