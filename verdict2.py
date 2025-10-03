"""
Final integrated verifier (granular claims)
- Uses Gemini (google.genai) to extract claims, cleans & canonicalizes them,
  then verifies each with TMDb / OMDb / Wikidata as needed.
- Requirements:
    pip install requests rapidfuzz google-genai
"""

import re
import time
import requests
import json
from rapidfuzz import process, fuzz

# ---------------------------
# CONFIG - replace OMDB if needed
# ---------------------------
TMDB_BEARER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhMTgyZjI1Njg0Nzc1ZjlkYTdjNDUyMzQ1MGVkYTEwNCIsIm5iZiI6MTc1ODg2MjY4OC4wOCwic3ViIjoiNjhkNjFkNjA3ZDExMTU0YmM3ZDNjZDM0Iiwic2NvcGVzIjpbImFwaV9yZWFkIl0sInZlcnNpb24iOjF9.lsBLFLRbb8mgUNWf1lR16P8KLArfvcPZGI_frqnCGtU"
OMDB_API_KEY = "a6f7938d"   # optional fallback (replace if you want OMDb fallback)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "MovieFactChecker/1.0 (contact: you@example.com)"

# ---------------------------
# Silence the google-genai Client destructor bug (optional)
# ---------------------------
try:
    import google.genai as _gg
    # override __del__ if present to avoid AttributeError when interpreter exits
    if hasattr(_gg, "Client"):
        _gg.Client.__del__ = lambda self: None
except Exception:
    # google.genai might not be installed; that's fine
    pass

# ---------------------------
# Robust GET with retries
# ---------------------------
def robust_get(url, params=None, headers=None, timeout=10, retries=3, backoff=0.6):
    attempt = 0
    while attempt < retries:
        try:
            resp = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            attempt += 1
            if attempt >= retries:
                raise
            time.sleep(backoff * (2 ** (attempt - 1)))

# ---------------------------
# TMDb helpers (Bearer token)
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
        resp = robust_get(url, params=params or {}, headers=headers, timeout=timeout)
        return resp.json()
    except Exception as e:
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
# Wikidata helpers (resilient)
# ---------------------------
def wikidata_query(query, timeout=15):
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = robust_get(WIKIDATA_SPARQL, params={"query": query, "format": "json"}, headers=headers, timeout=timeout)
        return resp.json()
    except Exception as e:
        print("Wikidata SPARQL error:", e)
        return None

def wikidata_person_qid(person_name):
    q = """
    SELECT ?person WHERE {
      ?person rdfs:label "%s"@en.
      ?person wdt:P31 wd:Q5.
    } LIMIT 5
    """ % person_name.replace('"', '\\"')
    data = wikidata_query(q)
    if not data:
        # fallback contains-search
        q2 = """
        SELECT ?person ?personLabel WHERE {
          ?person wdt:P31 wd:Q5.
          ?person rdfs:label ?personLabel.
          FILTER(CONTAINS(LCASE(?personLabel), LCASE("%s"))).
          SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
        } LIMIT 10
        """ % person_name.replace('"', '\\"')
        data2 = wikidata_query(q2)
        if not data2:
            return None
        bs = data2.get("results", {}).get("bindings", [])
        return bs[0]["person"]["value"].split("/")[-1] if bs else None
    bindings = data.get("results", {}).get("bindings", [])
    return bindings[0]["person"]["value"].split("/")[-1] if bindings else None

def wikidata_film_qid(title):
    q = """
    SELECT ?film WHERE {
      ?film wdt:P31 wd:Q11424.
      ?film rdfs:label "%s"@en.
    } LIMIT 10
    """ % title.replace('"', '\\"')
    data = wikidata_query(q)
    if not data:
        q2 = """
        SELECT ?film ?filmLabel WHERE {
          ?film wdt:P31 wd:Q11424.
          ?film rdfs:label ?filmLabel.
          FILTER(CONTAINS(LCASE(?filmLabel), LCASE("%s"))).
          SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
        } LIMIT 10
        """ % title.replace('"', '\\"')
        data2 = wikidata_query(q2)
        if not data2:
            return None
        bs = data2.get("results", {}).get("bindings", [])
        return bs[0]["film"]["value"].split("/")[-1] if bs else None
    bindings = data.get("results", {}).get("bindings", [])
    return bindings[0]["film"]["value"].split("/")[-1] if bindings else None

def wikidata_check_oscar_win(person_name, film_title=None, year=None):
    person_qid = wikidata_person_qid(person_name)
    if not person_qid:
        return {"supported": False, "evidence": [], "reason": f"No Wikidata QID for '{person_name}'"}
    film_qid = None
    if film_title:
        film_qid = wikidata_film_qid(film_title)
    film_filter = f"FILTER (?work = wd:{film_qid})" if film_qid else ""
    year_filter = f'FILTER (STRSTARTS(STR(?time), "{int(year)}"))' if year else ""
    query = f"""
    SELECT ?workLabel ?time ?awardLabel WHERE {{
      BIND(wd:{person_qid} AS ?person).
      ?person p:P166 ?awardStatement.
      ?awardStatement ps:P166 ?awardItem.
      ?awardItem wdt:P31 wd:Q19020.
      OPTIONAL {{ ?awardStatement pq:P1686 ?work. }}
      OPTIONAL {{ ?awardStatement pq:P585 ?time. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      {film_filter}
      {year_filter}
    }} LIMIT 50
    """
    data = wikidata_query(query)
    if not data:
        return {"supported": False, "evidence": [], "reason": "Wikidata query failed or timed out."}
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

# ---------------------------
# Claim cleaning & repair (granular A behavior)
# ---------------------------

def strip_numbering_and_bullets(line: str) -> str:
    line = re.sub(r'^\s*\d+[\.\)]\s*', '', line)  # leading numbers
    line = re.sub(r'^[\-\*\•\–\—\s]+', '', line)  # bullets/dashes
    return line.strip()

def extract_person_candidate(text: str):
    m = re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text)
    return m.group(1) if m else None

def normalize_movie_title(t: str):
    t = t.strip()
    t = re.sub(r'^[\'"]|[\'"]$', '', t)
    m = re.search(r'film\s+[\'"]?(.+?)[\'"]?$', t, re.I)
    if m:
        return m.group(1).strip()
    return t

def canonicalize_claim_from_fragment(fragment: str, last_subject: str = None):
    f = fragment.strip()
    f = re.sub(r'^[\-\*\•\s]*', '', f).strip()
    # "The Oscar was awarded for the film "Inception"."
    m = re.search(r'(?i)the\s+oscar\s+(?:was\s+awarded|was\s+given|awarded)\s+for\s+(?:the\s+film\s+)?[\'"]?(.+?)[\'"]?\.?$', f)
    if m and last_subject:
        movie = normalize_movie_title(m.group(1))
        return f"{last_subject} won an Oscar for {movie}."
    # "The Oscar was awarded in 2016."
    m = re.search(r'(?i)the\s+oscar\s+(?:was\s+awarded|was\s+given|awarded)\s+in\s+(\d{4})', f)
    if m and last_subject:
        return f"{last_subject} won an Oscar in {m.group(1)}."
    # "The film "Inception" was directed by Nolan."
    m = re.search(r'(?i)(?:the\s+film\s+)?[\'"]?(.+?)[\'"]?\s+was\s+directed\s+by\s+(.+)', f)
    if m:
        movie = normalize_movie_title(m.group(1))
        director = m.group(2).strip(' .')
        return f"{movie} was directed by {director}."
    # Accept canonical sentence with person and verb
    if re.search(r'\b(won|acted|starred|directed|was|played)\b', f, re.I) and extract_person_candidate(f):
        return f
    # fallback: if mentions Oscar and last_subject exists
    if last_subject and re.search(r'(?i)oscar|academy award|won', f):
        return f"{last_subject} {f}"
    return None

def postprocess_gemini_lines(lines, autofill_subject=True):
    cleaned = []
    last_person = None
    for raw in lines:
        if not raw or raw.lower().startswith("here are") or raw.lower().startswith("claims"):
            continue
        s = strip_numbering_and_bullets(raw)
        s = s.strip()
        # update last_person if explicit person appears
        p_cand = extract_person_candidate(s)
        if p_cand:
            last_person = p_cand
        canonical = canonicalize_claim_from_fragment(s, last_subject=last_person if autofill_subject else None)
        if canonical:
            cleaned.append(canonical)
            p = extract_person_candidate(canonical)
            if p:
                last_person = p
            continue
        # fallback heuristics
        if re.search(r'(?i)oscar|academy award', s) and last_person:
            m = re.search(r'(\d{4})', s)
            if m:
                cleaned.append(f"{last_person} won an Oscar in {m.group(1)}.")
                continue
            cleaned.append(f"{last_person} won an Oscar.")
            continue
        cleaned.append(s)
    # dedupe preserving order
    seen = set()
    out = []
    for c in cleaned:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out

# ---------------------------
# Gemini extraction wrapper (uses google.genai)
# ---------------------------
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

GEMINI_AVAILABLE = False
try:
    from google import genai
    genai_client = genai.Client()
    GEMINI_AVAILABLE = True
except Exception:
    genai_client = None
    GEMINI_AVAILABLE = False

import re

def normalize_extracted_claims(raw_claims):
    """
    Cleans claims from Gemini:
    - Removes numbering/bullets
    - Resolves pronouns to previous PERSON subject
    - Ensures subjects are human entities (not objects like "The Oscar")
    - Normalizes director syntax (X directed film Y → Y was directed by X)
    """
    cleaned = []
    last_person = None  # Track last seen human subject

    for claim in raw_claims:
        # Remove bullet points or numbering like "1." or "*"
        claim = re.sub(r'^\s*[\-\*\d\.\)]+\s*', '', claim).strip()

        # Skip empty or junk claims
        if not claim or len(claim.split()) < 3:
            continue

        # Detect if claim starts with a person (capitalized name pattern)
        person_match = re.match(r'^([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b', claim)
        is_human_subject = bool(person_match)

        # If valid person found → update last_person
        if is_human_subject:
            last_person = person_match.group(1)

        # Resolve pronouns ONLY if last_person exists
        if last_person:
            claim = re.sub(r'^(He|She|They|His|Her|Their)\b', last_person, claim, flags=re.I)
            claim = re.sub(r'\b(his|her|their)\b', last_person + "'s", claim, flags=re.I)

        # Skip claims where subject is an OBJECT like "The Oscar", "The film", etc.
        if re.match(r'^(The (Oscar|Film|Movie|Award))\b', claim, flags=re.I):
            # If we have a last_person, attempt to rewrite this claim properly
            if last_person:
                claim = re.sub(r'^(The Oscar)\b', last_person + " won an Oscar", claim, flags=re.I)
                claim = re.sub(r'^(The film|The movie)\b', '', claim, flags=re.I).strip()
            else:
                continue  # drop it

        # Normalize "Nolan directed the film Inception" → "Inception was directed by Nolan"
        dir_pattern = re.match(r'^([A-Z][a-zA-Z\s]+)\s+directed\s+(?:the\s+)?film\s+(.+)$', claim, flags=re.I)
        if dir_pattern:
            director = dir_pattern.group(1).strip()
            movie = dir_pattern.group(2).strip().strip('"')
            claim = f"{movie} was directed by {director}"

        # Append cleaned claim
        cleaned.append(claim)

    return cleaned

def extract_claims_with_gemini(sentence: str):
    if not GEMINI_AVAILABLE:
        raise RuntimeError("Gemini not available in this environment.")
    prompt = f"""
    You are a fact extraction assistant.
    Break the following sentence into independent factual claims:
    "{sentence}"
    """
    resp = genai_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = getattr(resp, "text", str(resp))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines

def extract_claims_fallback(sentence: str):
    if "\n" in sentence or "*" in sentence or "-" in sentence:
        lines = [l.strip() for l in re.split(r'[\n\r]+', sentence) if l.strip()]
        return [re.sub(r'^[\-\*\•\s]*', '', l).strip() for l in lines if l.strip()]
    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', sentence) if p.strip()]
    return parts

def get_claims(sentence: str, autofill_subject=True):
    if GEMINI_AVAILABLE and genai_client:
        try:
            raw_lines = extract_claims_with_gemini(sentence)
            cleaned = postprocess_gemini_lines(raw_lines, autofill_subject=autofill_subject)
            # If Gemini returned a single long line, try fallback sentence split
            if len(cleaned) == 1 and len(raw_lines) == 1:
                # split the single line on sentence boundaries and re-process
                parts = extract_claims_fallback(raw_lines[0])
                return postprocess_gemini_lines(parts, autofill_subject=autofill_subject)
            return cleaned
        except Exception as e:
            print("Gemini extraction failed, falling back:", e)
            raw_lines = extract_claims_fallback(sentence)
            return postprocess_gemini_lines(raw_lines, autofill_subject=autofill_subject)
    else:
        raw_lines = extract_claims_fallback(sentence)
        return postprocess_gemini_lines(raw_lines, autofill_subject=autofill_subject)

# ---------------------------
# (Re-use verification functions from earlier implementation)
# For brevity, we assume verify_single_claim(...) is defined as earlier in your code.
# If you want, I can paste the full verify_single_claim and all verify_* functions here
# (actor_in_movie, director_of_movie, won_oscar_for_movie, won_oscar, etc.)
# ---------------------------

# For demonstration, re-import the verification functions from above section if needed
# (If this file is the whole script, include the verification definitions here directly.)

# ---------------------------
# Quick demo using the granular pipeline
# ---------------------------
if __name__ == "__main__":
    test_sentence = "Leonardo DiCaprio won an Oscar for Inception in 2016 directed by Nolan."
    print("Input sentence:", test_sentence)
    print("\nExtracting granular claims...")
    claims = get_claims(test_sentence, autofill_subject=True)
    claims = normalize_extracted_claims(claims)
    for i, c in enumerate(claims, 1):
        print(f"{i}. {c}")

    # If verify_single_claim is defined in your script, run verification now:
    try:
        results = []
        for c in claims:
            res = verify_single_claim(c)   # assume function exists in the full script
            results.append({"claim": c, "result": res})
            time.sleep(0.2)
        print("\nVerification results:")
        print(json.dumps(results, indent=2))
    except NameError:
        print("\nNote: verify_single_claim(...) was not included in this patch excerpt.")
        print("Paste the verification functions (verify_actor_in_movie, verify_director_of_movie, verify_won_oscar_for_movie, etc.) into the same file and run again.")
