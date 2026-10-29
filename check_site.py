"""站点结构自检（浏览器实测，非 grep）。

三个维度，任一失败即退出码非 0：

  1. 资源可达  —— 所有 <a href> / <img src> 逐个 fetch，看真实 HTTP 状态
  2. 锚点有效  —— 每个 #anchor 在 DOM 里必须真有对应 id 元素
  3. 结构完整  —— 源码里出现的每个 id="..." 必须在渲染后的 DOM 里存在

第 3 条是专门为「内容被浏览器吞掉」这类 bug 写的。
起因：站点里有一处写成 `<code><script></code>` 的字面量，
浏览器从那个裸标签开始把后面所有内容当脚本文本吞掉，
源码 grep 完全正常（section 都在），但渲染出来的 DOM 里
「工程判断力 / 技术栈 / 联系」三个区块全部消失。
只查源码或只查资源 fetch 都发现不了 —— 必须查渲染后的 DOM。

用法：
  python -u _check_links.py http://127.0.0.1:8899/index.html
  python -u _check_links.py https://gengxuexin.github.io/
"""
import asyncio
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9360

# 站点必须存在的区块（顺序也检查）
EXPECTED_SECTIONS = [
    "strengths", "soft", "about", "projects", "how",
    "judgment", "stack", "roadmap", "contact",
]


def find_ws(port):
    for _ in range(40):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/list", timeout=2
            ) as r:
                tabs = json.loads(r.read().decode())
            for t in tabs:
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                    return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("no websocket")


async def main():
    url = sys.argv[1]
    profile = tempfile.mkdtemp(prefix="chk_")
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
         f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    failures = []
    try:
        async with websockets.connect(find_ws(PORT),
                                       max_size=64 * 1024 * 1024) as ws:
            mid = 0

            async def cdp(method, params=None):
                nonlocal mid
                mid += 1
                await ws.send(json.dumps(
                    {"id": mid, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == mid:
                        if "error" in msg:
                            raise RuntimeError(f"{method}: {msg['error']}")
                        return msg.get("result", {})

            await cdp("Page.enable")
            await cdp("Runtime.enable")
            await cdp("Network.enable")
            await cdp("Page.navigate", {"url": url})
            await asyncio.sleep(5)

            # ---------- 维度 3a：源码 vs DOM 的 id 对照 ----------
            src = await cdp("Runtime.evaluate", {
                "expression": "document.documentElement.outerHTML",
                "returnByValue": True})
            source_html = src.get("result", {}).get("value") or ""
            source_ids = set(re.findall(r'\bid="([^"]+)"', source_html))

            dom = await cdp("Runtime.evaluate", {
                "expression": """
                JSON.stringify({
                  domIds: Array.from(document.querySelectorAll('[id]'))
                            .map(e=>e.id),
                  sections: Array.from(document.querySelectorAll('section'))
                            .map(s=>s.id),
                  anchors: Array.from(document.querySelectorAll('a[href^="#"]'))
                            .map(a=>a.getAttribute('href').slice(1)),
                  scriptCount: document.querySelectorAll('script').length,
                  scriptsWithMarkup: Array.from(document.querySelectorAll('script'))
                    .filter(s=>/<\/?(?:td|tr|table|div|p|section|a|li)\b/i
                                 .test(s.textContent||''))
                    .map(s=>(s.textContent||'').slice(0,80)),
                  bodyH: document.body.scrollHeight
                })
                """, "returnByValue": True})
            d = json.loads(dom.get("result", {}).get("value") or "{}")
            dom_ids = set(d.get("domIds", []))

            missing_ids = sorted(source_ids - dom_ids)
            if missing_ids:
                failures.append(
                    f"源码里有 {len(missing_ids)} 个 id 在渲染后的 DOM 里不存在："
                    f"{missing_ids} —— 内容被浏览器吞掉了")

            if d.get("scriptsWithMarkup"):
                failures.append(
                    f"页面里有 {len(d['scriptsWithMarkup'])} 个 <script> "
                    f"包含 HTML 标记，通常意味着源码里写了裸标签："
                    f"{d['scriptsWithMarkup']}")

            print(f"源码 id {len(source_ids)} 个 / DOM id {len(dom_ids)} 个，"
                  f"丢失 {len(missing_ids)} 个", flush=True)

            # ---------- 维度 3b：区块齐全且顺序正确 ----------
            got = d.get("sections", [])
            print(f"区块: {got}", flush=True)
            if got != EXPECTED_SECTIONS:
                missing_sec = [s for s in EXPECTED_SECTIONS if s not in got]
                failures.append(
                    f"区块缺失或顺序不对：期望 {EXPECTED_SECTIONS}，实际 {got}"
                    + (f"，缺失 {missing_sec}" if missing_sec else ""))

            # ---------- 维度 2：锚点有效 ----------
            bad_anchor = []
            for a in d.get("anchors", []):
                if a not in dom_ids:
                    bad_anchor.append(a)
            if bad_anchor:
                failures.append(f"锚点指向不存在的元素：{sorted(set(bad_anchor))}")
            print(f"锚点 {len(d.get('anchors', []))} 个，失效 "
                  f"{len(set(bad_anchor))} 个", flush=True)

            # ---------- 维度 1：资源可达 ----------
            r = await cdp("Runtime.evaluate", {
                "expression": """
                JSON.stringify(Array.from(
                  document.querySelectorAll('a[href], img[src]')
                ).map(e => ({
                  tag: e.tagName,
                  text: (e.textContent||'').trim().slice(0,30),
                  href: e.getAttribute('href') || e.getAttribute('src'),
                  resolved: e.href || e.src
                })))
                """, "returnByValue": True})
            items = json.loads(r.get("result", {}).get("value") or "[]")
            print(f"\n页面共 {len(items)} 个资源链接\n", flush=True)

            bad = 0
            for it in items:
                href = it.get("href") or ""
                if href.startswith(("http://", "https://", "#", "mailto:")):
                    if "127.0.0.1" in it.get("resolved", "") or \
                       "localhost" in it.get("resolved", ""):
                        target = it["resolved"]
                    else:
                        print(f"  [外链] {it.get('text')}: {href}", flush=True)
                        continue
                else:
                    target = it.get("resolved")

                r = await cdp("Runtime.evaluate", {
                    "expression":
                        f"fetch({json.dumps(target)}).then("
                        "r=>r.status+' | '+(r.headers.get('content-type')||'-')"
                        "+' | '+(r.headers.get('content-length')||'-')"
                        ").catch(e=>'ERR:'+e.message)",
                    "awaitPromise": True, "returnByValue": True})
                res = r.get("result", {}).get("value")
                flag = "OK " if res and res.startswith("200") else "!! "
                if flag == "!! ":
                    bad += 1
                print(f"  [{flag}] {it.get('tag')}:{href}  ->  {res}",
                      flush=True)

            if bad:
                failures.append(f"{bad} 个资源不可达")

            print(f"\n资源失败 {bad} 个", flush=True)

            # ---------- 汇总 ----------
            print("\n" + "=" * 60, flush=True)
            if failures:
                print("自检未通过：", flush=True)
                for f in failures:
                    print(f"  ✗ {f}", flush=True)
                return 1
            print("自检全部通过 ✓", flush=True)
            return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
