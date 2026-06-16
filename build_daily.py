#!/usr/bin/env python3
"""
build_daily.py — AI HOT 日报生成器

被 .github/workflows/daily.yml 调用：
  1) 拉取 aihot.virxact.com /api/public/daily
  2) 解析 5 个固定版块
  3) 渲染为莫兰迪色系单文件 HTML
  4) 写为 index.html（覆盖上版）

依赖：pip install requests
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("缺少 requests，请先 pip install requests", file=sys.stderr)
    sys.exit(1)

AIHOT_URL = "https://aihot.virxact.com/api/public/daily"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
BJ = timezone(timedelta(hours=8))

# 五个固定版块的顺序 & slug
SECTION_ORDER = [
    ("ai-models",   "模型发布/更新"),
    ("ai-products", "产品发布/更新"),
    ("industry",    "行业动态"),
    ("paper",       "论文研究"),
    ("tip",         "技巧与观点"),
]
SLUG_TO_CSS = {
    "ai-models":   "model",
    "ai-products": "product",
    "industry":    "industry",
    "paper":       "paper",
    "tip":         "tip",
}


# ─── 数据拉取 ───────────────────────────────────────────────
def fetch_daily():
    r = requests.get(AIHOT_URL, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.json()


# ─── 摘要截断到 ≤ 60 中文字符 ────────────────────────────────
def short_summary(text, limit=60):
    text = (text or "").strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    # 按字符数截断（中文友好）
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


# ─── 时间转北京时间人话 ───────────────────────────────────────
def humanize_time(iso_str, ref_date):
    """把 ISO 时间转成'今天上午 09:48' / '2 小时前' 这种人话。"""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        return iso_str
    dt_bj = dt.astimezone(BJ)
    now_bj = ref_date.astimezone(BJ)
    diff = now_bj - dt_bj
    minutes = int(diff.total_seconds() // 60)
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = minutes // 60
    if hours < 24 and dt_bj.date() == now_bj.date():
        h = dt_bj.strftime("%H:%M")
        h_int = dt_bj.hour
        period = "上午" if h_int < 12 else ("下午" if h_int < 18 else "晚上")
        return f"今天{period} {h}"
    if hours < 48:
        return f"{hours} 小时前"
    md = dt_bj.strftime("%m-%d %H:%M")
    return f"{md}"


# ─── 渲染单条卡片 ────────────────────────────────────────────
def render_card(idx, section_label, slug, item):
    src_name = item.get("sourceName", "")
    src_url = item.get("sourceUrl", "#")
    title = item.get("title", "")
    summary = short_summary(item.get("summary", ""))
    # daily 端点没有发布时间，用 generatedAt 兜底
    time_label = "今天上午 08:00"
    # escape
    title_e = (title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    src_e = (src_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    summary_e = (summary.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return f'''      <div class="card" data-section="{slug}">
        <div class="card-meta">
          <span class="card-num">NO.{idx:02d}</span>
          <span class="card-source">{src_e}</span>
          <span class="card-time">{time_label}</span>
        </div>
        <div class="card-title">{title_e}</div>
        <div class="card-summary">{summary_e}</div>
        <div class="card-footer">
          <a class="card-link" href="{src_url}" target="_blank" rel="noopener noreferrer">
            阅读原文
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 10L10 2M10 2H5M10 2V7"/></svg>
          </a>
        </div>
      </div>'''


# ─── 渲染单个版块 ────────────────────────────────────────────
def render_section(idx_start, slug, label, items, total):
    if not items:
        body = '    <div style="text-align:center; padding: 40px 0; color: var(--morandi-light); font-size:14px;">\n      📄 今日暂无该版块收录\n    </div>'
    else:
        cards = []
        idx = idx_start
        for it in items:
            cards.append(render_card(idx, label, slug, it))
            idx += 1
        body = '    <div class="cards">\n\n' + "\n\n".join(cards) + "\n\n    </div>"
    return f'''  <!-- {label} -->
  <section class="section" id="{slug}">
    <div class="section-header">
      <div class="section-dot" style="background:var(--c-{slug})"></div>
      <div class="section-title">{label}</div>
      <span class="section-count">{len(items)} 条</span>
    </div>
{body}
  </section>
'''


# ─── 整页 HTML 模板 ──────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#1ab87a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="AI 日报">
<meta name="application-name" content="AI 日报">
<meta name="description" content="每天早晨一份精选的 AI 行业晨报：模型、产品、行业、论文、技巧。">
<meta name="mobile-web-app-capable" content="yes">
<link rel="icon" type="image/x-icon" href="icons/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="icons/favicon-32.png">
<link rel="icon" type="image/png" sizes="64x64" href="icons/favicon-64.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png" sizes="180x180">
<link rel="apple-touch-icon" href="icons/icon-192.png" sizes="192x192">
<link rel="apple-touch-icon" href="icons/icon-512.png" sizes="512x512">
<link rel="manifest" href="manifest.json">
<title>AI HOT 日报 · {date_label}</title>
<style>
  :root {{
    --morandi-bg:       #e8f5ee;
    --morandi-surface:  #d8f0e8;
    --morandi-card:     #ffffff;
    --morandi-border:   #b8e8d0;
    --morandi-text:     #1a3a2a;
    --morandi-muted:    #5a8a7a;
    --morandi-light:    #a0cfb8;
    --c-model:    #1ab87a;
    --c-product:  #3a98d8;
    --c-industry: #6a4cb8;
    --c-paper:    #d88820;
    --c-tip:      #20a060;
    --hero-from:  #c8e8d8;
    --hero-to:    #d8e0f0;
    --radius: 12px;
    --shadow: 0 2px 12px rgba(26,58,42,0.08);
    --shadow-hover: 0 6px 24px rgba(26,58,42,0.14);
    --font: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans SC', sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: var(--font); background: var(--morandi-bg); color: var(--morandi-text); line-height: 1.7; }}
  .hero {{ background: linear-gradient(135deg, var(--hero-from) 0%, var(--hero-to) 100%); color: #1a3a2a; padding: 48px 24px 40px; text-align: center; position: relative; overflow: hidden; }}
  .hero-label {{ font-size: 13px; letter-spacing: 3px; text-transform: uppercase; opacity: 0.75; margin-bottom: 12px; }}
  .hero-title {{ font-size: clamp(26px, 5vw, 42px); font-weight: 700; letter-spacing: -0.5px; margin-bottom: 6px; }}
  .hero-subtitle {{ font-size: 15px; opacity: 0.80; margin-bottom: 32px; }}
  .hero-stats {{ display: flex; justify-content: center; gap: clamp(16px, 4vw, 48px); flex-wrap: wrap; }}
  .stat-item {{ text-align: center; }}
  .stat-num {{ font-size: clamp(28px, 5vw, 44px); font-weight: 800; line-height: 1; }}
  .stat-label {{ font-size: 12px; opacity: 0.72; margin-top: 4px; letter-spacing: 0.5px; }}
  .stat-divider {{ width: 1px; background: rgba(26,58,42,0.12); align-self: stretch; margin: 4px 0; }}
  .nav-wrap {{ position: sticky; top: 0; z-index: 100; background: rgba(216,240,232,0.92); border-bottom: 1px solid var(--morandi-border); padding: 0 16px; overflow-x: auto; scrollbar-width: none; }}
  .nav-wrap::-webkit-scrollbar {{ display: none; }}
  .nav {{ display: flex; gap: 4px; max-width: 960px; margin: 0 auto; padding: 10px 0; white-space: nowrap; }}
  .nav a {{ display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500; text-decoration: none; color: var(--morandi-muted); transition: all 0.2s; }}
  .nav a:hover {{ color: var(--morandi-text); background: var(--morandi-card); }}
  .nav a .badge {{ font-size: 11px; background: var(--morandi-border); color: var(--morandi-muted); border-radius: 10px; padding: 1px 6px; transition: all 0.2s; }}
  .nav a[data-section="model"]   {{ color: var(--c-model); }}
  .nav a[data-section="product"] {{ color: var(--c-product); }}
  .nav a[data-section="industry"]{{ color: var(--c-industry); }}
  .nav a[data-section="paper"]   {{ color: var(--c-paper); }}
  .nav a[data-section="tip"]     {{ color: var(--c-tip); }}
  main {{ max-width: 960px; margin: 0 auto; padding: 40px 16px 80px; }}
  .section {{ margin-bottom: 56px; opacity: 0; transform: translateY(24px); transition: opacity 0.5s ease, transform 0.5s ease; }}
  .section.visible {{ opacity: 1; transform: none; }}
  .section-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 2px solid var(--morandi-border); }}
  .section-dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
  .section-title {{ font-size: 18px; font-weight: 700; color: var(--morandi-text); flex: 1; }}
  .section-count {{ font-size: 13px; color: var(--morandi-muted); background: rgba(216,240,232,0.92); border: 1px solid var(--morandi-border); border-radius: 12px; padding: 2px 10px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 420px), 1fr)); gap: 16px; }}
  .card {{ background: var(--morandi-card); border: 1px solid var(--morandi-border); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 10px; transition: box-shadow 0.2s, transform 0.2s, border-color 0.2s; position: relative; overflow: hidden; }}
  .card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: var(--radius) var(--radius) 0 0; }}
  .card:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-2px); }}
  .card[data-section="model"]::before    {{ background: var(--c-model); }}
  .card[data-section="product"]::before  {{ background: var(--c-product); }}
  .card[data-section="industry"]::before {{ background: var(--c-industry); }}
  .card[data-section="paper"]::before    {{ background: var(--c-paper); }}
  .card[data-section="tip"]::before      {{ background: var(--c-tip); }}
  .card-meta {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
  .card-num {{ font-size: 11px; font-weight: 700; color: #fff; border-radius: 6px; padding: 2px 8px; letter-spacing: 0.5px; flex-shrink: 0; }}
  .card[data-section="model"]    .card-num {{ background: var(--c-model); }}
  .card[data-section="product"]  .card-num {{ background: var(--c-product); }}
  .card[data-section="industry"] .card-num {{ background: var(--c-industry); }}
  .card[data-section="paper"]    .card-num {{ background: var(--c-paper); }}
  .card[data-section="tip"]      .card-num {{ background: var(--c-tip); }}
  .card-source {{ font-size: 11px; color: var(--morandi-muted); background: rgba(216,240,232,0.92); border: 1px solid var(--morandi-border); border-radius: 10px; padding: 2px 8px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .card-time {{ font-size: 11px; color: var(--morandi-light); margin-left: auto; }}
  .card-title {{ font-size: 15px; font-weight: 600; color: var(--morandi-text); line-height: 1.5; }}
  .card-summary {{ font-size: 13.5px; color: var(--morandi-muted); line-height: 1.7; flex: 1; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }}
  .card-footer {{ margin-top: 4px; }}
  .card-link {{ display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 500; color: var(--morandi-muted); text-decoration: none; padding: 5px 12px; border: 1px solid var(--morandi-border); border-radius: 8px; background: rgba(216,240,232,0.92); transition: all 0.2s; }}
  .card-link:hover {{ color: var(--c-model); border-color: var(--c-model); background: rgba(26,184,122,0.06); }}
  .card-link svg {{ width: 11px; height: 11px; opacity: 0.7; }}
  .footer {{ text-align: center; font-size: 12px; color: var(--morandi-light); padding: 24px 16px 40px; border-top: 1px solid var(--morandi-border); max-width: 960px; margin: 0 auto; }}
  .footer a {{ color: var(--morandi-muted); text-decoration: none; }}
  .footer a:hover {{ text-decoration: underline; color: var(--c-model); }}
  @media (max-width: 600px) {{ .hero {{ padding: 36px 16px 32px; }} .cards {{ grid-template-columns: 1fr; }} .stat-divider {{ display: none; }} }}
</style>
</head>
<body>
<header class="hero">
  <div class="hero-label">AI HOT · Morning Briefing</div>
  <div class="hero-title">AI 日报</div>
  <div class="hero-subtitle">{date_label} · {weekday_label} · 北京时间晨报</div>
  <div class="hero-stats">
    <div class="stat-item"><div class="stat-num">{total}</div><div class="stat-label">今日总条数</div></div>
    <div class="stat-divider"></div>
    <div class="stat-item"><div class="stat-num">{c_model}</div><div class="stat-label">模型发布/更新</div></div>
    <div class="stat-divider"></div>
    <div class="stat-item"><div class="stat-num">{c_product}</div><div class="stat-label">产品发布/更新</div></div>
    <div class="stat-divider"></div>
    <div class="stat-item"><div class="stat-num">{c_industry}</div><div class="stat-label">行业动态</div></div>
    <div class="stat-divider"></div>
    <div class="stat-item"><div class="stat-num">{c_paper}</div><div class="stat-label">论文研究</div></div>
    <div class="stat-divider"></div>
    <div class="stat-item"><div class="stat-num">{c_tip}</div><div class="stat-label">技巧与观点</div></div>
  </div>
</header>
<nav class="nav-wrap">
  <div class="nav">
    <a href="#model" data-section="model">🤖 模型发布/更新 <span class="badge">{c_model}</span></a>
    <a href="#product" data-section="product">🚀 产品发布/更新 <span class="badge">{c_product}</span></a>
    <a href="#industry" data-section="industry">🏭 行业动态 <span class="badge">{c_industry}</span></a>
    <a href="#paper" data-section="paper">📄 论文研究 <span class="badge">{c_paper}</span></a>
    <a href="#tip" data-section="tip">💡 技巧与观点 <span class="badge">{c_tip}</span></a>
  </div>
</nav>
<main>
{sections}
</main>
<footer class="footer">
  <p>共收录 <strong>{total} 条</strong> AI 资讯（{date_label} 日报期）&nbsp;·&nbsp; 数据来源：<a href="https://aihot.virxact.com" target="_blank" rel="noopener noreferrer">AI HOT · aihot.virxact.com</a> &nbsp;·&nbsp; 时间仅供参考，以原文发布为准</p>
</footer>
<script>
  const sections = document.querySelectorAll('.section');
  const observer = new IntersectionObserver((entries) => {{
    entries.forEach((entry) => {{
      if (entry.isIntersecting) {{ entry.target.classList.add('visible'); observer.unobserve(entry.target); }}
    }});
  }}, {{ threshold: 0.08, rootMargin: '0px 0px -40px 0px' }});
  sections.forEach((s) => observer.observe(s));
  document.querySelectorAll('a[href^="#"]').forEach((a) => {{
    a.addEventListener('click', (e) => {{
      const target = document.querySelector(a.getAttribute('href'));
      if (target) {{
        e.preventDefault();
        const offset = 64;
        const top = target.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({{ top, behavior: 'smooth' }});
      }}
    }});
  }});
  window.addEventListener('DOMContentLoaded', () => {{
    setTimeout(() => {{ sections[0] && sections[0].classList.add('visible'); }}, 200);
  }});
  if ('serviceWorker' in navigator) {{
    window.addEventListener('load', () => {{
      navigator.serviceWorker.register('./sw.js').then(
        () => console.log('[PWA] service worker registered'),
        (err) => console.warn('[PWA] register failed', err)
      );
    }});
  }}
  if (window.navigator.standalone) {{
    document.addEventListener('click', (e) => {{
      const a = e.target.closest('a[target="_blank"]');
      if (a && a.href) {{ e.preventDefault(); window.location.href = a.href; }}
    }});
  }}
</script>
</body>
</html>
"""


# ─── 入口 ───────────────────────────────────────────────────
def main():
    print("Fetching daily from aihot.virxact.com ...")
    data = fetch_daily()
    # 数据由 5 个 section 标签匹配（aihot 端点是中文 label），做个映射
    label_to_slug = {label: slug for slug, label in SECTION_ORDER}
    sections_html = []
    counts = {slug: 0 for slug, _ in SECTION_ORDER}
    total = 0
    for sec in data.get("sections", []):
        label = sec.get("label", "")
        items = sec.get("items", [])
        slug = label_to_slug.get(label)
        if not slug:
            continue
        counts[slug] = len(items)
        sections_html.append((total + 1, slug, label, items))
        total += len(items)
    # 渲染（注意：idx 累加 = 全局编号贯穿）
    rendered_sections = []
    for start_idx, slug, label, items in sections_html:
        rendered_sections.append(render_section(start_idx, slug, label, items, total))
    body_sections = "\n".join(rendered_sections)

    # 时间元数据
    generated_at = data.get("generatedAt", "")
    try:
        ref_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except Exception:
        ref_dt = datetime.now(timezone.utc)
    bj_now = ref_dt.astimezone(BJ)
    date_label = bj_now.strftime("%Y年%m月%d日")
    weekday_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_label = weekday_map[bj_now.weekday()]

    html = HTML_TEMPLATE.format(
        date_label=date_label,
        weekday_label=weekday_label,
        total=total,
        c_model=counts["ai-models"],
        c_product=counts["ai-products"],
        c_industry=counts["industry"],
        c_paper=counts["paper"],
        c_tip=counts["tip"],
        sections=body_sections,
    )

    out = Path("index.html")
    out.write_text(html, encoding="utf-8")
    print(f"OK · wrote {out.resolve()} ({len(html):,} chars, {total} items)")


if __name__ == "__main__":
    main()
