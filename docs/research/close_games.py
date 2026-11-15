import sys, os, json
sys.path.insert(0, "docs/research"); sys.path.insert(0, ".")  # run from the repo root
import backtest as b
from app import ESPN, TEAM
cache="/tmp/bgw-season-2026"; os.makedirs(cache, exist_ok=True)
sch=b.cached(f"{ESPN}/teams/dal/schedule?season=2026&seasontype=2", f"{cache}/schedule.json")
games=[]
for e in sch["events"]:
    if e["competitions"][0]["status"]["type"]["state"]!="post": continue
    s=b.cached(f"{ESPN}/summary?event={e['id']}", f"{cache}/{e['id']}.json")
    cs={c["homeAway"]:c for c in s["header"]["competitions"][0]["competitors"]}
    m=next(c for c in cs.values() if c["team"]["abbreviation"]==TEAM); o=next(c for c in cs.values() if c is not m)
    ot=max([p["period"]["number"] for p in s.get("plays",[])] or [0])>4
    if not s.get("plays"): continue
    games.append((e["date"][:10],o["team"]["abbreviation"],int(m["score"])-int(o["score"]),ot,b.readings(s)))
END=2880-300  # 5:00 left in the 4th
def run(rows, line, band, side):
    v=None; flips=0; stays=[]
    for el,opp,inw in rows:
        if not inw or el>END: continue
        x = opp if side=="opp" else max(opp,1-opp)
        stay = x > (line-band if v=="stay" else line)
        if v=="stay" and not stay: flips+=1
        v="stay" if stay else "watch"; stays.append(stay)
    return v, flips, all(stays) and stays
for side in ("opp","either"):
  for line in (0.90,0.95,0.97):
    for band in (0,0.03,0.05):
      res=[(g,run(g[4],line,band,side)) for g in games]
      sa=[g for g,r in res if r[0]=="stay"]
      wrong=[(g[0],g[1],g[2]) for g in sa if (g[2]>0 if side=="opp" else True) or abs(g[2])<=5]
      if side=="either": wrong=[(g[0],g[1],g[2]) for g in sa if abs(g[2])<=5]
      ots=[g[:3] for g in sa if g[3]]
      print(f"{side} line {line} band {band}: Stay away at 5:00 mark {len(sa)}; wins {sum(g[2]>0 for g in sa)}; within 5 {wrong}; OT {ots}; flips {sum(r[1] for g,r in res)}")
  wire=[g[:3] for g,r in [(g,run(g[4],0.95,0,side)) for g in games] if r[2]]
  print(side,"over 95 for every reading 6:00 2Q to 5:00 4Q:",len(wire),wire)
print(len(games),"games",sum(g[2]>0 for g in games),"wins", sum(abs(g[2])<=5 for g in games),"within 5", sum(g[3] for g in games),"OT")

print("---- 98/95 and start points, opponent side, freeze at 5:00 left")
def run2(rows,line,band,start):
    v=None;flips=0
    for el,opp,inw in rows:
        if el<start or el>END: continue
        stay=opp>(line-band if v=="stay" else line)
        if v=="stay" and not stay: flips+=1
        v="stay" if stay else "watch"
    return v,flips
for line,band in ((0.95,0.03),(0.97,0.03),(0.98,0.03),(0.98,0.05)):
  for start,name in ((1440-360,"6:00 2Q"),(1440,"halftime"),(2160,"start 4Q")):
    res=[(g,run2(g[4],line,band,start)) for g in games]
    sa=[g for g,r in res if r[0]=="stay"]
    print(f"{line}/{line-band:.2f} from {name}: Stay away {len(sa)}; close losses {[g[:3] for g in sa if abs(g[2])<=5]}; wins {sum(g[2]>0 for g in sa)}; flips {sum(r[1] for g,r in res)}; median margin {sorted(-g[2] for g in sa)[len(sa)//2] if sa else None}")
print("---- closeness measures over the whole game (home win probability, every Reading)")
import statistics as st
rowsout=[]
for g in games:
    ps=[r[1] for r in g[4]]
    sd=st.pstdev(ps); dist=sum(abs(p-0.5) for p in ps)/len(ps); inside=sum(0.2<=p<=0.8 for p in ps)/len(ps)
    rowsout.append((g[0],g[1],g[2],g[3],sd,dist,inside))
def corr(i):
    xs=[r[i] for r in rowsout]; ys=[abs(r[2]) for r in rowsout]; return st.correlation(xs,ys)
print("correlation with final margin: sd",round(corr(4),2),"avg distance from even",round(corr(5),2),"share of game between 20 and 80%",round(corr(6),2))
for key,name in ((4,"sd"),(5,"avgdist")):
    o=sorted(rowsout,key=lambda r:r[key])
    print(name,"lowest 3",[(r[0],r[1],r[2],round(r[key],3)) for r in o[:3]],"highest 3",[(r[0],r[1],r[2],round(r[key],3)) for r in o[-3:]])
o=sorted(rowsout,key=lambda r:r[5]); third=o[:27]
print("avgdist tertile cut",round(o[26][5],3),"; in close third: final within 5:",sum(abs(r[2])<=5 for r in third),"of",len(third),"; OT:",sum(r[3] for r in third),"; of all within-5 games caught:",sum(abs(r[2])<=5 for r in third),"/18")
seesaw=[r for r in rowsout if r[4]>0.3]
print("high sd games (>0.30):",[(r[0],r[1],r[2],round(r[5],2)) for r in seesaw][:8])
u=[r for r in rowsout if r[5]<=0.232 or abs(r[2])<=5 or r[3]]
print("union close-third or within 5 or OT:",len(u),"; blowouts 15+ in it:",[(r[0],r[1],r[2]) for r in u if abs(r[2])>=15])
