import requests

# ✅ Use the same Bearer Token that worked earlier
TMDB_BEARER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhMTgyZjI1Njg0Nzc1ZjlkYTdjNDUyMzQ1MGVkYTEwNCIsIm5iZiI6MTc1ODg2MjY4OC4wOCwic3ViIjoiNjhkNjFkNjA3ZDExMTU0YmM3ZDNjZDM0Iiwic2NvcGVzIjpbImFwaV9yZWFkIl0sInZlcnNpb24iOjF9.lsBLFLRbb8mgUNWf1lR16P8KLArfvcPZGI_frqnCGtU"

def tmdb_get(url, params=None):
    """Helper function to send authorized requests with proper headers."""
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_BEARER_TOKEN}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    return requests.get(url, headers=headers, params=params, timeout=10).json()

# 1) Search for a movie by name
movie_name = "Inception"
search_url = "https://api.themoviedb.org/3/search/movie"
search_response = tmdb_get(search_url, params={"query": movie_name})

print("Search Results:", search_response)

# 2) Take the first result ID and fetch credits
if search_response.get("results"):
    movie_id = search_response["results"][0]["id"]
    print(f"\nMovie ID for {movie_name}: {movie_id}")

    credits_url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits"
    credits_response = tmdb_get(credits_url)

    print("\nTop 5 Cast Members:")
    for cast_member in credits_response.get("cast", [])[:5]:
        print(f"- {cast_member['name']} as {cast_member['character']}")
else:
    print("Movie not found!")
