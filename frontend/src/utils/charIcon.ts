export function getCharIconUrl(c: any): string {
  if (!c) return '';
  if (typeof c === 'number' || typeof c === 'string') {
    return `/api/char-icon/${c}.png`;
  }
  if (c.icon_url) return c.icon_url;
  if (c.is_template_available || c.template_filename) {
    const id = c.id;
    if (!id) return '';
    return `/api/char-icon/${id}.png`;
  }
  return '';
}
