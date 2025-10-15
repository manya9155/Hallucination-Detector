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
        match = re.search(r'\[.*\]', text, re.DOTALL)
        claims = json.loads(match.group(0)) if match else []
    return claims

# ---------------------------
# Helpers
# ---------------------------
def parse_money(value):
    value = str(value).lower().replace(",", "").strip()
    if "billion" in value:
        return float(re.search(r"[\d.]+", value).group()) * 1e9
    if "million" in value:
        return float(re.search(r"[\d.]+", value).group()) * 1e6
    match = re.search(r"[\d.]+", value)
    return float(match.group()) if match else None

def fuzzy_match(val, options, threshold=95):
    val = val.lower()
    for opt in options:
        if fuzz.token_set_ratio(val, opt.lower()) >= threshold:
            return True
    return False

def extract_year(value):
    if not value: return None
    match = re.match(r"(\d{4})", str(value))
    return match.group(1) if match else None

# ---------------------------
# TMDB Smart Search
# ---------------------------
def get_tmdb_movie_info(title, year_hint=None):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
    resp = requests.get(url).json()
    if not resp.get("results"): return {}
    candidates = resp["results"]

    best = max(candidates, key=lambda x: fuzz.token_set_ratio(title.lower(), x["title"].lower()))
    if year_hint:
        best_year = best.get("release_date", "0000")[:4]
        if abs(int(best_year or 0) - year_hint) > 2:
            best = min(candidates, key=lambda x: abs(int(x.get("release_date", "9999")[:4]) - year_hint))

    movie_id = best["id"]
    details = requests.get(
        f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&append_to_response=credits,belongs_to_collection"
    ).json()
    return details

# ---------------------------
# OMDB Smart Search (patched)
# ---------------------------
def get_omdb_movie_info(title, year_hint=None):
    search_url = f"http://www.omdbapi.com/?s={title}&apikey={OMDB_API_KEY}"
    search_resp = requests.get(search_url).json()
    if "Search" not in search_resp: return {}

    candidates = search_resp["Search"]

    # Pick best fuzzy match first
    chosen = max(candidates, key=lambda x: fuzz.token_set_ratio(title.lower(), x["Title"].lower()))

    if year_hint:
        def extract_start_year(x):
            y = str(x.get("Year", "9999"))
            match = re.match(r"(\d{4})", y)
            return int(match.group(1)) if match else 9999
        chosen = min(candidates, key=lambda x: abs(extract_start_year(x) - year_hint))

    imdb_id = chosen["imdbID"]
    detail_url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={OMDB_API_KEY}"
    return requests.get(detail_url).json()

# ---------------------------
# Wikidata Smart Search
# ---------------------------
def get_wikidata_movie_info(title):
    endpoint = "https://query.wikidata.org/sparql"
    query = f"""
    SELECT ?item ?itemLabel ?directorLabel ?publicationDate ?boxOffice ?castLabel ?genreLabel ?awardLabel ?runtime ?productionCompanyLabel ?originalLanguageLabel ?countryLabel ?partOfLabel WHERE {{
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
      OPTIONAL {{ ?item wdt:P179 ?partOf. }}  # Franchise info
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
            tmdb_title = tmdb.get("title", "").lower()
            omdb_title = omdb.get("Title", "").lower()
            wikidata_titles = [e["itemLabel"]["value"].lower() for e in wikidata if "itemLabel" in e]
            matched = fuzzy_match(val, [tmdb_title, omdb_title] + wikidata_titles)
            verdicts.append(matched)
            if tmdb_title: sources_used.add("TMDB")
            if omdb_title: sources_used.add("OMDB")
            if wikidata_titles: sources_used.add("Wikidata")

        # --- DIRECTOR / ACTOR ---
        if attr in ["director", "actor"]:
          val_lower = val.lower()
          matched = False

          # --- TMDB ---
          if tmdb and "credits" in tmdb:
              if attr == "director":
                  directors = [c["name"].lower() for c in tmdb["credits"]["crew"] if c.get("job", "").lower() == "director"]
                  if val_lower in directors:
                      matched = True
              else:
                  actors = [c["name"].lower() for c in tmdb["credits"]["cast"]]
                  if val_lower in actors:
                      matched = True
              if "credits" in tmdb:
                  sources_used.add("TMDB")

          # --- OMDB ---
          if omdb:
              key = "Director" if attr == "director" else "Actors"
              if omdb.get(key):
                  names = [n.strip().lower() for n in omdb[key].split(",")]
                  if val_lower in names:
                      matched = True
              sources_used.add("OMDB")

          # --- Wikidata ---
          if wikidata:
              key = "directorLabel" if attr == "director" else "castLabel"
              wd_names = [entry[key]["value"].lower() for entry in wikidata if key in entry]
              if val_lower in wd_names:
                  matched = True
              sources_used.add("Wikidata")

          verdicts.append(matched)



        # --- RELEASE YEAR ---
        if attr=="release_year":
            if tmdb.get("release_date"): verdicts.append(val==extract_year(tmdb["release_date"]).lower()); sources_used.add("TMDB")
            if omdb.get("Year"): verdicts.append(val==extract_year(omdb["Year"]).lower()); sources_used.add("OMDB")
            if any(val==extract_year(entry.get("publicationDate", {}).get("value","")) for entry in wikidata if "publicationDate" in entry): verdicts.append(True); sources_used.add("Wikidata")

        # --- BOX OFFICE ---
        if attr=="box_office":
            claim_val = parse_money(val)
            matched = False
            if tmdb.get("revenue"): tmdb_val=float(tmdb.get("revenue")); matched |= claim_val and abs(claim_val-tmdb_val)/tmdb_val<0.1; sources_used.add("TMDB")
            if omdb.get("BoxOffice"): omdb_val=parse_money(omdb.get("BoxOffice")); matched |= claim_val and omdb_val and abs(claim_val-omdb_val)/omdb_val<0.1; sources_used.add("OMDB")
            if wikidata:
                for entry in wikidata:
                    if "boxOffice" in entry: wik_val=parse_money(entry["boxOffice"]["value"]); matched |= claim_val and wik_val and abs(claim_val-wik_val)/wik_val<0.1; sources_used.add("Wikidata")
            verdicts.append(matched)

        # --- GENRE / AWARD / RATING / RUNTIME / LANGUAGE / COUNTRY / PRODUCTION / FRANCHISE ---
        if attr in ["genre","award","rating","runtime","language","country","production_company","franchise_info"]:
            # TMDB
            if attr=="genre" and "genres" in tmdb: verdicts.append(fuzzy_match(val,[g["name"] for g in tmdb["genres"]])); sources_used.add("TMDB")
            if attr=="rating" and tmdb.get("vote_average"): verdicts.append(abs(float(tmdb["vote_average"])-float(val))<1); sources_used.add("TMDB")
            if attr=="runtime" and tmdb.get("runtime"): verdicts.append(str(tmdb["runtime"]) in val or val in str(tmdb["runtime"])); sources_used.add("TMDB")
            if attr=="franchise_info":
                found=False
                if tmdb.get("belongs_to_collection"):
                    coll_name = tmdb["belongs_to_collection"]["name"].lower()
                    if val in coll_name: verdicts.append(True); found=True
                for entry in wikidata:
                    if "partOfLabel" in entry and val in entry["partOfLabel"]["value"].lower(): verdicts.append(True); found=True; sources_used.add("Wikidata")
                if not found: verdicts.append(False)

            # OMDB
            if omdb:
                if attr=="genre" and omdb.get("Genre"): verdicts.append(fuzzy_match(val,omdb["Genre"].split(","))); sources_used.add("OMDB")
                if attr=="award" and omdb.get("Awards"): verdicts.append(fuzzy_match(val,[omdb["Awards"]])); sources_used.add("OMDB")
                if attr=="production_company" and omdb.get("Production"): verdicts.append(fuzzy_match(val,[omdb["Production"]])); sources_used.add("OMDB")
                if attr=="language" and omdb.get("Language"): verdicts.append(fuzzy_match(val,omdb["Language"].split(","))); sources_used.add("OMDB")
                if attr=="country" and omdb.get("Country"): verdicts.append(fuzzy_match(val,omdb["Country"].split(","))); sources_used.add("OMDB")

        # --- FINAL VERDICT ---
        if not sources_used: status=" No Data Available"
        elif all(verdicts): status=" Correct"
        elif any(verdicts): status=" Mixed/Partial"
        else: status="Incorrect"

        results.append({"claim":claim,"status":status,"sources_used":list(sources_used)})

    return results

# ---------------------------
# Main
# ---------------------------
if __name__=="__main__":
    sentence = "Dune is a sci-fi"
    claims = extract_claims(sentence)

    title_claims = [c for c in claims if c["attribute"].lower()=="title"]
    title = title_claims[0]["value"] if title_claims else "Avengers: Endgame"

    results = verify_claims(claims, title)

    print("\n=== JSON OUTPUT ===")
    print(json.dumps(results, indent=2))

    print("\n=== HUMAN-READABLE SUMMARY ===")
    for res in results:
        claim = res["claim"]
        print(f"Claim: {claim['attribute']} = {claim['value']} → {res['status']} (sources: {', '.join(res['sources_used'])})")
