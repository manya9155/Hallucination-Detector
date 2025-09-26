import requests

# 🔑 Replace with your actual API key string from TMDb (not the read access token)
API_KEY = "a182f25684775f9da7c4523450eda104"

# 1) Search for a movie by name
movie_name = "Inception"
search_url = f"https://api.themoviedb.org/3/search/movie?api_key={API_KEY}&query={movie_name}"

search_response = requests.get(search_url).json()
print("Search Results:", search_response)

# Take the first search result's ID
if search_response.get("results"):
    movie_id = search_response["results"][0]["id"]
    print(f"\nMovie ID for {movie_name}: {movie_id}")

    # 2) Fetch the cast & crew for that movie
    credits_url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits?api_key={API_KEY}"
    credits_response = requests.get(credits_url).json()

    print("\nTop 5 Cast Members:")
    for cast_member in credits_response.get("cast", [])[:5]:
        print(f"- {cast_member['name']} as {cast_member['character']}")
else:
    print("Movie not found!")
