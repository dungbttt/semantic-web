"""Parameterized SELECT templates for the SPARQL explorer."""


def build_explorer_query(template, parameter, integer_parameter=0):
    prefixes = """PREFIX cine: <https://example.org/cinegraph/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    """

    exact = f"VALUES ?lookup {{ {parameter} }}"

    query_bodies = {
        "movie_people": f"""SELECT DISTINCT ?role ?personName WHERE {{
      ?movie a cine:Movie ; cine:title ?lookup . {exact}
      {{ ?movie cine:hasActor ?person . BIND("Actor" AS ?role) }} UNION
      {{ ?movie cine:directedBy ?person . BIND("Director" AS ?role) }}
      ?person rdfs:label ?personName .
    }} ORDER BY ?role LCASE(STR(?personName)) LIMIT 100""",
        "coactors_by_actor": f"""SELECT ?personName (COUNT(DISTINCT ?sharedMovie) AS ?sharedFilms) (GROUP_CONCAT(DISTINCT STR(?sharedTitle); separator=", ") AS ?sharedTitles) WHERE {{
      ?focus a cine:Actor ; rdfs:label ?lookup . {exact}
      ?sharedMovie a cine:Movie ; cine:hasActor ?focus, ?collaborator ; cine:title ?sharedTitle .
      FILTER(?collaborator != ?focus)
      ?collaborator a cine:Actor ; rdfs:label ?personName .
    }} GROUP BY ?collaborator ?personName ORDER BY DESC(?sharedFilms) LCASE(STR(?personName)) LIMIT 100""",
        "actors_by_director": f"""SELECT ?actorName (COUNT(DISTINCT ?sharedMovie) AS ?sharedFilms) (GROUP_CONCAT(DISTINCT STR(?sharedTitle); separator=", ") AS ?movieTitles) WHERE {{
      ?focus a cine:Director ; rdfs:label ?lookup . {exact}
      ?sharedMovie a cine:Movie ; cine:directedBy ?focus ; cine:hasActor ?actor ; cine:title ?sharedTitle .
      ?actor a cine:Actor ; rdfs:label ?actorName .
    }} GROUP BY ?actor ?actorName ORDER BY DESC(?sharedFilms) LCASE(STR(?actorName)) LIMIT 100""",
        "actor_genre_profile": f"""SELECT ?genreName (COUNT(DISTINCT ?movie) AS ?filmCount) WHERE {{
      ?focus a cine:Actor ; rdfs:label ?lookup . {exact}
      ?movie a cine:Movie ; cine:hasActor ?focus ; cine:hasGenre ?genre .
      ?genre a cine:Genre ; rdfs:label ?genreName .
    }} GROUP BY ?genre ?genreName ORDER BY DESC(?filmCount) LCASE(STR(?genreName)) LIMIT 100""",
        "genres_by_min_movies": f"""SELECT ?genreName (COUNT(DISTINCT ?movie) AS ?movieCount) (AVG(?rating) AS ?averageRating) WHERE {{
      ?genre a cine:Genre ; rdfs:label ?genreName .
      ?movie a cine:Movie ; cine:hasGenre ?genre ; cine:imdbRating ?rating .
    }} GROUP BY ?genre ?genreName HAVING(COUNT(DISTINCT ?movie) >= {integer_parameter}) ORDER BY DESC(?averageRating) LCASE(STR(?genreName)) LIMIT 100""",
        "movies_by_min_cast": f"""SELECT ?title ?year (COUNT(DISTINCT ?actor) AS ?castSize) WHERE {{
      ?movie a cine:Movie ; cine:title ?title ; cine:hasActor ?actor .
      OPTIONAL {{ ?movie cine:releaseYear ?year }}
    }} GROUP BY ?movie ?title ?year HAVING(COUNT(DISTINCT ?actor) >= {integer_parameter}) ORDER BY DESC(?castSize) LCASE(STR(?title)) LIMIT 100""",
    }

    return prefixes + query_bodies[template]
