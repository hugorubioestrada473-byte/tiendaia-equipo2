import requests
import time

# Lista de Pokémon a consultar
nombres = [
    "pikachu", "bulbasaur", "charmander", "squirtle", "eevee",
    "snorlax", "gengar", "onix", "psyduck", "jigglypuff"
]

# ----------------------------------------------------
# 1. VERSIÓN REST
# ----------------------------------------------------
total_bytes_rest = 0
t_inicio_rest = time.perf_counter()

for n in nombres:
    r = requests.get(f"https://pokeapi.co/api/v2/pokemon/{n}", timeout=10)
    total_bytes_rest += len(r.content)

ms_rest = (time.perf_counter() - t_inicio_rest) * 1000

print(f"REST: {len(nombres)} peticiones, {total_bytes_rest} bytes, {ms_rest:.0f} ms")


# ----------------------------------------------------
# 2. VERSIÓN GRAPHQL
# ----------------------------------------------------
url_graphql = "https://graphql.pokeapi.co/v1beta2"

# Consulta para solicitar solo nombre, altura y tipos de los 10 Pokémon
query_graphql = """
query getPokemons {
  pokemon_v2_pokemon(where: {name: {_in: ["pikachu", "bulbasaur", "charmander", "squirtle", "eevee", "snorlax", "gengar", "onix", "psyduck", "jigglypuff"]}}) {
    name
    height
    pokemon_v2_pokemontypes {
      pokemon_v2_type {
        name
      }
    }
  }
}
"""

t_inicio_gql = time.perf_counter()

response_gql = requests.post(
    url_graphql,
    json={"query": query_graphql},
    headers={"Content-Type": "application/json"},
    timeout=10
)

ms_gql = (time.perf_counter() - t_inicio_gql) * 1000
total_bytes_gql = len(response_gql.content)

print(f"GraphQL: 1 peticion, {total_bytes_gql} bytes, {ms_gql:.0f} ms")