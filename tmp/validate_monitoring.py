import yaml
import json
import os
import sys

base = r"D:\链客宝"
files_yaml = [
    os.path.join(base, r"deploy\prometheus\prometheus.yml"),
    os.path.join(base, r"deploy\prometheus\alerts\liankebao_alerts.yml"),
    os.path.join(base, r"deploy\alertmanager\alertmanager.yml"),
    os.path.join(base, r"deploy\grafana\datasources\prometheus.yml"),
    os.path.join(base, r"deploy\grafana\grafana-dashboards.yaml"),
    os.path.join(base, r"deploy\docker-compose.monitoring.yml"),
]
files_json = [
    os.path.join(base, r"deploy\grafana\dashboards\chainke_overview.json"),
]

ok = True
print("=" * 55)
print("  链客宝 监控配置文件语法验证")
print("=" * 55)
print()

for f in files_yaml:
    if not os.path.isfile(f):
        print(f"  WARN 不存在: {f}")
        continue
    try:
        with open(f, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        print(f"  OK YAML: {os.path.basename(f)}")
        if isinstance(data, dict):
            if "scrape_configs" in data:
                print(f"    -> scrape_configs: {len(data['scrape_configs'])} targets")
                for s in data["scrape_configs"]:
                    print(
                        f"      - {s['job_name']}: {s['static_configs'][0]['targets']}"
                    )
            if "route" in data:
                print(f"    -> route/group_by: {data['route']['group_by']}")
            if "receivers" in data:
                print(f"    -> receivers: {len(data['receivers'])}")
                for r in data["receivers"]:
                    print(
                        f"      - {r['name']}: {len(r.get('webhook_configs', []))} webhooks"
                    )
            if "services" in data:
                print(f"    -> services: {list(data['services'].keys())}")
            if "datasources" in data:
                print(f"    -> datasources: {len(data['datasources'])}")
                for d in data["datasources"]:
                    print(f"      - {d['name']} ({d['type']}) -> {d['url']}")
            if "providers" in data:
                print(f"    -> providers: {len(data['providers'])}")
                for p in data["providers"]:
                    print(f"      - {p['name']}: path={p['options']['path']}")
            if "groups" in data:
                print(f"    -> alert groups: {len(data['groups'])}")
                for g in data["groups"]:
                    print(f"      - {g['name']}: {len(g['rules'])} rules")
                    for rule in g["rules"]:
                        print(
                            f"        * {rule['alert']} (severity={rule['labels']['severity']}, for={rule['for']})"
                        )
    except yaml.YAMLError as e:
        print(f"  FAIL YAML: {f}: {e}")
        ok = False

print()
for f in files_json:
    if not os.path.isfile(f):
        print(f"  WARN 不存在: {f}")
        continue
    try:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        print(f"  OK JSON: {os.path.basename(f)}")
        if "title" in data:
            print(f'    -> Dashboard: "{data["title"]}"')
        if "panels" in data:
            print(f"    -> panels: {len(data['panels'])}")
            for p in data["panels"]:
                print(f'      - Panel {p["id"]}: "{p["title"]}" ({p["type"]})')
        if "schemaVersion" in data:
            print(f"    -> schemaVersion: {data['schemaVersion']}")
    except json.JSONDecodeError as e:
        print(f"  FAIL JSON: {f}: {e}")
        ok = False

print()
if ok:
    print("ALL OK - 所有配置文件语法验证通过!")
else:
    print("SOME FAILED - 部分配置文件存在语法错误!")
    sys.exit(1)
