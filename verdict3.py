import os
import re
import json
import requests
from google import genai
from rapidfuzz import fuzz

# ---------------------------
# API KEYS
# ---------------------------
os.environ["GEMINI_API_KEY"] = "AIzaSyCNs-FR4ti3Xz_olgxXQWQt1h8boDWEJhU"
TMDB_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhMTgyZjI1Njg0Nzc1ZjlkYTdjNDUyMzQ1MGVkYTEwNCIsIm5iZiI6MTc1ODg2MjY4OC4wOCwic3ViIjoiNjhkNjFkNjA3ZDExMTU0YmM3ZDNjZDM0Iiwic2NvcGVzIjpbImFwaV9yZWFkIl0sInZlcnNpb24iOjF9.lsBLFLRbb8mgUNWf1lR16P8KLArfvcPZGI_frqnCGtU"
OMDB_API_KEY = "a6f7938d"

client = genai.Client()

# ---------------------------
# Claim Extraction
# ---------------------------
def extract_claims(sentence: str):
    prompt = f"""
    Extract factual claims about a movie and return them strictly in JSON format.
    Each claim should be an object with two fields:
    - attribute (examples: director, actor, release_year, award, rating, box_office, genre, runtime, production_company, language, country, franchise_info, title)
    - value (string or number)

    Sentence: "{sentence}"

    Only output JSON, nothing else.
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    text = response.text.strip()
    try:
        claims = json.loads(text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            claims = json.loads(match.group(0))
        else:
            claims = []
    return claims

# ---------------------------
# Helpers
# ---------------------------
def parse_money(value):
    """Convert human-readable money string to number"""
    value = str(value).lower().replace(",", "").strip()
    if "billion" in value:
        return float(re.search(r"[\d.]+", value).group()) * 1e9
    if "million" in value:
        return float(re.search(r"[\d.]+", value).group()) * 1e6
    match = re.search(r"[\d.]+", value)
    return float(match.group()) if match else None

def fuzzy_match(val, options, threshold=85):
    val = val.lower()
    for opt in options:
        if fuzz.token_set_ratio(val, opt.lower()) >= threshold:
            return True
    return False

def extract_year(value):
    return str(value)[:4]

# ---------------------------
# TMDB Smart Search
# ---------------------------
def get_tmdb_movie_info(title, year_hint=None):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
    resp = requests.get(url).json()
    if not resp.get("results"):
        return {}

    candidates = resp["results"]
    movie = candidates[0]

    if year_hint:
        # Pick movie closest to the year hint
        closest = min(
            candidates,
            key=lambda x: abs(int(x.get("release_date","9999-01-01")[:4]) - year_hint) if x.get("release_date") else 9999
        )
        movie = closest

    movie_id = movie["id"]
    details = requests.get(
        f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
    ).json()
    return details

# ---------------------------
# OMDB Smart Search
# ---------------------------
def get_omdb_movie_info(title, year_hint=None):
    search_url = f"http://www.omdbapi.com/?s={title}&apikey={OMDB_API_KEY}"
    search_resp = requests.get(search_url).json()
    if "Search" not in search_resp:
        return {}

    candidates = search_resp["Search"]
    chosen = candidates[0]

    if year_hint:
        closest = min(
            candidates,
            key=lambda x: abs(int(x.get("Year","9999")) - year_hint)
        )
        chosen = closest

    imdb_id = chosen["imdbID"]
    detail_url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={OMDB_API_KEY}"
    return requests.get(detail_url).json()

# ---------------------------
# Wikidata Smart Search
# ---------------------------
def get_wikidata_movie_info(title):
    endpoint = "https://query.wikidata.org/sparql"
    query = f"""
    SELECT ?item ?itemLabel ?directorLabel ?publicationDate ?boxOffice ?castLabel ?genreLabel ?awardLabel ?runtime ?productionCompanyLabel ?originalLanguageLabel ?countryLabel WHERE {{
      ?item wdt:P31 wd:Q11424.
      ?item rdfs:label ?label.
      FILTER(LANG(?label) = "en").
      FILTER(CONTAINS(LCASE(?label), LCASE("{title}"))).
      OPTIONAL {{ ?item wdt:P57 ?director. }}
      OPTIONAL {{ ?item wdt:P577 ?publicationDate. }}
      OPTIONAL {{ ?item wdt:P2142 ?boxOffice. }}
      OPTIONAL {{ ?item wdt:P161 ?cast. }}
      OPTIONAL {{ ?item wdt:P136 ?genre. }}
      OPTIONAL {{ ?item wdt:P166 ?award. }}
      OPTIONAL {{ ?item wdt:P2047 ?runtime. }}
      OPTIONAL {{ ?item wdt:P272 ?productionCompany. }}
      OPTIONAL {{ ?item wdt:P364 ?originalLanguage. }}
      OPTIONAL {{ ?item wdt:P495 ?country. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 10
    """
    headers = {"Accept": "application/sparql-results+json"}
    resp = requests.get(endpoint, params={"query": query}, headers=headers).json()
    return resp.get("results", {}).get("bindings", [])

# ---------------------------
# Claim Verification
# ---------------------------
def verify_claims(claims, title):
    year_hint = None
    for c in claims:
        if c["attribute"].lower() == "release_year":
            try: year_hint = int(c["value"])
            except: pass

    tmdb = get_tmdb_movie_info(title, year_hint)
    omdb = get_omdb_movie_info(title, year_hint)
    wikidata = get_wikidata_movie_info(title)

    results = []

    for claim in claims:
        attr, val = claim["attribute"].lower(), str(claim["value"]).lower()
        verdicts = []
        sources_used = set()

        # --- TITLE ---
        if attr == "title":
            tmdb_title = tmdb.get("title","").lower() if tmdb else ""
            omdb_title = omdb.get("Title","").lower() if omdb else ""
            wikidata_titles = [e["itemLabel"]["value"].lower() for e in wikidata if "itemLabel" in e]

            matched = val in [tmdb_title, omdb_title] + wikidata_titles
            if tmdb_title or omdb_title or wikidata_titles:
                verdicts.append(matched)
                if tmdb_title: sources_used.add("TMDB")
                if omdb_title: sources_used.add("OMDB")
                if wikidata_titles: sources_used.add("Wikidata")

        # --- DIRECTOR ---
        if attr == "director":
            if tmdb and "credits" in tmdb:
                directors = [c["name"] for c in tmdb["credits"]["crew"] if c["job"]=="Director"]
                if directors:
                    verdicts.append(fuzzy_match(val,directors))
                    sources_used.add("TMDB")
            if omdb and omdb.get("Director"):
                verdicts.append(fuzzy_match(val,[omdb.get("Director")]))
                sources_used.add("OMDB")
            if wikidata:
                matched = any(fuzzy_match(val,[entry.get("directorLabel",{}).get("value","")]) for entry in wikidata if "directorLabel" in entry)
                if matched: verdicts.append(True)
                sources_used.add("Wikidata")

        # --- ACTOR ---
        if attr == "actor":
            if tmdb and "credits" in tmdb:
                actors = [c["name"] for c in tmdb["credits"]["cast"][:50]]
                if actors:
                    verdicts.append(fuzzy_match(val,actors))
                    sources_used.add("TMDB")
            if omdb and omdb.get("Actors"):
                actors = [a.strip() for a in omdb.get("Actors","").split(",")]
                verdicts.append(fuzzy_match(val,actors))
                sources_used.add("OMDB")
            if wikidata:
                matched = any(fuzzy_match(val,[entry.get("castLabel",{}).get("value","")]) for entry in wikidata if "castLabel" in entry)
                if matched: verdicts.append(True)
                sources_used.add("Wikidata")

        # --- RELEASE YEAR ---
        if attr == "release_year":
            if tmdb and tmdb.get("release_date"):
                year = extract_year(tmdb.get("release_date"))
                verdicts.append(val==year.lower())
                sources_used.add("TMDB")
            if omdb and omdb.get("Year"):
                year = extract_year(omdb.get("Year"))
                verdicts.append(val==year.lower())
                sources_used.add("OMDB")
            if wikidata:
                matched = any(val in extract_year(entry.get("publicationDate",{}).get("value","")) for entry in wikidata if "publicationDate" in entry)
                if matched: verdicts.append(True)
                sources_used.add("Wikidata")

        # --- BOX OFFICE ---
        if attr == "box_office":
            claim_val = parse_money(val)
            matched = False
            if tmdb and tmdb.get("revenue"):
                tmdb_val = float(tmdb.get("revenue"))
                if claim_val and abs(claim_val - tmdb_val)/tmdb_val < 0.1:
                    matched = True
                sources_used.add("TMDB")
            if omdb and omdb.get("BoxOffice"):
                omdb_val = parse_money(omdb.get("BoxOffice"))
                if claim_val and omdb_val and abs(claim_val-omdb_val)/omdb_val<0.1:
                    matched=True
                sources_used.add("OMDB")
            if wikidata:
                for entry in wikidata:
                    if "boxOffice" in entry:
                        wik_val = parse_money(entry["boxOffice"]["value"])
                        if claim_val and wik_val and abs(claim_val-wik_val)/wik_val<0.1:
                            matched=True
                        sources_used.add("Wikidata")
            verdicts.append(matched)

        # --- FINAL VERDICT ---
        if not sources_used:
            status="❓ No Data Available"
        elif all(verdicts):
            status="✅ Correct"
        elif any(verdicts):
            status="⚠️ Mixed/Partial"
        else:
            status="❌ Incorrect"

        results.append({
            "claim": claim,
            "status": status,
            "sources_used": list(sources_used)
        })

    return results

# ---------------------------
# Main
# ---------------------------
if __name__=="__main__":
    sentence = "Titanic was directed by James Cameron, starred Leonardo DiCaprio, released in 1997, and made 2 billion dollars."
    claims = extract_claims(sentence)

    # get movie title from claims
    title_claims = [c for c in claims if c["attribute"].lower() == "title"]
    title = title_claims[0]["value"] if title_claims else "Titanic"

    results = verify_claims(claims,title)

    # Print JSON
    print("\n=== JSON OUTPUT ===")
    print(json.dumps(results, indent=2))

    # Human-readable summary
    print("\n=== HUMAN-READABLE SUMMARY ===")
    for res in results:
        claim = res["claim"]
        print(f"Claim: {claim['attribute']} = {claim['value']} → {res['status']} (sources used: {', '.join(res['sources_used'])})")
