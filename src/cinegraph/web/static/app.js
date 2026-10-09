const esc = (value = '') => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = (value = '') => /^https?:\/\//i.test(value) ? value : '';

function movieCard(movie) {
  const image = safeUrl(movie.image);
  const poster = image
    ? `<img class="poster" src="${esc(image)}" alt="Poster ${esc(movie.title)}" loading="lazy" onerror="this.outerHTML='<div class=poster-fallback>CG</div>'">`
    : '<div class="poster-fallback">CG</div>';
  const facts = [movie.year, movie.runtime_minutes ? `${Math.round(Number(movie.runtime_minutes))} min` : ''].filter(Boolean).join(' · ');
  const revenue = Number(movie.revenue) > 0 ? `Revenue $${(Number(movie.revenue) / 1_000_000).toFixed(0)}M` : '';
  const chips = (movie.genres || []).slice(0, 3).map(name => `<span class="chip">${esc(name)}</span>`).join('');
  const links = [
    movie.imdb_id ? `<a href="https://www.imdb.com/title/${encodeURIComponent(movie.imdb_id)}/" target="_blank" rel="noreferrer">IMDb ↗</a>` : '',
    safeUrl(movie.wikidata_url) ? `<a href="${esc(movie.wikidata_url)}" target="_blank" rel="noreferrer">Wikidata ↗</a>` : '',
    safeUrl(movie.dbpedia_url) ? `<a href="${esc(movie.dbpedia_url)}" target="_blank" rel="noreferrer">DBpedia ↗</a>` : '',
    ...(movie.entity_links || []).slice(0, 4).map(item => safeUrl(item.url)
      ? `<a href="${esc(item.url)}" target="_blank" rel="noreferrer" title="${esc(item.type)}">${esc(item.name)} ↗</a>`
      : '')
  ].filter(Boolean).join('');
  const description = movie.description ? `<p class="movie-description">${esc(movie.description)}</p>` : '';
  const identifier = String(movie.id || '');
  return `<article class="movie-card">${poster}<div class="movie-body"><h3>${esc(movie.title)}</h3><div class="movie-meta">${esc(facts)}${movie.rating ? ` <span class="rating">★ ${esc(movie.rating)} ${esc(movie.rating_source || '')}</span>` : ''}${movie.directors?.length ? ` · ${esc(movie.directors.join(', '))}` : ''}</div>${revenue ? `<div class="movie-meta">${esc(revenue)}</div>` : ''}<div class="chips">${chips}</div>${description}<div class="movie-actions"><div class="recommend-actions"><select data-recommend-type data-recommend="${esc(identifier)}" aria-label="Choose a related movie filter"><option value="" selected disabled>Choose a relation</option><option value="all">All</option><option value="genre">Same genre</option><option value="actor">Same cast</option><option value="director">Same director</option></select></div><span class="movie-links">${links}</span></div></div></article>`;
}

function personCard(person) {
  const image = safeUrl(person.image);
  const portrait = image
    ? `<img class="person-portrait" src="${esc(image)}" alt="Photo of ${esc(person.name)}" loading="lazy" onerror="this.outerHTML='<div class=person-portrait-fallback>CG</div>'">`
    : '<div class="person-portrait-fallback">CG</div>';
  const roles = (person.roles || []).map(role => role === 'actor' ? 'Actor' : 'Director');
  const lifespan = [person.birth_date ? `Born ${person.birth_date}` : '', person.death_date ? `Died ${person.death_date}` : ''].filter(Boolean).join(' · ');
  const movies = (person.movies || []).map(movie =>
    `<button class="person-movie-link" type="button" data-person-movie="${esc(movie.title)}">${esc(movie.title)}${movie.year ? ` (${esc(movie.year)})` : ''}</button>`
  ).join('');
  const links = [
    safeUrl(person.wikipedia_url) ? `<a href="${esc(person.wikipedia_url)}" target="_blank" rel="noreferrer">Wikipedia ↗</a>` : '',
    safeUrl(person.wikidata_url) ? `<a href="${esc(person.wikidata_url)}" target="_blank" rel="noreferrer">Wikidata ↗</a>` : '',
    safeUrl(person.tmdb_url) ? `<a href="${esc(person.tmdb_url)}" target="_blank" rel="noreferrer">TMDB ↗</a>` : '',
  ].filter(Boolean).join('');
  return `<article class="person-card">${portrait}<div class="person-body"><div class="person-heading"><h3>${esc(person.name)}</h3><span>${Number(person.movie_count || 0).toLocaleString('en-US')} movie credits</span></div><div class="person-roles">${roles.map(role => `<span>${esc(role)}</span>`).join('')}</div>${lifespan ? `<p class="person-lifespan">${esc(lifespan)}</p>` : ''}${person.description ? `<p class="person-description">${esc(person.description)}</p>` : ''}${movies ? `<div class="person-filmography"><strong>Known for</strong><div>${movies}</div></div>` : ''}${links ? `<div class="person-links">${links}</div>` : ''}</div></article>`;
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function searchMovies() {
  activeMovieSearch?.abort();
  const controller = new AbortController();
  activeMovieSearch = controller;
  const form = document.querySelector('#movieFilterForm');
  const params = new URLSearchParams(new FormData(form));
  const container = document.querySelector('#movies');
  const info = document.querySelector('#resultsInfo');
  params.set('limit', '200');
  document.querySelector('#recommendations').hidden = true;
  container.hidden = false;
  container.innerHTML = '<div class="empty">Searching movies…</div>';
  info.hidden = false;
  info.textContent = 'Applying filters…';
  try {
    const data = await getJson(`/api/movies?${params.toString()}`, {signal:controller.signal});
    container.innerHTML = data.movies.map(movieCard).join('') || '<div class="empty">No matching movies found in the graph.</div>';
    info.textContent = data.count > data.shown
      ? `Found ${data.count.toLocaleString('en-US')} movies; showing ${data.shown}. Add filters to narrow the results.`
      : `Found ${data.count.toLocaleString('en-US')} movies.`;
  } catch (error) {
    if (controller.signal.aborted) return;
    container.innerHTML = `<div class="empty">${esc(error.message)}</div>`;
    info.textContent = 'Could not apply the filters.';
  }
}

let personSearchTimer;
let activePersonSearch;
let peoplePage = 1;

async function searchPeople(page = 1) {
  activePersonSearch?.abort();
  const controller = new AbortController();
  activePersonSearch = controller;
  const form = document.querySelector('#peopleFilterForm');
  const params = new URLSearchParams(new FormData(form));
  params.set('page', String(page));
  const container = document.querySelector('#peopleResults');
  const info = document.querySelector('#peopleResultsInfo');
  const pagination = document.querySelector('#peoplePagination');
  container.hidden = false;
  container.innerHTML = '<div class="empty">Searching people…</div>';
  info.hidden = false;
  info.textContent = 'Applying filters with SPARQL…';
  pagination.hidden = true;
  try {
    const data = await getJson(`/api/people?${params.toString()}`, {signal:controller.signal});
    peoplePage = data.page;
    container.innerHTML = data.people.map(personCard).join('') || '<div class="empty">No matching people found.</div>';
    info.textContent = data.count > data.people.length
      ? `Found ${data.count.toLocaleString('en-US')} people; showing page ${data.page}/${data.pages}.`
      : `Found ${data.count.toLocaleString('en-US')} people.`;
    renderPeoplePagination(data.page, data.pages);
  } catch (error) {
    if (controller.signal.aborted) return;
    container.innerHTML = `<div class="empty">${esc(error.message)}</div>`;
    info.textContent = 'Could not search for people.';
  }
}

function renderPeoplePagination(page, pages) {
  const nav = document.querySelector('#peoplePagination');
  nav.replaceChildren();
  nav.hidden = pages <= 1;
  if (pages <= 1) return;
  const add = (text, target, active = false, disabled = false) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `recommendation-page${active ? ' active' : ''}`;
    button.textContent = text;
    button.dataset.peoplePage = target;
    button.disabled = active || disabled;
    if (active) button.setAttribute('aria-current', 'page');
    nav.append(button);
  };
  const pagesToShow = [...new Set([1, pages, page - 1, page, page + 1].filter(value => value >= 1 && value <= pages))].sort((a, b) => a - b);
  add('‹', page - 1, false, page <= 1);
  let previous = 0;
  for (const value of pagesToShow) {
    if (previous && value - previous > 1) {
      const dots = document.createElement('span');
      dots.className = 'recommendation-ellipsis';
      dots.textContent = '…';
      nav.append(dots);
    }
    add(String(value), value, value === page);
    previous = value;
  }
  add('›', page + 1, false, page >= pages);
}

async function loadFilterOptions() {
  const genreSelect = document.querySelector('#filterGenre');
  try {
    const options = await getJson('/api/filter-options');
    genreSelect.innerHTML = '<option value="">All genres</option>' +
      options.genres.map(genre => `<option value="${esc(genre)}">${esc(genre)}</option>`).join('');
  } catch (error) {
    console.warn('Could not load genre filter options.', error);
  }
}

function enableEntityDropdown(inputSelector, type, datalistId) {
  const input = document.querySelector(inputSelector);
  const datalist = document.getElementById(datalistId);
  let timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const query = input.value.trim();
    if (query.length < 2) {
      datalist.replaceChildren();
      return;
    }
    timer = setTimeout(async () => {
      try {
        const data = await getJson(`/api/suggestions?type=${type}&q=${encodeURIComponent(query)}`);
        if (input.value.trim() !== query) return;
        datalist.replaceChildren(...data.suggestions.map(value => {
          const option = document.createElement('option');
          option.value = value;
          return option;
        }));
      } catch (error) {
        datalist.replaceChildren();
      }
    }, 180);
  });
}

const graphQuestionTypes = {
  related_movies: { label:'Seed movie title', placeholder:'e.g. Inception', suggestion:'title' },
  movie_people: { label:'Movie title', placeholder:'e.g. Inception', suggestion:'title' },
  coactors_by_actor: { label:'Actor name', placeholder:'e.g. Leonardo DiCaprio', suggestion:'actor' },
  actors_by_director: { label:'Director name', placeholder:'e.g. Christopher Nolan', suggestion:'director' },
  actor_genre_profile: { label:'Actor name', placeholder:'e.g. Leonardo DiCaprio', suggestion:'actor' },
  genres_by_min_movies: { label:'Minimum movies in each genre', placeholder:'e.g. 20', numeric:true },
  movies_by_min_cast: { label:'Minimum cast size', placeholder:'e.g. 10', numeric:true }
};

const graphTemplateSelect = document.querySelector('#graphTemplate');
const graphValueInput = document.querySelector('#graphValue');
const graphSuggestions = document.querySelector('#graphSuggestions');
let graphSuggestionTimer;

function updateGraphQuestion() {
  const config = graphQuestionTypes[graphTemplateSelect.value] || graphQuestionTypes.related_movies;
  document.querySelector('#graphValueLabel').textContent = config.label;
  graphValueInput.placeholder = config.placeholder;
  graphValueInput.type = config.numeric ? 'number' : 'search';
  graphValueInput.step = config.decimal ? '0.1' : '1';
  graphValueInput.min = config.numeric ? '1' : '';
  graphValueInput.value = '';
  graphValueInput.removeAttribute('list');
  if (config.suggestion) graphValueInput.setAttribute('list', 'graphSuggestions');
  graphSuggestions.replaceChildren();
}

const queryColumnLabels = {
  title:'Movie title', year:'Year', rating:'IMDb rating', votes:'Votes',
  sharedCount:'Shared connections', role:'Role',
  personName:'Name', genreName:'Genre', roles:'Roles', filmCount:'Movie credits',
  runtime:'Runtime (min)', score:'Relevance score', reasons:'Shared connections',
  actorName:'Actor', sharedFilms:'Movies together', sharedTitles:'Movies together',
  movieTitles:'Collaborative movies', genreCount:'Genre count', genres:'Genres',
  movieCount:'Movie count', averageRating:'Average IMDb rating', castSize:'Cast size'
};

function renderQueryResults(data) {
  const container = document.querySelector('#graphQueryResults');
  container.replaceChildren();
  if (!data.rows?.length) {
    const empty = document.createElement('p');
    empty.className = 'query-empty';
    empty.textContent = 'No matching results found.';
    container.append(empty);
    return;
  }
  const table = document.createElement('table');
  table.className = 'query-results-table';
  const head = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const column of data.columns) {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = queryColumnLabels[column] || column;
    headerRow.append(cell);
  }
  head.append(headerRow);
  const body = document.createElement('tbody');
  for (const row of data.rows) {
    const rowElement = document.createElement('tr');
    for (const value of row) {
      const cell = document.createElement('td');
      cell.textContent = value;
      rowElement.append(cell);
    }
    body.append(rowElement);
  }
  table.append(head, body);
  container.append(table);
}

async function runGraphQuestion(event) {
  event.preventDefault();
  const template = graphTemplateSelect.value;
  const value = graphValueInput.value.trim();
  const runButton = document.querySelector('#graphRunButton');
  const info = document.querySelector('#graphResultInfo');
  if (!value) {
    graphValueInput.focus();
    return;
  }
  runButton.disabled = true;
  runButton.textContent = 'Running…';
  info.textContent = 'Running SPARQL on the RDF graph…';
  try {
    const data = await getJson('/api/sparql-explore', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({template, value})
    });
    renderQueryResults(data);
    document.querySelector('#exploreSparql').textContent = data.sparql;
    info.textContent = `SPARQL returned ${Number(data.count).toLocaleString('en-US')} rows (up to 100 per query).`;
  } catch (error) {
    renderQueryResults({columns:[], rows:[]});
    document.querySelector('#graphQueryResults .query-empty').textContent = error.message;
    info.textContent = 'Could not run the SPARQL query.';
  } finally {
    runButton.disabled = false;
    runButton.innerHTML = 'Run SPARQL <span>→</span>';
  }
}

const neighborhoodTypes = {
  movie: { suggestion:'title', placeholder:'e.g. Inception', glyph:'M' },
  actor: { suggestion:'actor', placeholder:'e.g. Leonardo DiCaprio', glyph:'A' },
  director: { suggestion:'director', placeholder:'e.g. Christopher Nolan', glyph:'D' },
  genre: { suggestion:'genre', placeholder:'e.g. Drama', glyph:'G' }
};
const neighborhoodForm = document.querySelector('#neighborhoodForm');
const neighborhoodType = document.querySelector('#neighborhoodType');
const neighborhoodValue = document.querySelector('#neighborhoodValue');
const neighborhoodSuggestions = document.querySelector('#neighborhoodSuggestions');
const neighborhoodSvg = document.querySelector('#neighborhoodSvg');
const neighborhoodTooltip = document.querySelector('#neighborhoodTooltip');
let neighborhoodSuggestionTimer;

function updateNeighborhoodFields(clearValue = true) {
  clearTimeout(neighborhoodSuggestionTimer);
  const config = neighborhoodTypes[neighborhoodType.value] || neighborhoodTypes.movie;
  neighborhoodValue.placeholder = config.placeholder;
  neighborhoodValue.value = clearValue ? '' : neighborhoodValue.value;
  neighborhoodSuggestions.replaceChildren();
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
}

function renderNeighborhood(data) {
  neighborhoodSvg.replaceChildren();
  neighborhoodTooltip.hidden = true;
  const defs = svgElement('defs');
  const marker = svgElement('marker', { id:'neighborhoodArrow', viewBox:'0 0 10 10', refX:'8', refY:'5', markerWidth:'6', markerHeight:'6', orient:'auto-start-reverse' });
  marker.append(svgElement('path', { d:'M 0 0 L 10 5 L 0 10 z', class:'neighborhood-arrow' }));
  defs.append(marker);
  neighborhoodSvg.append(defs);

  const center = { x:700, y:500 };
  const root = data.nodes.find(node => node.id === data.root);
  const firstHop = data.nodes.filter(node => node.depth === 1);
  const secondHop = data.nodes.filter(node => node.depth === 2);
  const positions = new Map([[data.root, center]]);
  const placeOnRing = (nodes, radius) => nodes.forEach((node, index) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * index / Math.max(nodes.length, 1));
    positions.set(node.id, { x:center.x + radius * Math.cos(angle), y:center.y + radius * Math.sin(angle) });
  });
  placeOnRing(firstHop, 220);
  placeOnRing(secondHop, 470);

  const nodeById = new Map(data.nodes.map(node => [node.id, node]));
  const edgeLayer = svgElement('g', { class:'neighborhood-edges' });
  for (const edge of data.edges) {
    const from = positions.get(edge.source);
    const to = positions.get(edge.target);
    if (!from || !to) continue;
    const sourceNode = nodeById.get(edge.source);
    const targetNode = nodeById.get(edge.target);
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const distance = Math.hypot(dx, dy) || 1;
    const sourceRadius = sourceNode.depth === 0 ? 36 : sourceNode.depth === 1 ? 28 : 24;
    const targetRadius = targetNode.depth === 0 ? 36 : targetNode.depth === 1 ? 28 : 24;
    const line = svgElement('line', {
      x1:from.x + dx / distance * sourceRadius, y1:from.y + dy / distance * sourceRadius,
      x2:to.x - dx / distance * targetRadius, y2:to.y - dy / distance * targetRadius,
      class:'neighborhood-edge', 'marker-end':'url(#neighborhoodArrow)'
    });
    const title = svgElement('title');
    title.textContent = `${sourceNode?.label || ''} ${edge.relation} ${targetNode?.label || ''}`;
    line.append(title);
    edgeLayer.append(line);
  }
  neighborhoodSvg.append(edgeLayer);

  const nodeLayer = svgElement('g', { class:'neighborhood-nodes' });
  for (const node of data.nodes) {
    const position = positions.get(node.id);
    if (!position) continue;
    const group = svgElement('g', {
      class:`neighborhood-node kind-${node.kind} depth-${node.depth}${node.id === data.root ? ' is-root' : ''}`,
      transform:`translate(${position.x} ${position.y})`,
      role:'button', tabindex:'0', 'aria-label':`${node.label}, ${node.kindLabel}, ${node.depth === 0 ? 'root entity' : `distance ${node.depth}`}`
    });
    group.append(svgElement('circle', { r:node.depth === 0 ? '36' : node.depth === 1 ? '28' : '24', class:'neighborhood-node-circle' }));
    const glyph = svgElement('text', { class:'neighborhood-node-glyph', 'text-anchor':'middle', dy:'0.36em' });
    glyph.textContent = neighborhoodTypes[node.kind]?.glyph || '•';
    group.append(glyph);
    if (node.id === data.root) {
      const rootLabel = svgElement('text', { class:'neighborhood-root-label', 'text-anchor':'middle', y:'49' });
      rootLabel.textContent = node.label.length > 30 ? `${node.label.slice(0, 27)}…` : node.label;
      group.append(rootLabel);
    }
    const focusNode = () => focusNeighborhoodNode(nodeById.get(node.id));
    const showTooltip = event => showNeighborhoodTooltip(node, data, nodeById, event, group);
    group.addEventListener('click', focusNode);
    group.addEventListener('pointerenter', showTooltip);
    group.addEventListener('pointermove', positionNeighborhoodTooltip);
    group.addEventListener('pointerleave', () => { neighborhoodTooltip.hidden = true; });
    group.addEventListener('focus', showTooltip);
    group.addEventListener('blur', () => { neighborhoodTooltip.hidden = true; });
    group.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        focusNode();
      }
    });
    nodeLayer.append(group);
  }
  neighborhoodSvg.append(nodeLayer);
}

function showNeighborhoodTooltip(node, data, nodeById, event, target) {
  neighborhoodTooltip.replaceChildren();
  const heading = document.createElement('div');
  heading.className = 'neighborhood-tooltip-heading';
  const name = document.createElement('strong');
  name.className = 'neighborhood-tooltip-name';
  name.textContent = node.label;
  const kind = document.createElement('span');
  kind.className = `neighborhood-tooltip-kind kind-${node.kind}`;
  kind.textContent = node.kindLabel;
  heading.append(name, kind);

  const depth = document.createElement('p');
  depth.className = 'neighborhood-tooltip-depth';
  depth.textContent = node.depth === 0 ? 'Root entity' : `${node.depth} steps from the root`;

  const connected = data.edges.filter(edge => edge.source === node.id || edge.target === node.id);
  const relationTitle = document.createElement('h4');
  relationTitle.className = 'neighborhood-tooltip-subtitle';
  relationTitle.textContent = `Connections in this graph · ${connected.length}`;
  const relationList = document.createElement('div');
  relationList.className = 'neighborhood-tooltip-relations';
  for (const edge of connected.slice(0, 4)) {
    const source = nodeById.get(edge.source);
    const destination = nodeById.get(edge.target);
    const item = document.createElement('div');
    item.className = 'neighborhood-tooltip-relation';
    const relation = document.createElement('span');
    relation.className = 'neighborhood-tooltip-relation-name';
    relation.textContent = edge.source === node.id
      ? edge.relation
      : ({ 'has actor':'actor in', 'directed by':'director of', 'has genre':'genre of' }[edge.relation] || edge.relation);
    const neighbor = document.createElement('span');
    neighbor.className = 'neighborhood-tooltip-neighbor';
    neighbor.textContent = edge.source === node.id ? destination?.label || '' : source?.label || '';
    item.append(relation, neighbor);
    relationList.append(item);
  }
  if (connected.length > 4) {
    const more = document.createElement('p');
    more.className = 'neighborhood-tooltip-more';
    more.textContent = `and ${connected.length - 4} more connections`;
    relationList.append(more);
  }
  neighborhoodTooltip.append(heading, depth, relationTitle, relationList);
  neighborhoodTooltip.hidden = false;
  positionNeighborhoodTooltip(event, target);
}

function positionNeighborhoodTooltip(event, target) {
  if (neighborhoodTooltip.hidden) return;
  const map = document.querySelector('.neighborhood-map-wrap');
  const mapBounds = map.getBoundingClientRect();
  const targetBounds = target?.getBoundingClientRect();
  const hasPointerPosition = event?.type === 'pointerenter' || event?.type === 'pointermove';
  const clientX = hasPointerPosition ? event.clientX : targetBounds.left + targetBounds.width / 2;
  const clientY = hasPointerPosition ? event.clientY : targetBounds.top + targetBounds.height / 2;
  const x = clientX - mapBounds.left;
  const y = clientY - mapBounds.top;
  const width = neighborhoodTooltip.offsetWidth;
  const height = neighborhoodTooltip.offsetHeight;
  let left = x + 18;
  if (left + width > mapBounds.width - 10) left = x - width - 18;
  let top = y + 18;
  if (top + height > mapBounds.height - 10) top = y - height - 18;
  neighborhoodTooltip.style.left = `${Math.max(10, Math.min(left, mapBounds.width - width - 10))}px`;
  neighborhoodTooltip.style.top = `${Math.max(10, Math.min(top, mapBounds.height - height - 10))}px`;
}

function focusNeighborhoodNode(node) {
  if (!node || !neighborhoodTypes[node.kind]) return;
  neighborhoodType.value = node.kind;
  updateNeighborhoodFields();
  neighborhoodValue.value = node.label;
  neighborhoodForm.requestSubmit();
}

async function runNeighborhood(event) {
  event.preventDefault();
  const value = neighborhoodValue.value.trim();
  const button = document.querySelector('#neighborhoodRunButton');
  const info = document.querySelector('#neighborhoodInfo');
  if (!value) {
    neighborhoodValue.focus();
    return;
  }
  button.disabled = true;
  button.textContent = 'Building graph…';
  info.textContent = 'Finding entities within two steps…';
  try {
    const params = new URLSearchParams({ type:neighborhoodType.value, value });
    const data = await getJson(`/api/neighborhood?${params}`);
    renderNeighborhood(data);
    const relationCount = data.edges.length;
    info.textContent = `Graph contains ${data.nodes.length.toLocaleString('en-US')} entities and ${relationCount.toLocaleString('en-US')} relationships, up to 2 steps from the root.${data.truncated ? ' Large branches were trimmed to keep the graph readable.' : ''}`;
  } catch (error) {
    info.textContent = error.message;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Show graph <span>→</span>';
  }
}

let recommendationState = null;

function renderRecommendationPagination(page, pages) {
  const nav = document.querySelector('#recommendationPagination');
  nav.replaceChildren();
  nav.hidden = pages <= 1;
  if (pages <= 1) return;

  const addPageButton = (text, target, {active = false, disabled = false, label = ''} = {}) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `recommendation-page${active ? ' active' : ''}`;
    button.textContent = text;
    button.dataset.recommendPage = target;
    button.disabled = disabled || active;
    if (active) button.setAttribute('aria-current', 'page');
    if (label) button.setAttribute('aria-label', label);
    nav.append(button);
  };
  const addEllipsis = () => {
    const span = document.createElement('span');
    span.className = 'recommendation-ellipsis';
    span.textContent = '…';
    span.setAttribute('aria-hidden', 'true');
    nav.append(span);
  };

  addPageButton('‹', page - 1, {disabled:page <= 1, label:'Previous page'});
  const visiblePages = new Set([1, pages]);
  for (let number = Math.max(1, page - 1); number <= Math.min(pages, page + 1); number++) {
    visiblePages.add(number);
  }
  let previous = 0;
  for (const number of [...visiblePages].sort((a, b) => a - b)) {
    if (previous && number - previous > 1) addEllipsis();
    addPageButton(String(number), number, {active:number === page});
    previous = number;
  }
  addPageButton('›', page + 1, {disabled:page >= pages, label:'Next page'});
}

async function loadRecommendationPage(page, state) {
  if (!state || recommendationState !== state) return;
  const container = document.querySelector('#recommendationMovies');
  const pagination = document.querySelector('#recommendationPagination');
  const requestId = ++state.requestId;
  container.innerHTML = '<div class="empty">Loading movies…</div>';
  pagination.hidden = true;
  pagination.replaceChildren();
  try {
    const params = new URLSearchParams({type:state.type, page:String(page)});
    const data = await getJson(`/api/recommend/${encodeURIComponent(state.identifier)}?${params}`);
    if (recommendationState !== state || state.requestId !== requestId) return;
    state.page = data.page;
    state.pages = data.pages;
    container.innerHTML = data.recommendations.map(item => movieCard(item.movie)).join('') || '<div class="empty">No related movies found.</div>';
    renderRecommendationPagination(data.page, data.pages);
  } catch (error) {
    if (recommendationState !== state || state.requestId !== requestId) return;
    container.innerHTML = `<div class="empty">${esc(error.message)}</div>`;
  }
}

async function showRecommendations(select) {
  const card = select.closest('.movie-card');
  const section = document.querySelector('#recommendations');
  const heading = document.querySelector('#recommendationHeading');
  const title = card.querySelector('h3')?.textContent || 'this movie';
  const type = select.value || 'all';
  const typeLabels = {all:`related to ${title}`, genre:`in the same genre as ${title}`, actor:`with the same cast as ${title}`, director:`by the same director as ${title}`};
  const state = {identifier:select.dataset.recommend, type, page:1, pages:0, requestId:0};
  recommendationState = state;
  heading.textContent = `Movies ${typeLabels[type] || typeLabels.all}:`;
  section.hidden = false;
  await loadRecommendationPage(1, state);
  if (recommendationState === state) section.scrollIntoView({behavior:'smooth', block:'start'});
}

async function loadStatus() {
  try {
    const data = await getJson('/api/status');
    const stats = data.statistics;
    for (const [id, key] of [['statMovies','movies'],['statActors','actors'],['statDirectors','directors'],['statGenres','genres']]) {
      const element = document.getElementById(id);
      if (element) element.textContent = Number(stats[key] || 0).toLocaleString('en-US');
    }
  } catch (error) {
    console.warn('Could not load knowledge graph statistics.', error);
  }
}

const movieFilterForm = document.querySelector('#movieFilterForm');
let movieSearchTimer;
let activeMovieSearch;

function scheduleMovieSearch() {
  clearTimeout(movieSearchTimer);
  activeMovieSearch?.abort();
  movieSearchTimer = setTimeout(searchMovies, 350);
}

movieFilterForm.addEventListener('input', event => {
  if (event.target.matches('input')) scheduleMovieSearch();
});
movieFilterForm.addEventListener('change', event => {
  if (event.target.matches('select')) {
    clearTimeout(movieSearchTimer);
    searchMovies();
  }
});
movieFilterForm.addEventListener('submit', event => {
  event.preventDefault();
  clearTimeout(movieSearchTimer);
  searchMovies();
});
movieFilterForm.addEventListener('reset', () => setTimeout(() => {
  clearTimeout(movieSearchTimer);
  ['movieSuggestions', 'directorSuggestions', 'actorSuggestions'].forEach(id => {
    document.getElementById(id).replaceChildren();
  });
  searchMovies();
}, 0));
const peopleFilterForm = document.querySelector('#peopleFilterForm');
peopleFilterForm.addEventListener('input', event => {
  if (event.target.matches('input')) {
    clearTimeout(personSearchTimer);
    personSearchTimer = setTimeout(() => searchPeople(1), 300);
  }
});
peopleFilterForm.addEventListener('change', event => {
  if (event.target.matches('select')) searchPeople(1);
});
peopleFilterForm.addEventListener('submit', event => {
  event.preventDefault();
  searchPeople(1);
});
peopleFilterForm.addEventListener('reset', () => setTimeout(() => searchPeople(1), 0));
enableEntityDropdown('#search', 'title', 'movieSuggestions');
enableEntityDropdown('[name="director"]', 'director', 'directorSuggestions');
enableEntityDropdown('[name="actor"]', 'actor', 'actorSuggestions');
graphTemplateSelect.addEventListener('change', updateGraphQuestion);
document.querySelector('#graphExploreForm').addEventListener('submit', runGraphQuestion);
graphValueInput.addEventListener('input', () => {
  clearTimeout(graphSuggestionTimer);
  const config = graphQuestionTypes[graphTemplateSelect.value];
  const query = graphValueInput.value.trim();
  if (!config.suggestion || query.length < 2) {
    graphSuggestions.replaceChildren();
    return;
  }
  graphSuggestionTimer = setTimeout(async () => {
    try {
      const data = await getJson(`/api/suggestions?type=${config.suggestion}&q=${encodeURIComponent(query)}`);
      if (graphValueInput.value.trim() !== query) return;
      graphSuggestions.replaceChildren(...data.suggestions.map(value => {
        const option = document.createElement('option');
        option.value = value;
        return option;
      }));
    } catch (error) {
      graphSuggestions.replaceChildren();
    }
  }, 180);
});
updateGraphQuestion();
neighborhoodType.addEventListener('change', () => updateNeighborhoodFields());
neighborhoodForm.addEventListener('submit', runNeighborhood);
neighborhoodValue.addEventListener('input', () => {
  clearTimeout(neighborhoodSuggestionTimer);
  const query = neighborhoodValue.value.trim();
  const entityType = neighborhoodType.value;
  const suggestionType = neighborhoodTypes[entityType]?.suggestion;
  if (!suggestionType || query.length < 2) {
    neighborhoodSuggestions.replaceChildren();
    return;
  }
  neighborhoodSuggestionTimer = setTimeout(async () => {
    try {
      const data = await getJson(`/api/suggestions?type=${suggestionType}&q=${encodeURIComponent(query)}`);
      if (neighborhoodValue.value.trim() !== query || neighborhoodType.value !== entityType) return;
      neighborhoodSuggestions.replaceChildren(...data.suggestions.map(value => {
        const option = document.createElement('option');
        option.value = value;
        return option;
      }));
    } catch (error) {
      neighborhoodSuggestions.replaceChildren();
    }
  }, 180);
});
updateNeighborhoodFields();
document.addEventListener('change', event => {
  const select = event.target.closest('select[data-recommend-type]');
  if (select?.value) showRecommendations(select);
});
document.addEventListener('click', event => {
  const button = event.target.closest('button[data-recommend-page]');
  if (button && recommendationState) loadRecommendationPage(Number(button.dataset.recommendPage), recommendationState);
  const peopleButton = event.target.closest('button[data-people-page]');
  if (peopleButton) searchPeople(Number(peopleButton.dataset.peoplePage));
  const movieLink = event.target.closest('button[data-person-movie]');
  if (movieLink) {
    document.querySelector('#search').value = movieLink.dataset.personMovie;
    searchMovies();
    document.querySelector('#movieSearchPane').scrollIntoView({behavior:'smooth', block:'start'});
  }
});
loadStatus();
loadFilterOptions();
