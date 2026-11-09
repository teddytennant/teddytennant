#!/usr/bin/env python3
"""Render the neofetch-style profile card as dark_mode.svg and light_mode.svg.

Static fields live in INFO below; everything under GitHub Stats is fetched
live. Needs GH_TOKEN (the Actions GITHUB_TOKEN is enough: only public data).
"""
import json
import os
import pathlib
import urllib.request
from datetime import date, datetime, timezone
from xml.sax.saxutils import escape

LOGIN = "teddytennant"
ROOT = pathlib.Path(__file__).resolve().parent.parent
WIDTH = 60  # characters in the right-hand column

INFO = [
    ("OS", "NixOS, Ubuntu, Arch, macOS"),
    ("Uptime", None),  # filled from account creation date
    ("Host", "NCSSM"),
    ("Daily Driver", "wizard"),
    None,
    ("Languages.Programming", "Python, Rust, C++"),
    ("Languages.Computer", "Nix, Typst, Shell, HTML"),
    None,
    ("Hobbies.Software", "AI Agents, ML, Terminal UIs"),
]
CONTACT = [
    ("Email", "teddy5tennant@gmail.com"),
    ("Website", "teddytennant.com"),
]

THEMES = {
    "dark": dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff",
                 dots="#616e7f", accent="#3fb950", logo="#7ebae4"),
    "light": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069",
                  dots="#c2cfde", accent="#1a7f37", logo="#5277c3"),
}


# ---------------------------------------------------------------- GitHub API

def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {os.environ['GH_TOKEN']}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


def fetch_stats():
    base = gql("""query($login:String!){ user(login:$login){
        createdAt followers{totalCount}
        repositoriesContributedTo(contributionTypes:[COMMIT,PULL_REQUEST,REPOSITORY]){totalCount}
    }}""", login=LOGIN)["user"]
    created = datetime.fromisoformat(base["createdAt"].replace("Z", "+00:00"))

    repos, stars, cursor = 0, 0, None
    while True:
        page = gql("""query($login:String!,$after:String){ user(login:$login){
            repositories(ownerAffiliations:OWNER, privacy:PUBLIC, first:100, after:$after){
              totalCount pageInfo{hasNextPage endCursor} nodes{stargazerCount}
        }}}""", login=LOGIN, after=cursor)["user"]["repositories"]
        repos = page["totalCount"]
        stars += sum(n["stargazerCount"] for n in page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    # contributionsCollection spans at most one year, so walk year by year.
    commits = 0
    now = datetime.now(timezone.utc)
    start = created
    while start < now:
        end = min(start.replace(year=start.year + 1), now)
        cc = gql("""query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
            contributionsCollection(from:$from,to:$to){totalCommitContributions}
        }}""", login=LOGIN, **{"from": start.isoformat(), "to": end.isoformat()})
        commits += cc["user"]["contributionsCollection"]["totalCommitContributions"]
        start = end

    # Merged PRs in repos owned by someone else.
    merged, upstream, cursor = 0, {}, None
    q = f"is:pr author:{LOGIN} is:merged -user:{LOGIN}"
    while True:
        page = gql("""query($q:String!,$after:String){ search(query:$q, type:ISSUE, first:100, after:$after){
            issueCount pageInfo{hasNextPage endCursor}
            nodes{ ... on PullRequest { repository{ nameWithOwner stargazerCount } } }
        }}""", q=q, after=cursor)["search"]
        merged = page["issueCount"]
        for n in page["nodes"]:
            r = n.get("repository")
            if r:
                upstream[r["nameWithOwner"]] = r["stargazerCount"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    return dict(
        created=created.date(),
        followers=base["followers"]["totalCount"],
        contributed=base["repositoriesContributedTo"]["totalCount"],
        repos=repos, stars=stars, commits=commits,
        merged=merged, upstream_repos=len(upstream),
        upstream_stars=sum(upstream.values()),
    )


# ---------------------------------------------------------------- formatting

def uptime(since, today=None):
    today = today or date.today()
    y, m, d = today.year - since.year, today.month - since.month, today.day - since.day
    if d < 0:
        m -= 1
        prev = date(today.year, today.month, 1).toordinal() - 1
        d += date.fromordinal(prev).day
    if m < 0:
        y -= 1
        m += 12
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return ", ".join(plural(n, w) for n, w in ((y, "year"), (m, "month"), (d, "day")))


def human(n):
    for div, suf in ((1_000_000, "M"), (1_000, "k")):
        if n >= div:
            return f"{n / div:.1f}".rstrip("0").rstrip(".") + suf
    return str(n)


# A line is a list of (text, style) spans; style is a theme key.

def kv(key, value, width=WIDTH, lead=". "):
    used = len(lead) + len(key) + 2 + len(value) + 1
    return [(lead, "dots"), (key, "key"), (": ", "text"),
            ("." * max(1, width - used) + " ", "dots"), (value, "value")]


def pair(k1, v1, w1, k2, v2):
    """Two stats on one line, split by ' | ' like the reference card."""
    left = kv(k1, v1, width=w1)
    right = kv(k2, v2, width=WIDTH - w1 - 3, lead="")
    return left + [(" | ", "text")] + right


def header(title, lead=""):
    rule = WIDTH - len(lead) - len(title) - 4
    return [(lead + title, "text"), (" " + "—" * rule + "-—-", "text")]


def build_lines(s):
    lines = [header(f"{LOGIN}@github")]
    for item in INFO:
        if item is None:
            lines.append([(".", "dots")])
        else:
            k, v = item
            lines.append(kv(k, v if v is not None else uptime(s["created"])))
    lines.append([])
    lines.append(header("Contact", "- "))
    lines += [kv(k, v) for k, v in CONTACT]
    lines.append([])
    lines.append(header("GitHub Stats", "- "))
    lines.append(pair("Repos", f"{s['repos']:,} {{Contributed: {s['contributed']}}}", 36,
                      "Stars", f"{s['stars']:,}"))
    lines.append(pair("Commits", f"{s['commits']:,}", 36, "Followers", f"{s['followers']:,}"))
    lines.append(kv("Merged PRs (not my repos)", f"{s['merged']:,}"))
    lines.append(kv("Upstream Repos", f"{s['upstream_repos']} {{{human(s['upstream_stars'])} combined stars}}"))
    return lines


def svg(theme, art, lines):
    t = THEMES[theme]
    lh, cw, top, art_x = 20, 9.6, 30, 15
    art_w = max(len(l) for l in art)
    info_x = art_x + int(art_w * cw) + 25
    rows = max(len(art), len(lines))
    width = info_x + int(WIDTH * cw) + 20
    height = top + rows * lh
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" font-family="ConsolasFallback,Consolas,monospace" '
           f'width="{width}px" height="{height}px" font-size="16px">',
           '<style>@font-face{src:local("Consolas"),local("Consolas Bold");font-family:"ConsolasFallback";'
           'font-display:swap;-webkit-size-adjust:109%;size-adjust:109%;}'
           + "".join(f".{k}{{fill:{v}}}" for k, v in t.items() if k != "bg")
           + "text,tspan{white-space:pre;}</style>",
           f'<rect width="{width}px" height="{height}px" fill="{t["bg"]}" rx="15"/>',
           f'<text x="{art_x}" y="{top}" class="logo" font-weight="bold">']
    art_top = top + (rows - len(art)) // 2 * lh  # center the logo beside the info
    for i, l in enumerate(art):
        out.append(f'<tspan x="{art_x}" y="{art_top + i * lh}">{escape(l)}</tspan>')
    out.append(f'</text>\n<text x="{info_x}" y="{top}" class="text">')
    for i, spans in enumerate(lines):
        y = top + i * lh
        inner = "".join(f'<tspan class="{c}">{escape(txt)}</tspan>' for txt, c in spans)
        out.append(f'<tspan x="{info_x}" y="{y}">{inner}</tspan>')
    out.append("</text>\n</svg>\n")
    return "\n".join(out)


def main():
    art = (ROOT / "scripts" / "ascii.txt").read_text().splitlines()
    stats = fetch_stats()
    print(json.dumps(stats, default=str, indent=2))
    lines = build_lines(stats)
    for theme in THEMES:
        (ROOT / f"{theme}_mode.svg").write_text(svg(theme, art, lines))


if __name__ == "__main__":
    main()
