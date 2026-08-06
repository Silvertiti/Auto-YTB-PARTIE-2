import json
from collections import defaultdict

FILE = r"c:\Users\methe\OneDrive\Bureau\Auto YTB PARTIE 2\BackupVPS\video_analytics.json"
OUTFILE = r"c:\Users\methe\OneDrive\Bureau\Auto YTB PARTIE 2\BackupVPS\rapport_analytics.txt"

with open(FILE, "r", encoding="utf-8") as f:
    raw = json.load(f)

by_url = {}
for entry in raw:
    if not isinstance(entry, dict):
        continue
    url = entry.get("url", "")
    if not url:
        continue
    if url not in by_url or entry.get("views", 0) > by_url[url].get("views", 0):
        by_url[url] = entry

videos = list(by_url.values())

def get_account(url):
    if "@" in url:
        try:
            return "@" + url.split("@")[1].split("/")[0]
        except:
            pass
    return "@inconnu"

by_account = defaultdict(list)
for v in videos:
    acc = get_account(v.get("url", ""))
    by_account[acc].append(v)

all_views = [v.get("views", 0) for v in videos]
all_likes = [v.get("likes", 0) for v in videos]

account_stats = []
for acc, vids in by_account.items():
    views = [v.get("views", 0) for v in vids]
    likes = [v.get("likes", 0) for v in vids]
    total_v = sum(views)
    total_l = sum(likes)
    max_v = max(views) if views else 0
    avg_v = total_v // len(vids) if vids else 0
    best = max(vids, key=lambda x: x.get("views", 0))
    account_stats.append({
        "account": acc,
        "nb_videos": len(vids),
        "total_views": total_v,
        "total_likes": total_l,
        "avg_views": avg_v,
        "max_views": max_v,
        "best_title": best.get("title", "?"),
        "ratio": total_l/max(1,total_v)*100
    })
account_stats.sort(key=lambda x: x["total_views"], reverse=True)

top10 = sorted(videos, key=lambda x: x.get("views", 0), reverse=True)[:10]
zero_likes = [v for v in videos if v.get("likes", 0) == 0]
over_1k  = [v for v in videos if v.get("views", 0) >= 1000]
over_5k  = [v for v in videos if v.get("views", 0) >= 5000]
over_10k = [v for v in videos if v.get("views", 0) >= 10000]

lines = []
lines.append(f"Videos uniques : {len(videos)}")
lines.append("")
lines.append("="*60)
lines.append(f"RAPPORT ANALYTICS - {len(videos)} videos uniques sur {len(by_account)} comptes")
lines.append("="*60)
lines.append("")
lines.append("GLOBAL")
lines.append(f"  Total vues   : {sum(all_views):,}")
lines.append(f"  Total likes  : {sum(all_likes):,}")
lines.append(f"  Ratio L/V    : {sum(all_likes)/max(1,sum(all_views))*100:.2f}%")
lines.append(f"  Vues moy/vid : {sum(all_views)//max(1,len(videos)):,}")
lines.append("")
lines.append("="*60)
lines.append("PAR COMPTE - trie par total vues")
lines.append("="*60)

for i, st in enumerate(account_stats, 1):
    lines.append("")
    lines.append(f"{i}. {st['account']}")
    lines.append(f"   Videos       : {st['nb_videos']}")
    lines.append(f"   Total vues   : {st['total_views']:,}")
    lines.append(f"   Total likes  : {st['total_likes']:,}")
    lines.append(f"   Vues moy/vid : {st['avg_views']:,}")
    lines.append(f"   Vues max     : {st['max_views']:,}")
    lines.append(f"   Ratio L/V    : {st['ratio']:.2f}%")
    lines.append(f"   Meilleure vid: {st['best_title'][:70]}")

lines.append("")
lines.append("="*60)
lines.append("TOP 10 VIDEOS GLOBALES")
lines.append("="*60)
for i, v in enumerate(top10, 1):
    acc = get_account(v.get("url", ""))
    lines.append(f"{i:>2}. [{acc}] {v.get('views',0):>6,} vues | {v.get('likes',0):>4} likes | {v.get('title','?')[:50]}")

lines.append("")
lines.append("="*60)
lines.append("STATISTIQUES D'ENGAGEMENT")
lines.append("="*60)
lines.append(f"  Videos >= 1 000 vues  : {len(over_1k)}")
lines.append(f"  Videos >= 5 000 vues  : {len(over_5k)}")
lines.append(f"  Videos >= 10 000 vues : {len(over_10k)}")
lines.append(f"  Videos 0 likes        : {len(zero_likes)} ({len(zero_likes)/max(1,len(videos))*100:.1f}%)")

output = "\n".join(lines)
print(output)

with open(OUTFILE, "w", encoding="utf-8") as f:
    f.write(output)
print(f"\n=> Rapport ecrit dans {OUTFILE}")
