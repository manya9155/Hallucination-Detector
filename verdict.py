"""
Full movie-claim verifier: TMDb (Bearer token) + OMDb fallback + Wikidata (Oscar verification)
- Requires: requests, rapidfuzz
    pip install requests rapidfuzz
- Replace OMDB_API_KEY placeholder with your actual OMDb key if you want OMDb fallback.
"""

import re
import requests
from rapidfuzz import process, fuzz
import json
import time

# ---------------------------
# CONFIG
# ---------------------------
TMDB_BEARER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhMTgyZjI1Njg0Nzc1ZjlkYTdjNDUyMzQ1MGVkYTEwNCIsIm5iZiI6MTc1ODg2MjY4OC4wOCwic3ViIjoiNjhkNjFkNjA3ZDExMTU0YmM3ZDNjZDM0Iiwic2NvcGVzIjpbImFwaV9yZWFkIl0sInZlcnNpb24iOjF9.lsBLFLRbb8mgUNWf1lR16P8KLArfvcPZGI_frqnCGtU"
OMDB_API_KEY = "a6f7938d"   # <-- replace if you want OMDb fallback

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "MovieFactChecker/1.0 (contact: you@example.com)"  # change if you want

# ---------------------------
# NETWORK / TMDB helpers (Bearer token)
# ---------------------------
def tmdb_get(path, params=None, timeout=10):
    base = "https://api.themoviedb.org/3"
    url = base.rstrip("/") + "/" + path.lstrip("/")
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_BEARER_TOKEN}",
        "User-Agent": USER_AGENT
    }
    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"TMDb network error for {url} : {e}")
        return None

def tmdb_search_person(name, limit=10):
    if not name:
        return []
    data = tmdb_get("/search/person", params={"query": name})
    return (data.get("results", [])[:limit]) if data else []

def tmdb_search_movie(title, year=None, limit=10):
    if not title:
        return []
    params = {"query": title}
    if year:
        params["year"] = year
    data = tmdb_get("/search/movie", params=params)
    return (data.get("results", [])[:limit]) if data else []

def tmdb_movie_details(movie_id):
    if not movie_id:
        return None
    return tmdb_get(f"/movie/{movie_id}", params={"append_to_response": "credits"})

def tmdb_movie_credits(movie_id):
    if not movie_id:
        return None
    return tmdb_get(f"/movie/{movie_id}/credits")

# ---------------------------
# OMDb helper (fallback)
# ---------------------------
def omdb_lookup_title(title, year=None):
    if not OMDB_API_KEY or OMDB_API_KEY.startswith("YOUR_OMDB"):
        return None
    params = {"t": title, "apikey": OMDB_API_KEY}
    if year:
        params["y"] = str(year)
    try:
        r = requests.get("https://www.omdbapi.com/", params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        return data if data.get("Response") == "True" else None
    except requests.exceptions.RequestException as e:
        print("OMDb network error:", e)
        return None

# ---------------------------
# Wikidata helpers (SPARQL) - for Oscars / Academy Awards verification
# ---------------------------
def wikidata_person_qid(person_name):
    """Try to find a Wikidata QID for the person by label (best-effort)."""
    q = """
    SELECT ?person WHERE {
      ?person rdfs:label "%s"@en.
      ?person wdt:P31 wd:Q5.
    } LIMIT 5
    """ % person_name.replace('"', '\\"')
    try:
        r = requests.get(WIKIDATA_SPARQL, params={"query": q, "format": "json"},
                         headers={"User-Agent": USER_AGENT}, timeout=10)
        r.raise_for_status()
        data = r.json()
        bindings = data.get("results", {}).get("bindings", [])
        if not bindings:
            # try search by alias (more flexible)
            q2 = """
            SELECT ?person ?personLabel WHERE {
              ?person wdt:P31 wd:Q5.
              ?person rdfs:label ?personLabel.
              FILTER(CONTAINS(LCASE(?personLabel), LCASE("%s"))).
              SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
            } LIMIT 10
            """ % person_name.replace('"', '\\"')
            r2 = requests.get(WIKIDATA_SPARQL, params={"query": q2, "format": "json"},
                              headers={"User-Agent": USER_AGENT}, timeout=10)
            r2.raise_for_status()
            data2 = r2.json()
            bs = data2.get("results", {}).get("bindings", [])
            if not bs:
                return None
            # pick first
            return bs[0]["person"]["value"].split("/")[-1]
        return bindings[0]["person"]["value"].split("/")[-1]
    except Exception as e:
        print("Wikidata person lookup error:", e)
        return None

def wikidata_film_qid(title):
    """Try to find a Wikidata QID for a film title."""
    q = """
    SELECT ?film WHERE {
      ?film wdt:P31 wd:Q11424.
      ?film rdfs:label "%s"@en.
    } LIMIT 10
    """ % title.replace('"', '\\"')
    try:
        r = requests.get(WIKIDATA_SPARQL, params={"query": q, "format": "json"},
                         headers={"User-Agent": USER_AGENT}, timeout=10)
        r.raise_for_status()
        data = r.json()
        bindings = data.get("results", {}).get("bindings", [])
        if not bindings:
            # fallback to contains match
            q2 = """
            SELECT ?film ?filmLabel WHERE {
              ?film wdt:P31 wd:Q11424.
              ?film rdfs:label ?filmLabel.
              FILTER(CONTAINS(LCASE(?filmLabel), LCASE("%s"))).
              SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
            } LIMIT 10
            """ % title.replace('"', '\\"')
            r2 = requests.get(WIKIDATA_SPARQL, params={"query": q2, "format": "json"},
                              headers={"User-Agent": USER_AGENT}, timeout=10)
            r2.raise_for_status()
            data2 = r2.json()
            bs = data2.get("results", {}).get("bindings", [])
            if not bs:
                return None
            return bs[0]["film"]["value"].split("/")[-1]
        return bindings[0]["film"]["value"].split("/")[-1]
    except Exception as e:
        print("Wikidata film lookup error:", e)
        return None

def wikidata_check_oscar_win(person_name, film_title=None, year=None):
    """
    Check Wikidata for Academy Award wins for a person (optionally restricted to a film and/or year).
    Returns dict with supported boolean, and evidence list.
    """
    person_qid = wikidata_person_qid(person_name)
    if not person_qid:
        return {"supported": False, "evidence": [], "reason": f"No Wikidata QID for '{person_name}'"}

    film_qid = None
    if film_title:
        film_qid = wikidata_film_qid(film_title)

    # Build SPARQL
    # Check P166 (award received) with award instance of Academy Award (Q19020)
    # Optionally filter on awarded for (P1686) and time (P585)
    film_filter = f"FILTER (?work = wd:{film_qid})" if film_qid else ""
    year_filter = f'FILTER (STRSTARTS(STR(?time), "{int(year)}"))' if year else ""
    query = f"""
    SELECT ?workLabel ?time ?awardLabel WHERE {{
      BIND(wd:{person_qid} AS ?person).
      ?person p:P166 ?awardStatement.
      ?awardStatement ps:P166 ?awardItem.
      ?awardItem wdt:P31 wd:Q19020.  # Academy Award
      OPTIONAL {{ ?awardStatement pq:P1686 ?work. }}
      OPTIONAL {{ ?awardStatement pq:P585 ?time. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      {film_filter}
      {year_filter}
    }} LIMIT 50
    """
    try:
        r = requests.get(WIKIDATA_SPARQL, params={"query": query, "format": "json"},
                         headers={"User-Agent": USER_AGENT}, timeout=15)
        r.raise_for_status()
        data = r.json()
        bindings = data.get("results", {}).get("bindings", [])
        if not bindings:
            return {"supported": False, "evidence": [], "reason": "No Academy Award win found on Wikidata for given filters."}
        evidence = []
        for b in bindings:
            evidence.append({
                "work": b.get("workLabel", {}).get("value"),
                "time": b.get("time", {}).get("value"),
                "award": b.get("awardLabel", {}).get("value")
            })
        return {"supported": True, "evidence": evidence}
    except Exception as e:
        print("Wikidata SPARQL error:", e)
        return {"supported": False, "evidence": [], "reason": "Wikidata query failed."}

# ---------------------------
# Claim parsing & fuzzy helpers
# ---------------------------
def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def parse_claim_text(claim: str):
    s = claim.strip()
    out = {"raw": s, "type": "unknown", "person": None, "movie": None, "award": None, "year": None, "director": None}
    # find year
    y = re.search(r"\b(19|20)\d{2}\b", s)
    if y:
        out["year"] = int(y.group(0))

    # director patterns
    m = re.search(r"(.+?)\s+was\s+directed\s+by\s+(.+)", s, re.I)
    if m:
        out["type"] = "director_of_movie"
        out["movie"] = m.group(1).strip(' "\'')
        out["director"] = m.group(2).strip(' "\'')
        return out
    m = re.search(r"(.+?)\s+directed\s+by\s+(.+)", s, re.I)
    if m:
        out["type"] = "director_of_movie"
        out["movie"] = m.group(1).strip(' "\'')
        out["director"] = m.group(2).strip(' "\'')
        return out

    # actor in movie
    m = re.search(r"(.+?)\s+(acted in|starred in|appeared in|played in)\s+(.+)", s, re.I)
    if m:
        out["type"] = "actor_in_movie"
        out["person"] = m.group(1).strip(' "\'')
        out["movie"] = m.group(3).strip(' "\'')
        return out

    # won Oscar for movie
    m = re.search(r"(.+?)\s+won\s+(an|the)?\s*oscar\s+for\s+(.+?)(?:\s+in\s+(\d{4}))?$", s, re.I)
    if m:
        out["type"] = "won_oscar_for_movie"
        out["person"] = m.group(1).strip(' "\'')
        out["movie"] = m.group(3).strip(' "\'')
        if m.group(4):
            out["year"] = int(m.group(4))
        out["award"] = "Oscar"
        return out

    # won Oscar in year
    m = re.search(r"(.+?)\s+won\s+(an|the)?\s*oscar\s+in\s+(\d{4})", s, re.I)
    if m:
        out["type"] = "won_oscar_in_year"
        out["person"] = m.group(1).strip(' "\'')
        out["year"] = int(m.group(3))
        out["award"] = "Oscar"
        return out

    # won Oscar (no movie)
    m = re.search(r"(.+?)\s+won\s+(an|the)?\s*oscar\b", s, re.I)
    if m:
        out["type"] = "won_oscar"
        out["person"] = m.group(1).strip(' "\'')
        out["award"] = "Oscar"
        return out

    # fallback: "Movie was directed by X" reversed
    m = re.search(r"(.+?)\s+was directed by\s+(.+)", s, re.I)
    if m:
        out["type"] = "director_of_movie"
        out["movie"] = m.group(1).strip(' "\'')
        out["director"] = m.group(2).strip(' "\'')
        return out

    # If none matched
    return out

# fuzzy thresholds
PERSON_THR = 82
MOVIE_THR = 80
CAST_THR = 85
DIRECTOR_THR = 85

def fuzzy_pick_person(name):
    candidates = tmdb_search_person(name)
    if not candidates:
        return {"found": False, "name": None, "id": None, "score": 0, "notice": ""}
    names = [p.get("name") for p in candidates if p.get("name")]
    best = process.extractOne(name, names, scorer=fuzz.token_sort_ratio)
    if not best:
        return {"found": False, "name": None, "id": None, "score": 0, "notice": ""}
    best_name, score = best[0], int(best[1])
    tmdb_id = next((p["id"] for p in candidates if p.get("name") == best_name), None)
    notice = ""
    if score < PERSON_THR:
        notice = f'Notice: best fuzzy match for "{name}" is "{best_name}" (score {score}%) — low confidence.'
    else:
        notice = f'Notice: using closest match "{best_name}" for input "{name}" (score {score}%).'
    return {"found": True, "name": best_name, "id": tmdb_id, "score": score, "notice": notice}

def fuzzy_pick_movie(title, year=None):
    candidates = tmdb_search_movie(title, year=year)
    if not candidates:
        return {"found": False, "title": None, "id": None, "score": 0, "release_year": None, "notice": ""}
    titles = [c.get("title") for c in candidates if c.get("title")]
    best = process.extractOne(title, titles, scorer=fuzz.token_sort_ratio)
    if not best:
        return {"found": False, "title": None, "id": None, "score": 0, "release_year": None, "notice": ""}
    best_title, score = best[0], int(best[1])
    tmdb_id = next((c["id"] for c in candidates if c.get("title") == best_title), None)
    release_year = next((c.get("release_date","")[:4] for c in candidates if c.get("title") == best_title), None)
    notice = f'Notice: using closest movie match "{best_title}" for input "{title}" (score {score}%).'
    return {"found": True, "title": best_title, "id": tmdb_id, "score": score, "release_year": release_year, "notice": notice}

# ---------------------------
# Verification functions
# ---------------------------
def verify_actor_in_movie(person_raw, movie_raw):
    notices = []
    person_res = fuzzy_pick_person(person_raw)
    if person_res["notice"]:
        notices.append(person_res["notice"])
    if not person_res["found"]:
        return {"verdict": "Not enough evidence", "explanation": f"No TMDb person found similar to '{person_raw}'", "evidence": [], "notices": notices}

    movie_res = fuzzy_pick_movie(movie_raw)
    if movie_res["notice"]:
        notices.append(movie_res["notice"])
    if not movie_res["found"]:
        return {"verdict": "Not enough evidence", "explanation": f"No TMDb movie found similar to '{movie_raw}'", "evidence": [], "notices": notices}

    credits = tmdb_movie_credits(movie_res["id"])
    if not credits:
        return {"verdict": "Not enough evidence", "explanation": "Could not retrieve movie credits from TMDb", "evidence": [], "notices": notices}

    cast_names = [c.get("name") for c in credits.get("cast", []) if c.get("name")]
    best = process.extractOne(person_res["name"], cast_names, scorer=fuzz.token_sort_ratio)
    if best and best[1] >= CAST_THR:
        matched_name, score = best[0], int(best[1])
        evidence = [f"TMDb movie: /movie/{movie_res['id']}"]
        return {"verdict": "Supported", "explanation": f"{person_res['name']} appears in cast of {movie_res['title']} (matched {matched_name}, {score}%).", "evidence": evidence, "notices": notices}
    else:
        evidence = [f"TMDb movie: /movie/{movie_res['id']}"]
        return {"verdict": "Refuted", "explanation": f"{person_res['name']} not found in cast of {movie_res['title']} (best cast match: {best}).", "evidence": evidence, "notices": notices}

def verify_director_of_movie(movie_raw, director_raw):
    notices = []
    movie_res = fuzzy_pick_movie(movie_raw)
    if movie_res["notice"]:
        notices.append(movie_res["notice"])
    if not movie_res["found"]:
        return {"verdict": "Not enough evidence", "explanation": f"No movie match for '{movie_raw}'", "evidence": [], "notices": notices}

    details = tmdb_movie_details(movie_res["id"])
    if not details:
        return {"verdict": "Not enough evidence", "explanation": "Could not fetch movie details from TMDb", "evidence": [], "notices": notices}

    directors = [c.get("name") for c in details.get("credits", {}).get("crew", []) if c.get("job") == "Director"]
    best = process.extractOne(director_raw, directors or [], scorer=fuzz.token_sort_ratio)
    if best and best[1] >= DIRECTOR_THR:
        return {"verdict": "Supported", "explanation": f"{best[0]} is listed as director of {details.get('title')}.", "evidence": [f"TMDb movie: /movie/{movie_res['id']}"], "notices": notices}
    else:
        return {"verdict": "Refuted", "explanation": f"{director_raw} not listed as director of {details.get('title')}. Best director match: {best}.", "evidence": [f"TMDb movie: /movie/{movie_res['id']}"], "notices": notices}

def verify_won_oscar_for_movie(person_raw, movie_raw, year=None):
    notices = []
    # 1. ensure person appears in the movie
    actor_check = verify_actor_in_movie(person_raw, movie_raw)
    if actor_check["verdict"] != "Supported":
        return {"verdict": "Refuted", "explanation": f"Actor check failed: {actor_check['explanation']}", "evidence": actor_check.get("evidence", []), "notices": actor_check.get("notices", [])}
    notices.extend(actor_check.get("notices", []))

    # 2. try OMDb for movie awards
    om = omdb_lookup_title(movie_raw, year)
    if om:
        awards_text = om.get("Awards", "")
        if "Oscar" in awards_text or "Academy Award" in awards_text:
            person_last = person_raw.split()[-1] if person_raw else None
            if person_last and person_last.lower() in awards_text.lower():
                return {"verdict": "Supported", "explanation": f"OMDb awards for {om.get('Title')} mention Oscars and include '{person_last}'.", "evidence": [f"OMDb: {om.get('Title')} awards: {awards_text}"], "notices": notices}
            # OMDb says movie has Oscars but not necessarily person-match: use Wikidata next
        else:
            # OMDb explicitly does not list Oscars for movie
            # but proceed to check Wikidata in case OMDb is incomplete
            pass
    # 3. Use Wikidata to check person-level Oscar win for that film/year
    wd = wikidata_check_oscar_win(person_raw, film_title=movie_raw, year=year)
    if wd.get("supported"):
        return {"verdict": "Supported", "explanation": f"Wikidata shows Academy Award win for {person_raw} (evidence: {wd.get('evidence')}).", "evidence": wd.get("evidence"), "notices": notices}
    # If neither OMDb nor Wikidata found evidence
    return {"verdict": "Refuted" if om and ("Oscar" not in (om.get("Awards") or "")) else "Not enough evidence",
            "explanation": "No reliable evidence found that person won an Oscar for the film (OMDb and Wikidata checks failed or were inconclusive).",
            "evidence": (om and [f"OMDb: {om.get('Title')} awards: {om.get('Awards')}"]) or wd.get("evidence", []),
            "notices": notices}

def verify_won_oscar(person_raw, year=None):
    # Person-level check: try Wikidata directly
    wd = wikidata_check_oscar_win(person_raw, film_title=None, year=year)
    if wd.get("supported"):
        return {"verdict": "Supported", "explanation": f"Wikidata shows Academy Award win(s) for {person_raw}.", "evidence": wd.get("evidence"), "notices": []}
    return {"verdict": "Not enough evidence", "explanation": "No person-level Oscar found via Wikidata.", "evidence": [], "notices": []}

# ---------------------------
# Top-level single-claim verifier
# ---------------------------
def verify_single_claim(claim_text):
    parsed = parse_claim_text(claim_text)
    ctype = parsed["type"]
    if ctype == "actor_in_movie":
        return verify_actor_in_movie(parsed["person"], parsed["movie"])
    if ctype == "director_of_movie":
        return verify_director_of_movie(parsed["movie"], parsed["director"])
    if ctype == "won_oscar_for_movie":
        return verify_won_oscar_for_movie(parsed["person"], parsed["movie"], year=parsed.get("year"))
    if ctype == "won_oscar_in_year":
        return {"verdict": "Not enough evidence", "explanation": "Year-specific person award checks are supported via Wikidata; pass with movie context for better accuracy."}
    if ctype == "won_oscar":
        return verify_won_oscar(parsed["person"], year=parsed.get("year"))
    return {"verdict": "Not enough evidence", "explanation": "Claim type not recognized.", "evidence": [], "notices": []}

# ---------------------------
# Claim extraction wrapper (Gemini optional)
# ---------------------------
import os

# Replace with your actual API key
os.environ["GEMINI_API_KEY"] = "AIzaSyCNs-FR4ti3Xz_olgxXQWQt1h8boDWEJhU"

# try:
#     from google import genai
#     genai_client = genai.Client()
#     GEMINI_AVAILABLE = True
# except Exception:
#     GEMINI_AVAILABLE = False

# def extract_claims_with_gemini(sentence: str):
#     if not GEMINI_AVAILABLE:
#         raise RuntimeError("Gemini client not available in this environment.")
#     prompt = f"""
# You are a fact extraction assistant.
# Break the following sentence into independent factual claims:
# "{sentence}"
# """
#     resp = genai_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
#     text = getattr(resp, "text", str(resp))
#     lines = [l.strip() for l in text.splitlines() if l.strip()]
#     cleaned = []
#     for line in lines:
#         if line.lower().startswith("here are"):
#             continue
#         c = re.sub(r'^[\-\*\•\s]*', '', line).strip()
#         if c:
#             cleaned.append(c)
#     else:
#         prompt = f"""
#         You are a fact extraction assistant.
#         Break the following sentence into independent factual claims:
#         "{sentence}"
#         """
#         response = genai_client.models.generate_content(
#             model="gemini-2.5-flash",  # You can choose other models like "gemini-2.5-pro" if needed
#             contents=prompt
#         )
#         claims = response.text.strip().split("\n")
#         return [claim.strip() for claim in claims if claim.strip()]
#     return cleaned
from google import genai

# Initialize the Gemini client
client = genai.Client()
GEMINI_AVAILABLE = True
def extract_claims(sentence):
    prompt = f"""
    You are a fact extraction assistant.
    Break the following sentence into independent factual claims:
    "{sentence}"
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",  # You can choose other models like "gemini-2.5-pro" if needed
        contents=prompt
    )
    claims = response.text.strip().split("\n")
    for c in claims:
        if "factual claims" in c:
            claims.remove(c)
        else:
            continue
    return [claim.strip() for claim in claims if claim.strip()]

def extract_claims_fallback(sentence: str):
    # If the sentence contains multiple bullet-like splits, split on newlines or bullets
    if "\n" in sentence or "*" in sentence or "-" in sentence:
        lines = [l.strip() for l in re.split(r'[\n\r]+', sentence) if l.strip()]
        return [re.sub(r'^[\-\*\•\s]*', '', l).strip() for l in lines if l.strip()]
    # otherwise split on sentence boundaries
    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', sentence) if p.strip()]
    return parts

def get_claims(sentence: str):
    if GEMINI_AVAILABLE:
        try:
            return extract_claims(sentence)
        except Exception as e:
            print("Gemini extraction failed, falling back:", e)
            return extract_claims_fallback(sentence)
    else:
        return extract_claims_fallback(sentence)

# ---------------------------
# Bulk verifier
# ---------------------------
def verify_claims_from_sentence(sentence: str):
    raw_claims = get_claims(sentence)
    results = []
    for rc in raw_claims:
        res = verify_single_claim(rc)
        results.append({"claim": rc, "result": res})
        # be polite to APIs
        time.sleep(0.2)
    return results

# ---------------------------
# Example usage
# ---------------------------
if __name__ == "__main__":
    test_sentence = "Leonardo DiCaprio won an Oscar for Inception in 2016 directed by Nolan."
    print("Input sentence:", test_sentence)
    print("\nExtracting claims...")
    claims = get_claims(test_sentence)
    for c in claims:
        if "factual claims" in c:
            continue
        else:
            print(c)

    print("\nVerifying claims...")
    results = verify_claims_from_sentence(test_sentence)
    print(json.dumps(results, indent=2))
