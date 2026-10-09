"""RDF namespaces, source labels, and recommendation weights."""

from ..vocabulary import CINE as CINE
from ..vocabulary import PROV as PROV
from ..vocabulary import SCHEMA as SCHEMA
from ..vocabulary import SOURCE_URLS

SOURCE_NAMES = {
    SOURCE_URLS["IMDb"]: "IMDb",
    SOURCE_URLS["Kaggle"]: "Kaggle · The Movies Dataset",
    SOURCE_URLS["OMDb"]: "OMDb API",
}
WEIGHTS = {CINE.hasGenre: 1, CINE.hasActor: 2, CINE.directedBy: 3}
REASONS = {
    CINE.hasGenre: "Same genre",
    CINE.hasActor: "Shared cast",
    CINE.directedBy: "Same director",
}
