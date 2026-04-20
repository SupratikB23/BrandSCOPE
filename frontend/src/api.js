async function request(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request to ${path} failed`);
  }
  return res.json();
}

export function extractDNA(url) {
  return request('/api/extract-dna', { url });
}

export function researchTrends({ services, top_keywords, existing_titles }) {
  return request('/api/research-trends', { services, top_keywords, existing_titles: existing_titles || [] });
}

export function buildBrief({ dna, trend, angle, article_type }) {
  return request('/api/build-brief', { dna, trend, angle, article_type });
}

export function writeArticle({ brief, dna, trend, model, api_key }) {
  return request('/api/write-article', { brief, dna, trend, model, api_key: api_key || undefined });
}
