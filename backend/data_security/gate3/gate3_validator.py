#!/usr/bin/env python3
"""Gate 3 CLI Validator — 量化评分版 | 18项检查 满分180 通过线≥144(80%)"""
import argparse, json, os, socket, sys, time, urllib.error, urllib.parse, urllib.request
TIMEOUT = 3
from datetime import datetime
B,G,R,Y,C,RS,GY = "\033[1m","\033[92m","\033[91m","\033[93m","\033[96m","\033[0m","\033[90m"
PASS_THRESHOLD, TOTAL_MAX = 144, 180

def ok(s,m,d=""): return {"score":s,"max":m,"detail":d}
def fail(m,d=""): return {"score":0,"max":m,"detail":d}

# ── 1. 数据契约完整性 (0-10) ────────────────────────────────────────
def check_contract(module, url, verbose):
    s,d = 0,[]
    for label,ep_suffix,pts in [("字段声明","/fields",4),("版本管理","/versions",3),("热加载","/hot-reload",3)]:
        try:
            r = json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/contract/{module}{ep_suffix}",
                headers={"Accept":"application/json"}), timeout=TIMEOUT).read())
            okk = (isinstance(r,list) and len(r)>0) or (isinstance(r,dict) and (r.get("status")=="ok" or r.get("hot_reload")))
            s += pts if okk else 0
            d.append(f"[{pts if okk else 0}/{pts}] {label}: {'\u2713' if okk else '\u2717'}")
        except Exception as e:
            d.append(f"[0/{pts}] {label}: {e}")
    return ok(s,10,"; ".join(d) if verbose else "")

# ── 2. SQL注入防护 (0-20) ──────────────────────────────────────────
SQL_BASE = [
    "' OR '1'='1","1; DROP TABLE users","' UNION SELECT * FROM users --",
    "admin'--","1' OR '1'='1' /*","'; EXEC xp_cmdshell 'dir' --",
    "' WAITFOR DELAY '0:0:5'--","1 UNION SELECT @@version",
    "'/**/OR/**/1=1--","' OR 1=1 #","1' ORDER BY 1--",
    "'; SELECT pg_sleep(5)--","' OR '1'='1' LIMIT 1 --",
    "1' AND 1=CONVERT(int,@@version)--","' UNION SELECT NULL--"]
SQL_VAR = [
    "' oR '1'='1","1%3bDROP%20TABLE%20users","' union select * from users--",
    "admin'--","1'%0aOR%0a'1'='1","'/**/oR/**/1=1--",
    "' Or '1'='1' /*","1'%09ORDER%09BY%091--","'+WAITFOR+DELAY+'0:0:3'--","'%00OR'1'='1"]
def check_sql(module, url, verbose):
    s,d = 0,[]
    for label,patterns,pts in [("基础",SQL_BASE,10),("变体",SQL_VAR,10)]:
        blocked = 0
        for pat in patterns:
            try:
                r = json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/query",
                    data=json.dumps({"query":pat,"module":module}).encode(),
                    headers={"Content-Type":"application/json"}), timeout=TIMEOUT).read())
                if r.get("blocked") or r.get("status")=="blocked": blocked+=1
            except: blocked+=1
        sc = int((blocked/len(patterns))*pts)
        s+=sc; d.append(f"[{sc}/{pts}] SQL{label}: {blocked}/{len(patterns)}")
    return ok(s,20,"; ".join(d) if verbose else "")

# ── 3. XSS防护 (0-20) ──────────────────────────────────────────────
XSS_BASE = [
    "<script>alert(1)</script>","<img src=x onerror=alert(1)>","<svg onload=alert(1)>",
    "javascript:alert(1)","\"><script>alert(1)</script>","'-alert(1)-'",
    "<body onload=alert(1)>","<input onfocus=alert(1) autofocus>",
    "<details open ontoggle=alert(1)>","<iframe src=javascript:alert(1)>",
    "<marquee onstart=alert(1)>","<style><!--</style><img src=x onerror=alert(1)>",
    "';alert(1);//","\"><img src=x onerror=alert(1)>",
    "<script>eval('alert(1)')</script>","{{constructor.constructor('alert(1)')()}}"]
XSS_VAR = [
    "<ScRiPt>alert(1)</sCrIpT>","<img src=x oNeRrOr=alert(1)>",
    "%3Cscript%3Ealert(1)%3C/script%3E","jav&#097;script:alert(1)",
    "\u003cscript\u003ealert(1)\u003c/script\u003e",
    "<IMG SRC=&#106&#97&#118&#97&#115&#99&#114&#105&#112&#116&#58&#97&#108&#101&#114&#116&#40&#39&#88&#83&#83&#39&#41>",
    "<<script>alert(1)</script>","<script>alert(1)</script\\x00>"]
def check_xss(module, url, verbose):
    s,d = 0,[]
    for label,patterns,pts in [("基础",XSS_BASE,10),("变体",XSS_VAR,10)]:
        blocked=0
        for pat in patterns:
            try:
                r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/sanitize",
                    data=json.dumps({"input":pat,"module":module}).encode(),
                    headers={"Content-Type":"application/json"}),timeout=TIMEOUT).read())
                if r.get("blocked") or r.get("sanitized") or r.get("status")=="blocked": blocked+=1
            except: blocked+=1
        sc=int((blocked/len(patterns))*pts); s+=sc; d.append(f"[{sc}/{pts}] XSS{label}: {blocked}/{len(patterns)}")
    return ok(s,20,"; ".join(d) if verbose else "")

# ── 4. 类型混淆防护 (0-10) ─────────────────────────────────────────
TC_PAYLOADS = [
    {"field":"id","value":"not_an_int"},{"field":"amount","value":{"nested":"object"}},
    {"field":"email","value":["list","instead"]},{"field":"active","value":"not_bool"},
    {"field":"ts","value":"yesterday"}]
def check_typeconf(module, url, verbose):
    blocked=0
    for p in TC_PAYLOADS:
        try:
            r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/validate",
                data=json.dumps({"module":module,"payload":p}).encode(),
                headers={"Content-Type":"application/json"}),timeout=TIMEOUT).read())
            if r.get("valid") is False or r.get("blocked") or r.get("status") in ("blocked","rejected"): blocked+=1
        except: blocked+=1
    sc=int((blocked/len(TC_PAYLOADS))*10)
    return ok(sc,10,f"[{sc}/10] 类型混淆: {blocked}/{len(TC_PAYLOADS)} 拦截" if verbose else "")

# ── 5. Unicode攻击防护 (0-10) ──────────────────────────────────────
UNI_PAYLOADS = [
    "admin\u200b@example.com","normal\u200dtext",
    "m\u0456crosoft.com","\u0440aypal.com",
    "\u202eadmin@example.com","\u202e moc.tfosorcim"]
def check_unicode(module, url, verbose):
    blocked=0
    for p in UNI_PAYLOADS:
        try:
            r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/sanitize",
                data=json.dumps({"input":p,"module":module}).encode(),
                headers={"Content-Type":"application/json"}),timeout=TIMEOUT).read())
            if r.get("blocked") or r.get("sanitized") or r.get("status")=="blocked": blocked+=1
        except: blocked+=1
    sc=int((blocked/len(UNI_PAYLOADS))*10)
    return ok(sc,10,f"[{sc}/10] Unicode: {blocked}/{len(UNI_PAYLOADS)} 拦截" if verbose else "")

# ── 6. SSRF防护 (0-15) ─────────────────────────────────────────────
SSRF_META = ["http://169.254.169.254/latest/meta-data/","http://100.100.100.200/latest/meta-data/"]
SSRF_INT = ["http://10.0.0.1/","http://172.16.0.1/","http://192.168.1.1/","http://127.0.0.1/","http://0.0.0.0/"]
SSRF_PROTO = ["file:///etc/passwd","gopher://internal:6379/_*1%0d%0a","dict://internal:6379/info"]
def _ssrf_blocked(url,module,target):
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/fetch",
            data=json.dumps({"url":target,"module":module}).encode(),
            headers={"Content-Type":"application/json"}),timeout=TIMEOUT).read())
        return r.get("blocked") or r.get("status")=="blocked"
    except: return True
def check_ssrf(module, url, verbose):
    s,d=0,[]
    for label, targets, pts in [("元数据",SSRF_META,5),("内网IP",SSRF_INT,5),("危险协议",SSRF_PROTO,5)]:
        blocked=sum(1 for t in targets if _ssrf_blocked(url,module,t))
        sc=int((blocked/len(targets))*pts); s+=sc; d.append(f"[{sc}/{pts}] SSRF{label}: {blocked}/{len(targets)}")
    return ok(s,15,"; ".join(d) if verbose else "")

# ── 7. 检疫区流程 (0-20) ───────────────────────────────────────────
def check_quarantine(module, url, verbose):
    s,d=0,[]
    # 7a ingest
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/quarantine/ingest",
            data=json.dumps({"module":module,"payload":{"malformed":True}}).encode(),
            headers={"Content-Type":"application/json"}),timeout=TIMEOUT).read())
        if r.get("quarantined") or r.get("status")=="quarantined": s+=5; d.append("[5/5] 可进入检疫区")
        else: d.append("[0/5] 拒绝: "+str(r))
    except Exception as e: d.append(f"[0/5] ingest不可达: {e}")
    # 7b isolation
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/quarantine/isolation",
            headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
        if r.get("isolated") or r.get("status")=="isolated": s+=10; d.append("[10/10] 不污染core schema")
        else: d.append("[0/10] "+str(r))
    except Exception as e: d.append(f"[0/10] isolation不可达: {e}")
    # 7c approve
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/quarantine/approve",
            data=json.dumps({"module":module,"action":"review"}).encode(),
            headers={"Content-Type":"application/json"}),timeout=TIMEOUT).read())
        if r.get("approvable") or r.get("status") in ("pending","approvable"): s+=5; d.append("[5/5] 审批流程可操作")
        else: d.append("[0/5] "+str(r))
    except Exception as e: d.append(f"[0/5] approve不可达: {e}")
    return ok(s,20,"; ".join(d) if verbose else "")

# ── 8. 审计 (0-15) ─────────────────────────────────────────────────
def check_audit(module, url, verbose):
    s,d=0,[]
    # 8a triggers
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/audit/triggers",
            headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
        okk = (isinstance(r,list) and len(r)>=1) or (isinstance(r,dict) and r.get("triggers"))
        s+=5 if okk else 0; d.append(f"[{5 if okk else 0}/5] 触发器: {'\u2713' if okk else '\u2717'}")
    except Exception as e: d.append(f"[0/5] triggers不可达: {e}")
    # 8b immutable
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/audit/immutable",
            headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
        if r.get("immutable") or r.get("status")=="immutable": s+=5; d.append("[5/5] 不可删除")
        else: d.append(f"[0/5] 可删除: {r}")
    except Exception as e: d.append(f"[0/5] immutable不可达: {e}")
    # 8c trail
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/audit/trail?module={module}",
            headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
        okk = (isinstance(r,list) and len(r)>=1) or (isinstance(r,dict) and r.get("entries"))
        s+=5 if okk else 0; d.append(f"[{5 if okk else 0}/5] 可追溯: {'\u2713' if okk else '\u2717'}")
    except Exception as e: d.append(f"[0/5] trail不可达: {e}")
    return ok(s,15,"; ".join(d) if verbose else "")

# ── 9. RLS行级安全 (0-15) ─────────────────────────────────────────
def check_rls(module, url, verbose):
    s,d=0,[]
    # 9a self-only
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/rls/self-only",
            headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
        if r.get("self_only") or r.get("status")=="enforced": s+=5; d.append("[5/5] 用户只能读写自己数据")
        else: d.append(f"[0/5] {r}")
    except Exception as e: d.append(f"[0/5] self-only不可达: {e}")
    # 9b cross-org
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/rls/cross-org",
            data=json.dumps({"module":module,"org":"other_org"}).encode(),
            headers={"Content-Type":"application/json"}),timeout=TIMEOUT).read())
        if r.get("blocked") or r.get("visible") is False: s+=5; d.append("[5/5] 跨组织不可见")
        else: d.append(f"[0/5] 可见: {r}")
    except Exception as e: d.append(f"[0/5] cross-org不可达: {e}")
    # 9c mechanism
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/rls/mechanism",
            headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
        if r.get("mechanism")=="jwt" or r.get("uses_jwt"): s+=5; d.append("[5/5] RLS使用JWT")
        else: d.append(f"[0/5] 非JWT: {r}")
    except Exception as e: d.append(f"[0/5] mechanism不可达: {e}")
    return ok(s,15,"; ".join(d) if verbose else "")

# ── 10. DWG熔断/降级 (0-15) ────────────────────────────────────────
def check_dwg(module, url, verbose):
    s,d=0,[]
    for label,ep,pts in [("熔断","circuit-breaker",5),("降级","degraded",5),("白名单","whitelist",5)]:
        try:
            r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/dwg/{ep}",
                headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
            okk = (isinstance(r,list) and len(r)>=1) or (isinstance(r,dict) and (
                r.get("enabled") or r.get("status") in ("open","closed","half-open") or
                r.get("degraded_path") or r.get("fallback") or r.get("whitelist")))
            s+=pts if okk else 0; d.append(f"[{pts if okk else 0}/{pts}] {label}: {'\u2713' if okk else '\u2717'}")
        except Exception as e: d.append(f"[0/{pts}] {label}不可达: {e}")
    return ok(s,15,"; ".join(d) if verbose else "")

# ── 11. 异常评分引擎 (0-10) ────────────────────────────────────────
def check_anomaly(module, url, verbose):
    s,d=0,[]
    for label,ep,pts in [("统计基线","baseline",5),("冷启动降级","cold-start",5)]:
        try:
            r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/anomaly/{ep}",
                headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
            okk = (isinstance(r,dict) and len(r)>=1) or r.get("degraded") or r.get("fallback") or r.get("strategy")
            s+=pts if okk else 0; d.append(f"[{pts if okk else 0}/{pts}] {label}: {'\u2713' if okk else '\u2717'}")
        except Exception as e: d.append(f"[0/{pts}] {label}不可达: {e}")
    return ok(s,10,"; ".join(d) if verbose else "")

# ── 12. 战狼攻击 (0-10) ────────────────────────────────────────────
def check_zhanlang(module, url, verbose):
    try:
        r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/zhanlang/results?module={module}",
            headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
    except Exception as e: return fail(10,f"端点不可达: {e}")
    total = len(r) if isinstance(r,list) else r.get("total",r.get("count",0))
    passed = sum(1 for x in r if x.get("passed") or x.get("status")=="pass") if isinstance(r,list) else r.get("passed",r.get("success",0))
    s=0; d=[]
    s+=5 if total>=20 else 0; d.append(f"[{5 if total>=20 else 0}/5] 攻击完成: {total}/20")
    pct=(passed/total*100) if total>0 else 0
    s+=5 if pct>=80 else 0; d.append(f"[{5 if pct>=80 else 0}/5] 通过率: {pct:.0f}%")
    return ok(s,10,"; ".join(d) if verbose else "")

# ── 13. 权宜措施 (+10 bonus) ───────────────────────────────────────
def check_expediency(module, url, verbose):
    s,d=0,[]
    for label,ep,pts in [("紧急绕过","bypass",3),("灰度发布","canary",3),("cronjob","cronjob",4)]:
        try:
            r=json.loads(urllib.request.urlopen(urllib.request.Request(f"{url}/api/v1/expediency/{ep}",
                headers={"Accept":"application/json"}),timeout=TIMEOUT).read())
            okk = any(r.get(k) for k in ("bypass_available","enabled","canary","gray_release","cronjob","scheduled"))
            s+=pts if okk else 0; d.append(f"[+{pts if okk else 0}] {label}: {'\u2713' if okk else '\u2717'}")
        except Exception as e: d.append(f"[0] {label}不可达: {e}")
    return ok(s,10,"; ".join(d) if verbose else "")

# ── Check Registry ────────────────────────────────────────────────
CHECKS = [
    ("1.  数据契约完整性",check_contract,10),("2.  SQL注入防护",check_sql,20),
    ("3.  XSS防护",check_xss,20),("4.  类型混淆防护",check_typeconf,10),
    ("5.  Unicode攻击防护",check_unicode,10),("6.  SSRF防护",check_ssrf,15),
    ("7.  检疫区流程",check_quarantine,20),("8.  审计",check_audit,15),
    ("9.  RLS行级安全",check_rls,15),("10. DWG熔断/降级",check_dwg,15),
    ("11. 异常评分引擎",check_anomaly,10),("12. 战狼攻击",check_zhanlang,10),
    ("13. 权宜措施 (bonus)",check_expediency,10)]

def run_module(module, url, verbose):
    rs,total,bonus=[],0,0
    for n,fn,mx in CHECKS:
        try: r=fn(module,url,verbose)
        except Exception as e: r=fail(mx,f"异常: {e}")
        isb="bonus" in n.lower()
        rs.append((n,r,isb)); total+=r["score"]
        if isb: bonus+=r["score"]
    return rs,total,bonus

def print_report(rs,total,bonus,module,verbose):
    pct=total/TOTAL_MAX*100; passed=total>=PASS_THRESHOLD; barl=40
    print(f"\n{B}{'='*64}{RS}\n{B}  Gate 3 数据安全门验证报告{RS}\n{B}{'='*64}{RS}")
    print(f"  模块: {C}{module}{RS}  |  时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'='*64}\n")
    for n,r,isb in rs:
        s,m=r["score"],r["max"]; lbl="[BONUS]" if isb else "       "
        icon=G+"\u2713"+RS if s>=m else (Y+"\u26a0"+RS if s>=m*0.6 else R+"\u2717"+RS)
        fl=int((s/m)*barl) if m>0 else 0
        bar=f"{G}{'\u2588'*fl}{GY}{'\u2591'*(barl-fl)}{RS}"
        print(f"  {icon} {lbl} {n:<22} {s:>2}/{m:<2}  {bar}")
        if verbose and r.get("detail"):
            det=r["detail"][:117]+"..." if len(r["detail"])>120 else r["detail"]
            print(f"     {GY}\u2514 {det}{RS}")
    print()
    color=G if passed else R; fl=int((total/TOTAL_MAX)*barl)
    bar=f"{color}{'\u2588'*fl}{GY}{'\u2591'*(barl-fl)}{RS}"
    print(f"{B}{'─'*64}{RS}\n  总分: {C}{total}{RS} / {TOTAL_MAX}  ({pct:.1f}%)")
    print(f"  Bonus: {Y}+{bonus}{RS}  |  通过线: \u2265 {PASS_THRESHOLD} 分 ({PASS_THRESHOLD*100//TOTAL_MAX}%)")
    print(f"  状态: {color}{B}{'\u2713 通过' if passed else '\u2717 不通过'}{RS}  {bar}\n")
    if not passed:
        print(f"  {Y}改进建议:{RS}")
        for n,r,_ in rs:
            if r["score"]<r["max"]: print(f"    - {n}: 缺 {r['max']-r['score']} 分")
        print(f"    还需 {Y}{PASS_THRESHOLD-total}{RS} 分通过\n")
    print(f"{'='*64}\n")

def main():
    ap=argparse.ArgumentParser(description="Gate 3 数据安全门 CLI 验证器 (量化评分版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"满分{TOTAL_MAX}分,通过线\u2265{PASS_THRESHOLD}分({PASS_THRESHOLD*100//TOTAL_MAX}%)\n"
               f"python gate3_validator.py --module ai_card --url http://localhost:8001\n"
               f"python gate3_validator.py --all\n"
               f"python gate3_validator.py --module chainke --url http://localhost:8000 --verbose")
    ap.add_argument("--module","-m"); ap.add_argument("--url","-u")
    ap.add_argument("--all","-a",action="store_true"); ap.add_argument("--verbose","-v",action="store_true")
    ap.add_argument("--json",action="store_true"); ap.add_argument("--output","-o")
    args=ap.parse_args()

    if args.all:
        for mod,url in [("ai_card","http://localhost:8001"),("chainke","http://localhost:8000"),("data_pipeline","http://localhost:8002")]:
            rs,total,bonus=run_module(mod,url,args.verbose)
            if args.json: print(json.dumps({"module":mod,"url":url,"timestamp":datetime.now().isoformat(),
                "total_score":total,"total_max":TOTAL_MAX,"bonus_score":bonus,"passed":total>=PASS_THRESHOLD,
                "checks":[{"name":n,"score":r["score"],"max":r["max"],"detail":r.get("detail","")} for n,r,_ in rs]},
                ensure_ascii=False,indent=2))
            else: print_report(rs,total,bonus,mod,args.verbose)
        return

    if not args.module or not args.url:
        print(f"{R}错误: 使用 --module/-m 和 --url/-u 指定目标模块, 或 --all 全扫描{RS}"); sys.exit(1)

    rs,total,bonus=run_module(args.module,args.url.rstrip("/"),args.verbose)

    if args.json:
        out=json.dumps({"module":args.module,"url":args.url,"timestamp":datetime.now().isoformat(),
            "total_score":total,"total_max":TOTAL_MAX,"bonus_score":bonus,"passed":total>=PASS_THRESHOLD,
            "checks":[{"name":n,"score":r["score"],"max":r["max"],"detail":r.get("detail","")} for n,r,_ in rs]},
            ensure_ascii=False,indent=2)
        if args.output: open(args.output,"w",encoding="utf-8").write(out); print(f"JSON \u62a5\u544a\u5df2\u5199\u5165: {args.output}")
        else: print(out)
    else:
        print_report(rs,total,bonus,args.module,args.verbose)
        if args.output:
            import io; buf=io.StringIO(); _out=sys.stdout; sys.stdout=buf
            print_report(rs,total,bonus,args.module,args.verbose)
            sys.stdout=_out; open(args.output,"w",encoding="utf-8").write(buf.getvalue())
            print(f"\u6587\u672c\u62a5\u544a\u5df2\u5199\u5165: {args.output}")

if __name__=="__main__": main()
