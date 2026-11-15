import json,sys,glob,collections,re
def secs(play):
    m,s=(play["clock"]["displayValue"].split(":")+["0"])[:2] if ":" in play["clock"]["displayValue"] else ("0",play["clock"]["displayValue"])
    left=int(m)*60+float(s); n=play["period"]["number"]
    return (n-1)*720+720-left if n<=4 else 2880+(n-5)*300+300-left
def rebuild(s, upto=None):
    st=collections.defaultdict(lambda: collections.Counter())
    plays=sorted(enumerate(s["plays"]),key=lambda ip:(secs(ip[1]),ip[0]))
    for _,p in plays:
        if upto is not None and secs(p)>upto: break
        t=p["type"]["text"]; ids=[x["athlete"]["id"] for x in p.get("participants",[])]
        if not ids: continue
        a=st[ids[0]]; txt=p["text"].lower()
        if "Free Throw" in t:
            a["FTA"]+=1; a["FTM"]+= p["scoringPlay"]; a["PTS"]+=p["scoreValue"] if p["scoringPlay"] else 0
        elif p.get("shootingPlay"):
            three=p.get("pointsAttempted")==3; a["FGA"]+=1; a["3PA"]+=three
            if p["scoringPlay"]:
                a["FGM"]+=1; a["3PM"]+=three; a["PTS"]+=p["scoreValue"]
                if len(ids)>1 and "assist" in txt: st[ids[1]]["AST"]+=1
            elif len(ids)>1 and "block" in txt: st[ids[1]]["BLK"]+=1
        elif "Rebound" in t: a["REB"]+=1
        elif "Turnover" in t:
            a["TO"]+=1
            if len(ids)>1 and "steal" in txt: st[ids[1]]["STL"]+=1
        elif "Foul" in t and "Technical" not in t and "Turnover" not in t: a["PF"]+=1
        if "Offensive Foul Turnover" in t: a["PF"]+=1
    return st
def official(s):
    out={}
    for team in s["boxscore"]["players"]:
        g=team["statistics"][0]; L=g["labels"]
        for ath in g["athletes"]:
            if not ath["stats"] or "id" not in ath.get("athlete",{}): continue
            d=dict(zip(L,ath["stats"]))
            fg=d["FG"].split("-"); tp=d["3PT"].split("-"); ft=d["FT"].split("-")
            out[ath["athlete"]["id"]]=dict(PTS=int(d["PTS"]),FGM=int(fg[0]),FGA=int(fg[1]),**{"3PM":int(tp[0]),"3PA":int(tp[1])},FTM=int(ft[0]),FTA=int(ft[1]),REB=int(d["REB"]),AST=int(d["AST"]),TO=int(d["TO"]),STL=int(d["STL"]),BLK=int(d["BLK"]),PF=int(d["PF"]))
    return out
tot=collections.Counter(); ok=collections.Counter(); games=0
for f in glob.glob("/tmp/bgw-season-2026/4*.json"):
    s=json.load(open(f))
    if not s.get("plays") or not s.get("boxscore",{}).get("players"): continue
    games+=1; r=rebuild(s); o=official(s)
    for pid,d in o.items():
        for k,v in d.items():
            tot[k]+=1; ok[k]+= r[pid][k]==v
print(games,"games;", {k: f"{ok[k]/tot[k]:.1%}" for k in tot})
