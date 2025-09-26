import requests

# 🔑 Replace with your actual API key string from TMDb (not the read access token)

# 1) Search for a movie by name
movie_name = "Kpop Demon Hunters"
search_url = f"http://www.omdbapi.com/?t={movie_name}&apikey=a6f7938d"
# "http://www.omdbapi.com/?&y=2010"
search_response = requests.get(search_url).json()
print("Search Results:", search_response)

# Take the first search result's ID
# if search_response.get("results"):
#     movie_id = search_response["results"][0]["id"]
#     print(f"\nMovie ID for {movie_name}: {movie_id}")

#     2) Fetch the cast & crew for that movie
#     credits_url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits?api_key=a6f7938d"
#     credits_response = requests.get(credits_url).json()

#     print("\nTop 5 Cast Members:")
#     for cast_member in credits_response.get("cast", [])[:5]:
#         print(f"- {cast_member['name']} as {cast_member['character']}")
# else:
#     print("Movie not found!")
